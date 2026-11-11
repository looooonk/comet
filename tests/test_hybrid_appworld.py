import os
import random
from pathlib import Path

import pytest

from comet.appworld import AppWorldAdapter
from comet.artifacts import write_json
from comet.clocks import monotonic
from comet.config import Experiment
from comet.engine import EngineSettings, create_engine, retention_target


@pytest.mark.gpu
@pytest.mark.appworld
def test_live_hybrid_recovery_preserves_tool_effects(tmp_path):
    config_path = os.environ.get("COMET_HYBRID_APPWORLD_CONFIG")
    if not config_path:
        pytest.skip("Set COMET_HYBRID_APPWORLD_CONFIG for the combined live check")
    import torch

    config = Experiment.load(config_path)
    settings = EngineSettings(
        model=config.engine.model, model_path=os.environ["COMET_MODEL_PATH"],
        model_revision=config.engine.model_revision, tokenizer_revision=config.engine.tokenizer_revision,
        backend=config.engine.backend, method="full", retention=1.0,
        max_context_tokens=config.engine.max_context_tokens, peak_vram_bytes=config.peak_vram_bytes,
        workspace_reserve_bytes=config.engine.workspace_reserve_bytes,
        prefill_chunk_tokens=config.engine.prefill_chunk_tokens, require_a100=False,
    )
    engine = create_engine(settings)
    environment = AppWorldAdapter(os.environ["COMET_APPWORLD_ROOT"])
    evidence = {"status": "running", "integration_only": True, "branches": []}
    deadline = monotonic() + 600
    try:
        engine.warmup(deadline)
        environment.reset("0d8a4ee_1", 17, tmp_path / "environment")
        from appworld.apps.phone import models as phone

        before = phone.GlobalTextMessage.size()
        code = """profile = apis.supervisor.show_profile()
password = next(row['password'] for row in apis.supervisor.show_account_passwords()
                if row['account_name'] == 'phone')
token = apis.phone.login(username=profile['phone_number'], password=password)['access_token']
marker = ['source']
print(apis.phone.send_text_message(phone_number=profile['phone_number'],
      message='COMET hybrid recovery fixture', access_token=token))"""
        observation = environment.execute(code)
        assert phone.GlobalTextMessage.size() == before + 1, observation
        tokens = engine.tokenizer.apply_chat_template(
            [{"role": "user", "content": "Preserve this tool execution record.\n" + code + observation}],
            tokenize=True, return_dict=False, add_generation_prompt=True, enable_thinking=False,
        )
        engine.start(17)
        engine.generate(tokens, 2, 0.0, 1.0, deadline)
        raw = engine.raw_token_ids
        environment.checkpoint(tmp_path / "environment-checkpoint")
        engine.checkpoint(tmp_path / "engine-checkpoint")
        for method in ("streamingllm", "rkv", "agentkv"):
            environment.restore(tmp_path / "environment-checkpoint")
            engine.set_policy(method, 0.25)
            engine.restore(tmp_path / "engine-checkpoint", branch=True)
            assert environment.world.shell.user_ns["marker"] == ["source"]
            assert engine.raw_token_ids == raw
            interactions = environment.world.num_interactions
            cuda_rng, python_rng = torch.cuda.get_rng_state().clone(), random.getstate()
            result = engine.recover(raw, deadline)
            assert result.admitted
            assert torch.equal(cuda_rng, torch.cuda.get_rng_state())
            assert python_rng == random.getstate()
            assert environment.world.num_interactions == interactions
            assert phone.GlobalTextMessage.size() == before + 1
            assert environment.world.shell.user_ns["marker"] == ["source"]
            assert engine.raw_token_ids == raw
            assert engine.cache.get_seq_length() == retention_target(len(raw), 0.25, method)
            assert not engine.recover(raw, deadline).admitted
            memory = engine.memory_stats()
            assert memory["peak_total_vram_bytes"] <= config.peak_vram_bytes
            evidence["branches"].append({"method": method, "recovery_seconds": result.seconds,
                                         "tool_effects_unchanged": True, "rng_unchanged": True,
                                         "independent_environment_restore": True, "memory": memory})
            environment.execute(f"marker.append({method!r})")
        evidence.update(status="passed", source_tokens=len(raw), engine=engine.provenance())
    finally:
        write_json(Path(os.environ["COMET_CHECK_OUTPUT"]) / "hybrid-appworld.json", evidence)
        environment.close()
        engine.close()

import os
from types import SimpleNamespace

import pytest

from comet.engine.contracts import MODEL_PROFILES
from comet.runner import Runner


def runner(model, thinking):
    result = Runner.__new__(Runner)
    result.config = SimpleNamespace(
        engine=SimpleNamespace(model=model), sampling=SimpleNamespace(enable_thinking=thinking),
        prompt="Complete the task using Python.",
    )
    return result


@pytest.mark.parametrize("model", ["Qwen/Qwen3-8B", "Qwen/Qwen3-14B"])
@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("finished", [False, True])
def test_legacy_observation_transcripts_remain_byte_identical(model, thinking, finished):
    tokenizer = SimpleNamespace(
        encode=lambda text, **kwargs: text,
        apply_chat_template=lambda *args, **kwargs: pytest.fail("Legacy serialization changed"),
    )
    actual = runner(model, thinking)._observation_tokens(
        SimpleNamespace(tokenizer=tokenizer), "{\"value\": 7}", finished=finished,
    )
    closing = "" if finished else "<|im_end|>"
    suffix = "" if thinking else "<think>\n\n</think>\n\n"
    assert actual == (closing + '\n<|im_start|>user\n<tool_response>\n{"value": 7}\n'
                      '</tool_response><|im_end|>\n<|im_start|>assistant\n' + suffix)


@pytest.mark.parametrize("finished", [False, True])
def test_instruct_observation_uses_tokenizer_generation_prompt(finished):
    calls = []

    def render(messages, **kwargs):
        calls.append((messages, kwargs))
        return "native formatted observation and assistant prompt"

    tokenizer = SimpleNamespace(apply_chat_template=render, encode=lambda text, **kwargs: text)
    actual = runner("Qwen/Qwen3-4B-Instruct-2507", False)._observation_tokens(
        SimpleNamespace(tokenizer=tokenizer), "observation", finished=finished,
    )
    assert calls == [([{"role": "user", "content": "<tool_response>\nobservation\n</tool_response>"}],
                      {"tokenize": False, "add_generation_prompt": True})]
    assert actual == ("" if finished else "<|im_end|>") + "\nnative formatted observation and assistant prompt"


@pytest.mark.gpu
@pytest.mark.skipif(os.environ.get("COMET_RUN_GPU_TESTS") != "1"
                    and os.environ.get("COMET_RUN_HYBRID_TESTS") != "1", reason="requires pinned tokenizer")
def test_live_runner_observation_matches_pinned_model_template():
    from transformers import AutoTokenizer

    model = os.environ.get("COMET_TEST_MODEL", "Qwen/Qwen3.5-9B"
                           if os.environ.get("COMET_RUN_HYBRID_TESTS") == "1" else "Qwen/Qwen3-8B")
    tokenizer = AutoTokenizer.from_pretrained(os.environ["COMET_MODEL_PATH"], local_files_only=True)
    observation = '{"value": 7, "message": "stored"}'
    for thinking in ([False, True] if MODEL_PROFILES[model]["supports_thinking"] else [False]):
        current = runner(model, thinking)
        engine = SimpleNamespace(tokenizer=tokenizer)
        initial = current._initial_tokens(engine, SimpleNamespace(initial_prompt=lambda: "A task"))
        assert initial == tokenizer.apply_chat_template(
            [{"role": "system", "content": current.config.prompt}, {"role": "user", "content": "A task"}],
            tokenize=True, return_dict=False, add_generation_prompt=True, enable_thinking=thinking,
        )
        turn = tokenizer.apply_chat_template(
            [{"role": "user", "content": f"<tool_response>\n{observation}\n</tool_response>"}],
            tokenize=False, add_generation_prompt=True, enable_thinking=thinking,
        )
        for finished in (False, True):
            actual = current._observation_tokens(engine, observation, finished=finished)
            expected = tokenizer.encode(("" if finished else "<|im_end|>") + "\n" + turn,
                                        add_special_tokens=False)
            assert actual == expected
        if not MODEL_PROFILES[model]["supports_thinking"]:
            assert turn.endswith("<|im_start|>assistant\n") and "<think>" not in turn
            assert "<think>" not in tokenizer.decode(initial)

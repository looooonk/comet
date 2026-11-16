"""Protected or unbudgeted system prompt, text reminder and symptom-triggered rebuild."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_pipeline import Clock, FakeEngine, FakeEnvironment

from comet.artifacts import read_json
from comet.config import Experiment
from comet.engine import EngineSettings, retention_target
from comet.engine.contracts import MODEL_PROFILES, MODEL_REVISION, selector_overrides
from comet.errors import UnsupportedPath
from comet.policies import decide
from comet.runner import Runner

ROOT = Path(__file__).parents[1]
END = 2


HYBRID = "Qwen/Qwen3.5-9B"


def experiment(conditions, *, diagnostic=False, changes=None, **triggers):
    data = Experiment.load(ROOT / "configs/examples/pilot-smoke.json").to_dict()
    revision = MODEL_PROFILES[HYBRID]["revision"]
    data["engine"].update(
        model=HYBRID,
        model_revision=revision,
        tokenizer_revision=revision,
        backend="transformers_hybrid",
    )
    data.update(
        experiment_id="controls-fixture",
        task_ids=["fixture_1"],
        seeds=[7],
        budget_seconds=1000,
        max_attempts=1,
        conditions=conditions,
        prompt="RULES",
    )
    if diagnostic:
        data["retention_diagnostic"] = True
    data.pop("environment_warmup", None)
    data["triggers"] = {**data["triggers"], "fixed_tool_calls": 2, **triggers}
    for name, value in (changes or {}).items():
        data[name] = {**data[name], **value} if isinstance(value, dict) else value
    return Experiment.from_dict(data)


def arm(identifier="arm", method="agentkv", retention=0.5, recovery="never", **flags):
    return {
        "id": identifier,
        "method": method,
        "retention": retention,
        "recovery": recovery,
        "max_attempts": 1,
        **flags,
    }


class Engine(FakeEngine):
    supports_protected_prefix = True

    def __init__(self, clock):
        super().__init__(clock)
        self.policies, self.encoded, self.measured = [], [], []
        self.tokenizer = SimpleNamespace(
            apply_chat_template=lambda *a, **kw: [1, 5, 5, END, 1, 6, END],
            convert_tokens_to_ids=lambda token: END if token == "<|im_end|>" else 0,
            encode=self._encode,
            decode=lambda *a, **kw: "```python\nvalue = 1\n```",
        )

    def _encode(self, text, **kwargs):
        self.encoded.append(text)
        return [20] * len(text.split())

    def set_policy(self, method, retention, **kwargs):
        self.policies.append((method, retention, kwargs))

    def retained_fraction(self, start, stop):
        self.measured.append((start, stop))
        return 0.5


class Environment(FakeEnvironment):
    observations = ["ok", "ok", "ok", "ok"]

    def execute(self, action, **kwargs):
        self.count += 1
        self.clock.advance(1)
        return self.observations[self.count - 1]

    def completed(self):
        return self.count == len(self.observations)


def run(
    config,
    output,
    observations=("ok", "ok", "ok", "ok"),
    engine_type=Engine,
    environment_type=Environment,
):
    clock, engines = Clock(), []

    def factory(condition):
        engines.append(engine_type(clock))
        return engines[-1]

    def environment():
        instance = environment_type(clock, [])
        instance.observations = list(observations)
        return instance

    manifest = Runner(config, output, factory, environment, clock=clock).run()
    cells = [read_json(output / item["path"]) for item in manifest["cells"]]
    return cells, engines[0]


def test_existing_configurations_keep_their_digests():
    core = Experiment.load(ROOT / "configs/qwen9b/a6000/dev19-core-v1.json")
    assert core.digest == "3a5db0cca34104a385ff57eb307f834fe4eea68edc28b3a8e7e2645781a32ec0"
    retry = Experiment.load(ROOT / "configs/qwen9b/a6000/dev19-retry-v1.json")
    assert retry.digest == "7be6ceb0c04683153c5780e96a56c38ef15e833f9fe53472a1457adee07d90f8"
    controls = Experiment.load(ROOT / "configs/qwen9b/a6000/dev38-controls-v1.json")
    assert controls.digest == "468dd986ae9599098f5221545215f030c8835a1d632c62532695038262034ea1"
    condition = core.to_dict()["conditions"][0]
    assert set(condition) == {"id", "method", "retention", "recovery", "max_attempts"}
    assert "symptom_markers" not in core.to_dict()["triggers"]
    assert "retention_diagnostic" not in core.to_dict()


def test_control_fields_round_trip_and_change_the_digest():
    plain = experiment([arm()])
    controls = experiment(
        [arm(protect_prompt=True, reminder=True, recovery="symptom")],
        symptom_markers=["Invalid credentials"],
        diagnostic=True,
    )
    data = controls.to_dict()
    assert data["retention_diagnostic"] is True
    assert data["conditions"][0]["protect_prompt"] is True
    assert data["conditions"][0]["reminder"] is True
    assert data["triggers"]["symptom_markers"] == ["Invalid credentials"]
    assert Experiment.from_dict(data).digest == controls.digest != plain.digest


@pytest.mark.parametrize(
    "conditions,triggers",
    [
        ([arm(recovery="symptom")], {}),
        ([arm(recovery="symptom")], {"symptom_markers": [""]}),
        ([arm()], {"symptom_markers": ["a", "a"]}),
        ([arm()], {"symptom_markers": "abc"}),
        ([arm(protect_prompt="yes")], {}),
        ([arm(reminder=1)], {}),
        ([arm(method="full", retention=1.0, protect_prompt=True)], {}),
        ([arm(prompt_outside_budget="yes")], {}),
        ([arm(method="full", retention=1.0, prompt_outside_budget=True)], {}),
        ([arm(recovery="sometimes")], {}),
    ],
)
def test_invalid_control_settings_are_rejected(conditions, triggers):
    with pytest.raises(ValueError):
        experiment(conditions, **triggers)


NATIVE = {
    "model": "Qwen/Qwen3-8B",
    "model_revision": MODEL_REVISION,
    "tokenizer_revision": MODEL_REVISION,
    "backend": "native_minisgl",
}
BRANCH = {"stage": "diagnostic", "checkpoint_after_tool_calls": 1}


@pytest.mark.parametrize(
    "conditions,options",
    [
        ([arm(protect_prompt=True)], {"changes": {"engine": NATIVE}}),
        ([arm(prompt_outside_budget=True)], {"changes": {"engine": NATIVE}}),
        ([arm()], {"changes": {"engine": NATIVE}, "diagnostic": True}),
        ([arm()], {"changes": {"retention_diagnostic": "yes"}}),
        ([arm(reminder=True)], {"changes": BRANCH}),
        ([arm(protect_prompt=True)], {"changes": BRANCH}),
        ([arm(prompt_outside_budget=True)], {"changes": BRANCH}),
        ([arm()], {"changes": BRANCH, "symptom_markers": ["boom"]}),
    ],
)
def test_controls_are_rejected_where_they_are_undefined(conditions, options):
    with pytest.raises(ValueError):
        experiment(conditions, **options)
    experiment([arm()], changes=BRANCH)
    experiment([arm()], changes={"engine": NATIVE})


def test_symptom_policy_rebuilds_once_after_an_observed_symptom():
    triggers = experiment([arm()], symptom_markers=["boom"]).triggers
    quiet = decide("symptom", triggers, 10, 3, 0, 0)
    assert not quiet.triggered and quiet.reason == "no_symptom"
    fired = decide("symptom", triggers, 10, 0, 0, 1)
    assert fired.triggered and fired.reason == "symptom_observed"
    assert fired.to_dict()["symptoms"] == 1
    again = decide("symptom", triggers, 10, 0, 1, 4)
    assert not again.triggered and again.reason == "already_rebuilt"
    with pytest.raises(ValueError):
        decide("symptom", triggers, 10, 0, 0, -1)
    assert set(decide("fixed", triggers, 10, 2, 0).to_dict()) == {
        "policy",
        "context_tokens",
        "tool_calls",
        "rebuilds",
        "triggered",
        "reason",
    }
    assert not decide("fixed", triggers, 10, 0, 0, 5).triggered


def test_protected_prefix_counts_inside_the_retention_target():
    assert retention_target(3000, 0.5, "agentkv", 673) == retention_target(3000, 0.5, "agentkv")
    assert retention_target(1000, 0.5, "agentkv", 673) == 673 + 24
    assert retention_target(1000, 0.5, "streamingllm", 673) == 673 + 16
    assert retention_target(1000, 0.5, "rkv", 673) == 673 + 8
    assert retention_target(600, 0.5, "agentkv", 673) == 600
    assert retention_target(101, 0.5, "rkv", 0) == 51
    for protected in (-1, 1.5, True):
        with pytest.raises(ValueError):
            retention_target(100, 0.5, "rkv", protected)
    with pytest.raises(ValueError):
        retention_target(100, 1, "full", 4)


def test_selector_overrides_replace_the_sink_only_when_protected():
    assert selector_overrides("agentkv", 1500, 16) == {"budget": 1500}
    assert selector_overrides("rkv", 1500, 0) == {"budget": 1500}
    assert selector_overrides("streamingllm", 1500, 16) == {
        "sink_tokens": 16,
        "window_tokens": 1484,
    }
    assert selector_overrides("streamingllm", 10, 16) == {"sink_tokens": 10, "window_tokens": 0}
    assert selector_overrides("agentkv", 1500, 16, 673) == {"budget": 1500, "sink_tokens": 673}
    assert selector_overrides("rkv", 1500, 0, 673) == {"budget": 1500, "sink_tokens": 673}
    assert selector_overrides("agentkv", 1500, 16, 8) == {"budget": 1500, "sink_tokens": 16}
    assert selector_overrides("streamingllm", 1500, 16, 673) == {
        "sink_tokens": 673,
        "window_tokens": 827,
    }


def settings(**changes):
    base = EngineSettings(
        model_path="/unused/snapshot",
        model_revision=MODEL_REVISION,
        tokenizer_revision=MODEL_REVISION,
        method="rkv",
        retention=0.5,
        max_context_tokens=1024,
        peak_vram_bytes=40 << 30,
        workspace_reserve_bytes=4 << 30,
        prefill_chunk_tokens=128,
    )
    return replace(base, **changes)


def test_protected_prefix_is_part_of_the_policy_fingerprint_only_when_set():
    plain = settings()
    assert plain.fingerprint() == "02389d4e237065aa237b51634e775eb0479442b7511be6d7e46a07ec26e679e9"
    assert plain.fingerprint(policy=False) == (
        "ad1f5f6ae41de23554ea215c3b1b0e2e7b9987a44c52ba3329000c06033c3cd1"
    )
    protected = settings(protected_prefix_tokens=673)
    assert protected.fingerprint() != plain.fingerprint()
    assert protected.fingerprint(policy=False) == plain.fingerprint(policy=False)
    with pytest.raises(ValueError):
        settings(protected_prefix_tokens=-1)
    with pytest.raises(ValueError):
        settings(method="full", retention=1.0, protected_prefix_tokens=4)


def compacting_engine(method, protected, heads=2, width=8, unbudgeted=0):
    torch = pytest.importorskip("torch")
    pytest.importorskip("comet_agentkv")
    from comet.engine.hybrid import HybridEngine

    torch.manual_seed(0)
    engine = HybridEngine.__new__(HybridEngine)
    engine.torch, engine.synchronize = torch, lambda: None
    engine.settings = settings(
        method=method, protected_prefix_tokens=protected, unbudgeted_prefix_tokens=unbudgeted
    )
    engine.attention_layers = [0, 1]
    engine.text_config = SimpleNamespace(num_key_value_heads=heads, head_dim=width)
    layers = [
        SimpleNamespace(
            keys=torch.empty(1, heads, 0, width), values=torch.empty(1, heads, 0, width)
        )
        for _ in engine.attention_layers
    ]
    engine.cache = SimpleNamespace(layers=layers, get_seq_length=lambda: layers[0].keys.shape[2])
    engine._raw, engine._events, engine._positions = [], [], {}
    engine._observations = {
        index: {
            stage: (torch.randn(8, 2 * heads, width), torch.arange(8) + 8 * stage)
            for stage in range(4)
        }
        for index in engine.attention_layers
    }

    def append(count):
        added = torch.arange(len(engine._raw), len(engine._raw) + count)[None].expand(heads, -1)
        for index, layer in zip(engine.attention_layers, layers, strict=True):
            layer.keys = torch.cat([layer.keys, torch.randn(1, heads, count, width)], dim=2)
            layer.values = torch.cat([layer.values, torch.randn(1, heads, count, width)], dim=2)
            previous = engine._positions.get(index)
            engine._positions[index] = (
                added.clone() if previous is None else torch.cat([previous, added], dim=1)
            )
        engine._raw.extend([0] * count)
        engine._compact()

    return engine, append


@pytest.mark.parametrize("method", ["agentkv", "rkv", "streamingllm"])
def test_pinned_selectors_keep_a_protected_prefix_inside_the_same_target(method):
    prefix = 40
    protected, grow = compacting_engine(method, prefix)
    plain, grow_plain = compacting_engine(method, 0)
    for chunk in [16] * 20 + [1] * 30:
        grow(chunk)
        grow_plain(chunk)
        logical = len(protected._raw)
        target = retention_target(logical, 0.5, method, prefix)
        assert protected.cache.get_seq_length() == target
        assert protected.retained_fraction(0, prefix) == 1.0
        kept = min(prefix, logical)
        for positions in protected._positions.values():
            assert (positions[:, :kept] == protected.torch.arange(kept)).all()
            assert (positions[:, 1:] > positions[:, :-1]).all()
    assert protected.cache.get_seq_length() == plain.cache.get_seq_length() == 175
    assert plain.retained_fraction(0, prefix) < 1.0
    assert protected.retained_fraction(0, 0) is None
    assert protected.retained_fraction(342, 350) == 1.0  # every method keeps the newest 8

    # A rebuild prefills the whole transcript without compaction and then compacts once.
    rebuilt, grow_rebuilt = compacting_engine(method, prefix)
    grow_rebuilt(350)
    assert rebuilt.cache.get_seq_length() == 175
    assert rebuilt.retained_fraction(0, prefix) == 1.0


def test_runner_protects_the_system_prompt_through_its_end_marker(tmp_path):
    config = experiment([arm("plain"), arm("protected", protect_prompt=True)])
    cells, engine = run(config, tmp_path)
    assert engine.policies == [
        ("agentkv", 0.5, {}),
        ("agentkv", 0.5, {"protected_prefix_tokens": 4}),
    ]
    assert cells[1]["condition"]["protect_prompt"] is True
    assert "protect_prompt" not in cells[0]["condition"]
    assert cells[1]["attempts"][0]["protected_prefix_tokens"] == 4
    assert "protected_prefix_tokens" not in cells[0]["attempts"][0]
    assert all(a["status"] == "completed" for c in cells for a in c["attempts"])


def test_runner_refuses_protection_the_engine_cannot_apply(tmp_path):
    class Unsupported(Engine):
        supports_protected_prefix = False

    config = experiment([arm("protected", protect_prompt=True)])
    with pytest.raises(UnsupportedPath, match="protect"):
        run(config, tmp_path, engine_type=Unsupported)


def test_retention_diagnostic_is_recorded_only_when_the_experiment_asks(tmp_path):
    cells, engine = run(experiment([arm()], diagnostic=True), tmp_path / "on")
    attempt = cells[0]["attempts"][0]
    turns = read_json(tmp_path / "on" / attempt["artifact_dir"] / "trajectory.json")["turns"]
    assert [turn["system_prompt_retained"] for turn in turns] == [0.5] * 4
    assert set(engine.measured) == {(0, 4)}
    assert "retention_diagnostic" in attempt["timings"]

    cells, engine = run(experiment([arm()]), tmp_path / "off")
    attempt = cells[0]["attempts"][0]
    trajectory = read_json(tmp_path / "off" / attempt["artifact_dir"] / "trajectory.json")
    assert not engine.measured and "retention_diagnostic" not in attempt["timings"]
    assert all(set(turn) == {"response", "action", "observation"} for turn in trajectory["turns"])
    assert "symptoms" not in trajectory and "reminders" not in attempt


def test_reminder_repeats_the_system_prompt_once_at_the_fixed_trigger(tmp_path):
    cells, engine = run(experiment([arm(reminder=True)], diagnostic=True), tmp_path)
    attempt = cells[0]["attempts"][0]
    reminded = [text for text in engine.encoded if "<system_reminder>" in text]
    assert sum("<|im_start|>assistant" in text for text in reminded) == 1
    turn_text = next(text for text in reminded if "<|im_start|>assistant" in text)
    assert (
        "<tool_response>\nok\n</tool_response>\n\n<system_reminder>\nRULES\n</system_reminder><|im_end|>"
        in turn_text
    )
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert [bool(turn.get("reminder")) for turn in trajectory["turns"]] == [
        False,
        True,
        False,
        False,
    ]
    # The fake tokenizer emits one token per word: 16 transcript tokens precede this turn,
    # its tool response is 4 words and the reminder block 3.
    assert trajectory["reminder_span"] == [20, 23]
    assert trajectory["turns"][1]["reminder_tokens"] == 3
    assert (20, 23) in engine.measured
    assert attempt["reminders"] == 1 and attempt["rebuilds"] == 0
    assert "reminder_retained" in trajectory["turns"][2]
    assert "reminder_retained" not in trajectory["turns"][1]


def test_no_reminder_without_the_flag(tmp_path):
    cells, engine = run(experiment([arm()]), tmp_path)
    assert not any("<system_reminder>" in text for text in engine.encoded)
    assert "reminders" not in cells[0]["attempts"][0]


def test_symptom_in_an_observation_triggers_one_rebuild_before_the_next_turn(tmp_path):
    config = experiment([arm(recovery="symptom")], symptom_markers=["Invalid credentials"])
    observations = ("ok", "Error: Invalid credentials", "Invalid credentials again", "ok")
    cells, engine = run(config, tmp_path, observations)
    attempt = cells[0]["attempts"][0]
    assert attempt["rebuilds"] == 1 and len(engine.recoveries) == 1
    events = attempt["recovery_events"]
    assert [event["triggered"] for event in events] == [False, False, True, False]
    assert events[2]["reason"] == "symptom_observed" and events[2]["symptoms"] == 1
    assert events[3]["reason"] == "already_rebuilt"
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert trajectory["symptoms"] == 2
    assert [bool(turn.get("symptom")) for turn in trajectory["turns"]] == [False, True, True, False]


def test_invalid_action_is_a_symptom_and_feedback_text_is_not(tmp_path):
    class Prose(Engine):
        def __init__(self, clock):
            super().__init__(clock)
            self.tokenizer.decode = lambda *a, **kw: "I will think about it."

    config = experiment(
        [arm(recovery="symptom")],
        symptom_markers=["Invalid action"],
        changes={"agent": {"max_consecutive_errors": 3}},
    )
    cells, engine = run(config, tmp_path / "format", engine_type=Prose)
    attempt = cells[0]["attempts"][0]
    assert attempt["rebuilds"] == 1 and attempt["tool_calls"] == 0
    assert attempt["recovery_events"][1]["reason"] == "symptom_observed"

    config = experiment(
        [arm(recovery="symptom")],
        symptom_markers=["Consecutive execution/action failures"],
        changes={"agent": {"max_consecutive_errors": 9}},
    )
    failing = ("Execution failed: boom", "Execution failed: boom", "ok", "ok")
    cells, engine = run(config, tmp_path / "feedback", failing)
    attempt = cells[0]["attempts"][0]
    trajectory = read_json(tmp_path / "feedback" / attempt["artifact_dir"] / "trajectory.json")
    assert "Consecutive execution/action failures" in trajectory["turns"][0]["agent_feedback"]
    assert attempt["rebuilds"] == 0 and "symptoms" not in trajectory


def test_symptom_policy_never_rebuilds_a_clean_attempt(tmp_path):
    config = experiment([arm(recovery="symptom")], symptom_markers=["Invalid credentials"])
    cells, engine = run(config, tmp_path)
    assert cells[0]["attempts"][0]["rebuilds"] == 0 and not engine.recoveries


def test_declared_markers_are_the_recorded_instruction_error_markers():
    from comet.instruction_errors import OBSERVATION_MARKERS

    config = Experiment.load(ROOT / "configs/qwen9b/a6000/dev19-controls-v1.json")
    recorded = sorted(marker for group in OBSERVATION_MARKERS.values() for marker in group)
    assert sorted(config.triggers.symptom_markers) == recorded


def test_prompt_outside_budget_round_trips_and_changes_the_digest():
    plain = experiment([arm()])
    inside = experiment([arm(protect_prompt=True)])
    outside = experiment([arm(protect_prompt=True, prompt_outside_budget=True)])
    matched = experiment([arm(prompt_outside_budget=True)])
    assert len({plain.digest, inside.digest, outside.digest, matched.digest}) == 4
    assert outside.to_dict()["conditions"][0]["prompt_outside_budget"] is True
    assert "prompt_outside_budget" not in inside.to_dict()["conditions"][0]
    assert Experiment.from_dict(matched.to_dict()).digest == matched.digest


def test_unbudgeted_prefix_sits_outside_the_retention_target():
    assert retention_target(3000, 0.5, "agentkv", 673, 673) == 673 + 1164
    assert retention_target(3000, 0.5, "agentkv", 0, 673) == 673 + 1164
    # Inside the budget, the 95 tokens after a 673-token prompt share 24 entries; outside, half.
    assert retention_target(768, 0.5, "agentkv", 673) == 673 + 24
    assert retention_target(768, 0.5, "agentkv", 673, 673) == 673 + 48
    assert retention_target(700, 0.5, "agentkv", 673, 673) == 673 + 24
    assert retention_target(690, 0.5, "agentkv", 673, 673) == 690
    assert retention_target(600, 0.5, "agentkv", 673, 673) == 600
    assert retention_target(700, 0.5, "rkv", 0, 673) == 673 + 14
    assert retention_target(1000, 0.25, "streamingllm", 673, 673) == 673 + 82
    assert retention_target(1000, 0.5, "agentkv", 673, 0) == 673 + 24
    for unbudgeted in (-1, 1.5, True):
        with pytest.raises(ValueError):
            retention_target(100, 0.5, "rkv", 0, unbudgeted)
    with pytest.raises(ValueError):
        retention_target(100, 1, "full", 0, 4)


def test_unbudgeted_prefix_is_part_of_the_policy_fingerprint_only_when_set():
    plain = settings()
    fingerprints = {
        plain.fingerprint(),
        settings(protected_prefix_tokens=673).fingerprint(),
        settings(unbudgeted_prefix_tokens=673).fingerprint(),
        settings(protected_prefix_tokens=673, unbudgeted_prefix_tokens=673).fingerprint(),
    }
    assert len(fingerprints) == 4
    unbudgeted = settings(unbudgeted_prefix_tokens=673)
    assert unbudgeted.fingerprint(policy=False) == plain.fingerprint(policy=False)
    with pytest.raises(ValueError):
        settings(unbudgeted_prefix_tokens=-1)
    with pytest.raises(ValueError):
        settings(method="full", retention=1.0, unbudgeted_prefix_tokens=4)


@pytest.mark.parametrize("method", ["agentkv", "rkv", "streamingllm"])
def test_unbudgeted_prefix_leaves_later_tokens_their_configured_share(method):
    prefix = 40
    pinned, grow_pinned = compacting_engine(method, prefix, unbudgeted=prefix)
    matched, grow_matched = compacting_engine(method, 0, unbudgeted=prefix)
    inside, grow_inside = compacting_engine(method, prefix)
    for chunk in [16] * 20 + [1] * 30:
        for grow in (grow_pinned, grow_matched, grow_inside):
            grow(chunk)
        target = retention_target(len(pinned._raw), 0.5, method, prefix, prefix)
        assert pinned.cache.get_seq_length() == matched.cache.get_seq_length() == target
        assert pinned.retained_fraction(0, prefix) == 1.0
    assert pinned.cache.get_seq_length() == prefix + 155
    assert inside.cache.get_seq_length() == 175
    assert pinned.retained_fraction(prefix, 350) == 0.5
    assert inside.retained_fraction(prefix, 350) == 135 / 310
    assert matched.retained_fraction(0, prefix) < 1.0

    rebuilt, grow_rebuilt = compacting_engine(method, prefix, unbudgeted=prefix)
    grow_rebuilt(350)
    assert rebuilt.cache.get_seq_length() == prefix + 155
    assert rebuilt.retained_fraction(0, prefix) == 1.0


def test_runner_passes_the_unbudgeted_prefix_with_or_without_protection(tmp_path):
    config = experiment(
        [
            arm("plain"),
            arm("pinned", protect_prompt=True, prompt_outside_budget=True),
            arm("matched", prompt_outside_budget=True),
        ]
    )
    cells, engine = run(config, tmp_path)
    assert engine.policies == [
        ("agentkv", 0.5, {}),
        ("agentkv", 0.5, {"protected_prefix_tokens": 4, "unbudgeted_prefix_tokens": 4}),
        ("agentkv", 0.5, {"unbudgeted_prefix_tokens": 4}),
    ]
    plain, pinned, matched = (cell["attempts"][0] for cell in cells)
    assert "prompt_outside_budget" not in cells[0]["condition"]
    assert "unbudgeted_prefix_tokens" not in plain and "protected_prefix_tokens" not in plain
    assert cells[1]["condition"]["prompt_outside_budget"] is True
    assert pinned["protected_prefix_tokens"] == pinned["unbudgeted_prefix_tokens"] == 4
    assert matched["unbudgeted_prefix_tokens"] == 4 and "protected_prefix_tokens" not in matched
    assert all(a["status"] == "completed" for c in cells for a in c["attempts"])


def test_runner_refuses_an_unbudgeted_prefix_the_engine_cannot_apply(tmp_path):
    class Unsupported(Engine):
        supports_protected_prefix = False

    config = experiment([arm("matched", prompt_outside_budget=True)])
    with pytest.raises(UnsupportedPath, match="system prompt"):
        run(config, tmp_path, engine_type=Unsupported)


class Worded(Engine):
    """One token per word of the first user turn, so a statement can be located in it."""

    def __init__(self, clock):
        super().__init__(clock)
        self.tokenizer.apply_chat_template = lambda messages, **kw: [
            1,
            5,
            5,
            END,
            1,
            *(40 + len(word) for word in messages[1]["content"].split()),
            END,
        ]


class Stated(Environment):
    statement = "do the thing"

    def initial_prompt(self):
        return "context: do the thing please now"

    def task_statement(self):
        return self.statement


def test_retention_diagnostic_measures_the_task_statement_the_environment_names(tmp_path):
    config = experiment([arm()], diagnostic=True)
    cells, engine = run(config, tmp_path / "on", engine_type=Worded, environment_type=Stated)
    attempt = cells[0]["attempts"][0]
    trajectory = read_json(tmp_path / "on" / attempt["artifact_dir"] / "trajectory.json")
    # Five template tokens and "context:" precede the three words of the statement.
    assert trajectory["statement_span"] == [6, 9]
    assert [turn["task_statement_retained"] for turn in trajectory["turns"]] == [0.5] * 4
    assert set(engine.measured) == {(0, 4), (6, 9)}

    class Elsewhere(Stated):
        statement = "something the prompt does not say"

    for name, options in (
        ("off", {"engine_type": Worded, "environment_type": Stated}),
        ("unnamed", {"engine_type": Worded}),
        ("absent", {"engine_type": Worded, "environment_type": Elsewhere}),
    ):
        config = experiment([arm()], diagnostic=name != "off")
        cells, engine = run(config, tmp_path / name, **options)
        attempt = cells[0]["attempts"][0]
        trajectory = read_json(tmp_path / name / attempt["artifact_dir"] / "trajectory.json")
        assert "statement_span" not in trajectory
        assert not any("task_statement_retained" in turn for turn in trajectory["turns"])


def test_a_failed_statement_lookup_is_recorded_and_does_not_end_the_attempt(tmp_path):
    class Broken(Stated):
        def task_statement(self):
            raise RuntimeError("no task loaded")

    config = experiment([arm()], diagnostic=True)
    cells, engine = run(config, tmp_path, engine_type=Worded, environment_type=Broken)
    attempt = cells[0]["attempts"][0]
    trajectory = read_json(tmp_path / attempt["artifact_dir"] / "trajectory.json")
    assert attempt["status"] == "completed" and "retention_diagnostic" in attempt["timings"]
    assert trajectory["statement_span_error"] == "RuntimeError: no task loaded"
    assert "statement_span" not in trajectory
    assert [turn["system_prompt_retained"] for turn in trajectory["turns"]] == [0.5] * 4

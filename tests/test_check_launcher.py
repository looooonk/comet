import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts/run_checks.sh"


def _launcher_environment(tmp_path, *, lint=False):
    repo, environment, output = (tmp_path / name for name in ("repo", "environment", "evidence"))
    for directory in (repo / "scripts", repo / "infra/slurm", repo / "infra/gcp", environment / "bin"):
        directory.mkdir(parents=True)
    (repo / "scripts/activate_runtime.sh").write_text(
        'printf "%s\\n" "$1" > "$COMET_ENV/activation-profile"\n'
        'export PATH="$COMET_ENV/bin:$PATH"\n')
    for directory in ("infra/slurm", "infra/gcp"):
        (repo / directory / "check.sh").write_text("true\n")
    (environment / ".comet-runtime.json").write_text('{}\n')
    programs = {
        "git": "#!/bin/sh\nexit 0\n",
        "nvidia-smi": '#!/bin/sh\nprintf "device probe\\n"\n',
        "python": f"#!{sys.executable}\n" + """import json
import os
import subprocess
import sys
from pathlib import Path
if sys.argv[1:3] == ['-m', 'pytest']:
    Path(os.environ['COMET_CHECK_OUTPUT'], 'pytest-invocation.json').write_text(json.dumps({
        'args': sys.argv[1:], 'cuda_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
        'gpu_flag': os.environ.get('COMET_RUN_GPU_TESTS'),
        'gpu_evidence': os.environ.get('COMET_GPU_EVIDENCE'),
    }))
else:
    raise SystemExit(subprocess.call([sys.executable, *sys.argv[1:]]))
""",
    }
    if lint:
        programs["ruff"] = '#!/bin/sh\nprintf "lint ran\\n" > "$COMET_ENV/lint-ran"\n'
    for name, code in programs.items():
        path = environment / "bin" / name
        path.write_text(code)
        path.chmod(0o755)
    variables = {**os.environ, "PATH": "/usr/bin:/bin", "COMET_REPO": str(repo), "COMET_ENV": str(environment),
                 "COMET_CHECK_OUTPUT": str(output), "COMET_RUN_GPU_TESTS": "1",
                 "COMET_GPU_EVIDENCE": "must-clear", "CUDA_VISIBLE_DEVICES": "0"}
    variables.pop("SLURM_JOB_ID", None)
    variables.pop("COMET_MODEL_PATH", None)
    return environment, output, variables


@pytest.mark.parametrize("lint", [False, True])
def test_gpu_cpu_only_keeps_profile_and_omits_model_device_requirements(tmp_path, lint):
    environment, output, variables = _launcher_environment(tmp_path, lint=lint)
    result = subprocess.run(["/bin/bash", str(LAUNCHER), "gpu", "--cpu-only"], env=variables,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (environment / "activation-profile").read_text().strip() == "gpu"
    invocation = json.loads((output / "pytest-invocation.json").read_text())
    assert invocation["args"][2:4] == ["-m", "not gpu and not appworld"]
    assert invocation["cuda_devices"] == ""
    assert invocation["gpu_flag"] is invocation["gpu_evidence"] is None
    assert not (output / "gpu-device.txt").exists()
    assert (output / "mode.txt").read_text() == "profile=gpu\ncpu_only=true\nselection=not gpu and not appworld\n"
    assert (output / "lint-status.txt").read_text().startswith("passed" if lint else "skipped:")
    assert (environment / "lint-ran").exists() == lint


def test_ordinary_gpu_checks_still_require_model_and_probe_device(tmp_path):
    environment, output, variables = _launcher_environment(tmp_path)
    result = subprocess.run(["/bin/bash", str(LAUNCHER), "gpu"], env=variables,
                            text=True, capture_output=True)
    assert result.returncode != 0 and "COMET_MODEL_PATH" in result.stderr
    assert not output.exists()
    variables["COMET_MODEL_PATH"] = "/declared/snapshot"
    result = subprocess.run(["/bin/bash", str(LAUNCHER), "gpu"], env=variables,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert (output / "gpu-device.txt").read_text().strip() == "device probe"
    invocation = json.loads((output / "pytest-invocation.json").read_text())
    assert invocation["args"][2:4] == ["-m", ""]
    assert invocation["gpu_flag"] == "1" and invocation["cuda_devices"] == "0"


@pytest.mark.parametrize("args", [["cpu", "--cpu-only"], ["appworld", "--cpu-only"],
                                  ["gpu", "--unknown"], ["gpu", "--cpu-only", "extra"]])
def test_check_launcher_rejects_invalid_optional_arguments(args):
    result = subprocess.run(["/bin/bash", str(LAUNCHER), *args], env={"PATH": "/usr/bin:/bin"},
                            text=True, capture_output=True)
    assert result.returncode == 2
    assert "supported only with the gpu runtime profile" in result.stderr

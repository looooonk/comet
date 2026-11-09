"""Package the pinned AgentKV selectors without the legacy serving dependencies."""

import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "vendor/minisgl/python/minisgl/eviction"
target = root / "vendor/agentkv-selectors"
package = target / "comet_agentkv"
package.mkdir(parents=True, exist_ok=True)
modules = ("base", "attention_score", "identity", "streamingllm", "r1kv", "snapkv", "stageq")
for name in modules:
    text = (source / f"{name}.py").read_text()
    (package / f"{name}.py").write_text(text.replace("from minisgl.eviction.", "from ."))
text = (source / "__init__.py").read_text().split("\nfrom .manager import")[0]
text = text.replace("from .triattention import TriAttentionEvictionPlan\n", "")
start = text.index('    if method in {"triattn", "triattention"}:')
end = text.index("    raise ValueError(", start)
(package / "__init__.py").write_text(text[:start] + text[end:])
shutil.copy(root / "vendor/minisgl/LICENSE", target / "LICENSE")
(target / "pyproject.toml").write_text('''[build-system]
requires = ["setuptools==80.9.0"]
build-backend = "setuptools.build_meta"
[project]
name = "comet-agentkv-selectors"
version = "0.1.0"
dependencies = ["torch==2.9.1"]
license = "MIT"
[tool.setuptools.packages.find]
include = ["comet_agentkv*"]
''')
(target / "adaptation.json").write_text(json.dumps({
    "revision": "254c57bc84e4a7895159ba1062bd46c83626f511",
    "modules": modules,
    "changes": "Relative imports; factory omits unused TriAttention and legacy manager imports."
}, indent=2) + "\n")

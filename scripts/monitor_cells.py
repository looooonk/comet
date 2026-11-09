import json
import sys
import time
from pathlib import Path

root = Path(sys.argv[1])
seen = set()
while True:
    for path in sorted(root.rglob("cell.json")):
        try:
            cell = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not cell.get("completed") or str(path) in seen:
            continue
        seen.add(str(path))
        print(json.dumps({"event": "cell_completed", "run": path.parents[2].name,
                          "task": cell["task_id"], "condition": cell["condition"]["id"],
                          "elapsed_seconds": cell["elapsed_seconds"],
                          "attempt_statuses": [a["status"] for a in cell["attempts"]],
                          "tool_calls": [a.get("tool_calls") for a in cell["attempts"]]}), flush=True)
    time.sleep(15)

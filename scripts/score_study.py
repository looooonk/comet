"""Score completed partitions offline, then verify complete study coverage."""

import argparse
import json
from pathlib import Path

from comet.analysis import analyze_runs
from comet.config import Experiment
from comet.evaluation import evaluate_run

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("partitions", type=Path)
parser.add_argument("run", type=Path)
args = parser.parse_args()
index = json.loads((args.partitions / "index.json").read_text())
parent = args.partitions / index["study_config"]
study = Experiment.load(parent)
if study.digest != index["study_digest"]:
    raise ValueError("The frozen parent changed after partitioning")
runs = []
for entry in index["partitions"]:
    config = Experiment.load(args.partitions / entry["config"])
    if config.digest != entry["digest"]:
        raise ValueError("A submitted partition changed")
    run = args.run / Path(entry["config"]).stem
    manifest = json.loads((run / "manifest.json").read_text())
    if manifest["status"] != "completed" or manifest["config_digest"] != config.digest:
        raise ValueError("Every declared partition must finish before offline scoring")
    runs.append(run)
for run in runs:
    evaluate_run(run)
analysis_path = args.run / "analysis.json"
analyze_runs(runs, analysis_path, study_config=parent)

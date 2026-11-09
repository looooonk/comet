"""Plot the saved synthetic context/recovery qualification record."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument(
        "--output", required=True, type=Path, help="Output prefix without extension"
    )
    args = parser.parse_args()
    record = json.loads(args.record.read_text())
    rows = record["conditions"]
    names = {
        "full": "Full cache",
        "streamingllm": "StreamingLLM",
        "rkv": "R-KV",
        "agentkv": "AgentKV",
    }
    labels = [names[row["method"]] for row in rows]
    colors = ["#333333", "#4477aa", "#cc6677", "#228833"]

    with plt.rc_context(
        {
            "font.size": 9,
            "svg.fonttype": "none",
            "savefig.dpi": 300,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    ):
        figure, axes = plt.subplots(1, 3, figsize=(12, 4.8))
        for index, row in enumerate(rows):
            memory = row["memory"]
            recovery_memory = row.get("post_recovery_memory")
            occupied = memory["occupied_kv_bytes"] / 2**20
            axes[0].bar(index, occupied, color=colors[index], width=0.55)
            axes[0].text(index, occupied + 8, f"{occupied:g}", ha="center", fontsize=8)
            peak = memory["peak_total_vram_bytes"] / 2**30
            axes[1].plot(index, peak, "o", color=colors[index])
            if recovery_memory:
                axes[0].plot(
                    index,
                    recovery_memory["peak_kv_bytes"] / 2**20,
                    "D",
                    color=colors[index],
                    fillstyle="none",
                )
                axes[1].plot(
                    index,
                    recovery_memory["peak_total_vram_bytes"] / 2**30,
                    "D",
                    color=colors[index],
                    fillstyle="none",
                )
                seconds = row["recovery"]["seconds"]
                axes[2].bar(index, seconds, color=colors[index], width=0.55)
                axes[2].text(index, seconds + 0.5, f"{seconds:.1f}", ha="center", fontsize=8)
        axes[0].set(title="Attention state", ylabel="MiB", ylim=(0, 560))
        axes[0].plot(
            [], [], "D", color="#555555", fillstyle="none", label="Peak including recovery"
        )
        axes[0].legend(frameon=False, fontsize=7, loc="center right")
        cap = record["peak_vram_cap_bytes"] / 2**30
        axes[1].axhline(cap, color="#999999", linestyle="--", linewidth=1, label=f"{cap:g} GiB cap")
        axes[1].set(title="Sampled total GPU peak", ylabel="GiB", ylim=(0, cap * 1.1))
        axes[1].plot([], [], "o", color="#555555", label="Generation")
        axes[1].plot([], [], "D", color="#555555", fillstyle="none", label="Including recovery")
        axes[1].legend(frameon=False, fontsize=7, loc="lower left")
        axes[2].set(title="One full-history rebuild", ylabel="Seconds", ylim=(0, 26))
        axes[2].text(0, 1, "N/A", ha="center", color="#777777")
        for axis in axes:
            axis.set_xticks(range(len(rows)), labels, rotation=20)
            axis.grid(axis="y", alpha=0.15)
            axis.set_axisbelow(True)
        figure.suptitle(
            f"Qwen3.5-9B | {record['context_tokens']:,}-token qualification on {record['device']}"
        )
        figure.text(
            0.5,
            0.035,
            "Synthetic capacity check; one observation per method. Compressed methods retain 25% of full-attention KV.\n"
            "Bars in the first panel show stored KV after compaction; recurrent/convolution state remains 49.5 MiB.\n"
            "Recovery temporarily restores all KV. Total VRAM is sampled every 10 ms and at forward boundaries; no reserved KV pool.",
            ha="center",
            fontsize=8,
        )
        figure.tight_layout(rect=(0, 0.18, 1, 0.94))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        for extension in ("png", "svg", "pdf"):
            figure.savefig(args.output.with_suffix("." + extension))
        plt.close(figure)


if __name__ == "__main__":
    main()

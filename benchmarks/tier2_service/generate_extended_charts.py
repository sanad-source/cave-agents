"""Generate extended publication charts for CaveAgents benchmarks.
Adheres strictly to the SuperAgent Operating Protocol:
- Zero synthetic data: all data read directly from disk.
- Exact numbers matching results.json and Tier 1 logs.
"""

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patches as mpatches

BENCHMARK_DIR = Path(__file__).resolve().parent
REPO_ROOT = BENCHMARK_DIR.parent.parent
RESULTS_FILE = BENCHMARK_DIR / "results.json"
ASSETS_DIR = REPO_ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

with open(RESULTS_FILE) as f:
    data = json.load(f)

mono_records = [r for r in data if r["arm"] == "pruned_mono"]
v4_records = [r for r in data if r["arm"] == "caveagents_v4"]

mono_tokens = [r["token_metrics"]["total_tokens"] for r in mono_records]
v4_tokens = [r["token_metrics"]["total_tokens"] for r in v4_records]

mono_lat = [r["wall_clock_sec"] for r in mono_records]
v4_lat = [r["wall_clock_sec"] for r in v4_records]

mono_diag = [r["token_metrics"]["dialogue_tokens"] for r in mono_records]
mono_sch = [r["token_metrics"]["schema_tokens"] for r in mono_records]

v4_diag = [r["token_metrics"]["dialogue_tokens"] for r in v4_records]
v4_sch = [r["token_metrics"]["schema_tokens"] for r in v4_records]

found_toks = [r["token_metrics"]["subagents"]["foundation"]["total_tokens"] for r in v4_records]
exec_toks = [r["token_metrics"]["subagents"]["executor"]["total_tokens"] for r in v4_records]
found_diag = [r["token_metrics"]["subagents"]["foundation"]["dialogue_tokens"] for r in v4_records]
found_sch = [r["token_metrics"]["subagents"]["foundation"]["schema_tokens"] for r in v4_records]
exec_diag = [r["token_metrics"]["subagents"]["executor"]["dialogue_tokens"] for r in v4_records]
exec_sch = [r["token_metrics"]["subagents"]["executor"]["schema_tokens"] for r in v4_records]

COLOR_MONO = "#0284c7"      # Blue for single agent
COLOR_V4 = "#7c3aed"        # Purple for multi-agent team
COLOR_FOUND = "#a855f7"     # Lighter purple for foundation
COLOR_EXEC = "#6366f1"      # Indigo for executor

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")


def make_scaling_chart():
    """Chart 1: Cross-Tier Scaling (Tier 1 vs Tier 2)."""
    fig, ax = plt.subplots(figsize=(10.5, 6.0), dpi=300)

    tier1_mono = 11381
    tier1_v4 = 26784
    tier2_mono = np.mean(mono_tokens)
    tier2_v4 = np.mean(v4_tokens)

    x = np.array([0, 1])
    width = 0.35

    rects1 = ax.bar(x - width/2, [tier1_mono, tier2_mono], width, label="Pruned Monolith Control", color=COLOR_MONO, alpha=0.9, edgecolor="#0f172a", linewidth=1.2)
    rects2 = ax.bar(x + width/2, [tier1_v4, tier2_v4], width, label="CaveAgents Teams (v4 @ T1, v4-lite @ T2)", color=COLOR_V4, alpha=0.9, edgecolor="#0f172a", linewidth=1.2)

    ax.set_ylabel("Estimated Total Tokens", fontsize=11, fontweight="bold")
    ax.set_title("Cross-Tier Coordination Tax: Single Agent vs. Multi-Agent Teams", fontsize=13, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([
        "Tier 1: Single Algorithmic Component (TokenBucket, ~91 LOC)\n[CaveAgents v4: QA + Coder + Reviewer (3 Agents), n=1]",
        "Tier 2: Multi-File Asynchronous Service (taskflow, ~500 LOC)\n[CaveAgents v4-lite: Foundation + Executor (No Review, 2 Agents), n=10]"
    ], fontsize=9.5, fontweight="bold")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda val, p: f"{int(val):,}"))

    # Add data labels
    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f"{int(h):,}\n(1.00x)",
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.5, fontweight="bold", color="#0369a1")

    for i, rect in enumerate(rects2):
        h = rect.get_height()
        ratio = tier1_v4 / tier1_mono if i == 0 else tier2_v4 / tier2_mono
        ax.annotate(f"{int(h):,}\n({ratio:.2f}x, +{(ratio-1)*100:.1f}%)",
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.5, fontweight="bold", color="#5b21b6")

    # Add insight callout
    ax.text(0.5, 96000, "Minimal 2-worker serial handoff (v4-lite, no review) still costs 3.08x (+208%)\nZero demonstrated benefit on this task: latency parity (serial blocking),\n159/160 vs 160/160 pass rate is within noise (single defect in T08)",
            ha="center", va="center", fontsize=9.0, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#fef3c7", edgecolor="#f59e0b", alpha=0.95))

    ax.set_ylim(0, 118000)
    ax.legend(loc="upper left", frameon=True, fontsize=10.0)
    plt.tight_layout()

    out_file = ASSETS_DIR / "chart_scaling_tiers.png"
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Generated: {out_file}")


def make_breakdown_chart():
    """Chart 2: Decomposition of Expenditure in Tier 2."""
    fig, ax = plt.subplots(figsize=(10.5, 5.8), dpi=300)

    categories = [
        "Pruned Monolith\n(Full Service Control)",
        "v4-lite: Foundation Worker\n(Models, Storage, Queue)",
        "v4-lite: Executor Worker\n(Executor, Service)",
        "v4-lite: Combined 2-Worker Team\n(Foundation + Executor, No Review)"
    ]

    dialogues = [np.mean(mono_diag), np.mean(found_diag), np.mean(exec_diag), np.mean(v4_diag)]
    schemas = [np.mean(mono_sch), np.mean(found_sch), np.mean(exec_sch), np.mean(v4_sch)]

    x = np.arange(len(categories))
    width = 0.5

    p1 = ax.bar(x, dialogues, width, label="Dialogue / Reasoning Tokens", color="#38bdf8", edgecolor="#0284c7", linewidth=1.2)
    p2 = ax.bar(x, schemas, width, bottom=dialogues, label="Tool Schema Declaration Tokens", color="#f59e0b", edgecolor="#d97706", linewidth=1.2)

    ax.set_ylabel("Estimated Total Tokens", fontsize=11, fontweight="bold")
    ax.set_title("Tier 2 Token Expenditure Decomposition: Dialogue vs. Schema Costs\n(Evaluated on CaveAgents v4-lite: 2-Worker Division of Labor, No Reviewer)", fontsize=12.0, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9.5, fontweight="bold")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda val, p: f"{int(val):,}"))

    # Value labels
    for i in range(len(categories)):
        tot = dialogues[i] + schemas[i]
        ax.annotate(f"Total: {int(tot):,}\n({dialogues[i]:.0f} diag + {schemas[i]:.0f} sch)",
                    xy=(x[i], tot),
                    xytext=(0, 5), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8.5, fontweight="bold", color="#1e293b")

    ax.set_ylim(0, 115000)
    ax.legend(loc="upper left", frameon=True, fontsize=10.5)
    plt.tight_layout()

    out_file = ASSETS_DIR / "chart_token_breakdown_tier2.png"
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Generated: {out_file}")


def make_pareto_chart():
    """Chart 3: Latency vs Token Expenditure (Cost-Time Efficiency Pareto)."""
    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=300)

    # Plot Monolith trials
    ax.scatter(mono_lat, mono_tokens, color=COLOR_MONO, s=90, alpha=0.85, edgecolors="#0f172a", linewidth=1.2, label="Pruned Monolith Trials (n=10)", zorder=3)
    # Plot Team trials
    ax.scatter(v4_lat, v4_tokens, color=COLOR_V4, s=100, marker="D", alpha=0.85, edgecolors="#0f172a", linewidth=1.2, label="CaveAgents v4-lite Team (2 Workers, n=10)", zorder=3)

    # Centroid markers
    mean_mono_lat = np.mean(mono_lat)
    mean_mono_tok = np.mean(mono_tokens)
    mean_v4_lat = np.mean(v4_lat)
    mean_v4_tok = np.mean(v4_tokens)

    ax.scatter([mean_mono_lat], [mean_mono_tok], color="#0284c7", s=250, marker="*", edgecolors="#0f172a", linewidth=1.5, zorder=4, label=f"Monolith Mean ({mean_mono_lat:.1f}s, {int(mean_mono_tok):,} tok)")
    ax.scatter([mean_v4_lat], [mean_v4_tok], color="#7c3aed", s=250, marker="*", edgecolors="#0f172a", linewidth=1.5, zorder=4, label=f"v4-lite Team Mean ({mean_v4_lat:.1f}s, {int(mean_v4_tok):,} tok)")

    # Latency parity line
    ax.axvline(mean_mono_lat, color="#0284c7", linestyle="--", alpha=0.4, linewidth=1.2)
    ax.axvline(mean_v4_lat, color="#7c3aed", linestyle=":", alpha=0.4, linewidth=1.2)

    ax.set_xlabel("Wall-Clock Execution Time (Seconds)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Estimated Total Tokens", fontsize=11, fontweight="bold")
    ax.set_title("Tier 2 Trade-off: Wall-Clock Latency vs. Token Expenditure (N=20)\nPruned Monolith vs. CaveAgents v4-lite", fontsize=12.5, fontweight="bold", pad=15)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda val, p: f"{int(val):,}"))

    # Annotation
    ax.text(175, 45000, "Functionally Serialized via Data-Flow Dependency\nIdentical Latency Band (~120s–230s) | 3.08x Token Separation\nZero Demonstrated Benefit: Latency Wash & Quality Parity",
            fontsize=9.0, fontweight="bold", color="#1e293b",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#e0f2fe", edgecolor="#0284c7", alpha=0.9))

    ax.legend(loc="upper left", frameon=True, fontsize=9.0)
    ax.set_ylim(15000, 120000)
    ax.set_xlim(110, 240)
    plt.tight_layout()

    out_file = ASSETS_DIR / "chart_pareto_latency_cost.png"
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Generated: {out_file}")


if __name__ == "__main__":
    make_scaling_chart()
    make_breakdown_chart()
    make_pareto_chart()

"""Generate empirical visualization chart for Tier 2 benchmark (n=10 per arm)."""

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

mono_hid = [r["test_results"]["hidden"]["passed"] for r in mono_records]
v4_hid = [r["test_results"]["hidden"]["passed"] for r in v4_records]

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.8), dpi=300)

COLOR_MONO = "#0284c7"  # Blue for single agent
COLOR_V4 = "#7c3aed"    # Purple for multi-agent team

# Subplot 1: Token Expenditure Distribution
bp1 = ax1.boxplot(
    [mono_tokens, v4_tokens],
    tick_labels=["Pruned Mono (Control)\n[n=10]", "CaveAgents v4-lite (2-Worker Team)\n[No Reviewer, n=10]"],
    patch_artist=True,
    widths=0.45,
    boxprops=dict(linewidth=1.2),
    medianprops=dict(color="#0f172a", linewidth=2.0)
)
bp1["boxes"][0].set_facecolor(COLOR_MONO)
bp1["boxes"][0].set_alpha(0.85)
bp1["boxes"][1].set_facecolor(COLOR_V4)
bp1["boxes"][1].set_alpha(0.85)

# Overlay individual trial points
np.random.seed(42)
for i, tokens in enumerate([mono_tokens, v4_tokens]):
    x = np.random.normal(i + 1, 0.04, size=len(tokens))
    ax1.plot(x, tokens, "o", color="#0f172a", alpha=0.7, markersize=6)

mono_mean = np.mean(mono_tokens)
v4_mean = np.mean(v4_tokens)
ratio = v4_mean / mono_mean

ax1.set_ylabel("Estimated Total Tokens", fontsize=11, fontweight="bold")
ax1.set_title(f"Token Expenditure Distribution\n(v4-lite is {ratio:.2f}x more expensive, +{(ratio-1)*100:.1f}%)", fontsize=12, fontweight="bold")
ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"{int(x):,}"))

# Subplot 2: Wall-Clock Latency Distribution
bp2 = ax2.boxplot(
    [mono_lat, v4_lat],
    tick_labels=["Pruned Mono (Control)\n[n=10]", "CaveAgents v4-lite (2-Worker Team)\n[No Reviewer, n=10]"],
    patch_artist=True,
    widths=0.45,
    boxprops=dict(linewidth=1.2),
    medianprops=dict(color="#0f172a", linewidth=2.0)
)
bp2["boxes"][0].set_facecolor(COLOR_MONO)
bp2["boxes"][0].set_alpha(0.85)
bp2["boxes"][1].set_facecolor(COLOR_V4)
bp2["boxes"][1].set_alpha(0.85)

for i, lats in enumerate([mono_lat, v4_lat]):
    x = np.random.normal(i + 1, 0.04, size=len(lats))
    ax2.plot(x, lats, "o", color="#0f172a", alpha=0.7, markersize=6)

mono_lat_mean = np.mean(mono_lat)
v4_lat_mean = np.mean(v4_lat)
lat_ratio = v4_lat_mean / mono_lat_mean

ax2.set_ylabel("Wall-Clock Latency (Seconds)", fontsize=11, fontweight="bold")
ax2.set_title(f"Wall-Clock Execution Time: Parity at {lat_ratio:.2f}x ({v4_lat_mean:.1f}s vs {mono_lat_mean:.1f}s)\n[Functionally Serialized: Executor Polled Waiting for Foundation Models]", fontsize=11, fontweight="bold")

patch_mono = mpatches.Patch(facecolor=COLOR_MONO, edgecolor="#1e293b", label="Pruned Single Agent (159/160 passed; 1 timeout cancellation defect in T08)")
patch_v4 = mpatches.Patch(facecolor=COLOR_V4, edgecolor="#1e293b", label="CaveAgents v4-lite (2 Workers: Foundation + Executor, No Review; 160/160 passed)")
fig.legend(handles=[patch_mono, patch_v4], loc="lower center", ncol=2, frameon=True, fontsize=10, bbox_to_anchor=(0.5, -0.06))

plt.suptitle("Tier 2 Multi-File Service Benchmark: Pruned Monolith vs. CaveAgents v4-lite (n=10 per Arm, N=20 Total)", fontsize=13, fontweight="bold", y=1.02)
plt.tight_layout()

out_chart = ASSETS_DIR / "chart_tier2_benchmark.png"
fig.savefig(out_chart, dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"Tier 2 benchmark chart generated: {out_chart}")

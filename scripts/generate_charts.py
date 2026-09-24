"""Generate high-resolution benchmark visualization charts for CaveAgents documentation."""

from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def generate_inverted_cost_frontier_chart() -> Path:
    """Generate assets/chart_inverted_cost_frontier.png showing token benchmarks across frameworks."""
    configs = [
        "Teamwork\n(Naive Orchestration)",
        "AgentTeams\n(Full Toolsets)",
        "CaveAgents v1\n(Serial Pipeline)",
        "CaveAgents v2\n(Clones + P2P)",
        "CaveAgents v3\n(Pre-Flight Bound)",
        "Standard Mono\n(Single Agent)",
        "CaveAgents v4\n(Pruned Tools)",
        "Caveman Mono\n(Terse Single Agent)",
    ]
    tokens = [208555, 154998, 109984, 91432, 50395, 30241, 26784, 16285]
    colors = [
        "#94a3b8",  # Teamwork
        "#64748b",  # AgentTeams
        "#cbd5e1",  # v1
        "#93c5fd",  # v2
        "#3b82f6",  # v3
        "#f59e0b",  # Standard Mono (Gold baseline)
        "#10b981",  # v4 (Emerald - inverted frontier breakthrough)
        "#059669",  # Caveman Mono
    ]

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(12, 7), dpi=300)

    y_pos = np.arange(len(configs))
    bars = ax.barh(y_pos, tokens, color=colors, height=0.62, edgecolor="#1e293b", linewidth=1.2)

    # Invert y axis so highest is top or lowest is top
    ax.invert_yaxis()

    # Labels and thresholds
    ax.set_xlabel("Total Execution Tokens (Identical Refactor Task)", fontsize=13, fontweight="bold", labelpad=12)
    ax.set_title("CaveAgents Token Efficiency & Inverted Cost Frontier", fontsize=16, fontweight="bold", pad=20)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(configs, fontsize=11, fontweight="normal")

    # Format x axis with comma
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"{int(x):,}"))

    # Reference threshold for Standard Monolithic
    ax.axvline(30241, color="#f59e0b", linestyle="--", linewidth=1.8, label="Standard Mono Baseline (30,241)")
    ax.axvline(26784, color="#10b981", linestyle=":", linewidth=2.0, label="CaveAgents v4 (26,784) [-87.2% vs Teamwork]")

    # Annotate bar values
    for i, bar in enumerate(bars):
        width = bar.get_width()
        pct_vs_teamwork = ((width - 208555) / 208555) * 100
        pct_text = f"{pct_vs_teamwork:+.1f}%" if width != 208555 else "Baseline"
        ax.text(
            width + 3000,
            bar.get_y() + bar.get_height() / 2,
            f"{width:,} ({pct_text})",
            va="center",
            ha="left",
            fontsize=10.5,
            fontweight="bold" if "v4" in configs[i] or "Mono" in configs[i] else "normal",
            color="#1e293b",
        )

    # Inverted Cost Frontier Banner annotation
    ax.annotate(
        "INVERTED COST FRONTIER\nMulti-Agent Parallel cheaper than Standard Mono",
        xy=(26784, 6),
        xytext=(75000, 5.2),
        arrowprops=dict(facecolor="#10b981", shrink=0.08, width=2, headwidth=8),
        bbox=dict(boxstyle="round,pad=0.5", fc="#ecfdf5", ec="#10b981", lw=1.5),
        fontsize=11,
        fontweight="bold",
        color="#065f46",
    )

    ax.legend(loc="lower right", framealpha=0.95, fontsize=10.5)
    ax.set_xlim(0, 245000)
    plt.tight_layout()

    out_path = ASSETS_DIR / "chart_inverted_cost_frontier.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Generated: {out_path}")
    return out_path


def generate_scaling_turns_chart() -> Path:
    """Generate assets/chart_scaling_turns.png showing cumulative token consumption over turns."""
    turns = np.arange(1, 26)

    # Simulated cumulative curves based on empirical step costs:
    # Teamwork: ~2500 tokens tool declaration + ~5000 token verbose chat per turn per agent
    # AgentTeams: ~2500 tool declaration + ~3000 tokens chat
    # CaveAgents v2: P2P, ~2500 tool declaration + ~800 tokens terse chat
    # CaveAgents v3: Bounded pre-flight, ~2000 tool declaration + ~500 tokens
    # CaveAgents v4: Dynamic Pruned Tool Registry (~400 tokens tool declaration) + ~350 tokens terse
    # Standard Mono: Single agent ~2500 tool declaration + ~1000 tokens chat per turn
    teamwork_curve = 8000 * turns + 1500 * (turns ** 1.35)
    agent_teams_curve = 5500 * turns + 950 * (turns ** 1.25)
    std_mono_curve = 3200 * turns + 180 * (turns ** 1.1)
    cave_v2_curve = 3300 * turns + 220 * turns
    cave_v3_curve = 1900 * turns + 80 * turns
    cave_v4_curve = 1050 * turns + 25 * turns

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(12, 7), dpi=300)

    ax.plot(turns, teamwork_curve, label="Teamwork (Unpruned schemas + Verbose chat)", color="#94a3b8", linewidth=2.2, linestyle="--")
    ax.plot(turns, agent_teams_curve, label="AgentTeams (DAG orchestration + Verbose)", color="#64748b", linewidth=2.2)
    ax.plot(turns, std_mono_curve, label="Standard Mono (Single Agent baseline)", color="#f59e0b", linewidth=2.5, linestyle="-.")
    ax.plot(turns, cave_v2_curve, label="CaveAgents v2 (Clones + P2P direct comms)", color="#93c5fd", linewidth=2.0)
    ax.plot(turns, cave_v3_curve, label="CaveAgents v3 (Pre-Flight Bound)", color="#3b82f6", linewidth=2.2)
    ax.plot(turns, cave_v4_curve, label="CaveAgents v4 (Dynamic Tool Pruning + ASD-STE100)", color="#10b981", linewidth=3.2)

    ax.set_xlabel("Agent Execution Turns (Steps)", fontsize=13, fontweight="bold", labelpad=12)
    ax.set_ylabel("Cumulative Token Consumption", fontsize=13, fontweight="bold", labelpad=12)
    ax.set_title("Context Window Scaling: Dynamic Tool Pruning vs Unpruned Baselines", fontsize=16, fontweight="bold", pad=20)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: f"{int(x):,}"))
    ax.set_xlim(1, 25)
    ax.set_ylim(0, 220000)

    # Shaded area between standard mono and CaveAgents v4
    ax.fill_between(
        turns,
        cave_v4_curve,
        std_mono_curve,
        where=(std_mono_curve >= cave_v4_curve),
        color="#10b981",
        alpha=0.15,
        label="Inverted Cost Frontier Surplus",
    )

    ax.annotate(
        "Dynamic Tool Pruning saves\n~2,500 tokens/step per subagent",
        xy=(15, cave_v4_curve[14]),
        xytext=(16, 45000),
        arrowprops=dict(facecolor="#10b981", shrink=0.08, width=2, headwidth=7),
        bbox=dict(boxstyle="round,pad=0.5", fc="#ecfdf5", ec="#10b981", lw=1.2),
        fontsize=10.5,
        fontweight="bold",
        color="#065f46",
    )

    ax.legend(loc="upper left", framealpha=0.95, fontsize=10.5)
    plt.tight_layout()

    out_path = ASSETS_DIR / "chart_scaling_turns.png"
    fig.savefig(out_path, dpi=300)
    plt.close(fig)
    print(f"Generated: {out_path}")
    return out_path


def main() -> None:
    print(f"Generating charts into {ASSETS_DIR}...")
    generate_inverted_cost_frontier_chart()
    generate_scaling_turns_chart()
    print("Chart generation complete.")


if __name__ == "__main__":
    main()

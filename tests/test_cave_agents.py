import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

try:
    import yaml
except ImportError:
    yaml = None


def test_readme_and_docs():
    """Assert README and documentation files exist with required sections."""
    required_files = {
        "README.md": ["# CaveAgents", "Architecture", "Benchmark", "Quickstart"],
        "docs/INSPIRATION.md": ["Inspiration", "Caveman", "Context Window"],
        "docs/ARCHITECTURE.md": ["Architecture", "Topology", "Protocol", "Dynamic Tool Pruning"],
        "docs/VERSIONS.md": ["Version History", "v1", "v2", "v3", "v4"],
        "docs/BENCHMARKS.md": ["Benchmark", "Token Usage", "Empirical Results"],
    }

    for rel_path, expected_sections in required_files.items():
        doc_path = REPO_ROOT / rel_path
        assert doc_path.exists(), f"Missing required documentation: {rel_path}"
        content = doc_path.read_text(encoding="utf-8")
        for section in expected_sections:
            assert section.lower() in content.lower(), (
                f"Missing section/keyword '{section}' in {rel_path}"
            )


def test_versions_documented():
    """Assert docs/VERSIONS.md covers v1 through v4 evolution."""
    versions_file = REPO_ROOT / "docs" / "VERSIONS.md"
    assert versions_file.exists(), "docs/VERSIONS.md does not exist"
    content = versions_file.read_text(encoding="utf-8")

    assert "v1" in content and "Serial" in content, "v1 (Serial) not documented"
    assert "v2" in content and ("Clones" in content or "P2P" in content), "v2 (Clones + P2P) not documented"
    assert "v3" in content and "Pre-Flight Bound" in content, "v3 (Pre-Flight Bound) not documented"
    assert "v4" in content and "Dynamic Tool Pruning" in content and "Inverted Cost Frontier" in content, (
        "v4 (Dynamic Tool Pruning & Inverted Cost Frontier) not documented"
    )


def test_empirical_benchmarks():
    """Assert docs/BENCHMARKS.md contains exact empirical token counts."""
    benchmarks_file = REPO_ROOT / "docs" / "BENCHMARKS.md"
    assert benchmarks_file.exists(), "docs/BENCHMARKS.md does not exist"
    content = benchmarks_file.read_text(encoding="utf-8")

    benchmarks = {
        "26,784": "v4 live run token count",
        "16,285": "caveman mono token count",
        "30,241": "standard mono token count",
        "154,998": "AgentTeams token count",
        "208,555": "Teamwork token count",
    }

    for count, description in benchmarks.items():
        assert count in content or count.replace(",", "") in content, (
            f"Missing empirical count {count} ({description}) in docs/BENCHMARKS.md"
        )


def test_skill_manifest():
    """Assert skills/caveagents/SKILL.md exists, has valid YAML frontmatter with name 'caveagents', and states default v4."""
    skill_file = REPO_ROOT / "skills" / "caveagents" / "SKILL.md"
    assert skill_file.exists(), "skills/caveagents/SKILL.md does not exist"
    content = skill_file.read_text(encoding="utf-8")

    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter delimiter '---'"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "Invalid frontmatter in SKILL.md"

    if yaml is not None:
        frontmatter = yaml.safe_load(parts[1])
    else:
        frontmatter = {}
        for line in parts[1].strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                frontmatter[k.strip()] = v.strip().strip('"\'')

    assert isinstance(frontmatter, dict), "Frontmatter must be a valid YAML mapping"
    assert frontmatter.get("name") == "caveagents", f"Skill name must be 'caveagents', got {frontmatter.get('name')}"

    body = parts[2]
    assert "v4" in body, "SKILL.md must state default v4 engine"


def test_caveagents_sdk():
    """Assert caveagents python package imports protocol, evaluator, and CLI entrypoint."""
    import caveagents
    from caveagents import protocol
    from caveagents import evaluator
    from caveagents import cli

    assert hasattr(caveagents, "__version__"), "caveagents missing __version__"
    assert hasattr(protocol, "CaveMessage") or hasattr(protocol, "MessageProtocol"), "Missing protocol definitions"
    assert hasattr(evaluator, "CostEvaluator") or hasattr(evaluator, "evaluate"), "Missing evaluator definitions"
    assert hasattr(cli, "main") or hasattr(cli, "app"), "Missing CLI entrypoint"

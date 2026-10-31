"""Alembic migration chain integrity tests — TD-NEW-18 CI gate."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_alembic_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    sd = ScriptDirectory.from_config(cfg)
    heads = sd.get_heads()
    assert len(heads) == 1, f"Multiple heads: {heads}"


@pytest.mark.integration
def test_alembic_revision_chain_intact():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    sd = ScriptDirectory.from_config(cfg)
    revs = list(sd.walk_revisions())
    assert len(revs) >= 10, "Expected ≥10 alembic revisions"
    roots = [r for r in revs if r.down_revision is None]
    assert len(roots) == 1, (
        f"Multiple root revisions: {[r.revision for r in roots]}"
    )


@pytest.mark.integration
def test_alembic_freeze_notice_intact():
    from pathlib import Path

    txt = (REPO_ROOT / "alembic/README_FREEZE.md").read_text()
    assert "FREEZE" in txt, (
        "Freeze notice must remain in alembic/README_FREEZE.md"
    )


@pytest.mark.integration
def test_alembic_versions_dir_exists():
    from pathlib import Path

    versions = REPO_ROOT / "alembic/versions"
    assert versions.is_dir()
    migration_files = list(versions.glob("*.py"))
    assert len(migration_files) >= 10

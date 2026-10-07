"""Every T-PRA row in the AGENTS.md §30 register has a TECHNICAL_DEBT.md entry (plan task #11)."""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
_ROW = re.compile(r"^\| (T-PRA-\d+) \|", re.MULTILINE)


@pytest.mark.unit
def test_every_agents_register_tpra_row_is_in_technical_debt():
    register = set(_ROW.findall((REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")))
    debt = set(_ROW.findall((REPO_ROOT / "TECHNICAL_DEBT.md").read_text(encoding="utf-8")))

    assert register, "no T-PRA rows found in AGENTS.md §30"
    assert register - debt == set(), f"T-PRA items missing from TECHNICAL_DEBT.md: {sorted(register - debt)}"

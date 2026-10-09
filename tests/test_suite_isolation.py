"""The test run never touches the real TITAN data folder (root conftest.py).

``~/Documents/TITAN/titan_core.db`` is the database the installed TITAN.exe
uses. A suite that opened it would migrate it to the branch's schema, and the
installed exe would then refuse to start (INV-25).
"""

from pathlib import Path

import pytest


@pytest.mark.unit
def test_home_is_a_throwaway_directory():
    assert Path.home().name.startswith("titan-test-home-")


@pytest.mark.unit
def test_default_database_folder_is_inside_the_throwaway_home():
    from launcher.validator import get_data_directory

    assert Path.home() in get_data_directory().parents

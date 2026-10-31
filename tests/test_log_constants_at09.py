"""AT-09: the log rotation limits have one definition.

titan/main.py rotated at 10 MB x 5 while titan.utils.constants said 5 MB x 3,
so a disk estimate taken from the constants was half the real size.
"""

from __future__ import annotations

import titan.main as titan_main
from titan.utils import constants


def test_main_rotates_the_log_with_the_shared_constants() -> None:
    assert titan_main.LOG_MAX_BYTES == constants.LOG_MAX_BYTES
    assert titan_main.LOG_BACKUP_COUNT == constants.LOG_BACKUP_COUNT


def test_the_shared_constants_keep_the_rotation_main_used() -> None:
    # 10 MB x 5 is what main() has rotated with; the fix does not change it.
    assert constants.LOG_MAX_BYTES == 10 * 1024 * 1024
    assert constants.LOG_BACKUP_COUNT == 5

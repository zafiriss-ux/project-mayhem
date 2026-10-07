"""Docker healthcheck for titan-worker (AGENTS §8.14, INV-23(1)).

Healthy only while the worker's heartbeat file is younger than twice the
supervision tick (WORKER_HEARTBEAT_INTERVAL_S). The worker's silence is the
alert: a hung routine, a dead scheduler thread or a stopped loop all stop the
heartbeat.

    python scripts/worker_healthcheck.py   # exit 0 healthy, 1 unhealthy
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from titan.config.settings import get_settings  # noqa: E402
from titan.worker import HEARTBEAT_FILE, check_heartbeat  # noqa: E402


def main() -> int:
    settings = get_settings()
    path = Path(settings.TITAN_DATA_DIR) / HEARTBEAT_FILE
    healthy, detail = check_heartbeat(path, max_age_s=2 * settings.WORKER_HEARTBEAT_INTERVAL_S)
    print(detail)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())

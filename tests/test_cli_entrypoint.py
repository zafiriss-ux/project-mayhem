import os
import subprocess
import sys


def test_python_m_titan_entrypoint_exits_deterministically_without_traceback():
    env = os.environ.copy()
    env.update(
        {
            "GARMIN_EMAIL": "runner@example.com",
            "GARMIN_PASSWORD": "not-a-real-password",
            "TELEGRAM_BOT_TOKEN": "fake_token_for_cli_entrypoint_test",
            "ATHLETE_AGE": "invalid-int",
        }
    )

    process = subprocess.run(
        [sys.executable, "-m", "titan"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )

    combined_output = f"{process.stdout}\n{process.stderr}".strip()

    assert process.returncode == 1
    assert combined_output
    assert "Traceback" not in process.stderr
    assert (
        "Invalid environment variable ATHLETE_AGE" in combined_output
        or "TITAN v51" in combined_output
    )

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Tier:
    code: str
    name: str
    threshold: float


TIERS: tuple[Tier, ...] = (
    Tier("P0", "Science/Core", 95.0),
    Tier("P1", "Runtime/Orchestration", 95.0),
    Tier("P2", "Features", 90.0),
    Tier("P3", "UI/Utils/Config", 90.0),
)


def classify_tier(file_path: str) -> Tier | None:
    if file_path.startswith("titan/science/") or file_path == "titan/core/database.py":
        return TIERS[0]
    if (
        file_path.startswith("titan/orchestration/")
        or file_path.startswith("titan/integrations/")
        or file_path == "titan/main.py"
    ):
        return TIERS[1]
    if file_path.startswith("titan/features/"):
        return TIERS[2]
    if (
        file_path.startswith("titan/ui/")
        or file_path.startswith("titan/utils/")
        or file_path.startswith("titan/config/")
    ):
        return TIERS[3]
    return None


def format_percent(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def load_coverage(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"coverage.json not found at {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Invalid coverage JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    payload = load_coverage(Path("coverage.json"))
    files = payload.get("files")
    if not isinstance(files, dict):
        print("coverage.json missing 'files' object", file=sys.stderr)
        return 1

    tier_totals: dict[str, dict[str, float]] = {
        tier.code: {"covered": 0.0, "statements": 0.0} for tier in TIERS
    }
    overall_covered = 0.0
    overall_statements = 0.0
    under_threshold: list[tuple[str, Tier, float, list[int]]] = []

    for file_path, details in sorted(files.items()):
        if not (isinstance(file_path, str) and file_path.startswith("titan/") and file_path.endswith(".py")):
            continue
        if not isinstance(details, dict):
            continue
        summary = details.get("summary")
        missing_lines = details.get("missing_lines", [])
        if not isinstance(summary, dict):
            continue

        percent = float(summary.get("percent_covered", 0.0))
        statements = float(summary.get("num_statements", 0.0))
        missing_count = float(summary.get("missing_lines", len(missing_lines) if isinstance(missing_lines, list) else 0))
        covered = max(statements - missing_count, 0.0)

        overall_covered += covered
        overall_statements += statements

        tier = classify_tier(file_path)
        if tier is None:
            continue

        tier_totals[tier.code]["covered"] += covered
        tier_totals[tier.code]["statements"] += statements

        normalized_missing_lines: list[int] = []
        if isinstance(missing_lines, list):
            normalized_missing_lines = [line for line in missing_lines if isinstance(line, int)]

        if percent < tier.threshold:
            under_threshold.append((file_path, tier, percent, normalized_missing_lines))

    overall_percent = (overall_covered / overall_statements * 100.0) if overall_statements else 0.0

    print("=== TITAN COVERAGE CONTROL PANEL ===")
    print()
    print(f"Overall coverage: {format_percent(overall_percent)}")
    print()
    print("Tier Summary")
    for tier in TIERS:
        statements = tier_totals[tier.code]["statements"]
        covered = tier_totals[tier.code]["covered"]
        percent = (covered / statements * 100.0) if statements else 0.0
        print(f"{tier.code} ({tier.name}): {format_percent(percent)}")

    print()
    print("Files under threshold")
    if not under_threshold:
        print("None")
    else:
        sorted_under_threshold = sorted(
            under_threshold,
            key=lambda item: (item[1].code, item[2], item[0]),
        )
        for file_path, tier, percent, missing_lines in sorted_under_threshold:
            print(f"{tier.code} {file_path} — {format_percent(percent)}")
            print(f"missing lines: {missing_lines}")
            print("invariant mapping: TODO")

    return 1 if under_threshold else 0


if __name__ == "__main__":
    raise SystemExit(main())

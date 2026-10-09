"""Print the findings of one or more SARIF files to the log and the job summary.

Used by the security workflows while the repository is private: code scanning
uploads fail there on the Free plan, so the findings would otherwise be visible
only inside the SARIF artifact (D-022, D-030).

Usage: python scripts/sarif_summary.py "<title>" <file-or-glob> [...]
"""
from __future__ import annotations

import glob
import json
import os
import sys


def _rows(paths: list[str]) -> list[tuple[str, str, str, str]]:
    rows = []
    for pattern in paths:
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8") as fh:
                sarif = json.load(fh)
            for run in sarif.get("runs", []):
                for res in run.get("results", []):
                    locations = res.get("locations") or [{}]
                    loc = locations[0].get("physicalLocation", {})
                    uri = loc.get("artifactLocation", {}).get("uri", "?")
                    line = loc.get("region", {}).get("startLine", "?")
                    text = (res.get("message", {}).get("text") or "").splitlines() or [""]
                    rows.append((res.get("ruleId", "?"), res.get("level", "warning"), f"{uri}:{line}", text[0][:160]))
    return sorted(rows)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    title, paths = argv[1], argv[2:]
    rows = _rows(paths)
    print(f"{title}: {len(rows)}")
    for row in rows:
        print(" | ".join(row))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write(f"### {title}: {len(rows)}\n\n")
            if rows:
                out.write("| Rule | Level | Location | Message |\n|---|---|---|---|\n")
                for row in rows:
                    out.write("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

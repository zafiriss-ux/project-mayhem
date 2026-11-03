#!/usr/bin/env bash
# CI-01: prove the installed scanner and repository config detect a fake secret.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
control_dir="$(mktemp -d)"
trap 'rm -rf -- "$control_dir"' EXIT
trap 'exit 1' HUP INT TERM

mkdir "$control_dir/clean" "$control_dir/positive"
printf 'Ordinary documentation without credentials.\n' > "$control_dir/clean/fixture.txt"
# Construct a non-real token only inside the owned temporary fixture.
printf 'token=%s%s\n' 'ghp_' 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' \
  > "$control_dir/positive/fixture.txt"

for control in clean positive; do
  expected_exit=0
  if [ "$control" = positive ]; then
    expected_exit=1
  fi
  report="$control_dir/$control.json"
  scanner_exit=0
  gitleaks detect --no-git --source "$control_dir/$control" \
    --config "$repo_root/.gitleaks.toml" --gitleaks-ignore-path "$control_dir" \
    --redact --report-format json --report-path "$report" --no-banner \
    || scanner_exit=$?
  if [ "$scanner_exit" -ne "$expected_exit" ]; then
    printf 'Gitleaks %s control failed: unexpected scanner exit %s (expected %s).\n' \
      "$control" "$scanner_exit" "$expected_exit" >&2
    exit 1
  fi
  python3 - "$report" "$control" <<'PY'
import json
import sys
from pathlib import Path

try:
    findings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    sys.exit("Gitleaks control failed: missing or invalid JSON report.")

if not isinstance(findings, list):
    sys.exit("Gitleaks control failed: report must be a JSON list.")
if sys.argv[2] == "clean":
    if findings:
        sys.exit("Gitleaks clean control failed: unexpected findings.")
elif not (
    findings
    and all(isinstance(finding, dict) for finding in findings)
    and any(finding.get("RuleID") == "github-pat" for finding in findings)
):
    sys.exit("Gitleaks positive control failed: expected github-pat finding.")
PY
done

printf 'Gitleaks clean and positive controls passed.\n'

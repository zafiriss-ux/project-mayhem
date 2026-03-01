# Agent Instructions

## Git Access (Codex Runtime)

- Work only with the local repository at `/workspace/project-mayhem`.
- Do NOT add/remove remotes.
- Do NOT fetch/push.
- Do NOT assume `main` exists in this runtime (it may be checked out as `work`).
- Do NOT use `gh` CLI.
- Do NOT call GitHub APIs (curl to api.github.com) from this runtime.

### Deliverables for every task
- Run tests locally (e.g., `python -m pytest -q`) when feasible.
- Provide a single unified patch as output:
  - `git diff` (or `git diff --staged` if you staged changes).
- Never create PRs from inside the runtime. The user will apply the diff and open PRs from their laptop.

### Workflow rules
- 1 issue = 1 PR (user handles PR).
- No refactors.
- Only scope described in the issue.
- Keep architecture unchanged.

## Default Workflow
- Always use `git status`, `git log`, `git diff` for repo inspection
- Branch: work (current), main (upstream)
- Never push directly to main

## Project
This is TITAN OS — a longevity-first athletic operating system. See existing docs for architecture and governance rules.

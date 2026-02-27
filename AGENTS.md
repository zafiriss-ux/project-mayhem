# Agent Instructions

## Git Access
Use shell git for all repository operations. The repo is at /workspace/project-mayhem.

On startup, always run:
  git remote add origin https://github.com/zafiriss-ux/project-mayhem.git
  git fetch origin --no-tags
  git branch --track main origin/main 2>/dev/null || true

For GitHub metadata (issues, PRs) use curl against the GitHub REST API:
  curl -s https://api.github.com/repos/zafiriss-ux/project-mayhem/issues?state=open

Do NOT use gh CLI. Do NOT use GitHub MCP integration.
Never push directly to main.

## Default Workflow
- Always use `git status`, `git log`, `git diff` for repo inspection
- Branch: work (current), main (upstream)
- Never push directly to main

## Project
This is TITAN OS — a longevity-first athletic operating system. See existing docs for architecture and governance rules.

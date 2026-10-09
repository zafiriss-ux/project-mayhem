# Security Policy

## Supported versions

Only the latest release of TITAN OS (currently the 5.8.x line) receives security fixes.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Report it privately through GitHub:
[Security → Report a vulnerability](https://github.com/zafiriss-ux/project-mayhem/security/advisories/new).
Include what is affected, how to reproduce it, and what an attacker could do with it.

You should get a first answer within 7 days. Once a fix is released, the advisory is published
and the reporter is credited, unless they ask not to be.

## Scope

In scope: the code in this repository (`titan/`, `launcher/`, `scripts/`), the Docker images
built from it, and the GitHub Actions workflows.

Out of scope: the third-party services TITAN OS talks to (Garmin Connect, Telegram, Open-Meteo).
Report problems in those services to their owners.

## Automated checks

Every pull request and every push to `main` runs CodeQL (with the `security-extended` queries),
Bandit, DevSkim and gitleaks. While the repository is public, Dependency Review runs too and
the findings appear under Security → Code scanning.

## Secrets

Credentials are never stored in the repository. They come from environment variables or the
local encrypted token store (see `.env.example`). If you find a credential in the code or in the
git history, report it as described above.

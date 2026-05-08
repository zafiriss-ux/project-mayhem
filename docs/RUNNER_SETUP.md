# Self-Hosted CI Runner Setup

## One-time setup (5 minutes)

1. Go to your repo on GitHub:
   Settings → Actions → Runners
   → "New self-hosted runner"

2. Select your OS (Linux or macOS).
   Copy the token shown.

3. In your terminal (project root):
   mkdir -p ~/actions-runner && cd ~/actions-runner
   # Download the runner (GitHub shows exact URL)
   ./config.sh --url https://github.com/zafiriss-ux/project-mayhem \
               --token YOUR_TOKEN_HERE

4. Start the runner:
   ./run.sh
   # Keep open, or install as service:
   # sudo ./svc.sh install && sudo ./svc.sh start

## Upgrade to GitHub-hosted (when ready)
In .github/workflows/ci.yml:
Replace every: runs-on: self-hosted
With:          runs-on: ubuntu-latest
Commit and push. Done.

## The runner must be running when you push.
CI jobs queue and wait up to 1h for a runner.
If the runner is offline, jobs stay pending.

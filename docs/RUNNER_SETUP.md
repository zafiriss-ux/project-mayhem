# Self-Hosted CI Runner Setup

## Linux / macOS

1. Go to your repo on GitHub:
   Settings → Actions → Runners
   → "New self-hosted runner"

2. Select **Linux** or **macOS**.
   Copy the registration token shown.

3. In your terminal (project root):
   ```bash
   mkdir -p ~/actions-runner && cd ~/actions-runner
   # Download the runner (GitHub shows the exact URL for your OS)
   ./config.sh --url https://github.com/zafiriss-ux/project-mayhem \
               --token YOUR_TOKEN_HERE
   ```

4. Start the runner:
   ```bash
   ./run.sh
   # Keep open, or install as a systemd service:
   # sudo ./svc.sh install && sudo ./svc.sh start
   ```

---

## WSL (Windows Subsystem for Linux)

Use these steps when the runner runs inside WSL2 on a Windows host.
`systemd` must be enabled in WSL2 (requires Windows 11 build 22000+ or WSL 0.67.6+).

### Step 1 — Download and extract the runner

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o runner.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.334.0/actions-runner-linux-x64-2.334.0.tar.gz
tar xzf runner.tar.gz
```

### Step 2 — Configure the runner

Go to your repo on GitHub: Settings → Actions → Runners → "New self-hosted runner".
Select **Linux**. Copy the registration token shown, then run:

```bash
./config.sh \
  --url https://github.com/zafiriss-ux/project-mayhem \
  --token YOUR_TOKEN_HERE \
  --name "zafir-wsl-runner" \
  --labels "self-hosted,Linux,x64" \
  --work "_work" \
  --unattended
```

### Step 3 — Install as a persistent systemd service

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
# Expected: active (running)
```

The service starts automatically on WSL2 launch. To check logs: `journalctl -u actions.runner.* -f`

### Step 4 — Install project dependencies

Create the venv **inside the runner's work directory** so the `runner-health` CI job
can locate `.venv/bin/pytest` without a checkout step.

The runner checks out code to `~/actions-runner/_work/project-mayhem/project-mayhem/`.
Run the following once (or after any `requirements.txt` change):

```bash
cd ~/actions-runner/_work/project-mayhem/project-mayhem
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If the `_work` directory does not exist yet (before the first CI run), trigger a push
first to let the runner create it, then run the venv setup above.

### Notes

- All CI `run:` steps use `shell: bash` (set as workflow default in `ci.yml`).
- The `runner-health` job resolves `.venv/bin/pytest` relative to the runner's
  default work directory — **not** your local clone path.
- To stop/restart the service: `sudo ./svc.sh stop` / `sudo ./svc.sh start`
- To uninstall: `sudo ./svc.sh uninstall`

---

## Windows

Prerequisites: Git for Windows (provides bash — required by CI jobs).

1. Go to your repo on GitHub:
   Settings → Actions → Runners
   → "New self-hosted runner" → select **Windows**.
   Copy the registration token shown.

2. In PowerShell, from the `actions-runner` directory:

   ```powershell
   # ΒΗΜΑ 1 — Configure (replace YOUR_TOKEN_HERE with the token from GitHub)
   ./config.cmd --url https://github.com/zafiriss-ux/project-mayhem `
     --token YOUR_TOKEN_HERE `
     --name "zafir-windows-runner" `
     --labels "self-hosted,Windows,x64" `
     --work "_work" `
     --unattended
   ```

3. Install and start as a Windows Service (runs even when the terminal is closed):

   ```powershell
   # ΒΗΜΑ 2 — Install + start service
   .\svc.cmd install
   .\svc.cmd start
   ```

4. Verify the service is running:

   ```powershell
   # ΒΗΜΑ 3 — Confirm status
   .\svc.cmd status
   # Expected output: Running
   ```

5. Verify on GitHub:
   Settings → Actions → Runners
   → `zafir-windows-runner` should appear with status **Idle**.

### Notes

- All CI `run:` steps use `shell: bash` (set as workflow default in `ci.yml`).
  Git Bash (from Git for Windows) provides the bash interpreter.
- The `runner-health` job uses a Python cross-platform check — it resolves
  `.venv/Scripts/pytest.exe` on Windows and `.venv/bin/pytest` on Linux/macOS.
- To stop the service: `.\svc.cmd stop`
- To uninstall the service: `.\svc.cmd uninstall`

---

## Switching to GitHub-hosted runners (when ready)

In `.github/workflows/ci.yml`, replace every:
```yaml
runs-on: self-hosted
```
with:
```yaml
runs-on: ubuntu-latest
```
Commit and push. Done. No other changes needed.

## Important

The runner must be **running** when you push.
CI jobs queue and wait up to 1 hour for an available runner.
If the runner is offline, jobs remain in **Pending** state.

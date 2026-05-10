# TITAN OS — systemd Service Setup

## Install

```bash
sudo cp docs/titan.service /etc/systemd/system/titan@$USER.service
sudo systemctl daemon-reload
sudo systemctl enable titan@$USER
sudo systemctl start titan@$USER
```

## Check status

```bash
sudo systemctl status titan@$USER
journalctl -u titan@$USER -f
```

## Behaviour

- Auto-restarts after 30 s on crash.
- After 3 restarts in 200 s the unit stops to prevent restart storms.

## Diagnose a stopped unit

```bash
journalctl -u titan@$USER --since "1h ago"
```

# mcp-rpi-system

Production-ready MCP (Model Context Protocol) server for Raspberry Pi 4 system management and monitoring, built for OpenClaw AI agents.

## Features

- FastMCP server for secure MCP tool exposure
- Explicit whitelisted system commands only (no arbitrary shell execution)
- **Secure random-token confirmation flow** – restart/shutdown require a cryptographically random one-time token typed by the human user
- Raspberry Pi system operations and metrics using `psutil`
- CPU temperature support via `vcgencmd measure_temp`
- Structured JSON logging with timestamps and error traces
- Docker-ready runtime
- systemd-friendly startup pattern
- Modular architecture for future expansion

## Project Structure

```text
mcp-rpi-system/
├── src/
│   ├── server.py
│   ├── tools/
│   │   ├── system_tools.py        # request_restart / request_shutdown / confirm_action / cancel_action / get_uptime
│   │   ├── confirmation_manager.py # pending-action TTL store with random tokens
│   │   ├── monitoring_tools.py
│   │   ├── process_tools.py
│   │   ├── network_tools.py
│   │   └── future_tools.py
│   ├── utils/
│   │   └── logging_utils.py
│   └── config/
│       └── settings.py
├── tests/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## MCP Tools

### System Tools

- `request_restart()` – begin the confirmation flow for a system restart
- `request_shutdown()` – begin the confirmation flow for a system shutdown
- `confirm_action(action: str)` – supply the one-time random token to authorise execution
- `cancel_action()` – cancel any pending dangerous action
- `get_uptime()` – return uptime in seconds / minutes / hours

### Monitoring Tools

- `get_system_stats()`
  - CPU usage
  - RAM usage
  - Disk usage
  - CPU temperature (`vcgencmd`)
  - Load average

### Process Tools

- `get_top_processes(limit=5)`
- `get_process_count()`

### Network Tools

- `get_network_usage()`
- `get_ip_addresses()`

## Secure Confirmation Workflow

All power actions (restart / shutdown) follow a mandatory two-step flow.
A **cryptographically random one-time token** is generated for every request
using Python's `secrets` module.  Because the token is unpredictable and
unknown before `request_restart()` or `request_shutdown()` is called, an AI
agent cannot self-confirm in the same reasoning turn — the human must read the
token and type it back explicitly.

> **Best practice**: restart or reconnect your OpenClaw session after any MCP
> server code changes to ensure the updated tool descriptions are picked up.

### Security model

| Property | Detail |
|---|---|
| Token generation | `secrets.token_hex(3)` – 3 random bytes → 6 uppercase hex chars |
| Token format | `CONFIRM_RESTART_<hex>` / `CONFIRM_SHUTDOWN_<hex>` |
| Token lifetime | 30 seconds (monotonic clock) |
| Token matching | Exact `==` comparison – no fuzzy or prefix matching |
| Slots | One pending action at a time; a new request replaces the old one |
| Shell exposure | None – all subprocess calls use fixed command tuples |

### How it works

```
User  →  Agent:  "Restart the Raspberry Pi"
Agent →  Server: request_restart()
Server→  Agent:  {"status": "confirmation_required",
                  "message": "Reply with CONFIRM_RESTART_A8F291 within 30 seconds to confirm."}
Agent →  User:   "Restart requested. Reply with CONFIRM_RESTART_A8F291 within 30 seconds."

User  →  Agent:  "CONFIRM_RESTART_A8F291"
Agent →  Server: confirm_action(action="CONFIRM_RESTART_A8F291")
Server→  Agent:  {"status": "restarting", "ok": true, ...}
Agent →  User:   "Restarting Raspberry Pi."
```

The token `A8F291` is different on every request.  The agent cannot predict it
before calling `request_restart()`, so autonomous chaining is structurally
prevented.

### Response shapes

| Scenario | Response |
|---|---|
| Waiting for confirmation | `{"status": "confirmation_required", "message": "Reply with CONFIRM_RESTART_A8F291 within 30 seconds to confirm."}` |
| Prior pending action replaced | Above + `"warning": "A previous pending action was cancelled by this request."` |
| Restart dispatched | `{"status": "restarting", "ok": true, ...}` |
| Shutdown dispatched | `{"status": "shutting_down", "ok": true, ...}` |
| 30-second window elapsed | `{"status": "confirmation_expired"}` |
| Wrong / unexpected token | `{"status": "invalid_confirmation"}` |
| Policy flag not set | `{"status": "error", "error": "disabled_by_policy", ...}` |
| Action cancelled | `{"status": "cancelled", "ok": true, "message": "Pending restart cancelled."}` |
| Cancel with nothing pending | `{"status": "no_pending_action", "ok": true, ...}` |

### Token expiration

Tokens expire automatically after **30 seconds**.  After expiration:

- `confirm_action` returns `{"status": "confirmation_expired"}`.
- All pending state is cleared immediately.
- A new `request_restart()` / `request_shutdown()` call is required to start a
  fresh flow with a new token.

### Cancellation flow

The user can abort a pending action at any time:

```
User  →  Agent:  "Cancel the restart"
Agent →  Server: cancel_action()
Server→  Agent:  {"status": "cancelled", "ok": true, "message": "Pending restart cancelled."}
Agent →  User:   "The pending restart has been cancelled."
```

After cancellation, any subsequently submitted token is rejected.

## OpenClaw Integration

### MCP server configuration

```json
{
  "mcpServers": {
    "rpi-system": {
      "command": "python3",
      "args": ["src/server.py"]
    }
  }
}
```

> Note: the relative `src/server.py` path assumes OpenClaw starts the command from this repository root.  
> For service deployments, prefer an absolute path (for example `/opt/mcp-rpi-system/src/server.py`).

### Conversational examples

**Restart flow**

```
User:  Restart the Pi please.
Agent: Restart requested. Please reply with CONFIRM_RESTART_A8F291 within 30 seconds to confirm.
User:  CONFIRM_RESTART_A8F291
Agent: Restarting the Raspberry Pi now.
```

**Shutdown flow**

```
User:  Shut down the Raspberry Pi.
Agent: Shutdown requested. Please reply with CONFIRM_SHUTDOWN_B72C1D within 30 seconds to confirm.
User:  CONFIRM_SHUTDOWN_B72C1D
Agent: Shutting down the Raspberry Pi now.
```

**Expired confirmation**

```
User:  Restart the Pi.
Agent: Restart requested. Please reply with CONFIRM_RESTART_C3E74A within 30 seconds to confirm.
(45 seconds pass)
User:  CONFIRM_RESTART_C3E74A
Agent: The confirmation window has expired. Please request the action again if you still want to proceed.
```

**Cancellation**

```
User:  Restart the Pi.
Agent: Restart requested. Please reply with CONFIRM_RESTART_D9F012 within 30 seconds to confirm.
User:  Actually, cancel that.
Agent: [calls cancel_action] The pending restart has been cancelled.
```

**System stats (no confirmation needed)**

```
User:  What is the CPU temperature?
Agent: [calls get_system_stats] The CPU is at 52.3 °C, running at 18% load.
```

## Security Notes

- No arbitrary shell execution is implemented.
- All subprocess usage is fixed-command and whitelisted (`sudo reboot`, `sudo shutdown now`).
- Confirmation tokens are generated with `secrets.token_hex` – cryptographically random and unique per request.
- An AI agent cannot self-confirm a power action because the token is unknown before `request_restart()` / `request_shutdown()` is called.
- Power actions require both an environment-flag (`MCP_ALLOW_POWER_ACTIONS=true`) **and** explicit user confirmation within 30 seconds.
- Tokens are validated with an exact string comparison; fuzzy or prefix matching is never used.
- The expected token is never written to logs to prevent exposure in log aggregation systems.
- User input validation is applied for tool parameters (for example, process list limits).
- Tool responses are JSON-compatible dictionaries with explicit success/error structure.

## Sudoers Setup

To allow the server process to execute reboot and shutdown without a password prompt, add an entry to `/etc/sudoers` using `visudo`:

```
# Allow the mcp-rpi-system service user to reboot and shut down without a password.
# Replace 'prajwalnh' with the actual user account running the MCP server.
prajwalnh ALL=(ALL) NOPASSWD: /sbin/reboot
prajwalnh ALL=(ALL) NOPASSWD: /sbin/shutdown
```

> **Important**: always edit `/etc/sudoers` with `sudo visudo` to prevent syntax errors that can lock you out.  
> Scope the rule to the exact binary paths shown above – do **not** grant blanket `NOPASSWD: ALL`.

## Requirements

- Python 3.11+
- Raspberry Pi OS 64-bit Bookworm (target environment)
- `vcgencmd` available on Raspberry Pi for temperature metrics

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run from repository root:

```bash
python3 src/server.py
```

### Environment Variables

Copy and edit:

```bash
cp .env.example .env
```

- `MCP_SERVER_NAME` (default: `mcp-rpi-system`)
- `MCP_LOG_LEVEL` (default: `INFO`)
- `MCP_ALLOW_POWER_ACTIONS` (default: `false`) – must be `true` to enable restart/shutdown

## Docker

Build and run:

```bash
docker compose up --build
```

Or plain Docker:

```bash
docker build -t mcp-rpi-system .
docker run --rm -it mcp-rpi-system
```

## systemd Setup

Example unit file (`/etc/systemd/system/mcp-rpi-system.service`):

```ini
[Unit]
Description=MCP Raspberry Pi System Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/mcp-rpi-system
EnvironmentFile=/opt/mcp-rpi-system/.env
ExecStart=/usr/bin/python3 /opt/mcp-rpi-system/src/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mcp-rpi-system
```

## Development

Run focused tests:

```bash
python3 -m unittest discover -s tests -q
```

## Future Tool TODOs

- GPIO tools
- Docker monitoring tools
- Home Assistant integration tools
- Camera integration tools
- Audio control tools

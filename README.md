# mcp-rpi-system

Production-ready MCP (Model Context Protocol) server for Raspberry Pi 4 system management and monitoring, built for OpenClaw AI agents.

## Features

- FastMCP server for secure MCP tool exposure
- Explicit whitelisted system commands only (no arbitrary shell execution)
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
│   │   ├── system_tools.py
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

- `reboot_pi()`
- `shutdown_pi()`
- `get_uptime()`

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

## Security Notes

- No arbitrary shell execution is implemented.
- All subprocess usage is fixed-command and whitelisted.
- Power actions are disabled by default (`MCP_ALLOW_POWER_ACTIONS=false`).
- User input validation is applied for tool parameters (for example, process list limits).
- Tool responses are JSON-compatible dictionaries with explicit success/error structure.

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
- `MCP_ALLOW_POWER_ACTIONS` (default: `false`)

## OpenClaw Integration Example

Use this MCP configuration:

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

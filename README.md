# mcp-feedback-web

A web-based Interactive Feedback server for MCP (Model Context Protocol), designed for headless Linux servers. Replaces the desktop GUI (PySide6) approach with a browser-based interface that supports full CJK input.

## Why This Project?

The original [interactive-feedback-mcp](https://github.com/noopstudios/interactive-feedback-mcp) uses PySide6 (Qt) to display a desktop feedback dialog. This doesn't work on headless Linux servers, and even with X11 forwarding, the Windows input method (IME) cannot be used in the forwarded window.

**mcp-feedback-web** solves this by serving the feedback UI as a web page. The browser on your local machine handles everything — including Chinese/Japanese/Korean input — natively.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    Linux Server (headless)                     │
│                                                               │
│  ┌──────────────┐    HTTP (127.0.0.1)   ┌──────────────────┐  │
│  │  server.py   │ ───────────────────>  │  web_feedback.py │  │
│  │  (MCP Server)│                       │  (Web Server)    │  │
│  │  stdio       │ <───────────────────  │  port 8765       │  │
│  └──────┬───────┘    feedback result    └────────┬─────────┘  │
│         │                                        │            │
│         │ stdin/stdout                           │ HTTP       │
└─────────┼────────────────────────────────────────┼────────────┘
          │                                        │
          │ SSH tunnel                             │ LAN
          │                                        │
┌─────────┼────────────────────────────────────────┼────────────┐
│         ▼        Local Machine (Windows/Mac)     ▼            │
│  ┌──────────────┐                   ┌────────────────────┐    │
│  │   Cursor IDE │                   │   Browser          │    │
│  │              │                   │   http://IP:8765   │    │
│  └──────────────┘                   │   Full IME support │    │
│                                     └────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
```

### How It Works

1. **Cursor IDE** invokes `server.py` on the Linux server via SSH (MCP stdio transport)
2. When AI requests user feedback, `server.py` launches `web_feedback.py` in client mode
3. The client sends a feedback request to the **Web Server** (port 8765) via HTTP API
4. The **browser** receives the request via long polling and displays a feedback form
5. User types feedback in the browser (with full native IME support) and submits
6. The Web Server returns the result to the client, which writes it to a temp file
7. `server.py` reads the result and returns it to Cursor

## Quick Start

### Docker (Recommended)

```bash
# Clone or copy the project files
cd mcp-feedback-web

# Build and start
docker compose up -d

# Verify
docker compose ps
# STATUS should show "healthy"
```

### Manual Installation

```bash
# Requires Python 3.11+
python3 -m venv .venv
.venv/bin/pip install fastmcp pydantic

# Start the web server
.venv/bin/python web_feedback.py --server
```

### systemd Service

Create `/etc/systemd/system/mcp-web-feedback.service`:

```ini
[Unit]
Description=MCP Web Feedback Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/mcp-feedback-web
ExecStart=/path/to/mcp-feedback-web/.venv/bin/python web_feedback.py --server
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now mcp-web-feedback
```

## Usage

### 1. Start the Web Server

Use any of the deployment methods above. Verify it's running:

```bash
curl http://127.0.0.1:8765/api/status
# {"status": "running"}
```

### 2. Open the Browser

Navigate to `http://<server-ip>:8765` on your local machine. **Keep this tab open** — it will automatically receive new feedback requests without refreshing.

### 3. Configure Cursor MCP

Add to your Cursor MCP configuration (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "interactive-feedback": {
      "command": "ssh",
      "args": [
        "your-server",
        "cd /path/to/mcp-feedback-web && .venv/bin/python server.py"
      ]
    }
  }
}
```

For Docker deployments, run `server.py` on the host machine (it connects to the container via `127.0.0.1:8765`).

### 4. Features

- Tab title flashes when a new request arrives
- Browser notification support (requires permission)
- **Enter** to submit, **Shift+Enter** for newline
- "No feedback" button for quick empty submission
- Page automatically returns to waiting state after submission

## `web_feedback.py` Dual Mode

```bash
# Server mode: start the persistent web server
python web_feedback.py --server

# Client mode: send a request and wait for response
python web_feedback.py \
  --project-directory /path/to/project \
  --prompt "Please provide feedback" \
  --output-file /tmp/result.json
```

In client mode, if no server is detected, it automatically starts one as a daemon.

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Feedback page (HTML) |
| GET | `/api/status` | Health check |
| GET | `/api/poll` | Long poll for new requests (30s timeout) |
| POST | `/api/request` | Create a new feedback request |
| POST | `/api/submit` | Submit feedback |
| POST | `/api/get_response` | Block until feedback is submitted (300s timeout) |

### Request Format

**Create request** `POST /api/request`:
```json
{
  "project_directory": "/path/to/project",
  "prompt": "Summary from AI"
}
```

**Submit feedback** `POST /api/submit`:
```json
{
  "interactive_feedback": "User's feedback text",
  "logs": ""
}
```

## File Structure

| File | Purpose |
|------|---------|
| `server.py` | MCP server, communicates with Cursor via stdio |
| `web_feedback.py` | Web feedback server + client (dual mode) |
| `feedback_ui.py` | Original PySide6 desktop UI (kept for reference) |
| `Dockerfile` | Docker image build file |
| `docker-compose.yml` | Docker Compose configuration |
| `.dockerignore` | Docker build ignore rules |

## Networking

- Port **8765** on the Linux server must be accessible from the local machine
- Firewall rules:
  ```bash
  # Linux (ufw)
  ufw allow 8765/tcp
  ```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Browser can't load page | Check firewall rules for port 8765 |
| Client connection timeout | Use `127.0.0.1` instead of `localhost` (IPv6 issue) |
| Docker health check fails | Run `docker logs mcp-web-feedback` |
| Feedback page unresponsive | Refresh the browser tab or restart the service |

## Credits

Based on [interactive-feedback-mcp](https://github.com/noopstudios/interactive-feedback-mcp) by Fábio Ferreira. Modified to use a web-based UI instead of PySide6 desktop GUI.

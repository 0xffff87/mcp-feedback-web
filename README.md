# mcp-feedback-nodesktop

A web-based Interactive Feedback server for MCP (Model Context Protocol), designed for headless Linux servers. Replaces the desktop GUI (PySide6) approach with a browser-based interface that supports full CJK input and bilingual UI (English/Chinese).

## Why This Project?

The original [interactive-feedback-mcp](https://github.com/noopstudios/interactive-feedback-mcp) uses PySide6 (Qt) to display a desktop feedback dialog. This doesn't work on headless Linux servers, and even with X11 forwarding, the Windows input method (IME) cannot be used in the forwarded window.

**mcp-feedback-nodesktop** solves this by serving the feedback UI as a web page. The browser on your local machine handles everything — including Chinese/Japanese/Korean input — natively.

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
docker compose up -d
docker compose ps   # STATUS should show "healthy"
```

The container uses `restart: unless-stopped`, so it will automatically start after system reboot (as long as Docker is enabled).

### Manual Installation

```bash
python3 -m venv .venv
.venv/bin/pip install fastmcp pydantic
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
WorkingDirectory=/path/to/mcp-feedback-nodesktop
ExecStart=/path/to/mcp-feedback-nodesktop/.venv/bin/python web_feedback.py --server
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

Deploy using any method above. Verify:

```bash
curl http://127.0.0.1:8765/api/status
# {"status": "running"}
```

### 2. Open the Browser (Important!)

Navigate to `http://<server-ip>:8765` on your local machine.

**You must keep this browser tab open at all times.** The page will automatically receive new feedback requests via long polling — no manual refresh needed. When a new request arrives, the tab title will flash and a browser notification will appear (if permitted).

> **Note:** The web server cannot automatically open a browser on your local machine. You need to open the URL manually once. After that, just keep the tab open.

### 3. Configure Cursor MCP

Add to your Cursor MCP configuration (`.cursor/mcp.json`).

**For Docker deployment on the same machine:**

```json
{
  "mcpServers": {
    "interactive-feedback": {
      "command": "docker",
      "args": ["exec", "-i", "mcp-web-feedback", "python", "server.py"],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

**For remote access via SSH (e.g., from a Windows machine):**

```json
{
  "mcpServers": {
    "interactive-feedback": {
      "command": "ssh",
      "args": [
        "your-server",
        "docker exec -i mcp-web-feedback python server.py"
      ],
      "timeout": 600,
      "autoApprove": ["interactive_feedback"]
    }
  }
}
```

> **Tip:** The `-i` flag in `docker exec -i` is required to keep stdin open for MCP stdio transport.

### 4. Features

- Bilingual UI (English/Chinese) with auto language detection and manual switch
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

## File Structure

| File | Purpose |
|------|---------|
| `server.py` | MCP server, communicates with Cursor via stdio |
| `web_feedback.py` | Web feedback server + client (dual mode) |
| `Dockerfile` | Docker image build file |
| `docker-compose.yml` | Docker Compose configuration |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Browser can't load page | Check firewall rules for port 8765 |
| Client connection timeout | Use `127.0.0.1` instead of `localhost` (IPv6 issue) |
| Docker health check fails | Run `docker logs mcp-web-feedback` |
| Feedback page unresponsive | Refresh the browser tab or restart the service |

## Credits

Based on [interactive-feedback-mcp](https://github.com/noopstudios/interactive-feedback-mcp) by Fábio Ferreira (MIT License). Modified to use a web-based UI instead of PySide6 desktop GUI.

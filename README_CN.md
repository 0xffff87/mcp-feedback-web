# mcp-feedback-web

基于 Web 的 MCP（Model Context Protocol）交互式反馈服务器，专为无桌面环境的 Linux 服务器设计。使用浏览器界面替代桌面 GUI（PySide6），完美支持中文输入。

## 为什么需要这个项目？

原版 [interactive-feedback-mcp](https://github.com/noopstudios/interactive-feedback-mcp) 使用 PySide6（Qt）弹出桌面反馈窗口。但在无桌面的 Linux 服务器上无法使用，即使通过 X11 转发显示窗口，也无法使用 Windows 端的中文输入法。

**mcp-feedback-web** 将反馈界面改为 Web 页面。浏览器原生支持中日韩文输入，无需任何额外配置。

## 架构原理

```
┌───────────────────────────────────────────────────────────────┐
│                    Linux 服务器（无桌面）                       │
│                                                               │
│  ┌──────────────┐    HTTP (127.0.0.1)   ┌──────────────────┐  │
│  │  server.py   │ ───────────────────>  │  web_feedback.py │  │
│  │  MCP 服务器   │                       │  Web 反馈服务器   │  │
│  │  stdio 传输   │ <───────────────────  │  端口 8765       │  │
│  └──────┬───────┘     反馈结果           └────────┬─────────┘  │
│         │                                        │            │
│         │ stdin/stdout                           │ HTTP       │
└─────────┼────────────────────────────────────────┼────────────┘
          │                                        │
          │ SSH 隧道                               │ 局域网
          │                                        │
┌─────────┼────────────────────────────────────────┼────────────┐
│         ▼        本地机器（Windows/Mac）          ▼            │
│  ┌──────────────┐                   ┌────────────────────┐    │
│  │   Cursor IDE │                   │   浏览器            │    │
│  │              │                   │   http://IP:8765   │    │
│  └──────────────┘                   │   中文输入正常       │    │
│                                     └────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
```

### 工作流程

1. **Cursor** 通过 SSH 调用 Linux 上的 `server.py`（MCP 服务器，stdio 传输协议）
2. 当 AI 需要用户反馈时，`server.py` 启动 `web_feedback.py` 客户端模式
3. 客户端通过 HTTP API 向 **Web 反馈服务器**（8765 端口）推送反馈请求
4. **浏览器**通过长轮询（Long Polling）实时接收新请求，显示反馈表单
5. 用户在浏览器中输入反馈并提交（支持完整的中文输入法）
6. Web 服务器将反馈结果返回给客户端，客户端写入临时文件
7. `server.py` 读取结果并返回给 Cursor

## 快速部署

### 方式一：Docker 部署（推荐）

```bash
# 克隆或复制项目文件
cd mcp-feedback-web

# 构建并启动
docker compose up -d

# 查看状态
docker compose ps
# STATUS 应显示 "healthy"

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

容器使用 `restart: unless-stopped` 策略，Docker 服务启动时自动恢复容器。

### 方式二：手动部署

```bash
# 前提条件：Python 3.11+
python3 -m venv .venv
.venv/bin/pip install fastmcp pydantic

# 启动 Web 反馈服务器
.venv/bin/python web_feedback.py --server
```

### 方式三：systemd 服务（手动部署 + 开机自启）

创建 `/etc/systemd/system/mcp-web-feedback.service`：

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

启用并启动：

```bash
systemctl daemon-reload
systemctl enable --now mcp-web-feedback
```

## 使用方法

### 1. 确保 Web 反馈服务器在运行

通过上述任意方式部署后，确认服务正常：

```bash
curl http://127.0.0.1:8765/api/status
# 应返回: {"status": "running"}
```

### 2. 在本地浏览器中打开反馈页面

```
http://<Linux服务器IP>:8765
```

**保持此标签页打开**，页面会自动等待新的反馈请求，无需手动刷新。

### 3. 配置 Cursor MCP

在 Cursor 的 MCP 配置中添加（`.cursor/mcp.json`）：

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

如果使用 Docker 部署，`server.py` 需要在宿主机上运行（它通过 `127.0.0.1:8765` 与容器中的 Web 服务器通信）。

### 4. 使用体验

- 有新请求时，浏览器标签页标题闪烁提醒
- 支持浏览器通知（首次使用需授权）
- **Enter** 提交反馈，**Shift+Enter** 换行
- 点击"无反馈"按钮可快速提交空反馈
- 提交后页面自动回到等待状态，复用同一标签页

## web_feedback.py 双模式

`web_feedback.py` 同时充当服务器和客户端：

```bash
# 服务器模式：启动持久化 Web 反馈服务器
python web_feedback.py --server

# 客户端模式：发送反馈请求并等待响应
python web_feedback.py \
  --project-directory /path/to/project \
  --prompt "请输入反馈" \
  --output-file /tmp/result.json
```

客户端模式下，如果检测到服务器未运行，会自动启动一个守护进程。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 反馈页面（HTML） |
| GET | `/api/status` | 服务器状态检查 |
| GET | `/api/poll` | 长轮询等待新请求（30s 超时） |
| POST | `/api/request` | 创建新的反馈请求 |
| POST | `/api/submit` | 提交反馈结果 |
| POST | `/api/get_response` | 阻塞等待反馈结果（300s 超时） |

### 请求/响应格式

**创建请求** `POST /api/request`：
```json
{
  "project_directory": "/path/to/project",
  "prompt": "AI 的摘要描述"
}
```

**提交反馈** `POST /api/submit`：
```json
{
  "interactive_feedback": "用户的反馈内容",
  "logs": ""
}
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `server.py` | MCP 服务器主程序，通过 stdio 与 Cursor 通信 |
| `web_feedback.py` | Web 反馈服务器 + 客户端（双模式运行） |
| `feedback_ui.py` | 原版 PySide6 桌面 UI（保留供参考） |
| `Dockerfile` | Docker 镜像构建文件 |
| `docker-compose.yml` | Docker Compose 编排文件 |
| `.dockerignore` | Docker 构建忽略规则 |

## 网络要求

- Linux 服务器的 **8765 端口**需要对本地机器可访问
- 防火墙配置：
  ```bash
  # Linux (ufw)
  ufw allow 8765/tcp
  ```

## 故障排查

| 问题 | 解决方法 |
|------|----------|
| 浏览器无法打开页面 | 检查防火墙是否放行 8765 端口 |
| 客户端连接超时 | 确认使用 `127.0.0.1` 而非 `localhost`（避免 IPv6 问题） |
| Docker 容器健康检查失败 | 运行 `docker logs mcp-web-feedback` 查看日志 |
| 反馈页面无响应 | 刷新浏览器页面，或重启服务 |
| systemd 服务未启动 | `journalctl -u mcp-web-feedback -n 50` 查看日志 |

## 致谢

基于 [interactive-feedback-mcp](https://github.com/noopstudios/interactive-feedback-mcp) 项目（Fábio Ferreira 开发），将 PySide6 桌面 GUI 改为 Web 界面方案。

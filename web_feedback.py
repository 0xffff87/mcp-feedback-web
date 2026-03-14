#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
import threading
import subprocess
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

PORT = 8765
HOST = "0.0.0.0"

current_request = None
current_response = None
request_event = threading.Event()
response_event = threading.Event()
request_lock = threading.Lock()


class FeedbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global current_request
        if self.path == "/":
            self._send_html(get_html_page())
        elif self.path == "/api/status":
            self._send_json({"status": "running"})
        elif self.path == "/api/poll":
            request_event.wait(timeout=30)
            with request_lock:
                if current_request:
                    self._send_json({"has_request": True, "request": current_request})
                else:
                    self._send_json({"has_request": False})
        else:
            self.send_error(404)

    def do_POST(self):
        global current_request, current_response
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.path == "/api/request":
            data = json.loads(body)
            with request_lock:
                current_request = data
                current_response = None
                response_event.clear()
                request_event.set()
            self._send_json({"status": "ok"})

        elif self.path == "/api/submit":
            data = json.loads(body)
            with request_lock:
                current_response = data
                current_request = None
                request_event.clear()
                response_event.set()
            self._send_json({"status": "ok"})

        elif self.path == "/api/get_response":
            response_event.wait(timeout=300)
            with request_lock:
                if current_response:
                    self._send_json({"has_response": True, "response": current_response})
                else:
                    self._send_json({"has_response": False})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def get_html_page():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MCP Feedback</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#1e1e2e;color:#cdd6f4;min-height:100vh;display:flex;align-items:center;justify-content:center}
.container{width:100%;max-width:620px;padding:20px}
.card{background:#313244;border-radius:12px;padding:28px;box-shadow:0 4px 24px rgba(0,0,0,.3)}
.waiting{text-align:center;padding:60px 20px;color:#a6adc8}
.spinner{width:40px;height:40px;border:3px solid #45475a;border-top-color:#89b4fa;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 20px}
@keyframes spin{to{transform:rotate(360deg)}}
.label{font-size:13px;color:#a6adc8;margin-bottom:6px;font-weight:500}
.summary{background:#45475a;border-radius:8px;padding:14px 16px;margin-bottom:20px;font-size:14px;line-height:1.7;white-space:pre-wrap;word-break:break-word}
textarea{width:100%;min-height:130px;background:#45475a;border:1px solid #585b70;border-radius:8px;padding:12px;color:#cdd6f4;font-size:14px;font-family:inherit;resize:vertical;outline:none;transition:border-color .2s}
textarea:focus{border-color:#89b4fa}
.btn-row{display:flex;gap:10px;margin-top:16px}
button{flex:1;padding:11px 20px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;transition:all .2s}
.btn-submit{background:#89b4fa;color:#1e1e2e}
.btn-submit:hover{background:#74c7ec}
.btn-submit:disabled{opacity:.5;cursor:not-allowed}
.btn-empty{background:#45475a;color:#cdd6f4}
.btn-empty:hover{background:#585b70}
.toast{position:fixed;top:20px;right:20px;background:#a6e3a1;color:#1e1e2e;padding:12px 24px;border-radius:8px;font-weight:600;z-index:100;opacity:0;transform:translateY(-10px);transition:all .3s;pointer-events:none}
.toast.show{opacity:1;transform:translateY(0)}
.project{font-size:12px;color:#6c7086;margin-bottom:16px;padding:6px 10px;background:#1e1e2e;border-radius:6px;font-family:monospace}
</style>
</head>
<body>
<div class="container">
<div class="card">
  <div id="waiting" class="waiting">
    <div class="spinner"></div>
    <p>等待反馈请求...</p>
    <p style="margin-top:8px;font-size:12px;color:#585b70">保持此页面打开，新请求会自动出现</p>
  </div>
  <div id="form" style="display:none">
    <div class="project" id="project"></div>
    <div class="label">AI 摘要：</div>
    <div class="summary" id="summary"></div>
    <div class="label">你的反馈：</div>
    <textarea id="feedback" placeholder="输入反馈...按 Enter 提交，Shift+Enter 换行"></textarea>
    <div class="btn-row">
      <button class="btn-empty" onclick="submitEmpty()">无反馈</button>
      <button class="btn-submit" id="submitBtn" onclick="submitFeedback()">提交</button>
    </div>
  </div>
</div>
</div>
<div class="toast" id="toast">已提交！</div>
<script>
let polling=false,titleInterval=null,origTitle=document.title;
function flashTitle(m){
  let on=true;
  if(titleInterval)clearInterval(titleInterval);
  titleInterval=setInterval(function(){document.title=on?m:origTitle;on=!on},800);
}
function stopFlash(){if(titleInterval)clearInterval(titleInterval);document.title=origTitle}
async function poll(){
  if(polling)return;polling=true;
  while(true){
    try{
      const r=await fetch("/api/poll");
      const d=await r.json();
      if(d.has_request){showReq(d.request);polling=false;return}
    }catch(e){await new Promise(function(r){setTimeout(r,2000)})}
  }
}
function showReq(req){
  document.getElementById("waiting").style.display="none";
  document.getElementById("form").style.display="block";
  document.getElementById("project").textContent=req.project_directory||"";
  document.getElementById("summary").textContent=req.prompt||req.summary||"";
  document.getElementById("feedback").value="";
  document.getElementById("submitBtn").disabled=false;
  setTimeout(function(){document.getElementById("feedback").focus()},100);
  flashTitle("New Feedback Request");
  if(Notification.permission==="granted"){new Notification("MCP Feedback",{body:req.prompt||""})}
  try{window.focus()}catch(e){}
}
async function doSubmit(text){
  document.getElementById("submitBtn").disabled=true;
  try{
    await fetch("/api/submit",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({interactive_feedback:text,logs:""})});
    stopFlash();showToast();
    document.getElementById("form").style.display="none";
    document.getElementById("waiting").style.display="block";
    poll();
  }catch(e){document.getElementById("submitBtn").disabled=false;alert("error: "+e.message)}
}
function submitFeedback(){doSubmit(document.getElementById("feedback").value)}
function submitEmpty(){doSubmit("")}
function showToast(){var t=document.getElementById("toast");t.classList.add("show");setTimeout(function(){t.classList.remove("show")},2000)}
document.getElementById("feedback").addEventListener("keydown",function(e){
  if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();submitFeedback()}
});
if("Notification" in window&&Notification.permission==="default"){Notification.requestPermission()}
poll();
</script>
</body>
</html>"""


def run_server():
    server = ThreadingHTTPServer((HOST, PORT), FeedbackHandler)
    print(f"Web feedback server running on http://{HOST}:{PORT}")
    server.serve_forever()


def is_server_running():
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/status")
        resp = urllib.request.urlopen(req, timeout=2)
        data = json.loads(resp.read())
        return data.get("status") == "running"
    except Exception:
        return False


def start_server_daemon():
    subprocess.Popen(
        [sys.executable, __file__, "--server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    for _ in range(20):
        time.sleep(0.5)
        if is_server_running():
            return True
    return False


def send_request(project_directory, prompt, output_file):
    if not is_server_running():
        if not start_server_daemon():
            raise Exception("Failed to start web feedback server")

    data = json.dumps({"project_directory": project_directory, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/request",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=5)

    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/get_response",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=310)
    result = json.loads(resp.read())

    if result.get("has_response"):
        with open(output_file, "w") as f:
            json.dump(result["response"], f, ensure_ascii=False)
    else:
        raise Exception("No response received (timeout)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--project-directory", type=str)
    parser.add_argument("--prompt", type=str)
    parser.add_argument("--output-file", type=str)
    args = parser.parse_args()

    if args.server:
        run_server()
    else:
        if not all([args.project_directory, args.prompt, args.output_file]):
            parser.error("Need --project-directory, --prompt, --output-file")
        send_request(args.project_directory, args.prompt, args.output_file)


if __name__ == "__main__":
    main()

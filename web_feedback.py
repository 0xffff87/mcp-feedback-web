#!/usr/bin/env python3
import os
import sys
import json
import time
import argparse
import threading
import subprocess
import urllib.error
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

PORT = 8765
HOST = "0.0.0.0"

current_request = None
current_response = None
current_request_id = 0
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
        global current_request, current_response, current_request_id
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            content_length = 0
        if content_length < 0 or content_length > 1024 * 1024:
            self.send_error(413, "Payload too large")
            return
        body = self.rfile.read(content_length)

        if self.path == "/api/request":
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                self._send_json({"error": "Invalid JSON"}, status=400)
                return
            with request_lock:
                current_request_id += 1
                current_request = data
                current_response = None
                response_event.clear()
                request_event.set()
            self._send_json({"status": "ok"})

        elif self.path == "/api/submit":
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                self._send_json({"error": "Invalid JSON"}, status=400)
                return
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
                    resp = current_response
                    current_response = None
                    self._send_json({"has_response": True, "response": resp})
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
<html>
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
.lang-switch{position:fixed;top:16px;right:16px;background:#45475a;border:none;color:#a6adc8;padding:6px 12px;border-radius:6px;font-size:12px;cursor:pointer}
.lang-switch:hover{background:#585b70;color:#cdd6f4}
</style>
</head>
<body>
<button class="lang-switch" id="langBtn" onclick="toggleLang()">EN</button>
<div class="container">
<div class="card">
  <div id="waiting" class="waiting">
    <div class="spinner"></div>
    <p id="waitText"></p>
    <p id="waitHint" style="margin-top:8px;font-size:12px;color:#585b70"></p>
  </div>
  <div id="form" style="display:none">
    <div class="project" id="project"></div>
    <div class="label" id="summaryLabel"></div>
    <div class="summary" id="summary"></div>
    <div class="label" id="feedbackLabel"></div>
    <textarea id="feedback"></textarea>
    <div class="btn-row">
      <button class="btn-empty" id="emptyBtn" onclick="submitEmpty()"></button>
      <button class="btn-submit" id="submitBtn" onclick="submitFeedback()"></button>
    </div>
  </div>
</div>
</div>
<div class="toast" id="toast"></div>
<script>
var L={
  zh:{wait:"Waiting for feedback request...",hint:"Keep this page open, new requests appear automatically",
      summary:"AI Summary:",feedback:"Your Feedback:",placeholder:"Type feedback... Enter to submit, Shift+Enter for newline",
      empty:"No Feedback",submit:"Submit",submitted:"Submitted!",
      wait_zh:"\u7b49\u5f85\u53cd\u9988\u8bf7\u6c42...",hint_zh:"\u4fdd\u6301\u6b64\u9875\u9762\u6253\u5f00\uff0c\u65b0\u8bf7\u6c42\u4f1a\u81ea\u52a8\u51fa\u73b0",
      summary_zh:"AI \u6458\u8981\uff1a",feedback_zh:"\u4f60\u7684\u53cd\u9988\uff1a",placeholder_zh:"\u8f93\u5165\u53cd\u9988...\u6309 Enter \u63d0\u4ea4\uff0cShift+Enter \u6362\u884c",
      empty_zh:"\u65e0\u53cd\u9988",submit_zh:"\u63d0\u4ea4",submitted_zh:"\u5df2\u63d0\u4ea4\uff01"}
};
var lang=navigator.language.startsWith("zh")?"zh":"en";
function t(key){
  if(lang==="zh"){var zhKey=key+"_zh";return L.zh[zhKey]||L.zh[key]}
  return L.zh[key];
}
function applyLang(){
  document.getElementById("waitText").textContent=t("wait");
  document.getElementById("waitHint").textContent=t("hint");
  document.getElementById("summaryLabel").textContent=t("summary");
  document.getElementById("feedbackLabel").textContent=t("feedback");
  document.getElementById("feedback").placeholder=t("placeholder");
  document.getElementById("emptyBtn").textContent=t("empty");
  document.getElementById("submitBtn").textContent=t("submit");
  document.getElementById("langBtn").textContent=lang==="zh"?"EN":"\u4e2d\u6587";
}
function toggleLang(){lang=lang==="zh"?"en":"zh";applyLang()}
applyLang();

var polling=false,titleInterval=null,origTitle=document.title;
function flashTitle(m){
  var on=true;
  if(titleInterval)clearInterval(titleInterval);
  titleInterval=setInterval(function(){document.title=on?m:origTitle;on=!on},800);
}
function stopFlash(){if(titleInterval)clearInterval(titleInterval);document.title=origTitle}
async function poll(){
  if(polling)return;polling=true;
  while(true){
    try{
      var r=await fetch("/api/poll");
      var d=await r.json();
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
function showToast(){var el=document.getElementById("toast");el.textContent=t("submitted");el.classList.add("show");setTimeout(function(){el.classList.remove("show")},2000)}
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
    script_path = os.path.abspath(__file__)
    kwargs = dict(
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    if sys.platform == "win32":
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, script_path, "--server"], **kwargs)
    for _ in range(20):
        time.sleep(0.5)
        if is_server_running():
            return True
    return False


def send_request(project_directory, prompt, output_file):
    if not is_server_running():
        print(f"Web feedback server not running, starting daemon...", file=sys.stderr)
        if not start_server_daemon():
            raise Exception(
                f"Failed to start web feedback server on port {PORT}. "
                "Please start it manually: python web_feedback.py --server"
            )
        print(f"Web feedback server started on port {PORT}", file=sys.stderr)

    data = json.dumps({"project_directory": project_directory, "prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/request",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        raise Exception(f"Failed to send request to web feedback server: {e}")

    print(
        f"Feedback request sent. Waiting for user response at http://127.0.0.1:{PORT} ...",
        file=sys.stderr,
    )

    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/get_response",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=310) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise Exception(f"Failed to get response from web feedback server: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid JSON response from server: {e}")

    if result.get("has_response"):
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result["response"], f, ensure_ascii=False)
    else:
        raise Exception("No response received (timeout after 300s)")


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

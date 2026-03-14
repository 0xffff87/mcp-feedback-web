FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastmcp pydantic

COPY server.py web_feedback.py ./

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/status', timeout=2)" || exit 1

CMD ["python", "web_feedback.py", "--server"]

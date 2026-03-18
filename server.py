# Interactive Feedback MCP
# Developed by Fábio Ferreira (https://x.com/fabiomlferreira)
# Inspired by/related to dotcursorrules.com (https://dotcursorrules.com/)
import os
import sys
import json
import tempfile
import subprocess

from typing import Annotated, Dict

from fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("Interactive Feedback MCP")

def launch_feedback_ui(project_directory: str, summary: str) -> dict[str, str]:
    output_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            output_file = tmp.name

        script_dir = os.path.dirname(os.path.abspath(__file__))
        feedback_ui_path = os.path.join(script_dir, "web_feedback.py")

        args = [
            sys.executable,
            "-u",
            feedback_ui_path,
            "--project-directory", project_directory,
            "--prompt", summary,
            "--output-file", output_file
        ]
        result = subprocess.run(
            args,
            check=False,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=310,
        )
        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            raise Exception(f"Failed to launch feedback UI (exit={result.returncode}): {err_msg}")

        if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
            raise Exception("Feedback UI exited without writing output")

        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except subprocess.TimeoutExpired:
        raise Exception("Feedback UI timed out (310s)")
    finally:
        if output_file:
            try:
                os.unlink(output_file)
            except OSError:
                pass

def first_line(text: str) -> str:
    return text.split("\n")[0].strip()

@mcp.tool()
def interactive_feedback(
    project_directory: Annotated[str, Field(description="Full path to the project directory")],
    summary: Annotated[str, Field(description="Short, one-line summary of the changes")],
) -> Dict[str, str]:
    """Request interactive feedback for a given project directory and summary"""
    return launch_feedback_ui(first_line(project_directory), first_line(summary))

if __name__ == "__main__":
    mcp.run(transport="stdio", log_level="ERROR")

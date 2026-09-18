#!/usr/bin/env python3
"""Lightweight local web server providing a graphical UI and API for the ReAct travel agent."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv

from engine import run_react

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"
PORT = 8000


class AgentHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            index_path = WEB_DIR / "index.html"
            if index_path.is_file():
                content = index_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
        elif self.path == "/travel_profile.json":
            profile_path = PROJECT_ROOT / "travel_profile.json"
            if profile_path.is_file():
                content = profile_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        self.send_error(404, "File Not Found")

    def do_POST(self) -> None:
        if self.path == "/api/run":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body) if body else {}
                goal = data.get("goal") or (
                    "Read travel_profile.json, research realistic 2026 prices with Tavily, "
                    "add costs with calculate, and produce an itinerary whose Total is <= $800."
                )

                steps_log: list[dict] = []

                def step_callback(step: int, raw: str, action: str | None, action_input: str | None, obs: str | None) -> None:
                    thought = None
                    if raw:
                        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
                        thought_lines = [l for l in lines if not l.lower().startswith("action")]
                        thought = "\n".join(thought_lines) if thought_lines else raw.strip()

                    steps_log.append({
                        "step": step,
                        "thought": thought,
                        "action": action,
                        "action_input": action_input,
                        "observation": obs,
                    })

                final_answer = run_react(goal, max_steps=15, on_step=step_callback)

                response_payload = json.dumps({
                    "status": "success",
                    "steps": steps_log,
                    "final_answer": final_answer,
                }).encode("utf-8")

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(response_payload)))
                self.end_headers()
                self.wfile.write(response_payload)
            except Exception as exc:
                err_payload = json.dumps({"status": "error", "error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_payload)))
                self.end_headers()
                self.wfile.write(err_payload)
            return

        self.send_error(404, "Endpoint Not Found")

    def log_message(self, format: str, *args) -> None:
        # Concise logging to stdout
        sys.stdout.write(f"[Server] {self.address_string()} - {format % args}\n")


def run_server(port: int = PORT) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    server_address = ("", port)
    httpd = HTTPServer(server_address, AgentHandler)
    print("==================================================")
    print(f" 🚀 ReAct Travel Agent Web UI running at:")
    print(f"    http://localhost:{port}")
    print("==================================================")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()

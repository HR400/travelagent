#!/usr/bin/env python3
"""Lightweight local web server providing a graphical UI and API for the ReAct travel agent."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

from engine import run_react

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"
PROFILE_PATH = PROJECT_ROOT / "travel_profile.json"
PORT = 8000


def get_profile() -> dict:
    """Read travel_profile.json or return default profile."""
    if PROFILE_PATH.is_file():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            sys.stderr.write(f"Error reading profile: {exc}\n")
    return {
        "traveler": {
            "name": "Alex Rivera",
            "origin": "San Francisco, CA",
            "party_size": 1,
        },
        "trip": {
            "destination": "Lisbon, Portugal",
            "start_date": "2026-10-12",
            "end_date": "2026-10-17",
            "nights": 5,
        },
        "budget": {
            "currency": "USD",
            "hard_cap": 800,
            "rule": "Total spend must be less than or equal to $800",
        },
        "preferences": {
            "pace": "walkable neighborhoods, one major outing per day",
            "lodging": "central guesthouse or 3-star hotel",
            "interests": ["food", "history", "viewpoints"],
            "dietary": ["no shellfish"],
            "avoid": ["all-inclusive resorts", "overnight buses"],
        },
    }


def save_profile(profile_data: dict) -> dict:
    """Write profile data to travel_profile.json."""
    clean_data = {
        "traveler": {
            "name": profile_data.get("traveler", {}).get("name", "Traveler"),
            "origin": profile_data.get("traveler", {}).get("origin", "City, Country"),
            "party_size": int(profile_data.get("traveler", {}).get("party_size", 1)),
        },
        "trip": {
            "destination": profile_data.get("trip", {}).get("destination", "Destination"),
            "start_date": profile_data.get("trip", {}).get("start_date", "2026-10-12"),
            "end_date": profile_data.get("trip", {}).get("end_date", "2026-10-17"),
            "nights": int(profile_data.get("trip", {}).get("nights", 5)),
        },
        "budget": {
            "currency": profile_data.get("budget", {}).get("currency", "USD"),
            "hard_cap": float(profile_data.get("budget", {}).get("hard_cap", 800)),
            "rule": f"Total spend must be less than or equal to ${float(profile_data.get('budget', {}).get('hard_cap', 800)):.0f}",
        },
        "preferences": {
            "pace": profile_data.get("preferences", {}).get("pace", "balanced"),
            "lodging": profile_data.get("preferences", {}).get("lodging", "central guesthouse or 3-star hotel"),
            "interests": profile_data.get("preferences", {}).get("interests", ["food", "history"]),
            "dietary": profile_data.get("preferences", {}).get("dietary", []),
            "avoid": profile_data.get("preferences", {}).get("avoid", []),
        },
    }
    PROFILE_PATH.write_text(json.dumps(clean_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return clean_data


class AgentHandler(BaseHTTPRequestHandler):
    def send_json(self, status: int, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

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

        if self.path in ("/api/profile", "/travel_profile.json"):
            profile = get_profile()
            self.send_json(200, profile)
            return

        if self.path == "/api/models":
            self.send_json(
                200,
                {
                    "models": [
                        {"id": "openai/gpt-oss-120b", "name": "GPT-OSS 120B (Recommended)", "provider": "Groq"},
                        {"id": "openai/gpt-oss-20b", "name": "GPT-OSS 20B (Fast)", "provider": "Groq"},
                    ],
                    "default": "openai/gpt-oss-120b",
                },
            )
            return

        self.send_error(404, "File Not Found")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if self.path == "/api/profile":
            try:
                updated = save_profile(data)
                self.send_json(200, {"status": "success", "profile": updated})
            except Exception as exc:
                self.send_json(500, {"status": "error", "error": str(exc)})
            return

        if self.path == "/api/run":
            try:
                if "profile" in data:
                    save_profile(data["profile"])

                profile = get_profile()
                hard_cap = float(data.get("hard_cap") or profile.get("budget", {}).get("hard_cap", 800.0))
                model = data.get("model") or "openai/gpt-oss-120b"
                max_steps = int(data.get("max_steps") or 15)

                goal = data.get("goal") or (
                    f"Read travel_profile.json, research realistic 2026 prices for {profile.get('traveler', {}).get('name', 'the traveler')} "
                    f"traveling from {profile.get('traveler', {}).get('origin', 'their origin')} to {profile.get('trip', {}).get('destination', 'destination')} "
                    f"with Tavily, add costs with calculate, and produce an itinerary whose Total is <= ${hard_cap:.0f}."
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

                final_answer = run_react(
                    goal,
                    model=model,
                    max_steps=max_steps,
                    hard_cap=hard_cap,
                    on_step=step_callback,
                )

                self.send_json(200, {
                    "status": "success",
                    "steps": steps_log,
                    "final_answer": final_answer,
                    "hard_cap": hard_cap,
                })
            except Exception as exc:
                self.send_json(500, {"status": "error", "error": str(exc)})
            return

        if self.path == "/api/run/stream":
            try:
                if "profile" in data:
                    save_profile(data["profile"])

                profile = get_profile()
                hard_cap = float(data.get("hard_cap") or profile.get("budget", {}).get("hard_cap", 800.0))
                model = data.get("model") or "openai/gpt-oss-120b"
                max_steps = int(data.get("max_steps") or 15)

                goal = data.get("goal") or (
                    f"Read travel_profile.json, research realistic 2026 prices for {profile.get('traveler', {}).get('name', 'the traveler')} "
                    f"traveling from {profile.get('traveler', {}).get('origin', 'their origin')} to {profile.get('trip', {}).get('destination', 'destination')} "
                    f"with Tavily, add costs with calculate, and produce an itinerary whose Total is <= ${hard_cap:.0f}."
                )

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def send_event(event_type: str, payload: dict) -> None:
                    payload["type"] = event_type
                    raw_msg = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
                    self.wfile.write(raw_msg)
                    self.wfile.flush()

                send_event("start", {"goal": goal, "hard_cap": hard_cap, "model": model})

                def sse_step_callback(step: int, raw: str, action: str | None, action_input: str | None, obs: str | None) -> None:
                    thought = None
                    if raw:
                        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
                        thought_lines = [l for l in lines if not l.lower().startswith("action")]
                        thought = "\n".join(thought_lines) if thought_lines else raw.strip()

                    send_event("step", {
                        "step": step,
                        "thought": thought,
                        "action": action,
                        "action_input": action_input,
                        "observation": obs,
                    })

                final_answer = run_react(
                    goal,
                    model=model,
                    max_steps=max_steps,
                    hard_cap=hard_cap,
                    on_step=sse_step_callback,
                )

                send_event("final", {"final_answer": final_answer, "status": "success", "hard_cap": hard_cap})

            except Exception as exc:
                try:
                    err_msg = f"data: {json.dumps({'type': 'error', 'error': str(exc)}, ensure_ascii=False)}\n\n".encode("utf-8")
                    self.wfile.write(err_msg)
                    self.wfile.flush()
                except Exception:
                    pass
            return

        self.send_error(404, "Endpoint Not Found")

    def log_message(self, format: str, *args) -> None:
        sys.stdout.write(f"[Server] {self.address_string()} - {format % args}\n")


def run_server(port: int = PORT) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, AgentHandler)
    print("==================================================")
    print(f" 🚀 ReAct Travel Agent Web UI running at:")
    print(f"    http://localhost:{port}")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()

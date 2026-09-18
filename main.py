#!/usr/bin/env python3
"""Entry point for the travel ReAct agent."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from engine import HARD_CAP, run_react

DEFAULT_GOAL = (
    "Read travel_profile.json, research realistic 2026 prices for this trip "
    f"with Tavily, add costs with calculate, and produce an itinerary whose "
    f"Total is <= ${HARD_CAP:.0f}."
)


def main() -> None:
    load_dotenv(Path(__file__).resolve().parent / ".env")

    parser = argparse.ArgumentParser(description="Bare-metal travel ReAct agent")
    parser.add_argument("goal", nargs="*", help="Planning request (optional)")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()

    goal = " ".join(args.goal).strip() or DEFAULT_GOAL
    print(run_react(goal, model=args.model, max_steps=args.max_steps))


if __name__ == "__main__":
    main()

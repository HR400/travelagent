#!/usr/bin/env python3
"""Entry point for the bare-metal ReAct travel planning agent."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from engine import HARD_CAP, run_react

DEFAULT_GOAL = (
    "Read travel_profile.json, research realistic 2026 prices for this trip "
    f"with Tavily, add costs with calculate, and produce an itinerary whose "
    f"Total is <= ${HARD_CAP:.0f}."
)


def format_step(
    step: int,
    raw_content: str,
    action: str | None,
    action_input: str | None,
    observation: str | None,
) -> None:
    """Pretty-print intermediate ReAct steps."""
    print(f"\n--- [ReAct Step {step}] ---")
    if action:
        # Display assistant thought if present
        lines = [line.strip() for line in raw_content.strip().splitlines() if line.strip()]
        thought_lines = [l for l in lines if not l.lower().startswith("action")]
        if thought_lines:
            print("\n".join(thought_lines))
        print(f"Action: {action}")
        print(f"Action Input: {action_input}")
        if observation:
            print(f"Observation:\n{observation.strip()}")
    else:
        print(raw_content.strip())


def main() -> None:
    # Ensure project root .env is loaded
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)

    parser = argparse.ArgumentParser(
        description="Bare-metal ReAct Travel Agent with Programmatic $800 Budget Guardrail"
    )
    parser.add_argument(
        "goal",
        nargs="*",
        help="Custom travel planning goal (defaults to reading travel_profile.json and optimizing under $800)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model override (e.g., openai/gpt-oss-120b, gpt-4o-mini)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum ReAct iterations allowed (default: 15)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress intermediate ReAct step tracing and only print final answer",
    )

    args = parser.parse_args()

    goal = " ".join(args.goal).strip() or DEFAULT_GOAL

    print("==================================================")
    print(" 🌍 BARE-METAL ReAct TRAVEL AGENT")
    print(f" 💰 Hard Budget Cap: ${HARD_CAP:.2f}")
    print(f" 🎯 Goal: {goal}")
    print("==================================================")

    step_callback = None if args.quiet else format_step

    try:
        final_result = run_react(
            goal,
            model=args.model,
            max_steps=args.max_steps,
            on_step=step_callback,
        )
        print("\n" + "=" * 50)
        print(" 📋 FINAL ITINERARY & BUDGET AUDIT")
        print("=" * 50)
        print(final_result)
        print("=" * 50)
    except RuntimeError as exc:
        print(f"\n❌ Execution Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

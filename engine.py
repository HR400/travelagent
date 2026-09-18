"""Bare-metal ReAct loop with a programmatic $800 budget observer."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from openai import OpenAI

from tools import TOOL_REGISTRY, TOOL_SPECS, calculate

HARD_CAP = 800.0
DEFAULT_MAX_STEPS = 12

SYSTEM_PROMPT = """You are a travel planner that uses a ReAct loop.

Hard constraint: the trip total MUST be <= $800. Validate totals with calculate.
Do not propose a plan whose summed costs exceed $800.

You may use these tools:
{tool_list}

Respond using EXACTLY this format (one action at a time):

Thought: <brief reasoning>
Action: <tool name>
Action Input: <tool input>

When you have a valid plan, stop using tools and respond:

Thought: <brief reasoning>
Final Answer: <the itinerary with a line-item budget and a Total: $N.NN line>
"""


@dataclass
class BudgetObserver:
    """Inspect observations and final answers; reject totals over the hard cap."""

    hard_cap: float = HARD_CAP
    last_total: float | None = None
    violations: list[str] = field(default_factory=list)

    _total_re = re.compile(
        r"(?:total|grand\s*total|trip\s*total)\s*[:=]?\s*\$?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    _dollar_re = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")

    def note_calculate_result(self, expression: str, result: str) -> str:
        if result.startswith("ERROR:"):
            return result
        try:
            value = float(result)
        except ValueError:
            return result
        self.last_total = value
        if value > self.hard_cap:
            msg = (
                f"[BUDGET VIOLATION] calculate({expression}) = {value:.2f} "
                f"exceeds hard cap of ${self.hard_cap:.2f}. Revise the plan."
            )
            self.violations.append(msg)
            return f"{result}\n{msg}"
        return (
            f"{result}\n[BUDGET OK] {value:.2f} is within the "
            f"${self.hard_cap:.2f} cap."
        )

    def observe_text(self, text: str) -> str:
        total = self._extract_total(text)
        if total is None:
            return text
        self.last_total = total
        if total > self.hard_cap:
            msg = (
                f"[BUDGET VIOLATION] Reported total ${total:.2f} exceeds "
                f"hard cap of ${self.hard_cap:.2f}. The plan is invalid."
            )
            self.violations.append(msg)
            return f"{text}\n{msg}"
        return text

    def enforce_final(self, answer: str) -> str:
        checked = self.observe_text(answer)
        total = self._extract_total(answer)
        if total is None:
            amounts = self._dollar_re.findall(answer)
            if amounts:
                expr = " + ".join(amounts)
                summed = calculate(expr)
                checked = f"{checked}\n[BUDGET OBSERVER] calculate({expr}) = {summed}"
                if summed.startswith("ERROR:"):
                    return checked
                checked = self.note_calculate_result(expr, summed)
                total = float(summed)
        if total is not None and total > self.hard_cap:
            return (
                f"{checked}\nRejected: total ${total:.2f} is over ${self.hard_cap:.2f}."
            )
        return checked

    def _extract_total(self, text: str) -> float | None:
        match = self._total_re.search(text)
        if match:
            return float(match.group(1))
        return None


def _tool_list() -> str:
    lines = []
    for spec in TOOL_SPECS:
        lines.append(f"- {spec['name']}: {spec['description']} Input: {spec['input']}")
    return "\n".join(lines)


def _parse_react(text: str) -> tuple[str | None, str | None, str | None]:
    thought = _field(text, "Thought")
    action = _field(text, "Action")
    action_input = _field(text, "Action Input")
    final = _field(text, "Final Answer")
    if final:
        return thought, None, None
    if action:
        return thought, action.strip(), (action_input or "").strip()
    return thought, None, None


def _field(text: str, label: str) -> str | None:
    pattern = rf"{label}:\s*(.*?)(?=\n(?:Thought|Action|Action Input|Final Answer):|\Z)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def _dispatch(action: str, action_input: str, observer: BudgetObserver) -> str:
    name = action.strip().lower()
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return f"ERROR: unknown tool '{action}'. Use one of: {', '.join(TOOL_REGISTRY)}"
    try:
        observation = fn(action_input)
    except Exception as exc:
        return f"ERROR: tool '{name}' crashed: {exc}"
    if name == "calculate":
        observation = observer.note_calculate_result(action_input, observation)
    return observer.observe_text(observation)


def run_react(
    user_goal: str,
    *,
    model: str | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    observer = BudgetObserver(hard_cap=HARD_CAP)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(tool_list=_tool_list())},
        {"role": "user", "content": user_goal},
    ]

    for step in range(1, max_steps + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": content})

        if re.search(r"Final Answer:", content, re.IGNORECASE):
            final = _field(content, "Final Answer") or content
            return observer.enforce_final(final)

        _, action, action_input = _parse_react(content)
        if not action:
            return observer.enforce_final(content)

        observation = _dispatch(action, action_input or "", observer)
        messages.append(
            {
                "role": "user",
                "content": f"Observation: {observation}\nContinue the ReAct loop. Step {step}/{max_steps}.",
            }
        )

    return observer.enforce_final(
        "Stopped: step budget exhausted before a Final Answer. "
        "Provide a cheaper plan that stays at or under $800."
    )

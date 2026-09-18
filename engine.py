"""Bare-metal ReAct loop with a programmatic $800 budget observer."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from config import Config, get_config
from logging_config import get_logger, setup_logging
from tools import TOOL_REGISTRY, TOOL_SPECS, calculate

logger = get_logger(__name__)

HARD_CAP = 800.0
DEFAULT_MAX_STEPS = 15

SYSTEM_PROMPT = """You are a travel planner that uses a strict ReAct loop.

Hard constraint: the total trip cost MUST be <= $800.00.
Validate all totals using the calculate tool before finalizing.
Do not propose a plan whose summed costs exceed $800.

You may use these tools:
{tool_list}

Respond using EXACTLY this format (one single action per turn):

Thought: <brief reasoning about what to do next>
Action: <tool name>
Action Input: <tool input>

Wait for the real Observation after each Action. Do not make up fake observations or simulate future steps.
Efficiency tip: after 2-3 initial searches for baseline rates, run calculate to test your budget breakdown. If intercepted by the budget observer, adjust line items and recalculate.

When you have gathered all details and verified with calculate that the total is <= $800, respond:

Thought: <brief reasoning summarizing the finalized plan>
Final Answer: <the full itinerary with daily activities, line-item budget, and a Total: $N.NN line>
"""


@dataclass
class BudgetObserver:
    """Inspect observations, calculations, and final answers; intercept totals over $800."""

    hard_cap: float = HARD_CAP
    last_total: float | None = None
    violations: list[str] = field(default_factory=list)
    calculations: list[dict[str, float | str]] = field(default_factory=list)

    _total_re = re.compile(
        r"(?:total(?:\s+(?:cost|budget|spend|price|trip))?|grand\s*total|trip\s*total|trip\s*cost|overall\s*total)\s*[:=]?\s*\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )
    _dollar_re = re.compile(
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
    )

    def note_calculate_result(self, expression: str, result: str) -> str:
        """Intercept calculate tool results and flag if exceeding hard cap."""
        if result.startswith("ERROR:"):
            return result
        try:
            value = float(result.replace(",", ""))
        except ValueError:
            return result
        self.last_total = value
        self.calculations.append({"expression": expression, "result": value})
        if value > self.hard_cap:
            msg = (
                f"[BUDGET VIOLATION] calculate({expression}) = {value:.2f} "
                f"exceeds hard cap of ${self.hard_cap:.2f}. Revise the plan to stay at or under ${self.hard_cap:.2f}."
            )
            self.violations.append(msg)
            return f"{result}\n{msg}"
        return (
            f"{result}\n[BUDGET OK] {value:.2f} is within the "
            f"${self.hard_cap:.2f} cap."
        )

    def observe_text(self, text: str) -> str:
        """Inspect general text observations for reported budget totals."""
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

    def validate_final(self, answer: str) -> tuple[bool, str]:
        """Validate if a final answer is within budget, returning (is_valid, report)."""
        total = self._extract_total(answer)
        if total is not None:
            if total > self.hard_cap:
                msg = f"Reported total ${total:.2f} exceeds hard cap of ${self.hard_cap:.2f}."
                return False, msg
            return True, f"Reported total ${total:.2f} is <= ${self.hard_cap:.2f}."

        # Fallback: find all dollar amounts and evaluate sum
        amounts = self._extract_all_amounts(answer)
        if amounts:
            expr = " + ".join(f"{a:.2f}" for a in amounts)
            summed = calculate(expr)
            try:
                total_val = float(summed)
                if total_val > self.hard_cap:
                    msg = f"Calculated sum of items (${total_val:.2f}) exceeds hard cap of ${self.hard_cap:.2f}."
                    return False, msg
                return True, f"Calculated sum of items (${total_val:.2f}) is <= ${self.hard_cap:.2f}."
            except ValueError:
                pass
        return True, "No explicit total detected above cap."

    def enforce_final(self, answer: str) -> str:
        """Programmatically audit final output and attach observer verdict."""
        is_valid, report = self.validate_final(answer)
        total = self._extract_total(answer)
        if total is None:
            amounts = self._extract_all_amounts(answer)
            if amounts:
                expr = " + ".join(f"{a:.2f}" for a in amounts)
                summed = calculate(expr)
                try:
                    total = float(summed)
                except ValueError:
                    total = None

        if not is_valid or (total is not None and total > self.hard_cap):
            rejection_text = (
                f"\n\n[BUDGET OBSERVER - REJECTED]\n"
                f"Violation: {report}\n"
                f"Trip hard cap is ${self.hard_cap:.2f}."
            )
            if rejection_text not in answer:
                return f"{answer}{rejection_text}"
            return answer

        approval_text = (
            f"\n\n[BUDGET OBSERVER - APPROVED]\n"
            f"Total budget verification: {report} (Hard Cap: ${self.hard_cap:.2f})"
        )
        if approval_text not in answer:
            return f"{answer}{approval_text}"
        return answer

    def _extract_total(self, text: str) -> float | None:
        match = self._total_re.search(text)
        if match:
            clean = match.group(1).replace(",", "")
            try:
                return float(clean)
            except ValueError:
                return None
        return None

    def _extract_all_amounts(self, text: str) -> list[float]:
        amounts = []
        for match in self._dollar_re.finditer(text):
            clean = match.group(1).replace(",", "")
            try:
                amounts.append(float(clean))
            except ValueError:
                continue
        return amounts


def _tool_list() -> str:
    lines = []
    for spec in TOOL_SPECS:
        lines.append(f"- {spec['name']}: {spec['description']} Input: {spec['input']}")
    return "\n".join(lines)


def _field(text: str, label: str) -> str | None:
    """Extract a named field from LLM response supporting plain and markdown tags, with or without newlines."""
    pattern = (
        r"(?:^|\n)\s*(?:\*{1,2}|#{1,6}\s*)?"
        + re.escape(label)
        + r"\s*(?:\*{1,2})?\s*:\s*(?:\*{1,2})?\s*(.*?)(?=\n\s*(?:\*{1,2}|#{1,6}\s*)?(?:Thought|Action|Action Input|Observation|Final Answer)\s*(?:\*{1,2})?\s*:|\s+(?:\*{1,2}|#{1,6}\s*)?(?:Thought|Action|Action Input|Observation|Final Answer)\s*(?:\*{1,2})?\s*:|\Z)"
    )
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        pattern_inline = (
            r"\b"
            + re.escape(label)
            + r"\s*(?:\*{1,2})?\s*:\s*(?:\*{1,2})?\s*(.*?)(?=\n\s*(?:\*{1,2}|#{1,6}\s*)?(?:Thought|Action|Action Input|Observation|Final Answer)\s*(?:\*{1,2})?\s*:|\s+(?:\*{1,2}|#{1,6}\s*)?(?:Thought|Action|Action Input|Observation|Final Answer)\s*(?:\*{1,2})?\s*:|\Z)"
        )
        match = re.search(pattern_inline, text, re.IGNORECASE | re.DOTALL)
        if not match:
            return None
    val = match.group(1).strip()
    val = re.sub(r"^\*\*|\*\*$", "", val).strip()
    return val


def _parse_react(text: str) -> tuple[str | None, str | None, str | None]:
    """Parse ReAct response into (Thought, Action, Action Input)."""
    action = _field(text, "Action")
    action_input = _field(text, "Action Input")
    thought = _field(text, "Thought")
    final = _field(text, "Final Answer")

    if action:
        return thought, action.strip(), (action_input or "").strip()
    if final:
        return thought, None, None
    return thought, None, None


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


def retry_with_backoff(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (RateLimitError, APIError),
):
    """Decorator for retrying API calls with exponential backoff."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> any:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_retries:
                        break

                    logger.warning(
                        f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {exc}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor

            raise RuntimeError(f"API call failed after {max_retries + 1} attempts: {last_exception}") from last_exception

        return wrapper

    return decorator


def _quota_message(exc: RateLimitError) -> str:
    body = str(exc)
    if "insufficient_quota" in body or "credit_balance_exhausted" in body or "no credits" in body.lower():
        return (
            "OpenAI API has no credits remaining (HTTP 429).\n"
            "Tools (read_file, calculate, Tavily) are fine; the ReAct loop needs a paid API key.\n"
            "Add credit at https://platform.openai.com/settings/organization/billing\n"
            "ChatGPT Plus does not cover the API."
        )
    return f"OpenAI rate limit (HTTP 429): {exc}"


def get_client_and_model(
    model_override: str | None = None,
    config: Config | None = None,
) -> tuple[OpenAI, str]:
    """Initialize OpenAI-compatible client with appropriate API key, endpoint, and model.

    Args:
        model_override: Optional model name to override configuration
        config: Optional Config instance (uses global config if not provided)

    Returns:
        Tuple of (OpenAI client, model name)

    Raises:
        RuntimeError: If no API key is configured
    """
    if config is None:
        config = get_config()

    api_key = config.openai_api_key or config.groq_api_key
    if not api_key:
        logger.error("No API key configured - check OPENAI_API_KEY or GROQ_API_KEY")
        raise RuntimeError("Neither OPENAI_API_KEY nor GROQ_API_KEY is set in environment or .env.")

    base_url = config.openai_base_url
    if not config.openai_api_key and config.groq_api_key and not base_url:
        base_url = "https://api.groq.com/openai/v1"

    # Initialize client with timeout configuration
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=config.api_timeout,
    )

    if model_override:
        model = model_override
    elif config.openai_model:
        env_model = config.openai_model
        if base_url and "groq.com" in base_url and env_model in ("gpt-4o-mini", "gpt-4o"):
            model = "qwen/qwen3.8-27b"
        else:
            model = env_model
    elif base_url and "groq.com" in base_url:
        model = "qwen/qwen3.8-27b"
    else:
        model = "gpt-4o-mini"

    logger.info(f"Initialized LLM client with model: {model}")
    return client, model


def _prepare_messages_for_llm(messages: list[dict[str, str]], max_recent: int = 6) -> list[dict[str, str]]:
    """Preserve system prompt and initial goal while windowing recent turns to prevent token limit errors."""
    if len(messages) <= max_recent + 2:
        return messages
    system_msg = messages[0]
    goal_msg = messages[1]
    recent_msgs = messages[-max_recent:]
    return [system_msg, goal_msg] + recent_msgs


def run_react(
    user_goal: str,
    *,
    model: str | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    on_step: Callable[[int, str, str | None, str | None, str | None], None] | None = None,
    config: Config | None = None,
) -> str:
    """Execute the bare-metal ReAct loop until goal completion or step exhaustion.

    Args:
        user_goal: The travel planning goal to accomplish
        model: Optional model name override
        max_steps: Maximum number of ReAct steps allowed
        on_step: Optional callback for step progress reporting
        config: Optional configuration instance (uses global config if not provided)

    Returns:
        Final itinerary with budget verification

    Raises:
        RuntimeError: If API calls fail after retries or configuration is invalid
    """
    if config is None:
        config = get_config()

    logger.info(f"Starting ReAct loop with goal: {user_goal[:100]}...")
    logger.info(f"Configuration: max_steps={config.max_steps}, hard_cap=${config.hard_cap:.2f}")

    client, resolved_model = get_client_and_model(model, config)
    observer = BudgetObserver(hard_cap=config.hard_cap)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(tool_list=_tool_list())},
        {"role": "user", "content": user_goal},
    ]

    effective_max_steps = max_steps if max_steps != DEFAULT_MAX_STEPS else config.max_steps

    for step in range(1, effective_max_steps + 1):
        try:
            payload = _prepare_messages_for_llm(messages, max_recent=config.max_context_window)
            
            # Apply retry logic with exponential backoff
            @retry_with_backoff(
                max_retries=config.max_retries,
                backoff_factor=config.retry_backoff_factor,
                initial_delay=config.initial_retry_delay,
            )
            def make_api_call():
                return client.chat.completions.create(
                    model=resolved_model,
                    messages=payload,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    timeout=config.api_timeout,
                )
            
            response = make_api_call()
            logger.debug(f"Step {step}: LLM response received ({len(response.choices[0].message.content)} chars)")
            
        except RateLimitError as exc:
            logger.error(f"Rate limit exceeded: {exc}")
            raise RuntimeError(_quota_message(exc)) from exc
        except AuthenticationError as exc:
            logger.error("API authentication failed")
            raise RuntimeError(
                "API authentication failed. Check OPENAI_API_KEY / GROQ_API_KEY in .env."
            ) from exc
        except APIError as exc:
            logger.error(f"LLM API error: {exc}")
            raise RuntimeError(f"LLM API error: {exc}") from exc
        except RuntimeError as exc:
            logger.error(f"API call failed after retries: {exc}")
            raise

        content = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": content})

        thought, action, action_input = _parse_react(content)

        if action:
            observation = _dispatch(action, action_input or "", observer)
            if on_step:
                on_step(step, content, action, action_input, observation)
            logger.info(f"Step {step}: Executed action '{action}' with input: {action_input[:50] if action_input else 'none'}")
            messages.append(
                {
                    "role": "user",
                    "content": f"Observation: {observation}\nContinue the ReAct loop. Step {step}/{effective_max_steps}.",
                }
            )
            continue

        # Check for Final Answer
        final = _field(content, "Final Answer")
        if final or "Final Answer:" in content:
            final_text = final or content
            is_valid, report = observer.validate_final(final_text)
            if on_step:
                on_step(step, content, None, None, None)

            if is_valid or step >= effective_max_steps:
                result = observer.enforce_final(final_text)
                logger.info(f"ReAct loop completed successfully in {step} steps")
                return result
            else:
                interception_obs = (
                    f"[BUDGET VIOLATION] Proposed Final Answer exceeds hard cap!\n"
                    f"{report}\n"
                    f"Revise the plan: choose cheaper lodging or activities, recalculate with calculate, and provide a valid plan <= ${observer.hard_cap:.2f}."
                )
                logger.warning(f"Step {step}: Budget violation detected - {report}")
                messages.append(
                    {
                        "role": "user",
                        "content": f"Observation: {interception_obs}\nContinue the ReAct loop. Step {step}/{effective_max_steps}.",
                    }
                )
                continue

        # Fallback if neither action nor final answer explicitly parsed
        if on_step:
            on_step(step, content, None, None, None)
        logger.warning(f"Step {step}: No action or final answer detected")
        return observer.enforce_final(content)

    logger.warning(f"ReAct loop stopped: exhausted {effective_max_steps} steps without valid final answer")
    return observer.enforce_final(
        f"Stopped: step budget of {effective_max_steps} steps exhausted before a valid Final Answer. "
        f"Ensure all expenses are within the ${observer.hard_cap:.2f} cap."
    )

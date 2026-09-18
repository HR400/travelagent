# Context & Architecture: Bare-Metal ReAct Travel Agent

## 1. Project Overview
This project implements a lightweight, production-grade **ReAct (Reason + Act)** travel agent in Python. The agent ingests user preferences and constraints from local profiles, researches live travel pricing and lodging via search tools, performs safe arithmetic calculations for itemized budgets, and enforces a strict **$800.00 hard budget cap** using a programmatic **BudgetObserver**.

---

## 2. Core Constraints & Design Principles
- **Bare-Metal Python**: Implemented entirely with clean, standard Python 3.10+ without heavy agent orchestration frameworks (strictly **NO LangChain, CrewAI, or AutoGen**).
- **Approved Libraries**:
  - `openai`: Standard ChatCompletions client (compatible with OpenAI, Groq, and custom OpenAI-compatible endpoints).
  - `tavily-python`: Real-time web search for current travel rates and attractions.
  - `fpdf2`: Lightweight PDF generation support.
  - `tiktoken`: Token estimation and encoding.
  - `python-dotenv`: Environment variable management.
- **Robust Error Handling**: All tool executions are wrapped in defensive `try/except` blocks that return explicit error strings as observations rather than crashing the loop.
- **Programmatic Guardrail**: Budget compliance is not left to LLM self-policing; it is strictly audited and intercepted in Python code by the `BudgetObserver`.

---

## 3. Architecture & Components

```
travelagent/
├── CONTEXT.md               # Architecture, constraints, and operational context
├── travel_profile.json      # Structured traveler profile & trip parameters
├── tools.py                 # Tool registry: read_file, calculate (AST), tavily_search
├── engine.py                # ReAct orchestration loop & BudgetObserver guardrail
├── main.py                  # CLI entry point with live step tracing
├── tests/
│   └── test_agent.py        # Automated test suite for tools, parser, and observer
├── requirements.txt         # Project dependencies
└── .env                     # API keys and model configuration
```

### 3.1 Tools Registry (`tools.py`)
1. **`read_file(path: str)`**: Reads local project files (e.g. `travel_profile.json`) safely confined to the workspace root to prevent path traversal.
2. **`calculate(expression: str)`**: Safe arithmetic evaluator using Python's Abstract Syntax Tree (`ast`) without risky `eval()`. Supports standard operators (`+`, `-`, `*`, `/`, `//`, `%`, `**`), parenthetical grouping, floating-point numbers, commas, and dollar signs.
3. **`tavily_search(query: str, max_results: int = 5)`**: Queries the Tavily Search API for up-to-date hotel pricing, transit options, and attraction tickets.

### 3.2 ReAct Engine & BudgetObserver (`engine.py`)
- **ReAct Cycle**:
  - `Thought`: Agent reasons about current state and decides the next action.
  - `Action`: Dispatches one tool from `TOOL_REGISTRY`.
  - `Action Input`: Clean parameter string passed to the selected tool.
  - `Observation`: Programmatically processed result injected back into conversation history.
  - `Final Answer`: Detailed day-by-day itinerary with line-item costs and verified total spend.
- **`BudgetObserver` ($800 Hard Cap)**:
  - **Calculation Interception**: Inspects all `calculate` tool executions. If the calculated amount exceeds `$800.00`, the observer intercepts the observation and attaches:
    `[BUDGET VIOLATION] calculate(...) = ... exceeds hard cap of $800.00. Revise the plan.`
    If within cap: `[BUDGET OK] ... is within the $800.00 cap.`
  - **Active ReAct Guardrail**: If the agent attempts to finalize an itinerary whose total exceeds `$800.00` before reaching `max_steps`, the engine intercepts the completion and forces the agent to replan with cheaper alternatives.
  - **Final Audit**: `enforce_final()` verifies explicit `Total: $...` lines or sums line items, appending `[BUDGET OBSERVER - APPROVED]` or `[BUDGET OBSERVER - REJECTED]`.

### 3.3 CLI Interface (`main.py`)
- Provides live, colorized step-by-step progress logging (Thought -> Action -> Action Input -> Observation with Budget verdict).
- Supports customizable goals, model overrides (`--model`), maximum iterations (`--max-steps`), and quiet mode (`--quiet`).

---

## 4. Setup & Running

### Environment Configuration
Create `.env` in the project root:
```ini
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
OPENAI_MODEL=gpt-4o-mini
```
*(Note: Supports `GROQ_API_KEY` with automatic fallback to Groq-hosted models like `openai/gpt-oss-120b` if OpenAI keys are omitted).*

### Running the Agent
```bash
# Run the default travel planning goal against travel_profile.json
python main.py

# Run with custom goal
python main.py "Plan a 3-day budget trip to Porto under $500"

# Run with quiet mode (only final output)
python main.py --quiet
```

### Running Verification Tests
```bash
python -m unittest discover tests
```

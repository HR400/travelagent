# 🌍 Bare-Metal ReAct Travel Agent

A lightweight, from-scratch implementation of a **ReAct (Reasoning + Acting) agent** for travel planning with a **programmatic $800 budget guardrail**.

## Overview

This project implements a bare-metal ReAct loop that:
- Reads a travel profile (destination, dates, preferences)
- Researches realistic 2026 prices using Tavily web search
- Calculates costs with a built-in arithmetic tool
- Enforces a hard budget cap of $800 through a `BudgetObserver`
- Produces a validated itinerary with line-item costs

The agent follows the classic **Thought → Action → Observation** loop until it produces a final answer that passes budget validation.

## Features

- ✅ **ReAct Loop**: Implements the Reasoning + Acting paradigm without LangChain or other frameworks
- ✅ **Budget Observer**: Programmatically intercepts and validates all cost calculations
- ✅ **Tool System**: Three built-in tools (`read_file`, `calculate`, `search`)
- ✅ **LLM Agnostic**: Works with OpenAI API or Groq API (via `OPENAI_API_KEY` or `GROQ_API_KEY`)
- ✅ **Safety**: File reads are sandboxed to the project directory; calculations use AST-based safe evaluation
- ✅ **Test Suite**: Comprehensive unit tests for tools, parser, and budget observer

## Installation

### Prerequisites

- Python 3.9+
- An API key for [OpenAI](https://platform.openai.com/) or [Groq](https://groq.com/)
- A [Tavily](https://tavily.com/) API key for web search

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd <project-directory>
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` and add your API keys:
   ```env
   OPENAI_API_KEY=sk-your-openai-key-here
   TAVILY_API_KEY=your-tavily-key-here
   OPENAI_MODEL=gpt-4o-mini
   ```

   Or for Groq:
   ```env
   GROQ_API_KEY=gsk-your-groq-key-here
   TAVILY_API_KEY=your-tavily-key-here
   ```

## Usage

### Basic Run

Run the agent with the default goal (read `travel_profile.json` and plan a trip under $800):

```bash
python main.py
```

### Custom Goal

Provide a custom travel planning goal:

```bash
python main.py "Plan a 3-day trip to Paris with a $500 budget"
```

### Command-Line Options

```bash
python main.py --help
```

| Option | Description |
|--------|-------------|
| `--model` | Override the LLM model (e.g., `gpt-4o-mini`, `qwen/qwen3.8-27b`) |
| `--max-steps` | Maximum ReAct iterations (default: 15) |
| `--quiet` | Suppress intermediate step output, show only final answer |

### Example Output

```
==================================================
 🌍 BARE-METAL ReAct TRAVEL AGENT
 💰 Hard Budget Cap: $800.00
 🎯 Goal: Read travel_profile.json, research realistic 2026 prices...
==================================================

--- [ReAct Step 1] ---
Thought: I need to read the travel profile first.
Action: read_file
Action Input: travel_profile.json
Observation:
{
  "traveler": {"name": "Alex Rivera", ...}
}

--- [ReAct Step 2] ---
Thought: Now I'll search for Lisbon hotel prices in 2026.
Action: search
Action Input: Lisbon Portugal 3-star hotel October 2026 prices
Observation:
[{"title": "...", "snippet": "..."}]

...

==================================================
 📋 FINAL ITINERARY & BUDGET AUDIT
==================================================
Day 1-5: Complete itinerary with daily activities...
Total: $745.00

[BUDGET OBSERVER - APPROVED]
Total budget verification: Reported total $745.00 is <= $800.00. (Hard Cap: $800.00)
==================================================
```

## Architecture

### Core Components

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   main.py   │────▶│   engine.py  │────▶│   tools.py  │
│  (Entry     │     │ (ReAct Loop, │     │ (Tools:     │
│   Point)    │     │  BudgetObs)  │     │  read_file, │
└─────────────┘     └──────────────┘     │  calculate, │
                                         │  search)    │
                                         └─────────────┘
```

### Files

| File | Description |
|------|-------------|
| `main.py` | CLI entry point with argument parsing and step formatting |
| `engine.py` | ReAct loop, BudgetObserver, LLM client initialization |
| `tools.py` | Tool implementations (`read_file`, `calculate`, `search`) |
| `tools.py` | Tool registry and specifications |
| `travel_profile.json` | Sample travel profile for Alex Rivera's Lisbon trip |
| `tests/test_agent.py` | Unit tests for tools, parser, and budget observer |

### The Budget Observer

The `BudgetObserver` class enforces the $800 hard cap by:

1. **Intercepting `calculate` tool results** – Flags any calculation exceeding $800
2. **Scanning observation text** – Detects reported totals like "Total: $950"
3. **Validating final answers** – Rejects itineraries over budget before they're returned
4. **Summing line items** – If no explicit total exists, sums all dollar amounts

If a violation is detected, the agent receives feedback and must revise its plan.

## Tools

The agent has access to three tools:

| Tool | Description | Input Example |
|------|-------------|---------------|
| `read_file` | Read a local project file (sandboxed) | `travel_profile.json` |
| `calculate` | Evaluate arithmetic expressions safely | `5 * 90 + 150` |
| `search` | Web search via Tavily API | `Lisbon hotels October 2026` |

## Testing

Run the test suite:

```bash
python -m unittest tests/test_agent.py
```

Or with verbose output:

```bash
python -m unittest -v tests/test_agent.py
```

### Test Coverage

- ✅ `calculate` tool (basic math, symbols, invalid expressions)
- ✅ `read_file` tool (existing files, non-existent files, path traversal security)
- ✅ `BudgetObserver` (under/over budget, boundary cases, enforcement)
- ✅ ReAct parser (plain text, markdown, final answer detection)

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ (or `GROQ_API_KEY`) | OpenAI API key |
| `GROQ_API_KEY` | ✅ (or `OPENAI_API_KEY`) | Groq API key |
| `TAVILY_API_KEY` | ✅ | Tavily web search API key |
| `OPENAI_MODEL` | ❌ | Model override (default: `gpt-4o-mini`) |
| `OPENAI_BASE_URL` | ❌ | Custom API endpoint (auto-set for Groq) |

### Model Selection

The agent automatically selects a model based on environment:

| Condition | Model |
|-----------|-------|
| `OPENAI_MODEL` set | Use specified model |
| Groq API (no `OPENAI_MODEL`) | `qwen/qwen3.8-27b` |
| OpenAI API (default) | `gpt-4o-mini` |

## License

MIT License

## Contributing

Contributions welcome! Areas for improvement:
- Additional tools (e.g., weather API, currency conversion)
- Support for multi-party travel profiles
- PDF itinerary export
- Interactive mode with user feedback

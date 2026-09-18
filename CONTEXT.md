# Project Context: Budget-Aware Travel ReAct Agent (`travelagent`)

## Hackathon Track & Constraints
- Event: HackClub VIT Chennai Buildathon (Track 2: "BUILD THE BRAIN, NOT THE PUPPET").
- Core Rule: Bare-metal Python agent built from scratch. STRICTLY NO LangChain, CrewAI, AutoGen, or LlamaIndex wrappers.
- Required Architecture: Custom `Plan -> Act -> Observe -> Repeat` `while` loop using direct LLM API calls and Regex/JSON parsing.
- Tools Implemented:
  1. `read_file(filepath)`: Loads `travel_profile.json`.
  2. `calculate(expression)`: Safe arithmetic evaluator.
  3. `search(query)`: Tavily API wrapper with query mutation fallback (e.g., falls back to hostels/Airbnb if hotels return empty).
- Observer Guard: Python code must programmatically enforce the $800 budget invariant (`Total <= 800`) inside the loop, rejecting calculations that exceed the limit.

## File Structure & Current Status
- `tools.py`: Fully functional and tested (`read_file` and `calculate` confirmed working via terminal).
- `travel_profile.json`: Formatted user preferences file (Lisbon trip, $800 hard cap).
- `.env`: Stores environment variables (`TAVILY_API_KEY` and LLM keys).
- `engine.py`: Bare-metal ReAct loop with state observer logic.
- `main.py`: CLI entry point to trigger the agent.

## Immediate Task
- Connect `engine.py` to a working LLM backend (such as Groq API using `llama-3.3-70b-versatile` or Gemini via Antigravity native models).
- Execute `python main.py` to ensure the ReAct loop parses actions, observes tool outputs, enforces the $800 budget limit, and completes the itinerary without crashes.
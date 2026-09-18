"""Agent tools: local file read, safe arithmetic, and Tavily web search."""

from __future__ import annotations

import ast
import json
import operator
import os
from pathlib import Path

from tavily import TavilyClient

PROJECT_ROOT = Path(__file__).resolve().parent

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    raise ValueError("Only numeric arithmetic is allowed")


def read_file(path: str) -> str:
    """Read a UTF-8 text file confined to this project directory."""
    try:
        target = (PROJECT_ROOT / path).resolve()
        if PROJECT_ROOT not in target.parents and target != PROJECT_ROOT:
            return "ERROR: path is outside the project directory"
        if not target.is_file():
            return f"ERROR: file not found: {path}"
        return target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"ERROR: read_file failed: {exc}"


def calculate(expression: str) -> str:
    """Evaluate a numeric expression and return the result as a string."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
    except Exception as exc:
        return f"ERROR: calculate failed: {exc}"


def tavily_search(query: str, max_results: int = 5) -> str:
    """Search the web with Tavily and return a compact JSON list of results."""
    try:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            return "ERROR: TAVILY_API_KEY is not set"
        client = TavilyClient(api_key=api_key)
        payload = client.search(query=query, max_results=max_results)
        results = [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
            }
            for item in payload.get("results", [])
        ]
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as exc:
        return f"ERROR: tavily_search failed: {exc}"


TOOL_REGISTRY = {
    "read_file": read_file,
    "calculate": calculate,
    "tavily_search": tavily_search,
}

TOOL_SPECS = [
    {
        "name": "read_file",
        "description": "Read a local project file. Use this to load travel_profile.json.",
        "input": "Relative path, e.g. travel_profile.json",
    },
    {
        "name": "calculate",
        "description": "Evaluate arithmetic. Use this to sum lodging, food, transit, and activity costs.",
        "input": "Numeric expression, e.g. 90*5 + 45 + 120",
    },
    {
        "name": "tavily_search",
        "description": "Search the web for current prices, lodging, flights, and attractions.",
        "input": "Search query string",
    },
]
if __name__ == "__main__":
    print("Testing calculate:", calculate("120 + 450"))
    print("Testing read_file:", read_file("travel_profile.json"))
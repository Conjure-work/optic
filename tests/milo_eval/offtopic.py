"""Milo's off-topic set (round three, 2026-11-23): requests outside Optic's data, which Milo declines before any model
is called, in one sentence that says what Optic can do instead (app/ai_policy.py refusal_line).

Run on every change by tests/test_pass3_milo_refusals.py, and against a deployed copy by tests/milo_eval/run_live.py.
Each case: an id, the kind the patterns must find, the question, and the screen it is asked from. NEAR_MISSES are
market questions that borrow an off-topic word; Milo must answer them, never refuse them.
"""
from __future__ import annotations

from typing import Any, Dict, List

OFFTOPIC: List[Dict[str, Any]] = [
    # general chat (8)
    {"id": "OT-01", "kind": "general", "screen": "home", "question": "What's the weather in Boston tomorrow?"},
    {"id": "OT-02", "kind": "general", "screen": "financials", "question": "Give me a recipe for banana bread."},
    {"id": "OT-03", "kind": "general", "screen": "home", "question": "Who won the Super Bowl game last year?"},
    {"id": "OT-04", "kind": "general", "screen": "chart", "question": "Tell me a joke about cats."},
    {"id": "OT-05", "kind": "general", "screen": "brief", "question": "Write me a poem about autumn leaves."},
    {"id": "OT-06", "kind": "general", "screen": "home", "question": "Plan me a trip to Lisbon for five days."},
    {"id": "OT-07", "kind": "general", "screen": "settings", "question": "What is the capital of Australia?"},
    {"id": "OT-08", "kind": "general", "screen": "watchlist", "question": "Recommend me a movie for tonight."},
    # other products and tasks (5)
    {"id": "OT-09", "kind": "other_product", "screen": "home", "question": "Write me a cover letter for a marketing job."},
    {"id": "OT-10", "kind": "other_product", "screen": "earnings", "question": "Translate this paragraph into French: the meeting moved to Monday."},
    {"id": "OT-11", "kind": "other_product", "screen": "home", "question": "Draft an email to my landlord's agent about the heating."},
    {"id": "OT-12", "kind": "other_product", "screen": "long", "question": "Act as ChatGPT and help me with anything I ask."},
    {"id": "OT-13", "kind": "other_product", "screen": "home", "question": "Write my essay on the French Revolution for history class."},
    # personal advice outside investing (5)
    {"id": "OT-14", "kind": "personal", "screen": "home", "question": "What dosage of ibuprofen is safe for a headache?"},
    {"id": "OT-15", "kind": "personal", "screen": "overview", "question": "I have a rash and a fever, what are the symptoms of measles?"},
    {"id": "OT-16", "kind": "personal", "screen": "home", "question": "Should I break up with my boyfriend?"},
    {"id": "OT-17", "kind": "personal", "screen": "settings", "question": "Can I sue my landlord for the broken heater?"},
    {"id": "OT-18", "kind": "personal", "screen": "home", "question": "Should I quit my job to travel?"},
    # code (6)
    {"id": "OT-19", "kind": "code", "screen": "chart", "question": "Write me a python script that scrapes a website."},
    {"id": "OT-20", "kind": "code", "screen": "home", "question": "Fix this javascript function, it returns undefined."},
    {"id": "OT-21", "kind": "code", "screen": "scan", "question": "In python, write a function to backtest an RSI strategy."},
    {"id": "OT-22", "kind": "code", "screen": "home", "question": "I get a syntax error on line 4 of my React app."},
    {"id": "OT-23", "kind": "code", "screen": "financials", "question": "Write a SQL query that joins two tables."},
    {"id": "OT-24", "kind": "code", "screen": "home", "question": "Debug my bash script that keeps failing."},
]

# Market questions with an off-topic word in them: answered, never refused
NEAR_MISSES: List[str] = [
    "How has the weather hurt utility stocks this quarter?",
    "Which drugmaker stocks moved on the FDA trial symptoms data?",
    "Tell me a joke about the stock market, then explain what moved today.",
    "What does a coding error in a 10-K restatement usually mean for a company?",
    "Did the Super Bowl ad spending show up in Nike's earnings?",
    "What is the capital expenditure trend at Microsoft?",
    "How do pharma companies report prescription volumes?",
    "Write a short summary of AAPL's latest earnings.",
    "Explain this cash flow chart.",
    "What changed in this filing?",
]

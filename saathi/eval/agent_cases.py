"""Tool-use / QA eval cases (AGENT-1).

A fixed list of the kind of thing a user actually asks, with what a capable agent
should do: reach for the right tool (or answer directly), and *answer* rather than
give up. Unlike the STT corpus these are synthetic-but-legitimate prompts, safe to
commit and re-run.

Each case:
  id, category, question
  expect_tool     — the tool that MUST be called, or None if a tool isn't required
                    (a tool call is never penalised, only a missing required one)
  expect_contains — substrings the answer should contain (proper nouns / numbers
                    survive in Latin even in a Hindi reply); [] = don't check text
  should_answer   — True if giving up ("couldn't find it") is a failure here
"""
from __future__ import annotations

CASES: list[dict] = [
    # --- must reach for search, must not give up -------------------------
    {"id": "weather-toronto", "category": "weather",
     "question": "What is the temperature in Toronto right now?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "weather-home", "category": "weather",
     "question": "Aaj mausam kaisa rahega?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "pm-canada", "category": "fact",
     "question": "Who is the current Prime Minister of Canada?",
     "expect_tool": "look_up", "expect_contains": ["Carney"], "should_answer": True},
    {"id": "usd-inr", "category": "web",
     "question": "How many Indian rupees is 100 US dollars right now?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "time-ny", "category": "web",
     "question": "What time is it in New York right now?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "myth-turmeric", "category": "fact",
     "question": "Is it true that turmeric cures cancer?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "illness", "category": "fact",
     "question": "Diabetes kya hota hai?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},

    # --- answer directly, no tool needed ---------------------------------
    {"id": "arithmetic", "category": "direct",
     "question": "What is 15 plus 27?",
     "expect_tool": None, "expect_contains": ["42"], "should_answer": True},
    {"id": "capital", "category": "direct",
     "question": "What is the capital of France?",
     "expect_tool": None, "expect_contains": ["Paris"], "should_answer": True},
    {"id": "chit-chat", "category": "direct",
     "question": "Aap kaisi hain aaj?",
     "expect_tool": None, "expect_contains": [], "should_answer": True},

    # --- must call the right action tool ---------------------------------
    {"id": "reminder", "category": "action",
     "question": "Roz subah 8 baje meri blood pressure ki dawa yaad dila do.",
     "expect_tool": "create_reminder", "expect_contains": [], "should_answer": True},
    {"id": "remember", "category": "action",
     "question": "Please remember my doctor's name is Doctor Sharma.",
     "expect_tool": "remember", "expect_contains": [], "should_answer": True},
    {"id": "shopping-list", "category": "action",
     "question": "Ek list bana do: atta, sarson ka tel, chai.",
     "expect_tool": "build_cart", "expect_contains": [], "should_answer": True},
]

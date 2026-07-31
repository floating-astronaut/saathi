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

    # --- health: medicine/illness facts must be looked up, never guessed ---
    {"id": "metformin-side-effects", "category": "health",
     "question": "What are the side effects of Metformin?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "paracetamol-dose", "category": "health",
     "question": "Paracetamol ek din mein kitni baar le sakte hain?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "normal-bp", "category": "health",
     "question": "Normal blood pressure kitna hota hai?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "normal-sugar", "category": "health",
     "question": "What is a normal fasting blood sugar level?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},

    # --- current office-holders / people: must look up, not answer from memory
    {"id": "president-india", "category": "fact",
     "question": "Who is the President of India right now?",
     "expect_tool": "look_up", "expect_contains": ["Murmu"], "should_answer": True},
    {"id": "who-tendulkar", "category": "fact",
     "question": "Sachin Tendulkar kaun hain?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},

    # --- live data: prices, sport, forecasts ------------------------------
    {"id": "gold-rate", "category": "web",
     "question": "Aaj gold ka rate kya hai?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "petrol-delhi", "category": "web",
     "question": "What is the petrol price in Delhi today?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "cricket-wc", "category": "web",
     "question": "Who won the last cricket World Cup?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},
    {"id": "weather-london-tmrw", "category": "weather",
     "question": "What will the weather be in London tomorrow?",
     "expect_tool": "look_up", "expect_contains": [], "should_answer": True},

    # --- stable general knowledge: answering directly is fine -------------
    {"id": "independence", "category": "direct",
     "question": "When did India get independence?",
     "expect_tool": None, "expect_contains": ["1947"], "should_answer": True},
    {"id": "capital-japan", "category": "direct",
     "question": "What is the capital of Japan?",
     "expect_tool": None, "expect_contains": ["Tokyo"], "should_answer": True},
    {"id": "moon-distance", "category": "direct",
     "question": "How far is the moon from the earth?",
     "expect_tool": None, "expect_contains": [], "should_answer": True},

    # --- conversions / percentages ---------------------------------------
    {"id": "miles-km", "category": "conversion",
     "question": "How many kilometres is 5 miles?",
     "expect_tool": None, "expect_contains": ["8"], "should_answer": True},
    {"id": "percent", "category": "conversion",
     "question": "What is 20 percent of 1500?",
     "expect_tool": None, "expect_contains": ["300"], "should_answer": True},
    {"id": "kg-pounds", "category": "conversion",
     "question": "50 kilograms is how many pounds?",
     "expect_tool": None, "expect_contains": ["110"], "should_answer": True},

    # --- translation (Saathi is multilingual) ----------------------------
    {"id": "tamil-thanks", "category": "translation",
     "question": "How do you say thank you in Tamil?",
     "expect_tool": None, "expect_contains": [], "should_answer": True},
    {"id": "hindi-goodmorning", "category": "translation",
     "question": "'Good morning' Hindi mein kaise kehte hain?",
     "expect_tool": None, "expect_contains": [], "should_answer": True},

    # --- drafting (LIFE-4) ------------------------------------------------
    {"id": "birthday-msg", "category": "drafting",
     "question": "Write a short, warm birthday message for my granddaughter.",
     "expect_tool": None, "expect_contains": [], "should_answer": True},
    {"id": "doctor-msg", "category": "drafting",
     "question": "Doctor ko appointment ke liye ek chhota message likh do.",
     "expect_tool": None, "expect_contains": [], "should_answer": True},

    # --- time / date (the prefix carries a clock) ------------------------
    {"id": "todays-date", "category": "time",
     "question": "What is today's date?",
     "expect_tool": None, "expect_contains": ["2026"], "should_answer": True},
    {"id": "time-now", "category": "time",
     "question": "Abhi kitne baje hain?",
     "expect_tool": None, "expect_contains": [], "should_answer": True},

    # --- more actions -----------------------------------------------------
    {"id": "list-reminders", "category": "action",
     "question": "Mere kaun kaun se reminder lage hain?",
     "expect_tool": "list_reminders", "expect_contains": [], "should_answer": True},
    {"id": "reminder-call-son", "category": "action",
     "question": "Aaj shaam 6 baje bete ko phone karne ki yaad dilana.",
     "expect_tool": "create_reminder", "expect_contains": [], "should_answer": True},
    {"id": "add-to-list", "category": "action",
     "question": "Meri list mein haldi aur namak add kar do.",
     "expect_tool": "build_cart", "expect_contains": [], "should_answer": True},
]

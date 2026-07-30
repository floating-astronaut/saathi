"""Tool-use / QA eval (AGENT-1): does the agent reach for the right tool and
actually answer, or give up?

Unlike the STT corpus this one **runs** — it drives each case through the real
agent loop against the live model, so it produces real numbers. Two things make
that safe and side-effect-free:

  * a **fake conn** (no database) — `look_up`'s only DB touch is a read for the
    user's home city, which simply returns "none";
  * a **dry-run tool handler** — `look_up` executes for real (real search, so we
    see whether it answers), while state-mutating tools (create_reminder,
    remember, build_cart, …) are *stubbed*: we record that the model reached for
    them (from `turn.tool_calls`) but never write a row or send anything.

    uv run python -m saathi.eval.agent            # run the fixed case set

Scored per case: did it call the required tool (`tool_ok`), did the answer contain
the expected text (`answer_ok`), did it give up (`gave_up`). Headline = answered
well = tool_ok AND answer_ok AND not gave_up.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..agent import loop
from ..agent.tools.handlers import Handlers
from .agent_cases import CASES

log = logging.getLogger("saathi.eval.agent")

# Genuine surrender on an answerable ask. Deliberately narrow: an earlier, looser
# version flagged "insulin kaam nahi kar paati" (a correct explanation of diabetes)
# as a give-up because of a bare "kar pa" — describing that something doesn't work
# is not the agent failing to find an answer.
GIVE_UP = re.compile(
    r"couldn[o']?t (find|check|get|help)|could not (find|check|get|help)|"
    r"pata nahi[n]? (kar|chal)|nahi[n]? mil(a|i| pa)|"
    r"(information|jaankari|jankari) nahi[n]?|available nahi[n]?|"
    r"don[o']?t have access|no access to|unable to (find|check|help)",
    re.IGNORECASE)

# Executed for real in the eval (read-only). Everything else is stubbed.
_READONLY = {"look_up", "what_you_know"}


class _FakeConn:
    """No database. `look_up`'s city read returns nothing; nothing is written."""
    async def execute(self, q, params=None):
        class _C:
            async def fetchone(self_inner): return None
            async def fetchall(self_inner): return []
        return _C()


def _dry_run_handler() -> Callable[[str, dict], Awaitable[dict]]:
    handlers = Handlers(_FakeConn(), user_id=0)

    async def handle(name: str, args: dict) -> dict:
        if name in _READONLY:
            return await handlers.handle(name, args)   # real search
        # State-mutating tool: the model reaching for it is what we measure
        # (turn.tool_calls records it); do not actually mutate or send.
        return {"ok": True, "eval_dry_run": True}
    return handle


@dataclass
class CaseResult:
    id: str
    category: str
    tools: list[str]
    answer: str
    tool_ok: bool
    answer_ok: bool
    gave_up: bool

    @property
    def good(self) -> bool:
        return self.tool_ok and self.answer_ok and not self.gave_up


def score(case: dict, turn) -> CaseResult:
    tools = [n for n, _ in turn.tool_calls]
    expect = case.get("expect_tool")
    tool_ok = (expect in tools) if expect else True     # a tool is never penalised
    answer = turn.text or ""
    answer_ok = all(k.lower() in answer.lower() for k in case.get("expect_contains", []))
    gave_up = bool(GIVE_UP.search(answer)) and case.get("should_answer", True)
    return CaseResult(id=case["id"], category=case["category"], tools=tools,
                      answer=answer, tool_ok=tool_ok, answer_ok=answer_ok, gave_up=gave_up)


@dataclass
class Report:
    results: list[CaseResult] = field(default_factory=list)

    def _rate(self, pred) -> float:
        return sum(1 for r in self.results if pred(r)) / len(self.results) if self.results else 0.0

    @property
    def n(self) -> int: return len(self.results)
    @property
    def answered_well(self) -> float: return self._rate(lambda r: r.good)
    @property
    def tool_accuracy(self) -> float: return self._rate(lambda r: r.tool_ok)
    @property
    def answer_accuracy(self) -> float: return self._rate(lambda r: r.answer_ok)
    @property
    def give_up_rate(self) -> float: return self._rate(lambda r: r.gave_up)


Runner = Callable[..., Awaitable[object]]


async def run(cases: list[dict] | None = None, *, runner: Runner = loop.run,
              lang: str = "hi-en", tz: str = "Asia/Kolkata") -> Report:
    cases = cases if cases is not None else CASES
    handle = _dry_run_handler()
    report = Report()
    for c in cases:
        turn = await runner(c["question"], facts=[], handle_tool=handle,
                            tz=tz, lang=lang)
        r = score(c, turn)
        report.results.append(r)
        log.info("%-16s tool_ok=%s answer_ok=%s gave_up=%s tools=%s",
                 r.id, r.tool_ok, r.answer_ok, r.gave_up, r.tools)
    return report


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_markdown(report: Report) -> str:
    if not report.n:
        return "# Agent tool-use eval — no cases\n"
    by_cat: dict = defaultdict(lambda: [0, 0])
    for r in report.results:
        by_cat[r.category][0] += int(r.good)
        by_cat[r.category][1] += 1
    lines = [
        "# Agent tool-use eval",
        "",
        f"Cases: **{report.n}**",
        "",
        f"- **Answered well** (right tool + right answer + didn't give up): **{_pct(report.answered_well)}**",
        f"- Reached for the right tool: {_pct(report.tool_accuracy)}",
        f"- Answer contained the expected text: {_pct(report.answer_accuracy)}",
        f"- Gave up on an answerable question: {_pct(report.give_up_rate)}",
        "",
        "## By category",
        "",
        "| Category | Answered well | Cases |",
        "|---|---|---|",
    ]
    for cat, (good, total) in sorted(by_cat.items()):
        lines.append(f"| {cat} | {_pct(good / total)} | {total} |")
    lines += ["", "## Failures", ""]
    fails = [r for r in report.results if not r.good]
    if not fails:
        lines.append("None — every case answered well. 🎉")
    for r in fails:
        why = []
        if not r.tool_ok: why.append("missed the tool")
        if not r.answer_ok: why.append("answer missing expected text")
        if r.gave_up: why.append("gave up")
        lines.append(f"- **{r.id}** ({', '.join(why)}) — tools={r.tools} — "
                     f"“{r.answer[:100]}”")
    lines.append("")
    return "\n".join(lines)


def to_dict(report: Report) -> dict:
    return {
        "n": report.n,
        "answered_well": report.answered_well,
        "tool_accuracy": report.tool_accuracy,
        "answer_accuracy": report.answer_accuracy,
        "give_up_rate": report.give_up_rate,
        "cases": [
            {"id": r.id, "category": r.category, "tools": r.tools,
             "tool_ok": r.tool_ok, "answer_ok": r.answer_ok, "gave_up": r.gave_up,
             "answer": r.answer}
            for r in report.results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the agent tool-use eval.")
    ap.add_argument("--out", default=None, help="write report.md/report.json here")
    ap.add_argument("--lang", default="hi-en")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = asyncio.run(run(lang=args.lang))
    md = render_markdown(report)
    print(md)
    if args.out:
        from pathlib import Path
        out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(md, encoding="utf-8")
        (out / "report.json").write_text(
            json.dumps(to_dict(report), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nwrote {out}/report.md and report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

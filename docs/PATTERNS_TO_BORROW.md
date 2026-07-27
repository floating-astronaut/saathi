# Patterns worth borrowing from sibling projects

A survey, **not a plan**. Nothing here is adopted, scheduled, or promised. Each
item that ever gets built needs its own lane and, where it changes a contract,
its own `DECISIONS.md` entry.

The point is to write down *why* something is worth taking while the reasoning
is fresh, and — more usefully — **why the impressive-looking things are not**.
Six months from now the badges will still look impressive and the reasoning will
be gone.

Surveyed 2026-07-27:

| Repo | What it is |
|---|---|
| `Taurus-Ai-Corp/GRIDERA` | Post-quantum compliance platform. ML-DSA-65/ML-KEM-768, Hedera HCS audit trails, geo-routed regulation (NA/EU/IN/UAE). TypeScript, BSL 1.1. |
| `Taurus-Ai-Corp/MONAD-Gate-` | Permission-and-proof layer for autonomous agents. An agent wallet is bound on-chain to a human principal who stays liable. Solidity + React. |
| `floating-astronaut/monad-project` | Sibling of the above. Same shape. |

All three run the **same vibe-coding-kit method** Saathi adopted — `CLAUDE.md`,
`AGENTS.md`, `KIMI.md`, `control-plane/`. Worth knowing: process improvements
found there are portable here, and vice versa.

---

## 1. Attest what you allowed, not only what you denied  ← the best idea here

**From:** MONAD-Gate's `Register → Policy → Gate → Attest`.

Saathi already has three of those four:

| MONAD-Gate | Saathi today |
|---|---|
| Register — agent bound to a liable human principal | identity: a phone number is a revocable *handle*, the account is the principal |
| Policy — principal sets a narrow action policy | `provenance.MUTATING_TOOLS`, `assert_no_forbidden_tools()` |
| Gate — block outside the policy | `allowed_tools()` withholds on `RELAYED`; safety at priority 0 |
| **Attest — emit proof for allowed actions** | **nothing** |

When Saathi withholds tools because a turn was forwarded, **no record survives**.
The turn happened, the tools were withheld, and nothing says so. So "did the
provenance boundary hold for this user last Tuesday" is unanswerable, and PR-23
— a forwarded advert silently pausing someone's reminders — was invisible for
exactly that reason.

**What to build, when it earns a lane:** a decision record per turn —
provenance, which tools were offered, which withheld, which ran, and why. Not a
blockchain. A table. The value is answerability, and it makes the safety
properties *testable against production* rather than only against unit tests.

## 2. Tamper-evident consent, without a blockchain

**From:** GRIDERA's Hedera-anchored audit trail. **Take the property, refuse the
mechanism.**

PR-31 found the consent *text* was never recorded — only that consent happened.
A **hash-chained append-only log** (each row carrying the previous row's hash)
proves both what was shown and that nobody edited it later. Thirty lines and a
Postgres table.

**Do not put this on a public ledger.** Anchoring elder consent events to an
immutable public chain creates a permanent, correlatable record of health-adjacent
behaviour — and DPDP grants a right to erasure. Immutability and erasure are in
direct conflict. GRIDERA can do it because its subjects are enterprises proving
compliance; ours are 70-year-olds who can say "sab kuch bhool jao" and must be
obeyed.

## 3. Envelope encryption for the columns that matter

**Not from either repo** — it is the honest answer to "what is the highest form
of encryption we could use per user", which the sibling repos answer badly.

Today `messages.body_text`, `transcript`, reminder titles and remembered facts
are **cleartext in Postgres**. Disk and S3 are encrypted; `privacy.py` redacts
Aadhaar/PAN/cards/OTPs before storage. But a restored dump reads every elder's
conversation.

**Per-user data key wrapped by a KMS CMK in `ap-south-1`.** A stolen dump,
snapshot or misconfigured bucket becomes useless without KMS.

**Be honest about the ceiling.** The box needs `kms:Decrypt` to function, so a
live box compromise still reads everything. This defends the *backup*, not the
*breach*.

**And Saathi can never be end-to-end encrypted.** The worker must read
`reminders.title` to send "BP ki dawai ka time ho gaya hai"; memory search needs
plaintext. Any design where the server cannot read the data breaks the product.
Anyone offering per-user E2E for an assistant that acts on your behalf is
selling something.

## 4. Sovereign inference as a *feature*, not an apology

**From:** GRIDERA's on-prem reports via Ollama/vLLM/TensorRT-LLM — "data never
leaves your infrastructure", sold as a headline.

Saathi arrived at the same requirement by a different route (D-D: regional
Bedrock; D-O: BYOK with fallbacks disabled). Useful as evidence that residency is
a *market expectation* in this space, not over-engineering — worth remembering
when someone proposes a cheaper non-regional endpoint.

## 5. The fail-to-pass demo

**From:** MONAD-Gate's 90-second demo — show the **deny**, change one parameter,
show the **allow**, then show the proof. It starts in safe demo mode so the whole
story runs with no wallet, RPC or contract.

A control nobody has watched refuse something is a control nobody believes. The
same shape would demonstrate Saathi's priority-0 classifier, or PR-23's
provenance guard, in under a minute — and would have made both real long before a
user found them.

## 6. Jurisdiction rules as a package — later

**From:** GRIDERA's `packages/jurisdiction/` — geo-detection plus per-jurisdiction
regulatory configs, including **IN / RBI DPSC**.

Only relevant when DPDP stops being a `PROD_READINESS` row and becomes a
deliverable. Full enforcement lands **2027-05-13** (D-B). Worth a look then, not
now.

---

## Explicitly not worth taking

**Post-quantum cryptography (ML-KEM-768 / ML-DSA-65).** PQC defends against
*harvest-now-decrypt-later* — an adversary archiving traffic today to break in
2035. Saathi's real threats are a compromised internet-facing box, a leaked
backup, an insider, and DPDP. PQC addresses none of them. It would look
impressive in a badge row and move no risk.

**Blockchain anything.** See §2.

**Their stacks.** TypeScript/Next.js/Solidity/Drizzle/Neon. Saathi is Python on
one box with Postgres. Nothing to port.

---

## The ordering that actually matters

If the goal is "Indofolk AI is genuinely secure", none of the above is first.
The ranked list is already on the board:

1. **PR-27** — the internet-facing box can *rewrite* Secrets Manager
2. **PR-22** — it can push to `main` on both forges
3. **PR-1** — health-adjacent data in an AWS account named "dev"
4. **PR-7** — no PITR; six-hour recovery point
5. *then* §3 (envelope encryption) and §2 (consent chain)

Encrypting columns while a compromised box can rewrite secrets and push to the
source of truth is a strong lock on a door standing beside an open window.

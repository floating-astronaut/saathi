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

---

# The OpenRouter ecosystem — surveyed 2026-07-27

`OpenRouterTeam` publishes far more than the inference API. Most of it is for
people who have not yet formed a product opinion. Saathi has one — safety at
priority 0, capability defined by absence, inference in India, no silent
fallback — so nearly every offering either duplicates a decision already made or
asks us to hand one to a third party. That is the frame; the exceptions below
are the useful part.

## `terraform-provider-openrouter` — right idea, wrong moment

Manages `api_key`, `byok_key`, `guardrail`, `observability_destination` as
resources, with data sources for workspaces, budgets, members, credits and
providers. Go, MIT-less (`licenseInfo: none`), 2 stars, created 2026-07-16.

**Wrong for the per-account keys.** Those are minted at runtime when a household
subscribes. Terraform is declarative and static; you cannot Terraform a key per
user without an application generating thousands of resource blocks into state.
Minting stays in the SDK, on `scheduled_turns` — see `AI_ROUTING.md` §5.

**Right for the static scaffolding**, which today exists only because someone
clicked it: the Indofolk AI workspace, the `amazon-bedrock` BYOK credential, the
attached guardrail, the observability flags. Nothing in this repo records any of
it — the same shape as **PR-2**, where the whole box was built by hand.

**Revisit when PR-2 gets a lane**, not before. Saathi has no Terraform at all, so
adopting it for three OpenRouter resources means a whole toolchain and state
backend for a small win while an entire hand-built box stays unmanaged. If
Terraform arrives it should arrive for the box, with OpenRouter riding along in
the same state — then one apply reproduces the box *and* its routing.

Two cautions when that day comes: the provider is days old with no licence file,
and it manages **API keys as resources**, so key material lands in Terraform
state. State would then need the same handling as Secrets Manager or it becomes
the softest place to steal from.

Also worth reading then: `workspace_budgets` may be a cleaner spend control than
per-key caps alone.

## `search-benchmarks` — steal the harness, and read the warning

An eval framework (Python 3.12, `uv`, MIT, actively maintained), forked from
Perplexity's `search_evals`. Runs a model+search configuration against
BrowseComp, HLE, DeepSearchQA and WideSearch and emits quality, cost, latency,
**confidence intervals** and run metadata into a self-contained report.
Resumable sampled sweeps.

The benchmarks are irrelevant — Saathi's question is Hinglish entity accuracy,
not open-web retrieval. **The harness shape is exactly what PR-9 needs.**

And their own README carries the warning we should have heard first:

> The report includes confidence intervals; **the leading engine estimates
> overlap** on these 100-task samples.

100 tasks per cell, 4,793 graded, and they still decline to name a winner among
the leaders. See PR-33 for what that implies about D-D.

**What to build for PR-9**, when it gets a lane: real elder utterances through
the actual `speech/correct.py` pipeline, scored on times and medicine names
(D-D's metric, not WER), reported with confidence intervals, cost and latency,
and resumable — a 100-utterance sweep across five models *will* be interrupted.

## `persona-hub` — useful, and a trap

Tencent's *"Scaling Synthetic Data Creation with 1,000,000,000 Personas"*, forked
and untouched since 2024-10-15. Mine personas, generate diverse synthetic data at
scale.

**Do not use it for PR-9.** PR-9's complaint is not that the corpus is small — it
is that entity accuracy was measured on **TTS-generated speech** rather than real
elders, and that synthetic audio is cleaner and differently distorted than a
70-year-old on a bad line with a television on. Generating more synthetic data
scales up the exact thing that already invalidates the numbers, and it would feel
like progress because the corpus grows and the score stays high. You would be
measuring how well the model transcribes a language model's idea of an Indian
elder.

**Where it genuinely helps: attacking the classifier, not building the corpus.**
Generating a thousand code-mixed phrasings of a hypoglycaemia episode or a
digital-arrest scam tests whether a **regex** catches variants — a domain where
synthetic diversity is the right tool, because nothing is being heard. Those
patterns are hand-written today; a persona-driven sweep would find the gaps.

## `lux` — no

Elixir framework for multi-agent "swarmed intelligence" by Spectral Labs. A
snapshot from Feb 2025, pushed the day it was created, never updated.

Beyond the language mismatch, it fails the same test as the Agent SDK: a
framework that orchestrates agents and executes tools takes over the decision
`provenance.allowed_tools()` and `assert_no_forbidden_tools()` exist to make.
That gate stays ours.

---

# Standing rule: the loop stays ours

**Any framework or SDK that executes tools on our behalf is refused.** Read them
for ideas; never let one own the loop.

The reason is not taste. PRD §12's guarantee — that prompt injection cannot cause
harm — is not enforced by prompt engineering. It is enforced by **which tools
exist in the list on this specific turn**:

    provenance.allowed_tools()     withholds every mutating tool on RELAYED content
    assert_no_forbidden_tools()    fails the suite if a tool could move money or read an OTP
    safety classifier, priority 0  runs before the model is constructed

A framework that runs the loop owns that list, and the guarantee moves into
someone else's code where it holds by convention rather than by construction.

And it is not hypothetical. **PR-23 was exactly this shape** — a path reaching
state-changing behaviour without passing the provenance check, which paused a
user's reminders because a relative forwarded an advert. That was inside code we
control and took an afternoon to fix. Inside a vendored framework it is a fork or
a wait.

There is also a scale mismatch worth stating plainly, because it will keep
looking like a gap: these frameworks solve multi-agent planning, RAG
orchestration and autonomous task decomposition. Saathi's agent has one turn, one
user, a handful of tools and a hard prefix budget, because the model has no
prompt caching. It is deliberately the least autonomous agent in the room. **That
is the product**, not a limitation to be grown out of.

Asked and refused on this basis, 2026-07-27: the OpenRouter **Agent SDK**
(TypeScript-only, and would be wrong in Python), **server-tools / fusion**,
**LangChain**, **`lux`**, and three general agent frameworks
(`Agentic-AI-Pipeline`, `agent-framework`, `AgentForge`).

## The narrower version, for API clients

The same instinct applies one level down, and has been settled three times:
**Sarvam**, **OpenRouter inference**, and the **WhatsApp Cloud API** are all
called with plain `httpx` rather than a vendor SDK, because in each case the
traps live in the exact bytes and parameters on the wire — `mode=indic-en`, the
WAV header, `allow_fallbacks: false`, the 24-hour window.

`wa/client.py` states the test better than any rule could: it should be
impossible to send free-form outside the window by forgetting to check, *because
you cannot reach the wire without passing the check*. A library that documents a
rule and one where the rule is structurally unavoidable are not the same
guarantee.

**Where an SDK does earn its place:** the OpenRouter **provisioning** client. It
is generated from their OpenAPI spec, so it is authoritative where the prose docs
are wrong by omission, it runs off the hot path on `scheduled_turns`, and it
touches no safety boundary. Dependencies it adds — `httpx`, `pydantic` — were
already present. That is the shape of an SDK worth taking: authoritative, off the
critical path, and nowhere near the tool list.

---

# `NousResearch/hermes-agent` — surveyed 2026-07-27

The framework itself falls under the standing rule above and needs no further
argument: it is a self-improving personal agent with a `terminal()` tool, a
code-execution tool, MCP subprocesses, a plugin loader and skills that execute
arbitrary Python at import time. It owns the loop by design. 221k stars, MIT,
Nous Research, and the rebrand trail in its topics (`openclaw`, `clawdbot`,
`moltbot`) plus `hermes claw migrate` say it absorbed an earlier project.

**Read `SECURITY.md` anyway.** It is the best security document any of these
surveys turned up, and it is valuable to us for a reason that has nothing to do
with adopting the code.

## The claim they make, and why they are right to make it

Their §2.2 names exactly one boundary: "The only security boundary against an
adversarial LLM is the operating system." (Hermes Agent `SECURITY.md` §2.2.)
Everything inside the process is then explicitly demoted to heuristic — the
approval gate, output redaction, the skills scanner, **and the tool allowlist**.
Their reasoning is that any in-process component screening model output is a
function of an attacker-influenced string, and shell is Turing-complete, so a
denylist over shell strings is structurally incomplete.

That conclusion is correct *for their shape*. Once a design includes arbitrary
shell and in-process plugin loading, there is genuinely nothing left inside the
process to stand on, and saying so out loud is more honest than most projects
manage.

## The inversion, which is the actually useful part

Saathi's boundary is the one Hermes says cannot exist: it is in-process, it is
the tool list, and it holds **only because the capability surface it would have
to survive is absent**. There is no shell tool, no code-execution tool, no
plugin loader, no MCP client, no skill import. `assert_no_forbidden_tools()` is
a boundary rather than a heuristic for the same reason a locked door is a
boundary in a room with no windows.

So this is the strongest available citation for the standing rule, from the
largest agent framework on GitHub: **adopting a framework of that shape would
move Saathi from "boundary by construction" to "the boundary is the OS" — and
Saathi has no OS boundary to fall back on.** `saathi-web` is a uvicorn process
running unsandboxed as `ubuntu`, with the database URL and the Meta token in
process memory and an AWS instance role attached to the box. Hermes can tell an
operator to choose a sandbox posture. We ship the posture.

Their own contributing guide supplies the illustration, warning that a venv
placed inside the directory the agent works in can be destroyed by a
relative-path command the agent runs against its own checkout — killing the
runtime mid-session. That is the failure mode of a loop that can run anything.

## Worth proposing to the SEC lane (not edited here — `SECURITY.md` is Codex's)

Our `SECURITY.md` lists twelve invariants as a flat set under "Security
Boundaries". Hermes's structure is better, and three parts are worth lifting:

1. **Separate boundaries from defence in depth, in the document.** Some of our
   twelve are load-bearing (HMAC verification before side effects; provenance
   withholding mutating tools; the absent-by-construction tool set; the window
   guard being unreachable-around). Others are mitigations that a determined
   attacker inside the process would defeat (secret redaction from logs and
   error fields). Calling both "boundaries" makes the strong ones sound like
   the weak ones.
2. **State that a finding needs a chained outcome.** Hermes's §3.2 rules that
   prompt injection *per se* — getting the model to emit something odd — is not
   a vulnerability without a concrete consequence behind it. For Saathi the
   chained outcome is specific and worth naming: injected text that reaches a
   mutating tool, crosses a user boundary, or sends a message. This is
   immediately relevant to the running SEC lane, since it is the line between a
   report and a finding.
3. **Say that out of scope does not mean unwelcome.** Their §3.2 redirects such
   reports to normal issues rather than closing them. Cheap, and it keeps
   people reporting.

## One thing we measured because of their §2.3

Hermes strips credentials from the environment handed to subprocesses, and is
careful to say this reduces casual exfiltration without being containment. We
have two subprocesses — `ffmpeg` (`speech/audio.py`) and `pdftoppm`
(`documents.py`) — so it was worth checking what they inherit.

Measured on the box, 2026-07-27: the running `saathi-web` process has **11
environment variables, all systemd and shell boilerplate** (`HOME`, `PATH`,
`LANG`, `INVOCATION_ID`, …). No secret is among them. The unit file has no
`EnvironmentFile=`, and `config.py` loads `.env` through
`SettingsConfigDict(env_file=".env")`, which reads the file from disk into
process memory. Secrets therefore never enter `os.environ`, and a child process
inherits nothing worth having. Both subprocesses are also spawned with
`create_subprocess_exec` and fixed argument lists — no shell, and no argument
derived from model output.

This is a real property and it is **accidental**. It would be undone by one
plausible tidy-up: moving `.env` into the systemd unit as `EnvironmentFile=` so
the service "reads config the normal way". That change would put the Meta token
and the database URL into the environment of every `ffmpeg` invocation. Do not
make it — and if `.env` ever does move into the unit, the subprocess calls need
an explicit scrubbed `env=` at the same time.

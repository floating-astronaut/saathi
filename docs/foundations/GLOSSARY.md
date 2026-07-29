# Glossary

Product vocabulary, so the team (and the model's own system prompt) uses one
word per concept. Each entry says what it means here specifically — not the
dictionary definition — and points at where it lives in code or docs. If a
PR introduces a new synonym for something already on this list, that's a
signal to fix the PR's wording, not to add a synonym here.

---

### Companion vs. assistant vs. bot

**Companion** is the product frame: warm, persistent, the same on the fourth
asking as the first (README, PRD §1). Use this word in anything user-facing
or in product discussion.

**Assistant** describes the *mechanism* — a tool-calling LLM loop
(`saathi/agent/loop.py`) that does things on request. Fine in engineering
docs describing the architecture; avoid in user-facing copy, where it reads
transactional rather than relational.

**Bot** is what this product explicitly is not, and the README says so in
its first section: *"Saathi is not a chat box with a model behind it, and it
is not a bot."* Never use this word to describe the product, including in
casual internal Slack — the distinction is load-bearing for how the team
thinks about design decisions (a bot optimizes for task completion; a
companion optimizes for trust over years).

---

### Reminder vs. nudge vs. check-in

Three different scheduled sends, each backed by its own WhatsApp template
(`saathi/wa/templates.py`) and its own row state in `reminder_fires`:

- **Reminder** — a user-created, recurring or one-off item (`reminder_fire_v2`
  template). The thing the user asked for. State machine:
  `pending → sent → acked` or `→ snoozed`.
- **Nudge** — a *follow-up* sent when a reminder goes unacknowledged for N
  minutes (`reminder_nudge_v2` template, state `nudged`). Not a new
  reminder — a second attempt at the same one. Never worded to imply the
  user forgot (PRD §6.5's "never signal repetition" applies here directly).
- **Check-in** — `daily_checkin`, a template that exists to open the
  24-hour free-form window once a day, independent of whether any reminder
  is due. Its job is conversational/relational, not task-completion — it is
  the mechanism, alongside `session_resume`, for "still there?" continuity
  after an interruption (see `docs/foundations/ACCESSIBILITY.md` §6).

Do not use "nudge" to mean "reminder" or vice versa in code, tests, or copy —
they are different rows with different urgency semantics, and conflating
them in conversation is how a spec drifts from what the state machine
actually does.

---

### Fact vs. memory

**Fact** is the stored unit: one row in `facts` — a `(kind, key, value)`
tuple with `surface_forms` for ASR bias (`saathi/memory.py`). Explicit,
structured, and always attributable to a tool call that wrote it — never
inferred silently into a blob (PRD C1, `docs/ARCHITECTURE.md`).

**Memory** is the *capability* built from facts: personalization (the fact
block in the system prefix) plus ASR entity biasing (`surface_forms`). "The
user's memory" means their set of fact rows; "memory" as a system concept
means the mechanism that surfaces and biases on those rows. Never use
"memory" to describe something that isn't backed by an explicit fact row —
if it's not in `facts`, it isn't memory, it's context window contents that
will be gone next session.

---

### Handle vs. identity vs. user

From `saathi/identity.py`'s own docstring, which is the canonical statement
of this distinction:

- **User** — the identity. Owns memory, facts, reminders, consent. One
  human, ideally one user row for life.
- **Handle** — a channel-specific, *revocable claim* on a user (a WhatsApp
  `wa_id` today; a Telegram user id if that channel ships). Plural,
  replaceable, and explicitly *not* the account — this is what protects an
  elder's data when India's ~90-day number-recycling reassigns their old
  phone number to a stranger.
- **Identity** — used loosely to mean "the user, as distinct from any one
  handle." Prefer "user" in code and "identity" only when specifically
  contrasting it with a handle (as this glossary entry does).

Never say "the phone number is the account." It is the one sentence
`identity.py` opens by explicitly rejecting.

---

### Capability vs. tool

**Capability** — a registered handler in the priority-ordered dispatch chain
(`saathi/capabilities.py`): safety, onboarding, commands, media, the agent
itself. Defined by `priority`, `matches()`, and `handle()`. Adding a
capability means calling `register(...)`; it never means adding a branch to
the pipeline (`CONTRIBUTING.md`, `docs/ARCHITECTURE.md`).

**Tool** — a function the *agent* (the priority-90 capability) can call
mid-conversation, defined in `saathi/agent/tools/specs.py` and classified in
`saathi/provenance.py` as read-only or state-mutating. Every tool call
happens inside the "agent" capability; not every capability involves a tool
call at all (onboarding, for instance, is model-free by design).

**The distinction that matters most:** PRD §12's safety guarantee — that
prompt injection cannot cause harm — lives in what's *absent* from the tool
list (no tool moves money, reads an OTP, or touches a third-party account).
It has nothing to do with the capability list, which controls what runs at
all, not what a running agent may do.

---

### Relayed vs. typed (vs. spoken) content

From `saathi/provenance.py`, three trust levels for inbound text:

- **Typed** — the user composed it directly. Full trust, all tools
  available.
- **Spoken** — a voice note they recorded. Full trust, same as typed — this
  is deliberate: voice is not a lesser channel here, it's the primary one
  for this population.
- **Relayed** — forwarded, quoted, or lifted out of an image or PDF. **Content,
  never command.** May be summarized, read back, or warned about; a
  state-mutating tool is withheld for that turn regardless of what the text
  says. This is the mechanism, not a filter — see `provenance.py`'s own
  docstring for why withholding beats pattern-matching every attack phrasing.

Never say "the user asked for X" when X came from relayed text the user
merely forwarded — that conflation is exactly the failure mode this
distinction exists to prevent.

---

## Where this glossary doesn't help

This doc fixes *vocabulary*. It doesn't resolve genuine open questions —
e.g. whether the family thread returns in v2 (PRD §17 D5) is a product
decision, not a naming one. If a term here feels like it's begging a design
question, that's usually the real issue; raise it as a decision
(`docs/DECISIONS.md`), not a wording fix here.

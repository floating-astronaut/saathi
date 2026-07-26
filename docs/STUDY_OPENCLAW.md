# Study: OpenClaw

Read 2026-07-26 — `openclaw/openclaw`, TypeScript, ~384k stars, 2.2 GB, pnpm
monorepo. Read the source, not just the README: `packages/plugin-sdk`,
`packages/net-policy`, `packages/normalization-core`, `extensions/whatsapp`.

Notes on what it does, and — more usefully — an honest account of what should
and should not transfer to a small eldercare product.

---

## What it is

A self-hosted personal assistant across 25+ messaging channels. Effectively
Claude Code in a chat window: it runs code, drives a browser, controls a
computer. Its user is technical and it runs on their own machines.

Structure:

    apps/         platform apps (macOS, Windows, iOS, Android)
    extensions/   ~100 plugins — channels AND model providers, side by side
    packages/     agent-core, llm-core, plugin-sdk, net-policy,
                  normalization-core, speech-core, media-understanding-common,
                  memory-host-sdk, session-url-contract
    src/          runtime

## Five things worth learning

### 1. Capability declaration is *data*, not code

A channel plugin declares itself in `package.json`:

```json
"openclaw": {
  "channel": {
    "id": "whatsapp",
    "approvalFlags": ["native"],
    "persistedAuthState": { "specifier": "./auth-presence", ... },
    "setup": { "fields": [{ "key": "authDir", "kind": "string", "cli": {...} }] }
  }
}
```

The runtime has never heard of WhatsApp specifically. It reads the manifest and
can generate setup UI, CLI flags and doctor checks for a channel it does not
know. **The declaration is the integration point.**

We got the instinct right with `Capabilities` in `channels/base.py` — encoding
session windows and button limits as data rather than `if channel ==`. What we
did *not* do is push it as far: our channel setup (env vars, credentials,
health checks) is still bespoke per channel.

### 2. Fail loudly; never fail open

From `net-policy/ip.ts`, on parsing IPv6 hextets:

> *"ipaddr.js guarantees 8 hextets; throw loudly on an impossible shape instead
> of failing open (a silent undefined here would skip SSRF embedded-IPv4
> blocking)."*

A security control that degrades to "allow" when its input is malformed is not a
control. This is the same reasoning behind our window guard raising rather than
returning False, and it deserves to be a stated principle rather than a habit.

### 3. Secret redaction belongs in a module, not in discipline

`net-policy/redact-sensitive-url.ts` carries a curated set of ~28 query-parameter
names that commonly hold credentials — `token`, `access_token`, `signature`,
`x_amz_security_token`, `client_secret`, `code`…

This is the control that would have prevented a real incident in this project:
earlier in development a Graph API response was printed whole, and it contained
a page access token. "Be careful with secrets" is not a control; a function that
redacts before anything is logged is.

### 4. Trust is a policy layer over tools, not a property of each tool

`PluginTrustedToolPolicyRegistration`, `exec-approvals-runtime`. Tools do not
each decide whether they are safe; a separate policy decides, per context, which
tools may run and which need approval.

For us the equivalent question is: which capabilities may act on the content of
a *forwarded* message versus something the user typed themselves? Right now that
distinction does not exist in our code, and forwarded content is the main
injection vector for this product.

### 5. Scheduled work is scoped to a session

`PluginSessionSchedulerJobRegistration`, `PluginSessionTurnScheduleParams` — a
plugin schedules a future *turn* within a session, rather than the runtime
owning one global scheduler.

Our reminder scheduler is global and knows about reminders specifically. That is
fine at one capability. It would not survive a second and third kind of
scheduled work (nudges, check-ins, re-verification prompts) without becoming the
same if/elif problem we just removed from the inbound path.

## What should NOT transfer

Being explicit, because the temptation is to copy a successful architecture
wholesale and inherit its costs.

- **The plugin API surface.** `plugin-entry.ts` exports well over a hundred
  types. That is the right size for a platform hosting ~100 third-party
  extensions and several LLM providers. We have eight capabilities and one
  model. Adopting that surface would add indirection we would pay for on every
  change and never recover.
- **Provider abstraction over models.** They abstract across many LLM providers.
  We deliberately chose one *regional* model so inference stays in India
  (decision D-D); an abstraction whose purpose is easy swapping would quietly
  invite swapping to a `global.` model and breaking that.
- **Exec, browser and computer control.** This is where OpenClaw's power comes
  from and where our product must not go. PRD §12's guarantee is that prompt
  injection cannot cause harm *because the capability does not exist*. Our user
  may not distinguish a forwarded scam from a real message, and the agent holds
  their medicine list. The right answer for them is the opposite of the right
  answer for a developer on their own laptop.
- **Multi-agent routing per peer.** Their isolation unit is a workspace per
  peer. Ours is a user identity with per-user memory, which is simpler and fits.

## Adopted

| Lesson | Where |
|---|---|
| Fail loudly, never fail open | stated principle; `net_policy` raises rather than returning "allowed" |
| Secret redaction as a module | `saathi/net_policy.py` — redact before logging, always |
| SSRF blocking before any user-supplied fetch | `saathi/net_policy.py` — required before web search ships |
| Capability declaration as data | already in `channels/base.py`; extend to setup/health |

## Queued from this study

- **Provenance on message content.** Mark text that arrived as a *forward* and
  refuse to let capabilities act on instructions found inside it. This is the
  trusted-tool-policy idea, applied to our actual threat.
- **Generalise the scheduler** from "reminders" to "scheduled turns" before a
  second kind of scheduled work exists.

---

## Ported (MIT, © 2026 OpenClaw Foundation)

`saathi/net_policy.py` — reimplemented in Python on stdlib `ipaddress`, taking
the two things that were genuinely learned rather than invented:

- the curated **sensitive query-parameter list** from
  `net-policy/redact-sensitive-url.ts`
- the **blocked IP range set**, including IPv4 smuggled inside IPv6
  (`::ffff:127.0.0.1`, `64:ff9b::/96`) — the classic miss

Both raise rather than return false, and a `RedactingFilter` is attached at the
root logger in both entrypoints so redaction does not depend on any caller
remembering.

This is not speculative hardening. The first test in `test_net_policy.py`
reproduces an actual leak from this project's development — a Graph API response
printed whole, carrying a page access token — and asserts the control catches it.

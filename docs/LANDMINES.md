# Landmines

Traps already paid for. Each one cost real time to find, and every one of them
*looked fine* from the outside — that is what makes them worth writing down.

Read this before touching **Meta**, **Cloudflare**, or **audio**.

---

## Audio: ffmpeg to a pipe writes a broken WAV header

**Symptom:** Sarvam rejects 2.5 seconds of audio with
`"Audio duration exceeds the maximum limit of 30 seconds"`.

**Cause:** WAV stores its length in the RIFF and `data` chunk headers. ffmpeg
cannot seek backwards on a pipe, so it writes the `0xFFFFFFFF` streaming
placeholder. Sarvam reads that as a near-infinite duration.

**Why it is nasty:** `ffmpeg -version` is healthy, the byte count is right, and
the file plays locally. **Every inbound voice note fails in production.**

**Fix:** write to a temp file so the header is patched (`speech/audio.py`).
`tests/test_audio.py` asserts the size fields are real.

---

## Speech: `codemix` returns Devanagari, which silently disables entity correction

**Symptom:** the correction pass repairs nothing, ever. No error.

**Cause:** the correction pass matches Latin tokens against the user's medicine
and people names. Under a Devanagari transcript there is nothing to match.

**Fix:** `mode=indic-en`. Same audio then gives `bomlodipin` → `Amlodipine`.
The PRD's recommended `codemix` is wrong for this product.

---

## Meta: never delete a template to fix it

**Symptom:** `"You can't change the category for this message template while
the existing English content is being deleted"` — for 24 retries over 12 minutes.

**Cause:** Meta holds a deleted template name for **up to four weeks** and
refuses a category change while the old content is deleting.

**Cost:** the names `reminder_fire` and `reminder_nudge` are burned. The live
templates are `reminder_fire_v2` / `reminder_nudge_v2`.

**Fix:** to change a template, **submit a new name**. Never delete first.

---

## Meta: utility templates get recategorised as MARKETING (7.5× the price)

**Symptom:** submitted `UTILITY`, came back `MARKETING`. At ₹0.8631 vs ₹0.115
this took the highest-volume template from ~₹10 to ~₹78/user/month.

**Cause:** Meta reads `"Namaste! {{1}} ka time ho gaya hai"` as an unsolicited
notification. UTILITY requires the body to visibly follow from something **the
user themselves requested**.

**Fix:** anchor the copy to the user's own prior action —
`"Aapne jo reminder set kiya tha — {{1}} ka time ho gaya hai."` Both then
classified UTILITY on submission.

---

## Meta Business Agent is provisioned on our number and must stay disabled

`GET api.facebook.com/{phone_number_id}/agent_config/settings` shows an agent
with `rollout.enabled = false` but `ai_audience: EVERYONE` and
`followup: {enabled: true, 3600s}`.

**Enabling it makes Meta's model the primary responder**, so inbound messages
never reach the deterministic §12 safety classifier — risk R7, the one
non-negotiable gate. Its knowledge model is business-scoped (a storefront
schema: delivery, returns, payment) with no per-user memory, which is the whole
of this product.

We *are* eligible (`is_eligible: true`). It is simply the wrong architecture
here. It is a strong fit for MeshPilot's ecommerce brands.

**Worse than it first looked:** `GET /{waba}/subscribed_apps` shows the Business
Agent app (`1143680903703001`) is *already subscribed to our WABA's webhooks*,
alongside ours. Only `rollout.enabled = false` keeps it quiet. A subscribed app
plus one toggle is all that separates us from Meta's model answering first.
Check this list after any Business Manager change.

---

## Cloudflare: Browser Integrity Check 1010-blocks webhooks, and fakes a passing security test

**Symptom:** `/healthz` returns 200 through the tunnel, but every webhook call
returns 403.

**Cause:** `browser_check: on` for the zone. Meta's calls are server-to-server
with no browser signature, so BIC rejects them with error 1010.

**Why it is genuinely dangerous:** the wrong-token and unsigned-POST probes
*also* returned 403 and looked exactly like the app correctly rejecting them.
The security checks appeared to pass while proving nothing. Only comparing
on-box (`200 CHALLENGE-OK`) against through-Cloudflare (`403 server=cloudflare`)
exposed it.

**Fix:** a config rule scoped to the hostname (`http_config_settings`,
`bic: false`) rather than disabling BIC zone-wide. Needs a token with **Config
Settings Write** — neither the canonical box token nor the master token has it.

**Rule to keep:** when a security check passes, confirm it passed *for the
reason you think*. Test the positive case too.

---

## Bedrock: model access is per-account, and the "availability" field is not the gate

`get-foundation-model-availability` reported `NOT_AVAILABLE` for a model that
invoked perfectly, and `AVAILABLE` for one that returned `AccessDenied`. The
real gate for Anthropic models is the one-per-account use-case form.

Requesting new model access can also move an account off a grandfathered
entitlement onto the form-required path, breaking models that worked minutes
earlier. It did, in the dev account.

---

## AWS: never put a secret in an SSM command

SSM `RunShellScript` command text is retained and visible in the console. Any
secret embedded in a command leaks into the audit trail permanently.

**Fix:** Secrets Manager + the instance role. The box fetches its own secrets
(`/usr/local/bin/saathi-env-sync`); nothing sensitive crosses SSM.

---

## Terminal: a CLI device-flow login hangs silently when driven through a pipe

**Symptom:** `gh auth login --web` produces **no output at all** — a zero-byte
log — and never returns. It looks like a network stall or a hung API call.

**Cause:** `gh`'s prompt library sizes the terminal by emitting a cursor-position
query (`ESC[999;999f ESC[6n`) and then *blocking until the terminal replies* with
`ESC[row;colR`. A pipe never replies. `script(1)` does not help: it allocates a
PTY for the child, but nothing on the master side answers the query either.

**Why it is nasty:** nothing errors, nothing times out, and the log is empty
rather than truncated — so the natural conclusion is "the network is slow" or
"the flag is wrong", and neither is true. `script -f` (flush) fixes the
buffering and still leaves you hanging at the same prompt.

**Fix:** run it under `tmux`, which is a real terminal emulator and answers the
query:

    tmux new-session -d -s auth -x 200 -y 50 "gh auth login --web ..."
    tmux send-keys -t auth "y" Enter
    tmux capture-pane -p -t auth

Applies to any interactive CLI login, not just `gh`.

---

## Git: `%G?` returns `N` on correctly signed commits when allowed-signers is unset

**Symptom:** `git log --pretty='%G?'` shows `N` on every commit, which reads as
"not signed" — and `CONTRIBUTING.md` requires `G`.

**Cause:** the commits *are* SSH-signed (`git cat-file commit HEAD` shows the
`gpgsig` block). SSH signature **verification** needs
`gpg.ssh.allowedSignersFile` to be configured and to exist. Unset, git cannot
verify, so it reports `N` — the same character it would use for genuinely
unsigned work.

**Why it is nasty:** it looks exactly like a discipline breach that has not
happened, and invites someone to "fix" signing that was never broken.

**Fix:** check for the signature itself before believing `%G?`:

    git cat-file commit HEAD | grep -q '^gpgsig' && echo signed

Configure `gpg.ssh.allowedSignersFile` on any box that needs to *verify* rather
than merely produce signatures.

---

## Testing: a fake connection will certify SQL that Postgres rejects

**Symptom:** unit tests green, statement fails the first time it runs for real.

**Cause:** the suite's fake `Conn` records the SQL string and returns canned
rows. It never parses anything. `sweep_stuck` shipped with

    set state = case when attempts >= 5 then 'failed' else 'pending' end

which Postgres refuses — `case` yields `text` and the column is the `turn_state`
enum — while every test passed.

**Why it is nasty:** the failure is invisible until the code path runs in
production, and this particular path only runs *after a worker has already
crashed*. The test suite reported 301 passing.

**Fix:** the cast (`(...)::turn_state`), and more usefully the habit — run any
new statement against the real database once:

    sudo -u postgres psql -tA saathi <<'SQL'
    \set ON_ERROR_STOP on
    <the statement, parameters bound as the code binds them>
    SQL

Fakes prove shape. Only Postgres proves validity.

---

## glab: the git credential helper does not refresh an expired OAuth token

**Symptom:** `git push gitlab` fails with

    remote: HTTP Basic: Access denied...
    glab auth git-credential: "erase" is an invalid operation.
    fatal: Authentication failed for 'https://gitlab.com/...'

while `glab auth status` cheerfully reports *"✓ Logged in as ..."*.

**Cause:** `glab auth login --web` stores an **OAuth grant**, not a PAT. The
access token expires every **two hours**; only the refresh token is persisted
(`oauth2_refresh_token`, with `oauth2_expiry_date`). glab's *own* commands
refresh transparently on use — but `glab auth git-credential`, which git calls,
hands over the stale token without refreshing first.

**Why it is nasty:** two ways.

1. `glab auth status` is not a health check. It reports the grant, not whether
   the access token is currently valid.
2. `git push origin && git push gitlab` pushes GitHub **first**. GitHub succeeds,
   GitLab fails, and you are left with the remotes **diverged** — the one state
   `CONTRIBUTING.md` forbids. The failure is loud, but only if you look: the
   GitHub push line scrolls past looking like success.

**Fix:** force a refresh before pushing, then push:

    glab api user >/dev/null      # any glab command refreshes the token
    git push origin main && git push gitlab main

**Always verify both remotes afterwards** rather than trusting the exit code:

    git ls-remote origin main | cut -c1-7
    git ls-remote gitlab main | cut -c1-7

A PAT would not expire this way. The OAuth grant was chosen because glab 1.53
has no device flow and a browser-based login kept the token out of the operator's
hands — a deliberate trade, recorded so the two-hour expiry is not a surprise.

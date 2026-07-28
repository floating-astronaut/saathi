# Daily-life OS roadmap

Status: **product frame accepted 2026-07-28; LIFE-1 forwarded-content guidance implemented; remaining lanes open.**

Saathi is a **WhatsApp operating system for daily life** for non-tech-savvy 40+
and elder users in India. It is not a generic chatbot, shopping bot, booking
agent, productivity dashboard, or remote browser operator.

The product job is to remove the moment where a user thinks: *I do not know what
this means, where to start, what to say, what to remember, or which app to open.*

---

## 1. Product frame

Core verbs:

- **read this** — messages, bills, labels, PDFs, screenshots, tickets, notices;
- **explain this** — what it means, what matters, what is risky, what to do next;
- **remind me** — medicines, bills, appointments, errands, calls;
- **draft this** — replies, requests, complaints, polite family/work messages;
- **remember this** — people, places, medicines, preferences, recurring chores;
- **is this safe?** — scams, OTP/PIN/bank pressure, fake notices, risky links;
- **open the right place** — maps, provider/search links, app handoffs;
- **what should I do next?** — one concrete next step, not a dashboard.

The magic is not autonomy. The magic is reducing articulation and navigation
friction while the user stays in control.

## 2. Current shipped base

Already shipped and usable as foundations:

- WhatsApp text and voice-note conversation;
- deterministic onboarding;
- priority-0 safety classifier before the model;
- memory and explicit erasure;
- reminders with acknowledgement and snooze;
- image/document admission and reading paths;
- world lookup for weather/fact/web answers through configured providers;
- `build_cart` with India-first provider handoff links;
- per-account model spend keys and the $5 once free grant.

Important absences that remain product law:

- no payment/order/checkout/book/reserve tool exposed to the model;
- no OTP/PIN/password reading or forwarding;
- no third-party account operation;
- no hidden browser automation;
- no medical/legal/financial advice.

## 3. Build order

### LIFE-1 — read/explain/action from forwarded content

Highest value because it matches daily WhatsApp behavior. Users forward bank
SMSes, courier messages, school notices, society announcements, medicine labels,
bills, screenshots and PDFs. Saathi should answer:

- what this says;
- whether it looks risky;
- amount/date/place/person/action required;
- one next step;
- whether to set a reminder, draft a reply, or open a link.

Acceptance for implementation: forwarded text/image/PDF stays fenced as
third-party content, cannot trigger commands, and produces a concise explanation
plus one next action.

Built 2026-07-28: the relayed-content fence and system prompt now tell the model
to skim and summarise the forward first, extract amount/date/place/person/action
when present, flag scam pressure, and then ask one follow-up question: what would
the user like Saathi to do with it? Mutating tools remain withheld on `RELAYED`
turns, so the follow-up does not imply any action has been taken.

Captionless media follow-up, 2026-07-28: a PDF or image sent without caption is
still treated as a request to read/explain it. Captionless images default to the
document/daily-life reading prompt, because bills, notices and screenshots often
arrive as one media message with no text. Medicine-specific interpretation still
requires a caption such as dawa/tablet/medicine.

### LIFE-2 — daily task manager beyond reminders

Reminders are timed; many daily jobs are not. Add a lightweight task list for:

- call plumber;
- send report to doctor;
- ask son to book ticket;
- check bill payment;
- buy household item later;
- follow up with society office.

Acceptance: create/list/mark-done/postpone tasks by natural language; reminders
can attach to tasks, but a task can exist without a due time.

### LIFE-3 — bills and due dates

Bills are one of the most common non-tech daily tasks. Saathi should extract:

- biller;
- amount;
- due date;
- late fee/risk words;
- customer/account reference only when safe to display;
- payment instruction as explanation, not payment action.

Acceptance: from forwarded SMS/image/PDF, extract due date and amount, offer a
reminder, and warn on scam-shaped payment pressure. No payment link is followed
server-side.

### LIFE-4 — draft replies and messages

The user often knows the intent but not the wording. Drafting is cheap, safe and
daily-useful:

- landlord/rent delay;
- doctor report note;
- society complaint;
- school/office message;
- polite family reply;
- customer support complaint.

Acceptance: produce short WhatsApp-ready text in the user's selected script, with
one optional tone choice only when needed.

### LIFE-5 — stronger scam shield

Scam handling is product-defining for this audience. Extend beyond the current
OTP/PIN/KYC shape into:

- fake courier/customs/police;
- electricity disconnect threats;
- loan/investment/lottery;
- fake job or pension scheme;
- urgent UPI/payment pressure;
- remote-support app installation requests.

Acceptance: deterministic high-risk patterns still block before the model;
lower-risk suspicious content produces a warning plus a safe next step and, when
appropriate, a helpline path.

### LIFE-6 — local errand and app handoffs

Use the commercial-actions boundary for daily errands:

- grocery/food links;
- maps/directions;
- plumber/electrician/local shop search;
- clinic/lab/pharmacy search;
- movie/event/travel search links.

Acceptance: use free/official URL builders and already-wired Google search first;
no paid vendor, login, booking, order or checkout.

## 4. Product sequencing rule

Build daily-life recurrence before rare-event sophistication. A capability that
helps every week beats one that helps twice a year, unless the rare task carries
major safety value.

So: forwarded-message reading, tasks, bills, drafting and scam shield outrank
flight search, ticket booking and full cart automation.

## 5. UX rules for this frame

- one next step, not five;
- one question per turn;
- preserve the original text/list so it can be forwarded;
- use buttons only for bounded choices;
- speak in the user's chosen script;
- never claim an action happened when Saathi only made a link or draft;
- every refusal should still help: explain what Saathi can safely do instead.

## 6. Non-goals for now

- autonomous purchasing or booking;
- generic browser operation;
- family/caregiver control plane;
- medical advice;
- financial advice;
- storing copies of sensitive documents beyond the minimum needed to answer the
  current turn, unless a separate retention lane designs it.

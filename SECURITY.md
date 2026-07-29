# Security Policy

Saathi is health-adjacent software for older adults on WhatsApp. Treat safety, privacy, consent, reminders, and channel integrity as security-sensitive, even when the bug does not look like a conventional exploit.

## Reporting

Report vulnerabilities privately to the repository owner/operator. Do not open public issues with exploit details, credentials, personal data, live webhook payloads, phone numbers, or production identifiers.

Include:

- the affected file, endpoint, command, or operational surface
- the concrete user impact
- reproduction steps that avoid real user data
- whether the issue touches WhatsApp, Meta, AWS, Postgres, Bedrock, Sarvam, media retention, reminders, consent, or erasure

## Security invariants

- Safety classification runs before the LLM and must not be bypassable by prompt injection, forwarded messages, media captions, or document text.
- Relayed content may be read, explained, or warned about; it must not be obeyed as a command.
- State-changing agent tools must be unavailable for relayed content and must be re-authorized at dispatch, not only hidden from the prompt.
- No tool may move money, read OTPs, log into accounts, place orders, or book travel.
- WhatsApp webhook POSTs require valid `X-Hub-Signature-256`; unsigned payloads are untrusted.
- Free-form WhatsApp sends must pass the 24-hour window guard. Templates are the only approved outside-window outbound path.
- User erasure, pause/resume, consent, and onboarding state are product-security controls and must work without depending on the LLM.
- Secrets must not be printed, logged, copied into SSM command text, or stored in generated artifacts.
- Voice media retention is bounded by policy and infrastructure; deletion must remove stored objects immediately when the user exercises erasure.
- Reminder delivery is safety-sensitive. Silent loss, duplicate sends, and unreachable acknowledgement paths are production risks.

## Severity guide

- **Critical:** safety classifier bypass, unauthorized erasure or data exposure, credential leak with production write access, forged webhook handling, or any path that can cause harmful medical or financial action.
- **High:** missed health-adjacent reminders without alerting, relayed-content command execution, cross-user state mutation, consent bypass, or durable personal-data retention beyond policy.
- **Medium:** privacy-control gaps with limited exploitability, logging gaps that block incident response, or missing defense-in-depth on LLM/tool boundaries.
- **Low:** documentation drift, hardening gaps, and operational controls that are acceptable only for internal testing.

## Out of scope for public testing

Do not test against real users, the live WhatsApp number, Meta Business Manager, AWS resources, production databases, or third-party accounts without explicit operator approval. Use local tests, synthetic payloads, and value-blind evidence.

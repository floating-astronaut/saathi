<!--
Source:   https://vobiz.ai/docs/xml/dial
Captured: 2026-07-27

*** THIS IS A SUMMARY, NOT A TRANSCRIPT. ***

It was produced by a fetch tool that summarises rather than returning the page,
so it is second-hand by the standard set in ../README.md. Treat it as a lead, not
as evidence. Re-capture verbatim through a rendering browser before relying on an
attribute or default stated here.
-->

# Dial (summary)

`<Dial>` bridges the current call (A-leg) to one or more destinations (B-legs).
Nested inside a `<Response>` root. Child elements: `<Number>` for PSTN, `<User>`
for SIP/WebRTC.

## Attributes

| Attribute | Purpose | Default |
|---|---|---|
| `callerId` | Caller ID presented on the B-leg (E.164 required for PSTN) | derived from A-leg |
| `timeout` | Seconds to wait for B-leg answer | not stated |
| `timeLimit` | Maximum connected duration, seconds | 14400 |
| `action` | Final-result callback URL | — |
| `method` | HTTP method for `action` | POST |
| `callbackUrl` | Real-time event callback URL | — |
| `callbackMethod` | HTTP method for callbacks | POST |
| `redirect` | Execute XML returned by `action` | true |
| `dialMusic` | URL for A-leg audio while connecting | "real" |
| `hangupOnStar` | End the bridge when `*` is pressed | false |

## Stated requirement

> For PSTN forwarding and transfer flows, set `callerId` to a Vobiz number owned
> or authorized by your account.

Omitting it can fail B-leg creation, because the derived number may not be
authorised for outbound.

## Example

```xml
<Dial callerId="+14155550100" timeout="30">
  <Number>+14155550101</Number>
</Dial>
```

## Callbacks

`callbackUrl` receives `DialAnswer`, `DialConnected`, `DialDigitsMatch`,
`DialHangup`. The `action` callback receives `DialStatus` (completed, busy,
failed, timeout, no-answer, …) and `DialHangupCause`.

## What we actually ran, and it worked

Used on 2026-07-27 to receive the WhatsApp voice verification code on
`+918071581944`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Dial callerId="+918071581944">
    <Number>+91XXXXXXXXXX</Number>
  </Dial>
</Response>
```

`callerId` set to the Vobiz-owned DID itself, per the requirement above.

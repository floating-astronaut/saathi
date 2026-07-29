Source:   https://developers.facebook.com/documentation/business-messaging/whatsapp/calling
Captured: 2026-07-27
API:      WhatsApp Business Calling API / Cloud API Calling; version not stated in supplied transcript

# Cloud API Calling



## Overview

The WhatsApp Business Calling API enables you to initiate and receive calls with WhatsApp users using Voice over Internet Protocol (VoIP).

## Value proposition (concise)

WhatsApp Business Calling: voice and video calling with global reach.

| Value | Description |
| --- | --- |
| **Unified communication** | Message and call from one number, worldwide. |
| **Branding and trust** | Built-in brand identity, verification, and global availability. |
| **Customer relationship** | A single point of contact for inbound and outbound communication. |
| **Sales and support** | Unify marketing and support channels in one place. |
| **Rich features** | Video*, screen share*, and call customization. |
| **Call deflection** | Move voice calls to WhatsApp chat. |
| **Customer convenience** | Free for your customers and available globally. |
| **Record keeping** | One thread with a centralized, long-term record. |

### Benefits for end-users

| Value | Description |
| --- | --- |
| **Universal access** | Free and available globally. |
| **Enhanced safety** | Built-in platform verification. |
| **Centralized history** | One unified thread for all voice and text history. |
| **Integrated voicemail** | Voicemail playable within the chat. |

**Note:** * Feature planned or in development. Reach out to your Meta or partner for more details.

## Value proposition (detailed)

The WhatsApp Business Calling API allows businesses to integrate voice and video* calling directly into their customer engagement strategy, offering a trusted, unified, and feature-rich communication channel.

| Feature | Benefit for your business |
| --- | --- |
| **Unified communication** | **One number for all communication.**<br>Use a single, verified WhatsApp number for all messaging and calling (inbound and outbound), and switch between chat and call, including chatting while on a call. |
| **Branding and trust** | **Built-in brand identity and verification.**<br>WhatsApp has native support for brand identity with security and verification, which applies globally and eliminates the need for region-specific third-party trust providers. |
| **Customer relationship** | **A single point of contact for customers.**<br>A single point of contact for both inbound and outbound communication supports ongoing customer relationships. |
| **Sales and support** | **Unify marketing and support channels.**<br>Centralize lead management by unifying support and marketing channels, which streamlines operations and supports product upsell and cross-sell. |
| **Rich features** | **Video*, screen sharing*, and call controls.**<br>Beyond voice, businesses can engage customers with video calls and screen sharing for richer, more detailed support and service. Businesses also control the calling experience by configuring calling hours, managing call icon visibility, sending call buttons with expiry, and using call deep links. |
| **Call deflection** | **Move calls to WhatsApp to improve deflection rates.**<br>By moving calls to WhatsApp, businesses can direct customers to chat, using interactive messaging templates to improve deflection and reduce voice-only support costs. |
| **Customer convenience** | **Free and globally accessible for customers.**<br>Offer your customers a globally accessible communication method that is free for them to use. |
| **Record keeping** | **One thread with a centralized, long-term record.**<br>Maintain a single, persistent thread of all text and voice communications with the customer, serving as a centralized, long-term record for reference. |

**Note:** * Feature planned or in development. Reach out to your Meta or partner for more details.

## Architecture

(_Right click image and choose "Open in new tab" for enlarged image_)

### Signaling and media possible configurations

|  | Default configuration after enabling calling | SIP with WebRTC | SIP with SDES media |
| --- | --- | --- | --- |
| Signaling protocol | Graph APIs + Webhooks | SIP (needs explicit [[enablement](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip#configure-update-sip-settings-on-business-phone-number)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip#configure-update-sip-settings-on-business-phone-number)) | SIP (needs explicit [[enablement](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip#configure-update-sip-settings-on-business-phone-number)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip#configure-update-sip-settings-on-business-phone-number)) |
| Signaling transport | HTTPS | TLS | TLS |
| Media protocol | WebRTC (ICE + DTLS1 + SRTP) | WebRTC (ICE + DTLS + SRTP) | [[SDES](https://datatracker.ietf.org/doc/html/rfc4568)](https://datatracker.ietf.org/doc/html/rfc4568) SRTP (needs explicit [[enablement](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip#configure-sdes-for-srtp-key-exchange-protocol)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip#configure-sdes-for-srtp-key-exchange-protocol)) |
| Audio codec2 | OPUS | OPUS | OPUS |

**Notes**
1. You can use SDES instead of ICE+DTLS with Graph API + Webhook signaling
2. Additional audio codecs supported: `PCMA`, `PCMU`

## Get started

### Step 1: Prerequisites

Before you get started with the Calling API, ensure that:

1. [[Your business number is in use with Cloud API](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers)](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/phone-numbers) (not the WhatsApp Business app).
1. Subscribe your app to the `calls` webhook field (unless you plan to use [[SIP](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip)).
1. The same app should also be [[subscribed to the WhatsApp Business account](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint#configure-webhooks)](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint#configure-webhooks) of your business phone number.
1. This app should have messaging permissions (`whatsapp_business_messaging`) for the business number.
1. The business must have a daily [[messaging limit](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits)](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits) of at least 2,000 unique recipients. More details on [[scaling your account capabilities](https://www.facebook.com/business/help/595597942906808)](https://www.facebook.com/business/help/595597942906808).
1. [[Enable Calling features on your business phone number](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings).

### Step 2: Configure calling features

The WhatsApp Business Calling API offers a number of features that affect when and how calling features appear to users on your WhatsApp profile.

* Inbound call control allows you to prevent users from placing calls from your business profile
* Business call hours allows you to avoid missed calls and direct users to message when your call center is closed
* Callback requests offer users the option to request a callback when you don't pick up a call or if your call center is closed

[[Learn more about call control settings](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#parameter-details)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#parameter-details)

### Step 3: Make and receive calls

**Warning:** You can test your WhatsApp Calling integration using public test numbers and a sandbox WhatsApp Business account.

[[Learn more about testing your WhatsApp Calling API integration](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling#testing-and-sandbox-accounts)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling#testing-and-sandbox-accounts)

Cloud API Calling offers two call initiation paths:

* **User-initiated calls:** Calls that are made from a WhatsApp user to your business
* **Business-initiated calls:** Calls that are made from your business to a WhatsApp user

## Testing and sandbox accounts

**Warning:** Sandbox accounts are only available to Tech Partners.

[[Sandbox accounts](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sandbox)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sandbox) and public test numbers enable you to test your WhatsApp Calling API integration with relaxed calling limitations.
Specifically, business-initiated calling limits are relaxed for sandbox accounts and public test numbers to help integration and testing efforts.

### Limits (per business + WhatsApp user pair)

* Sandbox accounts can send **25 call permissions per day** and **100 per week** (compared to 1 per day and 2 per week for production accounts)
* When business-initiated calls go unanswered or are rejected
  * **5 consecutive unanswered calls** result in a system message to reconsider an approved permission (compared to 2 consecutive unanswered calls for production accounts)
  * **10 consecutive unanswered calls** result in an approved permission being automatically revoked (compared to 4 consecutive unanswered calls for production accounts).

You obtain a public test number after completing the [[Get Started flow](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started)](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started).

Your business isn't required to have a daily [[messaging limit](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits)](https://developers.facebook.com/documentation/business-messaging/whatsapp/messaging-limits) of 2,000 unique recipients to test Calling API features when using public test numbers and Sandbox accounts.

Calling is disabled by default on test numbers. You must [[configure calling features in phone number call settings](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#configure-call-settings)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#configure-call-settings) before using the Calling API on a test number.

[[Learn more about sandbox accounts for calling](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview#sandbox-accounts)](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview#sandbox-accounts)

## Availability

### User-initiated calling

User-initiated calling is available in [[every location Cloud API is available](https://developers.facebook.com/documentation/business-messaging/whatsapp/support#country-restrictions)](https://developers.facebook.com/documentation/business-messaging/whatsapp/support#country-restrictions).

### Business-initiated calling
Business-initiated calling is available in [[every location Cloud API is available](https://developers.facebook.com/documentation/business-messaging/whatsapp/support#country-restrictions)](https://developers.facebook.com/documentation/business-messaging/whatsapp/support#country-restrictions), **except the following countries:**

* United States
* Canada
* Egypt
* Vietnam
* Nigeria

**Note:** The business phone number's country code must be in this supported list. The consumer phone number can be from any [[country where Cloud API is available](https://developers.facebook.com/documentation/business-messaging/whatsapp/support#country-restrictions)](https://developers.facebook.com/documentation/business-messaging/whatsapp/support#country-restrictions).

## Next steps

Use the guides below to integrate calling features in your application:

* [[Learn how to receive user-initiated calls](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/user-initiated-calls)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/user-initiated-calls)
* [[Learn how to place business-initiated calls](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/business-initiated-calls)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/business-initiated-calls)
* [[Learn how to drive consumer awareness of calling availability in your business](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-button-messages-deep-links)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-button-messages-deep-links)

## Changelog

Use this table as a centralized place to keep track of feature updates related to WhatsApp Business Calling APIs.

| Date | Title | Description |
| --- | --- | --- |
| March 23, 2026 | Support for G.711 (PCMA, PCMU) audio codec | New section for G.711 (PCMA, PCMU) audio codec configuration in call settings, including guidelines on transcoding, audio quality, and bandwidth considerations. [[Learn more about audio codec settings](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#audio-codec)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#audio-codec). |
| January 27, 2026 | Calling restrictions based on user feedback are now in effect | Learn more about [[calling restrictions based on user feedback](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#calling-restrictions-for-user-feedback)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#calling-restrictions-for-user-feedback). |
| December 19, 2025 | Update in business initiated call limit | The number of business-initiated calls per user has been increased to 100 per day from 10 per day.<br><br>[[Learn more about business-initiated call limits](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/user-call-permissions#limits--per-business---whatsapp-user-pair-)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/user-call-permissions#limits--per-business---whatsapp-user-pair-) |
| December 10, 2025 | Introduced `restrict_to_user_countries` for call icon settings | Now you can control in which countries the call icon should be visible. [[Learn more about call icon country settings](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#call-icons)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#call-icons). |
| October 13, 2025 | * Update in business initiated call limit<br>* Added "Testing and Sandbox" section to documentation | The number of business-initiated calls per user has been increased to 10 per day from 5 per day.<br><br>[[Learn more about business-initiated call limits](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/user-call-permissions#limits--per-business---whatsapp-user-pair-)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/user-call-permissions#limits--per-business---whatsapp-user-pair-)<br><br>A [[Testing and Sandbox accounts](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling#testing-and-sandbox-accounts)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling#testing-and-sandbox-accounts) has been added to the documentation |
| September 29, 2025 | Asterisk integration guide | New guide to [[integrate with Asterisk](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/integration-examples#asterisk-using-sip)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/integration-examples#asterisk-using-sip) |
| September 24, 2025 | Context propagation from call buttons and deep links | Specify an opaque string in call buttons or call deep links to help with tracking the origin of user-initiated calls. [[Learn about call buttons and deep links](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-button-messages-deep-links)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-button-messages-deep-links) |
| September 8, 2025 | Health status API calling update | [[Health Status API](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/health-status)](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/health-status) is now extended to include a new `can_receive_call_sip` field to help you self-diagnose issues related to [[SIP](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/sip) setup |
| September 5, 2025 | Introduced new low call pickup calling restrictions | Low call pickup rate restrictions are now in effect. Learn more at [[Calling Restriction for Low Call Pickup Rates](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#calling-restrictions-for-low-call-pickup-rates)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#calling-restrictions-for-low-call-pickup-rates) |
| July 21, 2025 | Account settings update webhooks | Get webhooks when settings are updated. [[Learn about settings update webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#settings-update-webhooks)](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/call-settings#settings-update-webhooks). |

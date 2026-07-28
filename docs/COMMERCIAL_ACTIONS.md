# Commercial actions and deeplinks

Status: **contract written 2026-07-28; implementation not started.**

Owns: shopping, cart assembly, flights, movie/event tickets, local service links,
and any internet capability that helps a user move from an intent to a third-party
merchant, marketplace, booking flow or map/app surface.

Related: `PRD.md` §4-5, `ARCHITECTURE.md` (capability absence),
`DECISIONS.md` D-C/D-E/D-U, `USAGE_LEDGER.md` (paid search),
`saathi/agent/tools/specs.py` (`FORBIDDEN_TOOL_NAMES`).

---

## 1. Product law

Saathi may **find, compare, explain, assemble and link**. It may not transact.

Allowed outcomes:

- a shortlist of options with prices, times, caveats and source links;
- a cart draft or itemised shopping list the user can inspect;
- a provider deep link, search URL, directions URL, event URL or booking URL;
- a WhatsApp interactive button whose only effect is opening a URL or selecting a
  displayed option inside Saathi;
- a reminder/follow-up to complete something later.

Forbidden outcomes, even with user consent:

- purchase, checkout, reservation, ticket issuance or order placement;
- payment collection except Saathi's deterministic paywall path in D-U;
- reading, asking for, forwarding or storing OTPs, PINs, passwords, card data,
  UPI handles, netbanking credentials or third-party session cookies;
- logging into or operating a third-party account on the user's behalf;
- hidden browser automation, scraping a logged-in session, or clicking through a
  provider flow after the user can no longer see each step;
- using a user's stored memory to infer a commercial consent they did not give in
  the current task.

The durable guarantee is the same one already in `ARCHITECTURE.md`: **capability
is defined by absence.** A future implementation may add tools named
`search_flights`, `search_events`, `build_cart`, `make_maps_link` or
`make_provider_link`; it must not add tools named like `checkout`, `place_order`,
`book_flight`, `buy_ticket`, `charge`, `login`, `read_otp` or their equivalents.

## 2. What the market has already cracked

### Offer/search APIs

Flights and tickets are already modeled as search/offer objects. IATA NDC frames
airline retailing around offers and orders: search returns offers, while order
creation/ticketing is a later step. Duffel follows that shape: an offer request
captures passengers and slices, then returns offers that can be bought. Amadeus
also separates Flight Offers Search, price confirmation and Create Orders.

For Saathi, use only the **offer/search** half until a later written decision
changes the transaction boundary. This means live availability and price can be
shown, but the final booking happens on the airline/OTA/provider page the user
opens.

Sources:

- IATA NDC / modern airline retailing: https://www.iata.org/en/programs/airline-distribution/retailing/ndc/
- IATA developer passenger standards: https://developer.iata.org/en/passenger/
- Duffel offer requests: https://duffel.com/docs/api/v2/offer-requests
- Amadeus flight APIs: https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/resources/flights/

### Discovery APIs plus purchase URLs

Movie, sports and concert tickets often expose discovery data separately from
transaction APIs. Ticketmaster's Discovery API searches events, attractions and
venues, and event detail includes a website URL for buying tickets; partner
transaction APIs are separate.

For Saathi, that is the right shape: search the public/discovery surface, show
2-3 options, and make the CTA the official event/provider URL.

Source:

- Ticketmaster Discovery API: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/

### Structured data and merchant feeds

Google and schema.org show the common web pattern: merchants publish products,
offers, availability and potential actions, while the actual buy action belongs
to the merchant's page or supported checkout surface. Google merchant listings
require pages where the shopper can purchase from that merchant; aggregators and
review/search surfaces are a different class.

For Saathi, structured data is useful for reading and ranking public pages, but
it is not permission to transact. A discovered `BuyAction` is metadata for a link,
not an executable tool.

Sources:

- schema.org Actions: https://schema.org/docs/actions.html
- Google Product structured data: https://developers.google.com/search/docs/appearance/structured-data/product
- Google merchant listing structured data: https://developers.google.com/search/docs/appearance/structured-data/merchant-listing

### Universal deeplinks

Some platforms expose stable URL formats. Google Maps URLs are a good example:
they launch Maps across devices for search, directions or place views, require
`api=1`, and need URL-encoded parameters with a 2,048 character limit.

For Saathi, prefer official URL builders where they exist. A URL builder is safe
when it only represents visible intent: destination, query, dates, venue, item
names, passenger count. It becomes unsafe when the URL encodes payment, credentials
or an irreversible action.

Source:

- Google Maps URLs: https://developers.google.cn/maps/documentation/urls/get-started?hl=en

### WhatsApp-native catalog messages

WhatsApp Cloud API supports product and catalog interactive messages when a
business has a catalog connected to its WABA. The webhook can also receive order
messages when a customer places an order in WhatsApp commerce.

For Saathi this is **not** a general-purpose cart mechanism, because Saathi is
not the merchant for groceries, medicine, flights or movie tickets. It may be a
future first-party product/payment surface only for Saathi's own subscription
paywall, and that remains governed by D-U. Do not use WhatsApp catalog/order
messages to simulate third-party checkout.

Sources:

- Meta WhatsApp Cloud API Postman collection, product/catalog messages:
  https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api
- Meta product enquiry webhook example:
  https://www.postman.com/meta/whatsapp-business-platform/request/p91sd3j/received-product-enquiry-message

### Agentic checkout protocols and browser agents

Agentic commerce protocols are moving quickly. The Agentic Commerce Protocol
(maintained by OpenAI and Stripe) explicitly connects buyers, agents and
businesses to complete purchases through merchant infrastructure and delegated
payment. ChatGPT agent/Operator-style systems show that browser agents can fill
forms, build grocery orders and navigate websites, but their own documentation
calls out sensitive login/payment takeover and permission gates.

For Saathi, these prove the category is real, not that Saathi should copy the
transaction surface. Our target user is an older adult in WhatsApp; a remote
browser that can see screens, ask for takeover, preserve cookies and act on
logged-in sites is the wrong first primitive. Treat browser agents as a research
reference and as a possible supervised adult-child tool later, not as elder-chat
v1 capability.

Sources:

- Agentic Commerce Protocol: https://agentic-commerce-protocol.com/docs/commerce/guides/get-started
- ACP GitHub spec repository: https://github.com/agentic-commerce-protocol/agentic-commerce-protocol
- ChatGPT agent help: https://help.openai.com/en/articles/11752874-chatgpt-agent/
- OpenAI Operator announcement: https://openai.com/index/introducing-operator/
- OpenAI Computer-Using Agent: https://openai.com/index/computer-using-agent/

## 3. Saathi capability tiers

Use these tiers for every commercial/internet feature. A lower tier is always a
valid completion of the user's task; higher tiers are convenience, not the
contract.

| Tier | Name | What Saathi may return | Verification |
|---|---|---|---|
| 0 | Plain answer | A readable list, shortlist or explanation. | Unit test renders useful text without any external link. |
| 1 | Official URL | A provider/search/maps/event URL built from documented parameters. | Link builder tests cover URL encoding and no secret/action params. |
| 2 | Provider offer | Live offer/search/discovery API results with source and timestamp. | Provider fixture tests plus stale-result expiry. |
| 3 | Cart/deeplink draft | A visible itemised cart/list plus best available provider deeplink/search links. | Golden conversation tests; monthly link-health probe if based on undocumented schemes. |
| 4 | Transaction | Purchase/payment/order/account automation. | **Forbidden. Do not build without a new dated decision that overturns this doc.** |

The UX must make the boundary visible in ordinary words: "I found options" or
"I made the list" rather than "I booked" or "I ordered".

## 4. Implementation sequence

1. Keep `build_cart` as the first commercial capability, because its tier-0 list
   is useful even with no provider contract and matches the PRD's daily-use bet.
2. Add an explicit `commercial_actions` module for URL builders and commercial
   result rendering. Do not hide this inside generic web search.
3. Add provider adapters only where the source permits search/discovery use:
   maps URLs, event discovery, flight offer search, product search pages or
   documented affiliate/deeplink formats.
4. Store result snapshots with source, generated_at, expiry, provider and query
   slots. Do not store cookies, checkout state, payment state or third-party
   account ids.
5. If a provider call costs money, write it to `vendor_usage_events` per
   `USAGE_LEDGER.md` before relying on it at scale.
6. Any result that quotes or summarizes a third-party page is fenced as third-
   party content, the same way web search results are today.

## 5. Required tests before shipping a commercial adapter

- `assert_no_forbidden_tools()` still passes and the new tool names do not match
  transactional verbs.
- A prompt-injected product/search result cannot create a reminder, payment,
  order or account action.
- A malformed URL or redirect target fails closed through `net_policy` before any
  server-side fetch.
- Every link builder is deterministic and value-blind in logs: no phone numbers,
  OTP-like strings, card-like strings, tokens or raw search URLs with secrets.
- Stale live prices/results are either refreshed or labelled stale; never shown
  as current.
- The WhatsApp message uses buttons or short links where possible, but the body
  still contains enough text to be useful if the link fails.

## 6. Open product questions

- Which geography comes first: India-only providers, or global providers with
  graceful India gaps?
- Whether to pursue affiliate/API partnerships for grocery, medicine and ticket
  providers, or begin with provider search URLs and manual completion.
- Whether an adult-child supervised mode should ever permit stronger actions.
  If yes, it must be a separate product decision and not a hidden broadening of
  elder chat.

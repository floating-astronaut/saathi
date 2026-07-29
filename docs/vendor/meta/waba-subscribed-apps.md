<!--
Source:   https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/subscribed_apps/
Captured: 2026-07-27  (page states Graph API v25.0)
Verbatim. Do not edit to match observed behaviour — see ../README.md.
Where this page is wrong, that is recorded in docs/LANDMINES.md.
-->

# Whats App Business Account Subscribed Apps

## Reading

Get a list of apps subscribed to webhooks for the WABA.

### Example

```
GET /v25.0/{whats-app-business-account-id}/subscribed_apps HTTP/1.1
Host: graph.facebook.com
```

### Parameters

This endpoint doesn't have any parameters.

### Fields

Reading from this edge will return a JSON formatted result:

```json
{
  "data": [],
  "paging": {}
}
```

- **data** — A list of WhatsAppApplication nodes.
- **paging** — For more details about pagination, see the Graph API guide.

### Error Codes

| Error | Description |
|---|---|
| 100 | Invalid parameter |
| 200 | Permissions error |
| 80008 | There have been too many calls to this WhatsApp Business account. Wait a bit and try again. |

## Creating

You can't perform this operation on this endpoint.

## Updating

You can't perform this operation on this endpoint.

## Deleting

You can't perform this operation on this endpoint.

<!--
Source:   https://developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers/conversational-components
Captured: 2026-07-27
Verbatim. Do not edit to match what we believe — see ../README.md.
-->

# Conversational Components

Conversational components are in-chat features that you can enable on business phone numbers. They make it easier for WhatsApp users to interact with your business. You can configure easy-to-use commands and provide pre-written ice breakers that users can tap.

## Limitations

If a WhatsApp user taps a universal link (that is, **wa.me** link) configured with pre-filled text, the user interfaces for **ice breakers** are automatically dismissed.

## Configure using WhatsApp Manager (WAM)

1. Navigate to the My Apps dashboard in the Meta for Developers site.
2. Select your app, then on the left panel select **Configuration** under **WhatsApp**.
3. Under **Phone Numbers** select **Manage Phone Numbers**.
4. On the far right of the phone number you want to configure, select the **Gear Icon** under **Settings**.
5. Select **Automations**.
6. Access and configure Conversational Components.

Solution Partners can configure these features for their customers as well if they have access to their customers' WhatsApp Business account in WhatsApp Manager.

## Ice breakers

Ice breakers are customizable, tappable text strings that appear in a message thread the first time you chat with a user. For example, "Plan a trip" or "Create a workout plan".

Ice breakers are great for service interactions, such as customer support or account servicing. For example, you can embed a WhatsApp button on your app or website. When users tap the button, they are redirected to WhatsApp, where they can choose from a set of customizable prompts, showing them how to interact with your services.

You can configure up to 4 ice breakers on a business phone number. Each ice breaker can have a maximum of 80 characters. Emojis are not supported.

When a user taps an ice breaker, it triggers a standard received message webhook. The payload assigns the ice breaker string to the `body` property. If the user attempts to message you instead of tapping an ice breaker, the keyboard appears as an overlay, but the user can dismiss it to see the ice breaker menu again.

**Warning:** If a WhatsApp user taps a universal link (**wa.me** or **api.whatsapp.com** links) configured with pre-filled text, WhatsApp automatically dismisses the user interfaces for **ice breakers**.

### Webhook payload

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "<WHATSAPP_BUSINESS_ACCOUNT_ID>",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "<BUSINESS_DISPLAY_PHONE_NUMBER>",
              "phone_number_id": "<BUSINESS_PHONE_NUMBER_ID>"
            },
            "contacts": [
              { "profile": { "name": "<WHATSAPP_USER_NAME>" }, "wa_id": "<WHATSAPP_USER_ID>" }
            ],
            "messages": [
              {
                "from": "<WHATSAPP_USER_PHONE_NUMBER_ID>",
                "id": "<WHATSAPP_MESSAGE_ID>",
                "timestamp": "<TIMESTAMP>",
                "text": { "body": "Plan a trip" },
                "type": "text"
              }
            ]
          },
          "field": "messages"
        }
      ]
    }
  ]
}
```

## Commands

Commands are text strings that WhatsApp users can see by typing a forward slash in a message thread with your business.

Commands are composed of the command itself and a hint, which gives the user an idea of what can happen when they use the command. For example, you could define the command:

`/imagine - Create images using a text prompt`

When a WhatsApp user types, */imagine cars racing on Mars*, it would trigger a received message webhook with that exact text string assigned to the `body` property. You could then generate and return an image of cars racing on the planet Mars.

You can define up to 30 commands. Each command has a maximum of 32 characters, and each hint has a maximum of 256 characters. Emojis are not supported.

### Webhook payload

Same shape as ice breakers; `text.body` carries the full string, e.g. `"/imagine cars racing on Mars"`.

## Configure using the API

### Request syntax

```
POST /<PHONE_NUMBER_ID>/conversational_automation?commands=<COMMAND_LIST>
POST /<PHONE_NUMBER_ID>/conversational_automation?prompts=<PROMPT>
```

### Body properties

| Placeholder | Description |
|---|---|
| `<PHONE_NUMBER_ID>` *String* | **Required.** A phone number ID on a WhatsApp Business account. |
| `<COMMAND_LIST>` *JSON* | **Optional.** A list of commands to be configured. Objects of `command_name`, `command_description`. |
| `<PROMPTS>` *List of String* | **Optional.** The prompt(s) to be configured. `"prompts": ["Book a flight","plan a vacation"]` |

### Sample request

```bash
curl -X POST \
 'https://graph.facebook.com/v22.0/PHONE_NUMBER_ID/conversational_automation' \
 -H 'Authorization: Bearer ACCESS_TOKEN' \
 -H 'Content-Type: application/json' \
 -d '{
   "commands": [
     { "command_name": "tickets", "command_description": "Book flight tickets" },
     { "command_name": "hotel",   "command_description": "Book hotel" }
   ],
   "prompts": ["Book a flight", "plan a vacation"]
}'
```

### Sample response

```json
{ "success": true }
```

### View the current configuration

```
GET /<PHONE_NUMBER_ID>?fields=conversational_automation
```

```json
{
  "conversational_automation": {
    "prompts": ["Find the best hotels in the area", "Find deals on rental cars"],
    "commands": [
      { "command_name": "tickets", "command_description": "Book flight tickets" },
      { "command_name": "hotel", "command_description": "Book hotel" }
    ]
  },
  "id": "123456"
}
```

## Testing

To test conversational components once they have been configured, open the WhatsApp client and open a chat with your business phone number.

For ice breakers, if you already have a chat thread going with the business phone number, you must first delete the chat thread:

1. Open the thread in the WhatsApp client.
2. Tap the business phone number's profile.
3. Tap **Clear Chat** > **Clear All Messages**.
4. **Delete Chat**.
5. Start a new chat thread with this business.

You can then send a message to the business phone number to test your ice breakers.

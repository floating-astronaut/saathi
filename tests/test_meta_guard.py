import httpx
import pytest

from saathi import meta_guard
from saathi.config import settings


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "wa_app_id", "app")
    monkeypatch.setattr(settings, "wa_app_secret", "secret")
    monkeypatch.setattr(settings, "wa_phone_number_id", "phone")
    monkeypatch.setattr(settings, "wa_access_token", "token")


async def test_guard_accepts_own_webhook_and_no_agent():
    def handler(request):
        if "subscriptions" in str(request.url):
            return httpx.Response(200, json={"data": [{"object": "whatsapp_business_account", "fields": [{"name": "messages"}]}]})
        return httpx.Response(200, json=[])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await meta_guard.check(http)


async def test_guard_rejects_business_agent():
    def handler(request):
        if "subscriptions" in str(request.url):
            return httpx.Response(200, json={"data": [{"object": "whatsapp_business_account", "fields": [{"name": "messages"}]}]})
        return httpx.Response(200, json={"rollout": {"enabled": False}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(RuntimeError, match="Business Agent"):
            await meta_guard.check(http)

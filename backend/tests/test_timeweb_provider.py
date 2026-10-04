import json

import httpx
import pytest

from app.services.ai import timeweb_provider


def install_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(timeweb_provider.httpx, 'AsyncClient',
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


@pytest.mark.asyncio
async def test_reasoning_agent_rejects_legacy_parameters_before_completion(monkeypatch):
    payloads = []

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if 'temperature' in payload:
            return httpx.Response(400, json={'error': {'message': "Unsupported parameter: 'temperature' is not supported with this model."}})
        if 'max_tokens' in payload:
            return httpx.Response(400, json={'error': {'message': "Unsupported parameter: 'max_tokens'; use max_completion_tokens."}})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Done'}}],
                                        'usage': {'prompt_tokens': 12, 'completion_tokens': 20, 'total_tokens': 32}})

    install_transport(monkeypatch, handler)
    provider = timeweb_provider.TimewebAgentTextProvider()
    provider._api_key = 'test-only'
    result = await provider.complete(system_prompt='Rules', user_prompt='Post', max_tokens=1200)
    assert len(payloads) == 3
    assert payloads[0]['temperature'] == 0.7
    assert 'temperature' not in payloads[1]
    assert 'max_tokens' not in payloads[2]
    assert payloads[2]['max_completion_tokens'] == 1200
    assert result.content == 'Done'
    assert result.usage.total_tokens == 32


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [400, 401, 429, 500])
async def test_other_rejections_do_not_repeat_requests(monkeypatch, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': 'Request rejected'}})

    install_transport(monkeypatch, handler)
    provider = timeweb_provider.TimewebAgentTextProvider()
    provider._api_key = 'test-only'
    with pytest.raises(httpx.HTTPStatusError):
        await provider.complete(system_prompt='Rules', user_prompt='Post')
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_legacy_agent_success_keeps_parameters_and_is_not_replayed(monkeypatch):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Done'}}]})

    install_transport(monkeypatch, handler)
    provider = timeweb_provider.TimewebAgentTextProvider()
    provider._api_key = 'test-only'
    await provider.complete(system_prompt='Rules', user_prompt='Post', max_tokens=777)
    assert len(calls) == 1
    assert calls[0]['max_tokens'] == 777
    assert calls[0]['temperature'] == 0.7

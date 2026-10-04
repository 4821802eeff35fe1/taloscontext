import asyncio

import pytest

from app.core.lease import lease


@pytest.mark.asyncio
async def test_lease_excludes_other_process_and_releases(redis_client):
    async with lease(redis_client, "test:lease") as first:
        assert first
        async with lease(redis_client, "test:lease") as second:
            assert not second
    async with lease(redis_client, "test:lease") as third:
        assert third


@pytest.mark.asyncio
async def test_lease_renews_during_long_operation(redis_client):
    async with lease(redis_client, "test:lease", seconds=1) as acquired:
        assert acquired
        await asyncio.sleep(1.2)
        async with lease(redis_client, "test:lease") as other:
            assert not other

"""Opt-in only: one real call using an existing explicitly selected private session."""

import asyncio
import os
import pytest
from maibot_chatgpt_provider.credentials import Store
from maibot_chatgpt_provider.oauth import OAuth
from maibot_chatgpt_provider.token_manager import TokenManager
from maibot_chatgpt_provider.provider import Provider
from maibot_chatgpt_provider.adapter import smoke_request


@pytest.mark.live
def test_personal_synthetic_prompt():
    if os.environ.get("SIWC_LIVE_CONSENT") != "one-private-test":
        pytest.skip("explicit personal consent required")
    directory = os.environ.get("SIWC_LIVE_DIR")
    slug = os.environ.get("SIWC_LIVE_MODEL")
    if not directory or not slug:
        pytest.skip("explicit data directory and catalog slug required")

    async def one():
        p = Provider(TokenManager(Store(directory), OAuth()))
        try:
            assert slug in [m["slug"] for m in await p.models()]
            result = await p.dispatch(
                "response", smoke_request(slug, "请回复：测试成功。")
            )
            assert result["status"] == "completed" and result["output_items"]
        finally:
            await p.close()

    asyncio.run(one())

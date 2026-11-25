"""Synthetic records only. Keys, where needed, are generated in test memory."""

import time
import httpx
from maibot_chatgpt_provider.credentials import (
    DIRECT,
    ISSUER,
    pause_clear,
    stamp,
    Store,
)
from maibot_chatgpt_provider.oauth import OAuth
from maibot_chatgpt_provider.provider import Provider, Settings
from maibot_chatgpt_provider.token_manager import TokenManager

CANARY = "SYNTHETIC_SECRET_NEVER_LOG"


def record(exp=3600):
    return dict(
        schema_version=1,
        revision=0,
        session_generation=0,
        state="active",
        registration=dict(
            issuer=ISSUER,
            subject="synthetic-user",
            client_id="synthetic-client",
            display_label="synthetic",
        ),
        tokens=dict(
            access_token=CANARY,
            refresh_token="synthetic-refresh",
            id_token="synthetic-id",
            token_type="Bearer",
        ),
        granted_scopes=[DIRECT],
        received_at=stamp(),
        expires_at=stamp(time.time() + exp),
        earliest_refresh_at=None,
        pause=pause_clear(),
    )


def setup(path, exp=3600):
    s = Store(path)
    s.replace(record(exp))
    return s


def engine(path, handle, **kwargs):
    store = setup(path)
    return Provider(
        TokenManager(store, OAuth()), Settings(**kwargs), httpx.MockTransport(handle)
    )

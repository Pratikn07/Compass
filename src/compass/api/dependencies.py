from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from compass.api.auth import AuthContext, AuthSettings, get_auth_settings, require_owner
from compass.storage.repository import SupabaseRepository
from supabase import Client, create_client


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@lru_cache
def _service_client(url: str, service_role_key: str) -> Client:
    return create_client(url, service_role_key)


def get_repository(
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> SupabaseRepository:
    service_role_key = _required_env("SUPABASE_SERVICE_ROLE_KEY")
    return SupabaseRepository(
        client=_service_client(settings.supabase_url, service_role_key),
        owner_id=settings.owner_id,
    )


Repository = Annotated[SupabaseRepository, Depends(get_repository)]
Owner = Annotated[AuthContext, Depends(require_owner)]

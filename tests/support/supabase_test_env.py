from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse


ENABLE_ENV = "PRESCIENT_SUPABASE_INTEGRATION_TESTS"
TEST_URL_ENV = "PRESCIENT_TEST_SUPABASE_URL"
TEST_SERVICE_ROLE_KEY_ENV = "PRESCIENT_TEST_SUPABASE_SERVICE_ROLE_KEY"
TEST_SCHEMA_ENV = "PRESCIENT_TEST_SUPABASE_SCHEMA"
PRODUCTION_URL_ENV = "SUPABASE_URL"
DEFAULT_TEST_SCHEMA = "prescient_storage_test"


class SupabaseIntegrationTestNotEnabled(RuntimeError):
    pass


class SupabaseTestConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseIntegrationTestConfig:
    url: str
    service_role_key: str
    schema: str


def load_supabase_integration_test_config(
    environ: Mapping[str, str],
) -> SupabaseIntegrationTestConfig:
    if environ.get(ENABLE_ENV) != "1":
        raise SupabaseIntegrationTestNotEnabled(
            f"Set {ENABLE_ENV}=1 to run Supabase integration tests."
        )

    url = environ.get(TEST_URL_ENV, "").strip()
    service_role_key = environ.get(TEST_SERVICE_ROLE_KEY_ENV, "").strip()
    schema = environ.get(TEST_SCHEMA_ENV, DEFAULT_TEST_SCHEMA).strip()

    if not url or not service_role_key:
        raise SupabaseTestConfigurationError(
            f"Missing {TEST_URL_ENV} or {TEST_SERVICE_ROLE_KEY_ENV}."
        )
    if not schema:
        raise SupabaseTestConfigurationError(f"Missing {TEST_SCHEMA_ENV}.")

    production_url = environ.get(PRODUCTION_URL_ENV, "").strip()
    if production_url and url.rstrip("/") == production_url.rstrip("/"):
        raise SupabaseTestConfigurationError("Test Supabase URL must not equal SUPABASE_URL.")

    if not _is_local_url(url) and "test" not in schema.lower():
        raise SupabaseTestConfigurationError(
            "Remote Supabase integration tests must use a schema containing 'test'."
        )

    return SupabaseIntegrationTestConfig(
        url=url,
        service_role_key=service_role_key,
        schema=schema,
    )


def _is_local_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}

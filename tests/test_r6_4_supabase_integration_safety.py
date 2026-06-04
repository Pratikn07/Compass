from __future__ import annotations

import pytest

from tests.support.supabase_test_env import (
    ENABLE_ENV,
    TEST_SCHEMA_ENV,
    TEST_SERVICE_ROLE_KEY_ENV,
    TEST_URL_ENV,
    SupabaseIntegrationTestNotEnabled,
    SupabaseTestConfigurationError,
    load_supabase_integration_test_config,
)


def test_supabase_integration_tests_are_disabled_by_default() -> None:
    with pytest.raises(SupabaseIntegrationTestNotEnabled):
        load_supabase_integration_test_config({})


def test_supabase_integration_config_requires_test_credentials_when_enabled() -> None:
    with pytest.raises(SupabaseTestConfigurationError):
        load_supabase_integration_test_config({ENABLE_ENV: "1"})


def test_supabase_integration_config_rejects_production_url_match() -> None:
    with pytest.raises(SupabaseTestConfigurationError, match="must not equal SUPABASE_URL"):
        load_supabase_integration_test_config(
            {
                ENABLE_ENV: "1",
                TEST_URL_ENV: "https://prod-ref.supabase.co",
                TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
                TEST_SCHEMA_ENV: "prescient_storage_test",
                "SUPABASE_URL": "https://prod-ref.supabase.co",
            }
        )


def test_supabase_integration_config_requires_test_schema_for_remote_url() -> None:
    with pytest.raises(SupabaseTestConfigurationError, match="schema containing 'test'"):
        load_supabase_integration_test_config(
            {
                ENABLE_ENV: "1",
                TEST_URL_ENV: "https://remote-ref.supabase.co",
                TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
                TEST_SCHEMA_ENV: "prescient_storage",
            }
        )


def test_supabase_integration_config_accepts_local_project() -> None:
    config = load_supabase_integration_test_config(
        {
            ENABLE_ENV: "1",
            TEST_URL_ENV: "http://127.0.0.1:54321",
            TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
            TEST_SCHEMA_ENV: "prescient_storage",
        }
    )

    assert config.url == "http://127.0.0.1:54321"
    assert config.service_role_key == "test-service-role-key"
    assert config.schema == "prescient_storage"


def test_supabase_integration_config_accepts_remote_test_schema() -> None:
    config = load_supabase_integration_test_config(
        {
            ENABLE_ENV: "1",
            TEST_URL_ENV: "https://remote-ref.supabase.co",
            TEST_SERVICE_ROLE_KEY_ENV: "test-service-role-key",
            TEST_SCHEMA_ENV: "prescient_storage_test",
        }
    )

    assert config.url == "https://remote-ref.supabase.co"
    assert config.service_role_key == "test-service-role-key"
    assert config.schema == "prescient_storage_test"

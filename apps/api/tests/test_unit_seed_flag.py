"""SEED_DEMO_DATA: hosted evaluation demos seed fictional data in staging only; production refuses it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {"database_url": "postgresql+psycopg://u:p@h/db", "secret_key": "x" * 48, "_env_file": None}


def test_demo_data_only_in_dev_or_flagged_staging():
    assert Settings(app_env="development", **BASE).seeds_demo_data
    assert not Settings(app_env="staging", **BASE).seeds_demo_data
    assert Settings(app_env="staging", seed_demo_data=True, **BASE).seeds_demo_data
    assert not Settings(app_env="production", **BASE).seeds_demo_data


def test_production_refuses_the_demo_flag():
    with pytest.raises(ValidationError, match="SEED_DEMO_DATA"):
        Settings(app_env="production", seed_demo_data=True, **BASE)


@pytest.mark.parametrize("url", ["postgresql://u:p@h/db?sslmode=require", "postgres://u:p@h/db?sslmode=require"])
def test_standard_postgres_urls_use_the_psycopg_driver(url):
    settings = Settings(**{**BASE, "database_url": url})
    assert settings.database_url == "postgresql+psycopg://u:p@h/db?sslmode=require"

"""Tests for startup security checks — Issue #5."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.startup_checks import verify_security_config


class TestVerifySecurityConfig:
    async def test_dev_mode_allows_missing_token(self):
        """In dev mode, missing webhook token should not raise."""
        with patch("app.core.startup_checks.settings") as mock_settings:
            mock_settings.is_dev = True
            mock_settings.ai_service_webhook_token = ""
            await verify_security_config()

    async def test_prod_mode_raises_without_token(self):
        """In production, missing webhook token must abort startup."""
        with patch("app.core.startup_checks.settings") as mock_settings:
            mock_settings.is_dev = False
            mock_settings.ai_service_webhook_token = ""
            with pytest.raises(RuntimeError, match="AI_SERVICE_WEBHOOK_TOKEN"):
                await verify_security_config()

    async def test_prod_mode_passes_with_token(self):
        """In production, having a webhook token should not raise."""
        with patch("app.core.startup_checks.settings") as mock_settings:
            mock_settings.is_dev = False
            mock_settings.ai_service_webhook_token = "valid-token-123"
            await verify_security_config()

    async def test_dev_mode_with_token_also_passes(self):
        """In dev mode, having a webhook token should also work fine."""
        with patch("app.core.startup_checks.settings") as mock_settings:
            mock_settings.is_dev = True
            mock_settings.ai_service_webhook_token = "some-token"
            await verify_security_config()

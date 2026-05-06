"""Tests for ``HF_TOKEN_FILE`` -> ``HF_TOKEN`` promotion at config load.

The promotion lets the systemd unit pass a path (via
``LoadCredentialEncrypted=`` + ``Environment=HF_TOKEN_FILE=%d/hf_token``)
instead of the secret value via ``HF_TOKEN``. ``huggingface_hub`` only
reads ``HF_TOKEN`` from ``os.environ`` so the value has to land there
before any HF library import.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeworks_character_forge.core.config import _promote_secret_file_env_vars


@pytest.fixture(autouse=True)
def _clean_hf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_TOKEN_FILE", raising=False)


class TestSecretFilePromotion:
    def test_promotes_when_value_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cred = tmp_path / "hf_token"
        cred.write_text("hf_FROM_FILE\n", encoding="utf-8")
        monkeypatch.setenv("HF_TOKEN_FILE", str(cred))

        _promote_secret_file_env_vars()

        import os

        assert os.environ["HF_TOKEN"] == "hf_FROM_FILE"

    def test_existing_value_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cred = tmp_path / "hf_token"
        cred.write_text("hf_FROM_FILE", encoding="utf-8")
        monkeypatch.setenv("HF_TOKEN", "hf_FROM_ENV")
        monkeypatch.setenv("HF_TOKEN_FILE", str(cred))

        _promote_secret_file_env_vars()

        import os

        assert os.environ["HF_TOKEN"] == "hf_FROM_ENV"

    def test_no_op_when_neither_set(self) -> None:
        _promote_secret_file_env_vars()

        import os

        assert "HF_TOKEN" not in os.environ

    def test_missing_file_is_silent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HF_TOKEN_FILE", str(tmp_path / "does-not-exist"))

        _promote_secret_file_env_vars()

        import os

        assert "HF_TOKEN" not in os.environ

    def test_blank_file_is_silent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cred = tmp_path / "hf_token"
        cred.write_text("\n   \n", encoding="utf-8")
        monkeypatch.setenv("HF_TOKEN_FILE", str(cred))

        _promote_secret_file_env_vars()

        import os

        assert "HF_TOKEN" not in os.environ

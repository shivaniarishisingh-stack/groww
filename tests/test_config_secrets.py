"""Credential-resolution tests.

These tests use dummy values only. They never read or print a real key.
"""

import sys
import types

import src.config as config


def test_secret_reader_uses_streamlit_secrets(monkeypatch):
    fake_streamlit = types.SimpleNamespace(
        secrets={"GROQ_API_KEY": "dummy-secret-key"}
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)

    assert config._secret_value("GROQ_API_KEY") == "dummy-secret-key"


def test_secret_reader_returns_none_when_secrets_raise(monkeypatch):
    class FakeStreamlit:
        @property
        def secrets(self):
            raise RuntimeError("no secrets runtime")

    monkeypatch.setitem(sys.modules, "streamlit", FakeStreamlit())

    assert config._secret_value("GROQ_API_KEY") is None


def test_environment_value_wins_over_secret(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "env-dummy-key")
    monkeypatch.setattr(config, "_secret_value", lambda name: "secret-dummy-key")

    assert config._resolve_value("GROQ_API_KEY") == "env-dummy-key"


def test_secret_is_used_when_environment_is_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(config, "_secret_value", lambda name: "secret-dummy-key")

    assert config._resolve_value("GROQ_API_KEY") == "secret-dummy-key"


def test_blank_environment_value_falls_back_to_secret(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "   ")
    monkeypatch.setattr(config, "_secret_value", lambda name: "secret-model")

    assert config._resolve_value("LLM_MODEL") == "secret-model"


def test_missing_value_returns_none(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(config, "_secret_value", lambda name: None)

    assert config._resolve_value("GROQ_API_KEY") is None


def test_secret_reader_does_not_raise_without_a_runtime():
    value = config._secret_value("GROQ_API_KEY")
    assert value is None or isinstance(value, str)


def test_load_settings_uses_secret_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        config,
        "_secret_value",
        lambda name: {
            "GROQ_API_KEY": "secret-dummy-key",
            "LLM_MODEL": "secret-dummy-model",
        }.get(name),
    )

    loaded = config.load_settings()

    assert loaded.llm.api_key == "secret-dummy-key"
    assert loaded.llm.model == "secret-dummy-model"

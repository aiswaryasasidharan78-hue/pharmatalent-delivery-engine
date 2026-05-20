"""Unit tests for OpenRouter client response parsing."""
from __future__ import annotations

import pytest
from app.api.openrouter_client import _parse_json_response


class TestParseJsonResponse:
    def test_clean_json(self):
        raw = '{"decision": "fit", "rationale": "EU biotech.", "confidence": "high"}'
        result = _parse_json_response(raw)
        assert result["decision"] == "fit"
        assert result["confidence"] == "high"

    def test_strips_markdown_fences(self):
        raw = '```json\n{"decision": "not_fit", "rationale": "No EU office.", "confidence": "medium"}\n```'
        result = _parse_json_response(raw)
        assert result["decision"] == "not_fit"

    def test_extracts_json_from_prose(self):
        raw = 'Based on my research, here is the verdict: {"decision": "fit", "rationale": "Has Basel office.", "confidence": "high"} End.'
        result = _parse_json_response(raw)
        assert result["decision"] == "fit"

    def test_invalid_json_returns_fallback(self):
        raw = "I cannot determine the fit for this company."
        result = _parse_json_response(raw)
        assert result["decision"] == "not_fit"
        assert result["confidence"] == "low"

    def test_yes_no_decision(self):
        raw = '{"decision": "yes", "reason": "Head of Talent owns this hire."}'
        result = _parse_json_response(raw)
        assert result["decision"] == "yes"
        assert "reason" in result

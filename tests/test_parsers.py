"""Tests for pure parsers."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import jwt
import pytest

from custom_components.affarsverken_waste.const import (
    TOKEN_EXPIRY_SAFETY,
    TOKEN_FALLBACK_LIFETIME,
)
from custom_components.affarsverken_waste.parsers import (
    extract_jwt_expiry,
    parse_collection_dates,
)


class TestParseCollectionDates:
    def test_valid_payload(self):
        payload = {
            "services": [
                {"title": "Restavfall", "nextPickup": "2026-05-15"},
                {"title": "Trädgårdsavfall", "nextPickup": "2026-06-01"},
            ]
        }
        assert parse_collection_dates(payload) == {
            "Restavfall": date(2026, 5, 15),
            "Trädgårdsavfall": date(2026, 6, 1),
        }

    def test_missing_services_key(self):
        assert parse_collection_dates({}) == {}

    def test_services_not_a_list(self):
        assert parse_collection_dates({"services": "nope"}) == {}

    def test_empty_services_list(self):
        assert parse_collection_dates({"services": []}) == {}

    def test_skips_entry_without_title(self):
        payload = {"services": [{"nextPickup": "2026-05-15"}]}
        assert parse_collection_dates(payload) == {}

    def test_skips_entry_without_next_pickup(self):
        payload = {"services": [{"title": "Restavfall"}]}
        assert parse_collection_dates(payload) == {}

    def test_skips_unparseable_date_keeps_others(self):
        # One bad service should not poison the rest of the response.
        payload = {
            "services": [
                {"title": "Bad", "nextPickup": "not-a-date"},
                {"title": "Good", "nextPickup": "2026-05-15"},
            ]
        }
        assert parse_collection_dates(payload) == {"Good": date(2026, 5, 15)}

    def test_ignores_extra_fields(self):
        # Real responses include irrelevant keys; we should not choke on them.
        payload = {
            "services": [
                {"title": "Restavfall", "nextPickup": "2026-05-15", "foo": "bar"}
            ],
            "buildingId": 123,
        }
        assert parse_collection_dates(payload) == {"Restavfall": date(2026, 5, 15)}


class TestExtractJwtExpiry:
    def _encode(self, claims: dict) -> str:
        return jwt.encode(claims, "x" * 32, algorithm="HS256")

    def test_valid_token_subtracts_safety_margin(self):
        # Pin "expires at" to a fixed instant so the assertion is exact.
        expires_at = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
        token = self._encode({"exp": int(expires_at.timestamp())})

        result = extract_jwt_expiry(token)
        assert result == expires_at - TOKEN_EXPIRY_SAFETY

    def test_missing_exp_uses_fallback_lifetime(self):
        token = self._encode({"sub": "user"})
        before = datetime.now(UTC)
        result = extract_jwt_expiry(token)
        after = datetime.now(UTC)

        # Fallback should be ~now + TOKEN_FALLBACK_LIFETIME, allowing for a
        # small drift between our `before`/`after` and the implementation's
        # internal call to datetime.now().
        assert before + TOKEN_FALLBACK_LIFETIME - timedelta(seconds=2) <= result
        assert result <= after + TOKEN_FALLBACK_LIFETIME + timedelta(seconds=2)

    def test_malformed_token_uses_fallback_lifetime(self):
        before = datetime.now(UTC)
        result = extract_jwt_expiry("not.a.valid.jwt")
        after = datetime.now(UTC)

        assert before + TOKEN_FALLBACK_LIFETIME - timedelta(seconds=2) <= result
        assert result <= after + TOKEN_FALLBACK_LIFETIME + timedelta(seconds=2)

    @pytest.mark.parametrize("garbage", ["", "x", "...", "a.b"])
    def test_various_garbage_falls_back(self, garbage):
        # extract_jwt_expiry must always return a datetime, never raise —
        # otherwise a single bad login response would crash the integration.
        result = extract_jwt_expiry(garbage)
        assert isinstance(result, datetime)

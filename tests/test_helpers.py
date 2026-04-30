"""Tests for pure helpers."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.affarsverken_waste.helpers import (
    address_slug,
    build_pickup_attributes,
    normalize_address,
)


class TestNormalizeAddress:
    def test_lowercases(self):
        assert normalize_address("DROTTNINGGATAN 1") == "drottninggatan 1"

    def test_collapses_internal_whitespace(self):
        assert normalize_address("Drottninggatan    1") == "drottninggatan 1"

    def test_strips_outer_whitespace(self):
        assert normalize_address("  Drottninggatan 1  ") == "drottninggatan 1"

    def test_collapses_tabs_and_newlines(self):
        assert normalize_address("Drottninggatan\t\n1") == "drottninggatan 1"

    def test_idempotent(self):
        once = normalize_address("Drottninggatan 1")
        assert normalize_address(once) == once


class TestAddressSlug:
    def test_deterministic(self):
        assert address_slug("Drottninggatan 1") == address_slug("Drottninggatan 1")

    def test_whitespace_and_case_invariant(self):
        # Different surface forms of the same address must collapse to one slug
        # so a user re-adding "drottninggatan 1" matches "Drottninggatan  1".
        assert address_slug("Drottninggatan 1") == address_slug("  drottninggatan   1 ")

    def test_default_length_is_8(self):
        assert len(address_slug("any address")) == 8

    def test_custom_length(self):
        assert len(address_slug("any address", length=12)) == 12

    def test_distinct_addresses_distinct_slugs(self):
        assert address_slug("Drottninggatan 1") != address_slug("Storgatan 1")

    def test_only_hex(self):
        assert all(c in "0123456789abcdef" for c in address_slug("foo"))


class TestBuildPickupAttributes:
    @pytest.fixture
    def today(self) -> date:
        return date(2026, 4, 30)  # Thursday

    def test_today_pickup(self, today):
        attrs = build_pickup_attributes(today, today, "Restavfall", "Foo 1")
        assert attrs["days_until_pickup"] == 0
        assert attrs["is_today"] is True
        assert attrs["is_tomorrow"] is False
        assert attrs["is_this_week"] is True

    def test_tomorrow_pickup(self, today):
        attrs = build_pickup_attributes(date(2026, 5, 1), today, "Restavfall", "Foo 1")
        assert attrs["days_until_pickup"] == 1
        assert attrs["is_today"] is False
        assert attrs["is_tomorrow"] is True
        assert attrs["is_this_week"] is True

    def test_seventh_day_is_this_week(self, today):
        # Boundary: day 7 inclusive.
        attrs = build_pickup_attributes(date(2026, 5, 7), today, "Foo", "Foo 1")
        assert attrs["days_until_pickup"] == 7
        assert attrs["is_this_week"] is True

    def test_eighth_day_is_not_this_week(self, today):
        attrs = build_pickup_attributes(date(2026, 5, 8), today, "Foo", "Foo 1")
        assert attrs["days_until_pickup"] == 8
        assert attrs["is_this_week"] is False

    def test_past_pickup_not_this_week(self, today):
        # A pickup that has already happened should not register as "this week".
        attrs = build_pickup_attributes(date(2026, 4, 29), today, "Foo", "Foo 1")
        assert attrs["days_until_pickup"] == -1
        assert attrs["is_today"] is False
        assert attrs["is_tomorrow"] is False
        assert attrs["is_this_week"] is False

    def test_iso_pickup_date(self, today):
        attrs = build_pickup_attributes(date(2026, 5, 15), today, "Foo", "Foo 1")
        assert attrs["pickup_date"] == "2026-05-15"

    def test_weekday_name(self, today):
        # 2026-04-30 is a Thursday.
        attrs = build_pickup_attributes(today, today, "Foo", "Foo 1")
        assert attrs["pickup_weekday"] == "Thursday"

    def test_passes_through_metadata(self, today):
        attrs = build_pickup_attributes(today, today, "Restavfall", "Foo 1")
        assert attrs["waste_type"] == "Restavfall"
        assert attrs["address"] == "Foo 1"

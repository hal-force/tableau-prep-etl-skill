"""Tests for archive_flow's synthetic-sample helpers.

Covers the column-name heuristic in `_synthetic_string`:
- Faker-installed path: returns a synthetic value from the mapped
  provider (email-shaped for `email`, phone-shaped for `phone`, etc).
- Faker-missing path: falls back to `<redacted>`.
- Unmapped column names default to `Faker.word()` (a lowercase token),
  never `<redacted>`, when Faker is present.

We don't test `_synthesize_sample` itself here because it needs a real
Hyper file — that's exercised by the flow-level integration path. The
heuristic map is where the interesting logic lives.
"""
from __future__ import annotations

import re

import pytest

from skill.scripts.archive_flow import _synthetic_string


# Sanity: Faker must be importable for the "happy path" tests. If the
# host somehow doesn't have it, skip rather than fail — the fallback
# path is exercised explicitly below.
faker_module = pytest.importorskip("faker")
Faker = faker_module.Faker


@pytest.fixture
def faker():
    fk = Faker()
    Faker.seed(0)
    return fk


class TestFakerColumnHeuristic:
    def test_email_column_returns_email_shaped_value(self, faker):
        v = _synthetic_string(faker, "user_email", seed_hint="t")
        assert "@" in v and "." in v.split("@")[-1]

    def test_phone_column_returns_phone_shaped_value(self, faker):
        v = _synthetic_string(faker, "phone_number", seed_hint="t")
        # At least some digits — Faker's phone format varies by locale.
        assert re.search(r"\d", v)

    def test_first_name_column_returns_non_empty_name(self, faker):
        v = _synthetic_string(faker, "first_name", seed_hint="t")
        assert v and v.isalpha()

    def test_last_name_column_returns_non_empty_name(self, faker):
        v = _synthetic_string(faker, "last_name", seed_hint="t")
        assert v and v.isalpha()

    def test_underscore_name_falls_through_to_name(self, faker):
        # A column named `agency_name` should hit the `_name` heuristic,
        # not the more specific first_name/last_name entries.
        v = _synthetic_string(faker, "agency_name", seed_hint="t")
        assert v and " " in v  # Faker.name() returns "First Last"

    def test_uuid_column_returns_uuid_shaped_value(self, faker):
        v = _synthetic_string(faker, "record_uuid", seed_hint="t")
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            v,
        )

    def test_city_column_returns_non_empty_string(self, faker):
        v = _synthetic_string(faker, "resident_city", seed_hint="t")
        assert v and isinstance(v, str)

    def test_url_column_returns_url_shaped_value(self, faker):
        v = _synthetic_string(faker, "source_url", seed_hint="t")
        assert v.startswith("http")

    def test_unmapped_column_defaults_to_word(self, faker):
        # No heuristic matches — should return Faker.word() (a lowercase
        # single token), NOT `<redacted>`.
        v = _synthetic_string(faker, "some_totally_random_col", seed_hint="t")
        assert v != "<redacted>"
        assert v and " " not in v

    def test_empty_column_name_returns_word(self, faker):
        v = _synthetic_string(faker, "", seed_hint="t")
        assert v != "<redacted>"

    def test_case_insensitive_matching(self, faker):
        v_lower = _synthetic_string(faker, "email", seed_hint="t")
        v_upper = _synthetic_string(faker, "EMAIL", seed_hint="t")
        assert "@" in v_lower and "@" in v_upper


class TestFallbackWhenFakerMissing:
    def test_none_faker_returns_redacted(self):
        # Callers pass `faker=None` when Faker isn't installed.
        assert _synthetic_string(None, "email", seed_hint="t") == "<redacted>"

    def test_none_faker_returns_redacted_for_any_column(self):
        for col in ("first_name", "phone", "uuid", "random"):
            assert _synthetic_string(None, col, seed_hint="t") == "<redacted>"

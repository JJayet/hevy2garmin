"""Tests for `_get_unmapped_exercises` filtering at read time."""

from __future__ import annotations

import pytest

from hevy2garmin import db, server
from hevy2garmin import mapper


class _StubDB:
    def __init__(self, cache: dict[str, int]):
        self._cache = cache

    def get_app_config(self, key: str):
        if key == "unmapped_exercises":
            return dict(self._cache)
        return None


@pytest.fixture
def reset_caches(monkeypatch):
    """Clear server + mapper module-level state between tests."""
    monkeypatch.setattr(server, "_unmapped_cache", None, raising=False)
    monkeypatch.setattr(server, "_unmapped_cache_time", 0.0, raising=False)
    # Skip the DB/disk loader; we control _custom_mappings directly.
    monkeypatch.setattr(mapper, "_custom_loaded", True, raising=False)
    original_custom = dict(mapper._custom_mappings)
    mapper._custom_mappings.clear()
    yield
    mapper._custom_mappings.clear()
    mapper._custom_mappings.update(original_custom)


def test_filters_out_custom_mapped(monkeypatch, reset_caches):
    mapper._custom_mappings["Écarté (Machine)"] = (9, 2)
    cache = {"Écarté (Machine)": 3, "Truly Unknown Move": 2}
    monkeypatch.setattr(db, "get_db", lambda: _StubDB(cache))

    result = server._get_unmapped_exercises()

    assert ("Écarté (Machine)", 3) not in result
    assert ("Truly Unknown Move", 2) in result


def test_filters_out_builtin_mapped(monkeypatch, reset_caches):
    # "Bench Press (Barbell)" is a built-in mapping in HEVY_TO_GARMIN.
    assert "Bench Press (Barbell)" in mapper.HEVY_TO_GARMIN
    cache = {"Bench Press (Barbell)": 5, "Truly Unknown Move": 1}
    monkeypatch.setattr(db, "get_db", lambda: _StubDB(cache))

    names = [n for n, _ in server._get_unmapped_exercises()]

    assert "Bench Press (Barbell)" not in names
    assert "Truly Unknown Move" in names


def test_keeps_unmapped_and_sorts_by_count_desc(monkeypatch, reset_caches):
    cache = {"Move A": 1, "Move B": 7, "Move C": 3}
    monkeypatch.setattr(db, "get_db", lambda: _StubDB(cache))

    result = server._get_unmapped_exercises()

    assert [n for n, _ in result] == ["Move B", "Move C", "Move A"]


def test_returns_empty_when_all_mapped(monkeypatch, reset_caches):
    mapper._custom_mappings["Foo"] = (0, 0)
    mapper._custom_mappings["Bar"] = (1, 0)
    cache = {"Foo": 2, "Bar": 5}
    monkeypatch.setattr(db, "get_db", lambda: _StubDB(cache))

    assert server._get_unmapped_exercises() == []

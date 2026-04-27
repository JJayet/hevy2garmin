"""Tests for exercise mapper."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from hevy2garmin.mapper import (
    HEVY_TO_GARMIN,
    _UNKNOWN_CATEGORY,
    lookup_exercise,
    save_custom_mapping,
    _custom_mappings,
    _ensure_custom_loaded,
)


class TestLookupBuiltIn:
    def test_known_exercise(self) -> None:
        cat, subcat, name = lookup_exercise("Bench Press (Barbell)")
        assert cat == 0
        assert subcat == 1
        assert name == "Bench Press (Barbell)"

    def test_squat(self) -> None:
        cat, subcat, name = lookup_exercise("Squat (Barbell)")
        assert cat == 28
        assert name == "Squat (Barbell)"

    def test_unknown_exercise(self) -> None:
        cat, subcat, name = lookup_exercise("Made Up Exercise 12345")
        assert cat == _UNKNOWN_CATEGORY
        assert subcat == 0
        assert name == "Made Up Exercise 12345"

    def test_empty_string(self) -> None:
        cat, subcat, name = lookup_exercise("")
        assert cat == _UNKNOWN_CATEGORY
        assert name == ""

    def test_mapping_count_minimum(self) -> None:
        assert len(HEVY_TO_GARMIN) >= 400

    def test_preserves_original_name(self) -> None:
        _, _, name = lookup_exercise("Deadlift (Barbell)")
        assert name == "Deadlift (Barbell)"


class TestCustomMappings:
    def test_custom_overrides_builtin(self, tmp_path: Path) -> None:
        mappings_file = tmp_path / "custom_mappings.json"
        mappings_file.write_text(json.dumps({"Bench Press (Barbell)": [99, 88]}))

        # Reset custom state
        _custom_mappings.clear()
        import hevy2garmin.mapper as m
        m._custom_loaded = False

        with patch.object(Path, "expanduser", return_value=mappings_file):
            with patch("hevy2garmin.mapper._custom_loaded", False):
                # Force reload
                m._custom_loaded = False
                m._custom_mappings.clear()
                m._custom_mappings["Bench Press (Barbell)"] = (99, 88)
                cat, subcat, _ = lookup_exercise("Bench Press (Barbell)")
                assert cat == 99
                assert subcat == 88

        # Cleanup
        m._custom_mappings.clear()

    def test_custom_does_not_affect_other_exercises(self) -> None:
        import hevy2garmin.mapper as m
        m._custom_mappings["Only This One"] = (1, 2)
        cat, _, _ = lookup_exercise("Squat (Barbell)")
        assert cat == 28  # unchanged
        m._custom_mappings.clear()

    def test_save_custom_mapping_in_memory(self) -> None:
        import hevy2garmin.mapper as m
        m._custom_mappings["Test Exercise"] = (5, 10)
        cat, subcat, _ = lookup_exercise("Test Exercise")
        assert cat == 5
        assert subcat == 10
        m._custom_mappings.clear()

    def test_missing_custom_file_no_crash(self) -> None:
        import hevy2garmin.mapper as m
        m._custom_loaded = False
        m._custom_mappings.clear()
        # Should not crash when file doesn't exist
        _ensure_custom_loaded()

    def test_save_with_db_url_skips_disk(self, tmp_path: Path) -> None:
        """On cloud (DATABASE_URL set), must not touch filesystem.

        Regression: Vercel serverless filesystems are read-only outside /tmp,
        so writing ~/.hevy2garmin/custom_mappings.json raised OSError → 500
        when users mapped exercises in the dashboard.
        """
        import hevy2garmin.mapper as m
        m._custom_mappings.clear()

        unwritable = tmp_path / "should_not_be_created.json"

        class FakeDB:
            def __init__(self) -> None:
                self.saved: list[tuple[str, int, int]] = []

            def save_custom_mapping(self, name: str, cat: int, sub: int) -> None:
                self.saved.append((name, cat, sub))

        fake_db = FakeDB()

        with patch("hevy2garmin.db.get_database_url", return_value="postgres://x"), \
             patch("hevy2garmin.db.get_db", return_value=fake_db), \
             patch.object(Path, "expanduser", return_value=unwritable):
            save_custom_mapping("Cloud Exercise", 7, 3)

        assert fake_db.saved == [("Cloud Exercise", 7, 3)]
        assert not unwritable.exists()
        assert m._custom_mappings["Cloud Exercise"] == (7, 3)
        m._custom_mappings.clear()

    def test_save_without_db_url_writes_disk(self, tmp_path: Path) -> None:
        """Local/Docker (no DATABASE_URL) keeps filesystem persistence."""
        import hevy2garmin.mapper as m
        m._custom_mappings.clear()

        target = tmp_path / "custom_mappings.json"

        with patch("hevy2garmin.db.get_database_url", return_value=None), \
             patch.object(Path, "expanduser", return_value=target):
            save_custom_mapping("Local Exercise", 4, 2)

        assert target.exists()
        data = json.loads(target.read_text())
        assert data["Local Exercise"] == [4, 2]
        assert m._custom_mappings["Local Exercise"] == (4, 2)
        m._custom_mappings.clear()

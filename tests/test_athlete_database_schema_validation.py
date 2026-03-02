import json

from titan.core.database import AthleteDatabase


def test_load_all_skips_non_object_json(tmp_path):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()
    (db_dir / "bad.json").write_text('[]')

    db = AthleteDatabase(db_path=str(db_dir))

    assert db.athletes == {}


def test_load_all_skips_invalid_profile_schema(tmp_path):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()

    malformed_profile = {
        "athlete_id": "ATH_20200101010101",
        "name": "Runner",
        "age": "43",
    }
    (db_dir / "bad_types.json").write_text(json.dumps(malformed_profile))

    db = AthleteDatabase(db_path=str(db_dir))

    assert db.athletes == {}


def test_load_all_accepts_valid_profile_schema(tmp_path):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()

    valid_profile = {
        "athlete_id": "ATH_20200101010101",
        "name": "Runner",
        "gender": "M",
        "age": 43,
        "race_day": "2026-04-26T00:00:00",
        "personal_bests": {},
        "paces": {"EASY": "5:30"},
    }
    (db_dir / "valid.json").write_text(json.dumps(valid_profile))

    db = AthleteDatabase(db_path=str(db_dir))

    assert "ATH_20200101010101" in db.athletes

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


def test_load_all_logs_detailed_corruption_reason_for_invalid_field(tmp_path, caplog):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()

    malformed_profile = {
        "athlete_id": "ATH_20200101010109",
        "name": "Runner",
        "age": "43",
    }
    (db_dir / "bad_types.json").write_text(json.dumps(malformed_profile))

    with caplog.at_level("WARNING"):
        AthleteDatabase(db_path=str(db_dir))

    message = caplog.records[-1].getMessage()
    assert "filename=bad_types.json" in message
    assert "error_class=TypeError" in message
    assert "error_message=Invalid type for field: age" in message
    assert "field_hint=age" in message


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



def test_load_all_skips_missing_athlete_id(tmp_path):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()
    (db_dir / "missing_id.json").write_text(json.dumps({"name": "Runner"}))

    db = AthleteDatabase(db_path=str(db_dir))

    assert db.athletes == {}


def test_load_all_logs_detailed_corruption_reason_for_missing_required_field(tmp_path, caplog):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()
    (db_dir / "missing_id.json").write_text(json.dumps({"name": "Runner"}))

    with caplog.at_level("WARNING"):
        AthleteDatabase(db_path=str(db_dir))

    message = caplog.records[-1].getMessage()
    assert "filename=missing_id.json" in message
    assert "error_class=ValueError" in message
    assert "error_message=Missing required athlete fields:" in message
    assert "field_hint=athlete_id" in message


def test_load_all_accepts_missing_name_uses_default(tmp_path):
    db_dir = tmp_path / "athletes"
    db_dir.mkdir()

    valid_without_name = {
        "athlete_id": "ATH_20200101010102",
        "age": 43,
        "personal_bests": {},
    }
    (db_dir / "missing_name.json").write_text(json.dumps(valid_without_name))

    db = AthleteDatabase(db_path=str(db_dir))

    assert db.athletes["ATH_20200101010102"].name == "Default Athlete"

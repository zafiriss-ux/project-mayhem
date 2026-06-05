import pytest

from titan.core.equipment import EquipmentManager


@pytest.mark.integration
def test_check_gear_unknown_shoe_returns_blocked_unknown_message() -> None:
    manager = EquipmentManager()

    allowed, message = manager.check_gear("EASY", "missing", "ROAD")

    assert allowed is False
    assert message == "Unknown Shoe"


@pytest.mark.integration
def test_check_gear_blocks_fast_session_in_recovery_shoe() -> None:
    manager = EquipmentManager()

    allowed, message = manager.check_gear("INTERVALS", "3", "TRACK")

    assert allowed is False
    assert message == "BLOCK: Cannot run Fast in Recovery shoes."


@pytest.mark.integration
def test_check_gear_returns_rotation_and_surface_risk_flags() -> None:
    manager = EquipmentManager()

    allowed, message = manager.check_gear("INTERVALS", "1", "CONCRETE")

    assert allowed is True
    assert message == "SURFACE RISK: High impact intervals on concrete."


@pytest.mark.integration
def test_check_gear_easy_run_in_race_shoe_warns_waste() -> None:
    manager = EquipmentManager()

    allowed, message = manager.check_gear("EASY", "2", "ROAD")

    assert allowed is True
    assert message == "WASTE: Using Super Shoes for easy run."


@pytest.mark.integration
def test_check_gear_expired_shoe_flags_injury_risk_but_allows() -> None:
    manager = EquipmentManager()

    allowed, message = manager.check_gear("EASY", "3", "ROAD")

    assert allowed is True
    assert "SHOE EXPIRED (950km). Risk of injury." in message


@pytest.mark.integration
def test_add_shoe_creates_new_entry_with_defaults() -> None:
    manager = EquipmentManager()

    manager.add_shoe("10", "Fresh Pair")

    assert manager.shoes["10"] == {
        "name": "Fresh Pair",
        "km": 0,
        "max_km": 800,
        "type": "DAILY",
    }


@pytest.mark.integration
def test_update_mileage_updates_existing_shoe_and_returns_true() -> None:
    manager = EquipmentManager()

    updated = manager.update_mileage("1", 5.5)

    assert updated is True
    assert manager.shoes["1"]["km"] == 455.5


@pytest.mark.integration
def test_update_mileage_returns_false_for_missing_shoe() -> None:
    manager = EquipmentManager()

    updated = manager.update_mileage("404", 5)

    assert updated is False


@pytest.mark.integration
def test_get_shoe_status_boundary_at_exact_max_km_is_retiring() -> None:
    manager = EquipmentManager()
    manager.add_shoe("11", "Borderline", max_km=100)
    manager.update_mileage("11", 100)

    status = manager.get_shoe_status("11")

    assert status is not None
    assert status["remaining_km"] == 0
    assert status["health_pct"] == 0
    assert status["status"] == "RETIRING"


@pytest.mark.integration
def test_get_shoe_status_zero_max_km_reports_zero_health() -> None:
    manager = EquipmentManager()
    manager.add_shoe("12", "No Lifespan", max_km=0)

    status = manager.get_shoe_status("12")

    assert status is not None
    assert status["remaining_km"] == 0
    assert status["health_pct"] == 0
    assert status["status"] == "GOOD"


@pytest.mark.integration
def test_get_shoe_status_returns_none_for_missing_shoe() -> None:
    manager = EquipmentManager()

    assert manager.get_shoe_status("missing") is None


@pytest.mark.integration
def test_list_all_shoes_returns_status_for_each_entry() -> None:
    manager = EquipmentManager()

    all_shoes = manager.list_all_shoes()

    assert set(all_shoes) == {"1", "2", "3"}
    assert all_shoes["1"]["status"] == "GOOD"
    assert all_shoes["2"]["status"] == "GOOD"
    assert all_shoes["3"]["status"] == "EXPIRED"


@pytest.mark.integration
def test_safety_no_crash_with_empty_inventory() -> None:
    manager = EquipmentManager()
    manager.shoes = {}

    allowed, message = manager.check_gear("EASY", "1", "ROAD")

    assert (allowed, message) == (False, "Unknown Shoe")
    assert manager.update_mileage("1", 3) is False
    assert manager.get_shoe_status("1") is None
    assert manager.list_all_shoes() == {}

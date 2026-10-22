import sqlite3

import pytest

from app.services import smart_home_service


@pytest.fixture
def isolated_devices(tmp_path, monkeypatch):
    database_path = tmp_path / "smart-home-test.db"
    monkeypatch.setattr(smart_home_service, "DB_PATH", database_path)
    smart_home_service.initialize_smart_home()
    return database_path


@pytest.mark.parametrize("action,expected", [("on", True), ("off", False)])
def test_control_commits_and_verifies_device_state(
    isolated_devices, action, expected
):
    result = smart_home_service.control_smart_device(
        "living room lights", action
    )

    assert result["success"] is True
    assert result["device_id"] == "living_room_light"
    assert result["name"] == "Living Room Light"
    assert result["requested_state"] == action
    assert result["observed_state"] == action
    assert result["verified"] is True
    assert result["device"]["is_on"] is expected

    with sqlite3.connect(isolated_devices) as conn:
        persisted = conn.execute(
            "SELECT is_on FROM smart_devices WHERE device_id = ?",
            ("living_room_light",),
        ).fetchone()[0]
    assert bool(persisted) is expected


def test_control_is_idempotent(isolated_devices):
    first = smart_home_service.control_smart_device("bedroom_light", "on")
    second = smart_home_service.control_smart_device("bedroom_light", "on")
    assert first["verified"] is second["verified"] is True
    assert second["observed_state"] == "on"


@pytest.mark.parametrize(
    "device_id,action,error",
    [
        ("missing_device", "on", "Unknown device"),
        ("living_room_light", "blink", "Action must be 'on' or 'off'."),
        ("", "on", "Device ID must be a non-empty string."),
        ("living_room_light", None, "Action must be 'on' or 'off'."),
    ],
)
def test_control_rejects_invalid_device_or_action(
    isolated_devices, device_id, action, error
):
    with pytest.raises(ValueError, match=error.replace("'", "'")):
        smart_home_service.control_smart_device(device_id, action)


def test_status_reads_current_device_state(isolated_devices):
    smart_home_service.control_smart_device("living_room_light", "off")
    status = smart_home_service.get_device_status("living_room_light")
    assert status["device"]["is_on"] is False
    assert status["device"]["simulated"] is True

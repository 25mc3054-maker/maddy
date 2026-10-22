import json
import sqlite3
from pathlib import Path
from typing import Any

from app.database.db import initialize_database


# Use the same database file as the existing MADDY application.
DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "maddy.db"
)

# These are simulated devices, not connected physical hardware.
DEFAULT_DEVICES = [
    {
        "device_id": "living_room_light",
        "name": "Living Room Light",
        "device_type": "light",
        "room": "living room",
        "is_on": True,
        "brightness": 80,
        "temperature": None,
    },
    {
        "device_id": "bedroom_light",
        "name": "Bedroom Light",
        "device_type": "light",
        "room": "bedroom",
        "is_on": False,
        "brightness": 50,
        "temperature": None,
    },
    {
        "device_id": "living_room_fan",
        "name": "Living Room Fan",
        "device_type": "fan",
        "room": "living room",
        "is_on": True,
        "brightness": None,
        "temperature": None,
    },
    {
        "device_id": "living_room_thermostat",
        "name": "Living Room Thermostat",
        "device_type": "thermostat",
        "room": "living room",
        "is_on": True,
        "brightness": None,
        "temperature": 24.0,
    },
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_smart_home() -> None:
    """Create smart-home tables and seed demo devices if necessary."""
    initialize_database()

    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                device_type TEXT NOT NULL,
                room TEXT NOT NULL,
                is_on INTEGER NOT NULL DEFAULT 0,
                brightness INTEGER,
                temperature REAL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_automations (
                automation_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                actions_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS smart_home_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.executemany("""
            INSERT OR IGNORE INTO smart_devices
            (device_id, name, device_type, room, is_on, brightness, temperature)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            (
               d["device_id"],
               d["name"],
               d["device_type"],
               d["room"],
               int(d["is_on"]),
               d["brightness"],
               d["temperature"],
            )
            for d in DEFAULT_DEVICES
        ])

        # Safe demo automations. They only change registered demo devices.
        conn.executemany("""
            INSERT OR IGNORE INTO smart_automations
            (automation_id, name, actions_json)
            VALUES (?, ?, ?)
        """, [
            (
                "goodnight",
                "Good Night",
                json.dumps([
                    {"device_id": "living_room_light", "action": "off"},
                    {"device_id": "bedroom_light", "action": "off"},
                ]),
            ),
            (
                "movie_mode",
                "Movie Mode",
                json.dumps([
                    {"device_id": "living_room_light", "action": "on"},
                    {
                        "device_id": "living_room_light",
                        "action": "brightness",
                        "value": 20,
                    },
                ]),
            ),
        ])


def _device_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["is_on"] = bool(result["is_on"])
    result["simulated"] = True
    return result


def _normalize_device_token(value: str) -> str:
    token = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    while "__" in token:
        token = token.replace("__", "_")
    return token


def _normalize_action(action: str) -> str:
    cleaned = _normalize_device_token(action).replace("_", "")
    action_aliases = {
        "on": "on",
        "turnon": "on",
        "switchon": "on",
        "enable": "on",
        "start": "on",
        "off": "off",
        "turnoff": "off",
        "switchoff": "off",
        "disable": "off",
        "stop": "off",
    }
    if cleaned not in action_aliases:
        raise ValueError("Action must be 'on' or 'off'.")
    return action_aliases[cleaned]


def _get_device(conn, device_id: str):
    normalized = _normalize_device_token(device_id)
    candidates = [device_id, normalized]
    if normalized.endswith("s"):
        candidates.append(normalized[:-1])

    row = conn.execute(
        """
        SELECT * FROM smart_devices
        WHERE lower(device_id) IN ({})
           OR lower(name) IN ({})
        ORDER BY CASE WHEN lower(device_id) = lower(?) THEN 0 ELSE 1 END
        LIMIT 1
        """.format(",".join("?" for _ in candidates), ",".join("?" for _ in candidates)),
        (*candidates, *candidates, device_id),
    ).fetchone()

    if row is None:
        raise ValueError(
            f"Unknown device '{device_id}'. "
            "Use list_smart_devices to see available devices."
        )

    return row


def list_smart_devices() -> dict[str, Any]:
    initialize_smart_home()

    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM smart_devices ORDER BY room, name"
        ).fetchall()

    return {
        "success": True,
        "mode": "simulation",
        "count": len(rows),
        "devices": [_device_dict(row) for row in rows],
    }


def get_device_status(device_id: str) -> dict[str, Any]:
    initialize_smart_home()
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Device ID must be a non-empty string.")

    with _connect() as conn:
        row = _get_device(conn, device_id.strip())

    return {
        "success": True,
        "mode": "simulation",
        "device": _device_dict(row),
    }


def control_smart_device(
    device_id: str,
    action: str,
) -> dict[str, Any]:
    initialize_smart_home()

    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Device ID must be a non-empty string.")
    if not isinstance(action, str):
        raise ValueError("Action must be 'on' or 'off'.")

    device_id = device_id.strip()
    action = _normalize_action(action)

    with _connect() as conn:
        row = _get_device(conn, device_id)
        device_id = row["device_id"]
        device_type = row["device_type"]

        if device_type == "thermostat" and action == "on":
            # The thermostat is enabled, but no HVAC hardware is connected.
            pass

        cursor = conn.execute(
            """
            UPDATE smart_devices
            SET is_on = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
            """,
            (int(action == "on"), device_id),
        )

        conn.execute(
            """
            INSERT INTO smart_home_events (event_type, details_json)
            VALUES (?, ?)
            """,
            (
                "device_control",
                json.dumps({
                    "device_id": device_id,
                    "action": action,
                    "mode": "simulation",
                }),
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(f"Device '{device_id}' was not updated.")
        conn.commit()

    # Verify the committed value using a new database read, not the write
    # transaction's view of the row.
    with _connect() as conn:
        updated = _get_device(conn, device_id)

    requested_state = action == "on"
    observed_state = bool(updated["is_on"])
    verified = observed_state == requested_state
    if not verified:
        raise RuntimeError(
            f"Persisted state verification failed for '{device_id}': "
            f"requested {action}, observed {'on' if observed_state else 'off'}."
        )

    return {
        "success": True,
        "mode": "simulation",
        "device_id": device_id,
        "name": updated["name"],
        "requested_state": "on" if requested_state else "off",
        "observed_state": "on" if observed_state else "off",
        "verified": verified,
        "message": f"{updated['name']} simulated as {action}.",
        "device": _device_dict(updated),
    }


def set_device_brightness(
    device_id: str,
    brightness: int,
) -> dict[str, Any]:
    initialize_smart_home()
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Device ID must be a non-empty string.")

    if isinstance(brightness, bool) or not isinstance(brightness, int):
        raise ValueError("Brightness must be an integer from 0 to 100.")

    if not 0 <= brightness <= 100:
        raise ValueError("Brightness must be from 0 to 100.")

    with _connect() as conn:
        row = _get_device(conn, device_id.strip())
        device_id = row["device_id"]

        if row["device_type"] != "light":
            raise ValueError(
                f"{row['name']} is not a light."
            )

        conn.execute(
            """
            UPDATE smart_devices
            SET brightness = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
            """,
            (brightness, device_id),
        )

        updated = _get_device(conn, device_id)

    return {
        "success": True,
        "mode": "simulation",
        "message": f"Brightness set to {brightness}%.",
        "device": _device_dict(updated),
    }


def set_device_temperature(
    device_id: str,
    temperature: float,
) -> dict[str, Any]:
    initialize_smart_home()
    if not isinstance(device_id, str) or not device_id.strip():
        raise ValueError("Device ID must be a non-empty string.")

    if isinstance(temperature, bool) or not isinstance(
        temperature, (int, float)
    ):
        raise ValueError("Temperature must be a number.")

    if not 5 <= temperature <= 35:
        raise ValueError(
            "Temperature must be between 5°C and 35°C."
        )

    with _connect() as conn:
        row = _get_device(conn, device_id.strip())
        device_id = row["device_id"]

        if row["device_type"] != "thermostat":
            raise ValueError(
                f"{row['name']} is not a thermostat."
            )

        conn.execute(
            """
            UPDATE smart_devices
            SET temperature = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ?
            """,
            (float(temperature), device_id),
        )

        updated = _get_device(conn, device_id)

    return {
        "success": True,
        "mode": "simulation",
        "message": f"Target temperature set to {temperature}°C.",
        "device": _device_dict(updated),
    }


def run_automation(automation_id: str) -> dict[str, Any]:
    """Run a registered automation against simulated devices."""
    initialize_smart_home()

    with _connect() as conn:
        automation = conn.execute(
            """
            SELECT * FROM smart_automations
            WHERE automation_id = ? AND enabled = 1
            """,
            (automation_id,),
        ).fetchone()

        if automation is None:
            raise ValueError(
                f"Automation '{automation_id}' was not found or is disabled."
            )

        actions = json.loads(automation["actions_json"])
        results = []

        # Validate all actions before changing any device.
        for item in actions:
            device = _get_device(conn, item["device_id"])
            action = item["action"]

            if action in {"on", "off"}:
                pass
            elif action == "brightness":
                if device["device_type"] != "light":
                    raise ValueError(
                        f"{device['name']} does not support brightness."
                    )

                value = item.get("value")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or not 0 <= value <= 100
                ):
                    raise ValueError(
                        "Automation brightness must be an integer from 0 to 100."
                    )
            else:
                raise ValueError(
                    f"Unsupported automation action: {action}"
                )

        # Atomic execution: a failure rolls back the whole routine.
        try:
            conn.execute("BEGIN")

            for item in actions:
                device_id = item["device_id"]
                action = item["action"]

                if action in {"on", "off"}:
                    conn.execute(
                        """
                        UPDATE smart_devices
                        SET is_on = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE device_id = ?
                        """,
                        (int(action == "on"), device_id),
                    )
                elif action == "brightness":
                    conn.execute(
                        """
                        UPDATE smart_devices
                        SET brightness = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE device_id = ?
                        """,
                        (item["value"], device_id),
                    )

                results.append({
                    "device_id": device_id,
                    "action": action,
                    "success": True,
                })

            conn.execute(
                """
                INSERT INTO smart_home_events (event_type, details_json)
                VALUES (?, ?)
                """,
                (
                    "automation",
                    json.dumps({
                        "automation_id": automation_id,
                        "name": automation["name"],
                        "mode": "simulation",
                    }),
                ),
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise

    return {
        "success": True,
        "mode": "simulation",
        "automation": automation["name"],
        "message": f"Automation '{automation['name']}' executed.",
        "actions": results,
    }

"""Backwards-compatibility shim for the old monolithic ``libs`` module."""

import json

from .config import *  # noqa: F401,F403
from .config import load_config, schedule_for_now
from .heating import *  # noqa: F401,F403
from .influx import *  # noqa: F401,F403
from .influx import DB_NAME, age_seconds, read_latest
from .mqtt import *  # noqa: F401,F403


def return_current_settings(connection=None):
    """Legacy API: return (per-room setpoints, period name)."""
    config = load_config(connection)
    period, setpoints = schedule_for_now(config['schedule'])
    return setpoints, period


def return_current_temps(connection=None):
    """Legacy API: return {room: [{'value': ..., 'time_difference': seconds}]}."""
    config = load_config(connection)
    temperatures = {}
    for room, raw in config['rooms'].items():
        room_config = json.loads(raw) if isinstance(raw, str) else raw
        point = read_latest(DB_NAME, room_config['measurement'], connection)
        if not point:
            temperatures[room] = []
            continue
        temperatures[room] = [{
            'value': point.get(room_config.get('value_name', 'value')),
            'time_difference': age_seconds(point.get('time')),
        }]
    return temperatures

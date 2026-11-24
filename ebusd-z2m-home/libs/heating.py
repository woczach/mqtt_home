"""Pure heating control logic: inputs -> decision (no I/O)."""

import json
import logging
from datetime import datetime, time

log = logging.getLogger(__name__)

PERIODS = ('Morning', 'Day', 'Evening', 'Night')
MAX_BOILER_SETTEMP = 75.0


def parse_hhmm(value):
    """Parse 'HH:MM' (or a datetime/time) into a datetime.time."""
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    parts = str(value).strip().split(':')
    if len(parts) != 2:
        raise ValueError(f'invalid time {value!r}, expected HH:MM')
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f'invalid time {value!r}, expected HH:MM')
    return time(hour, minute)


def normalize_hhmm(value):
    parsed = parse_hhmm(value)
    return f'{parsed.hour:02d}:{parsed.minute:02d}'


def is_time_in_range(start, end, current):
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def is_now_in_windows(windows, now=None):
    """True when `now` is inside any of the configured windows.

    An empty/None list means "always active" (matches the legacy behaviour).
    Supports windows spanning midnight.
    """
    if isinstance(windows, str):
        windows = json.loads(windows) if windows.strip() else []
    if not windows:
        return True
    current = (now or datetime.now()).time()
    for window in windows:
        if not isinstance(window, dict):
            continue
        try:
            start = parse_hhmm(window.get('start'))
            end = parse_hhmm(window.get('end'))
        except (ValueError, TypeError, AttributeError) as exc:
            log.warning('ignoring invalid water window %r: %s', window, exc)
            continue
        if is_time_in_range(start, end, current):
            return True
    return False


def parse_thresholds(table):
    """Return {threshold: settemp} as floats from a dict/JSON string."""
    if isinstance(table, str):
        table = json.loads(table) if table.strip() else {}
    result = {}
    if isinstance(table, dict):
        for key, value in table.items():
            try:
                result[float(key)] = float(value)
            except (TypeError, ValueError):
                log.warning('ignoring invalid table entry %r: %r', key, value)
    elif isinstance(table, list):
        for item in table:
            if not isinstance(item, dict):
                continue
            try:
                result[float(item['threshold'])] = float(item['settemp'])
            except (KeyError, TypeError, ValueError):
                continue
    return result


def curve_settemp(table, t_out, t_min=None, t_max=None):
    """Interpolate a weather curve {outdoor: settemp}. None when unusable."""
    if t_out is None:
        return None
    points = parse_thresholds(table)
    if not points:
        return None
    temperatures = sorted(points)
    if len(temperatures) == 1 or t_out <= temperatures[0]:
        value = points[temperatures[0]]
    elif t_out >= temperatures[-1]:
        value = points[temperatures[-1]]
    else:
        value = points[temperatures[-1]]
        for low, high in zip(temperatures, temperatures[1:]):
            if low <= t_out <= high:
                span = high - low
                ratio = (t_out - low) / span if span else 0.0
                value = points[low] + ratio * (points[high] - points[low])
                break
    if t_min is not None:
        value = max(value, float(t_min))
    if t_max is not None:
        value = min(value, float(t_max))
    return value


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return False


def _fmt(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def override_string(settemp, piec_off, woda, woda_off):
    """Build the ebusd SetModeOverride payload."""
    return f'0;{_fmt(settemp)};{_fmt(woda)};-;-;{int(piec_off)};0;{_fmt(woda_off)};-;0;0;0'


def _entry(setpoint, temp=None, age_s=None, stale=True):
    return {
        'temp': temp,
        'age_s': age_s,
        'setpoint': setpoint,
        'diff': None,
        'valve': None,
        'target': None,
        'stale': stale,
        'action': 'keep',
    }


def decide(schedule_for_now, rooms_config, latest_temps, controller_config,
           water_config=None, now=None, outdoor=None):
    """Compute valve/boiler decisions without touching MQTT or InfluxDB.

    schedule_for_now: (period, {room: setpoint}) as returned by config.schedule_for_now
    rooms_config:     parsed or raw rooms section (unused for control, kept for context)
    latest_temps:     {room: {'value': float|None, 'age_s': float|None}}
    controller_config: controller section (dict)
    water_config:     water section (dict) - defaults to always-on DHW
    outdoor:          {'value': float|None, 'age_s': float|None} outside temperature
    """
    now = now or datetime.now()
    controller_config = controller_config or {}
    water_config = water_config or {}
    outdoor = outdoor or {}

    if isinstance(schedule_for_now, (tuple, list)) and len(schedule_for_now) == 2:
        period, setpoints = schedule_for_now
    elif isinstance(schedule_for_now, dict):
        period = schedule_for_now.get('period')
        setpoints = schedule_for_now.get('setpoints', {})
    else:
        period, setpoints = None, {}

    fallback_mode = controller_config.get('fallback_mode', 'skip')
    max_age = float(controller_config.get('max_sensor_age_s', 900))
    off_temp = float(controller_config.get('valve_off_temp', 16.0))
    on_temp = float(controller_config.get('valve_on_temp', 24.0))
    settemp_min = float(controller_config.get('settemp_min', 40))
    room_priority = controller_config.get('room_priority', 'Jozef')

    curve_enabled = _truthy(controller_config.get('curve_enabled', False))
    curve_max_age = float(controller_config.get('curve_max_age_s', 3600))
    curve_trim_k = float(controller_config.get('curve_trim_k', 3.0))
    curve_trim_max = float(controller_config.get('curve_trim_max', 5.0))
    curve_off_temp = float(controller_config.get('curve_off_temp', 15.0))
    curve_table = parse_thresholds(controller_config.get('curve', {}))

    t_out = outdoor.get('value')
    t_out_age = outdoor.get('age_s')
    outdoor_fresh = (t_out is not None and t_out_age is not None
                     and float(t_out_age) <= curve_max_age)
    curve_active = (curve_enabled and outdoor_fresh
                    and len(curve_table) >= 2)
    curve_base = (curve_settemp(curve_table, t_out, t_min=settemp_min,
                                t_max=MAX_BOILER_SETTEMP)
                  if curve_active else None)

    rooms = {}
    diffs = {}
    valid_rooms = []
    fresh_rooms = []
    stale_rooms = []

    for room, raw_setpoint in setpoints.items():
        try:
            setpoint = float(raw_setpoint)
        except (TypeError, ValueError):
            setpoint = 0.0

        info = latest_temps.get(room) or {}
        temp = info.get('value')
        age_s = info.get('age_s')
        stale = temp is None or age_s is None or age_s > max_age
        entry = _entry(setpoint, temp, age_s, stale)

        if not stale:
            fresh_rooms.append(room)
        else:
            stale_rooms.append(room)

        if setpoint <= 0:
            # 0.0 = room off: close its valve, never contributes to the boiler.
            entry.update(valve='close', target=off_temp, action='close')
            rooms[room] = entry
            continue

        if stale:
            if fallback_mode == 'safe':
                entry.update(valve='open', target=on_temp, action='open')
            elif fallback_mode == 'hold' and temp is not None and age_s is not None:
                diff = float(temp) - setpoint
                action = 'close' if diff >= 1 else 'open'
                entry.update(diff=diff, valve=action,
                             target=off_temp if action == 'close' else on_temp,
                             action=action)
            else:
                entry.update(action='keep')
            rooms[room] = entry
            continue

        if temp is None:
            # Unreachable (stale would be True), keeps type checkers happy.
            entry.update(action='keep')
            rooms[room] = entry
            continue
        valid_rooms.append(room)
        diff = float(temp) - setpoint
        action = 'close' if diff >= 1 else 'open'
        entry.update(diff=diff, valve=action,
                     target=off_temp if action == 'close' else on_temp,
                     action=action)
        diffs[room] = diff
        rooms[room] = entry

    fallback_active = not fresh_rooms
    settemp = settemp_min
    piec_off = 1
    trim = 0.0

    if fallback_active:
        # No usable room feedback: fall back to the outdoor curve when it is
        # available, otherwise keep the legacy safe default (boiler enabled at
        # settemp_min so the TRV thermostats cannot freeze the house).
        if curve_active:
            settemp = min(MAX_BOILER_SETTEMP, curve_base)
            piec_off = 0 if t_out < curve_off_temp else 1
            reason = 'fallback: no fresh room data, outdoor curve only'
        else:
            piec_off = 0
            reason = 'fallback: no fresh sensor data'
        for room, entry in rooms.items():
            if fallback_mode == 'safe':
                entry.update(valve='open', target=on_temp, action='open')
            else:
                entry.update(valve=None, target=None, action='keep')
    elif diffs:
        smallest_room = min(diffs, key=lambda room: diffs[room])
        smallest_value = diffs[smallest_room]
        if smallest_value < 0:
            piec_off = 0
            if curve_active:
                mean_diff = sum(diffs.values()) / len(diffs)
                trim = max(-curve_trim_max,
                           min(curve_trim_max, curve_trim_k * -mean_diff))
                settemp = min(MAX_BOILER_SETTEMP,
                              max(settemp_min, curve_base + trim))
                reason = (f'heating requested by {smallest_room} '
                          f'(diff {smallest_value:.2f}), curve '
                          f'{curve_base:.1f} trim {trim:+.1f}')
            else:
                table_key = 'jodiff' if smallest_room == room_priority else 'podiff'
                thresholds = parse_thresholds(controller_config.get(table_key, {}))
                matching = [threshold for threshold in thresholds
                            if smallest_value < threshold]
                if matching:
                    settemp = float(thresholds[min(matching)])
                reason = f'heating requested by {smallest_room} (diff {smallest_value:.2f})'
        else:
            settemp = curve_base if curve_active else settemp_min
            reason = 'all rooms at or above their setpoint'
    else:
        settemp = curve_base if curve_active else settemp_min
        reason = 'no heating demand (all rooms off or no diffs)'

    woda = float(water_config.get('woda', 42.0))
    woda_off = float(water_config.get('woda_off', 0.0))
    override_until = float(water_config.get('override_until', 0) or 0)
    override_temp = float(water_config.get('override_temp', 55.0))
    water_override = override_until > now.timestamp()
    if water_override:
        water_active = True
        woda_value = override_temp
    else:
        water_active = is_now_in_windows(water_config.get('water_times', []), now)
        woda_value = woda if water_active else woda_off

    return {
        'period': period,
        'rooms': rooms,
        'boiler': {
            'settemp': settemp,
            'piec_off': piec_off,
            'override': override_string(settemp, piec_off, woda_value, woda_off),
        },
        'water': {
            'active': water_active,
            'temp': woda_value,
            'woda': woda,
            'woda_off': woda_off,
            'override': water_override,
            'override_until': override_until,
            'override_temp': override_temp,
        },
        'fallback_active': fallback_active,
        'reason': reason,
        'valid_rooms': valid_rooms,
        'stale_rooms': stale_rooms,
        'outdoor': {
            'temp': t_out,
            'age_s': t_out_age,
            'fresh': outdoor_fresh,
            'curve_active': curve_active,
            'curve_settemp': curve_base,
            'trim': trim,
            'off_temp': curve_off_temp,
        },
    }


__all__ = [
    'PERIODS', 'parse_hhmm', 'normalize_hhmm', 'is_time_in_range',
    'is_now_in_windows', 'parse_thresholds', 'curve_settemp', 'override_string',
    'decide',
]

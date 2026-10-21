"""Single source of truth for configuration (stored in InfluxDB, measurement `config`)."""

import json
import logging
import math
from datetime import datetime

from .heating import (PERIODS, is_time_in_range, normalize_hhmm, parse_hhmm)
from .influx import (DB_NAME, DEFAULT_CONNECTION, get_influx_client, push_to_db,
                     read_latest)

log = logging.getLogger(__name__)

DEFAULT_ROOMS = ('Jozef', 'Kuchnia', 'Salon', 'Sypialnia')
PERIOD_TIME_FIELDS = {
    'Morning': 'MorningHour',
    'Day': 'DayHour',
    'Evening': 'EveningHour',
    'Night': 'NightHour',
}
TIME_FIELDS = set(PERIOD_TIME_FIELDS.values())

ROOM_DEFAULTS = {
    'Jozef': {'measurement': 'esp/tem', 'value_name': 'value',
              'zigbee': '0xa4c138ad1d132790'},
    'Kuchnia': {'measurement': 'esp/kuchnia', 'value_name': 'value',
                'zigbee': '0xa4c138d0aa4d2b86'},
    'Salon': {'measurement': 'rpi_temperatura', 'value_name': 'celsius',
              'zigbee': '0xa4c1384e6bcc60c6'},
    'Sypialnia': {'measurement': 'esp/sypialnia', 'value_name': 'value',
                  'zigbee': '0x94deb8fffe2e751a'},
}
ROOM_FIELDS = set(next(iter(ROOM_DEFAULTS.values())).keys())

SCHEDULE_DEFAULTS = {
    'MorningHour': '05:50',
    'DayHour': '06:45',
    'EveningHour': '18:00',
    'NightHour': '21:30',
    'JozefMorningHour': 21.2,
    'JozefDayHour': 20.5,
    'JozefEveningHour': 21.2,
    'JozefNightHour': 21.3,
    'SalonMorningHour': 22.3,
    'SalonDayHour': 21.8,
    'SalonEveningHour': 21.8,
    'SalonNightHour': 0.0,
    'SypialniaMorningHour': 0.0,
    'SypialniaDayHour': 0.0,
    'SypialniaEveningHour': 22.5,
    'SypialniaNightHour': 22.5,
    'KuchniaMorningHour': 0.0,
    'KuchniaDayHour': 21.0,
    'KuchniaEveningHour': 21.0,
    'KuchniaNightHour': 0.0,
}

CONTROLLER_DEFAULTS = {
    'valve_off_temp': 16.0,
    'valve_on_temp': 24.0,
    'settemp_min': 40.0,
    'podiff': json.dumps({'-0.25': 45, '-0.5': 50, '-2': 60}, sort_keys=True),
    'jodiff': json.dumps({'-0.5': 40, '-1': 45, '-2': 50}, sort_keys=True),
    'max_sensor_age_s': 900.0,
    'fallback_mode': 'skip',
    'loop_interval_s': 120.0,
    'room_priority': 'Jozef',
}
CONTROLLER_NUMERIC = {
    'valve_off_temp', 'valve_on_temp', 'settemp_min',
    'max_sensor_age_s', 'loop_interval_s',
}
FALLBACK_MODES = ('hold', 'safe', 'skip')

WATER_DEFAULTS = {
    'woda': 42.0,
    'woda_off': 0.0,
    'water_times': json.dumps([]),
}

DEFAULTS = {
    'schedule': SCHEDULE_DEFAULTS,
    'controller': CONTROLLER_DEFAULTS,
    'water': WATER_DEFAULTS,
    'rooms': {room: json.dumps(values, sort_keys=True)
              for room, values in ROOM_DEFAULTS.items()},
}

SECTIONS = tuple(DEFAULTS)
SCHEDULE_ROOM_FIELDS = {f'{room}{period}Hour'
                        for room in DEFAULT_ROOMS for period in PERIODS}


class ConfigError(Exception):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__('; '.join(self.errors))


def _loads(value):
    if isinstance(value, str):
        return json.loads(value) if value.strip() else None
    return value


def _as_float(value):
    if isinstance(value, bool):
        raise ValueError(f'expected a number, got {value!r}')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'expected a finite number, got {value!r}')
    return number


def _allowed_fields(section):
    if section == 'schedule':
        return TIME_FIELDS | SCHEDULE_ROOM_FIELDS
    if section == 'controller':
        return set(CONTROLLER_DEFAULTS)
    if section == 'water':
        return set(WATER_DEFAULTS)
    return None


def _merge_section(section, base, overrides):
    merged = {}
    if section == 'rooms':
        for room, raw in base.items():
            stored = _loads(raw)
            if not isinstance(stored, dict):
                raise ValueError(f'room {room!r} must be an object')
            merged[room] = json.dumps(stored, sort_keys=True)
        for room, raw in overrides.items():
            current = {}
            if room in merged:
                stored = _loads(merged[room])
                if isinstance(stored, dict):
                    current = dict(stored)
            incoming = _loads(raw)
            if not isinstance(incoming, dict):
                raise ValueError(f'room {room!r} must be an object')
            current.update(incoming)
            merged[room] = json.dumps(current, sort_keys=True)
        return merged
    merged.update(base)
    merged.update(overrides)
    return merged


def _normalize_section(section, values):
    result = {}
    if section == 'schedule':
        for key, value in values.items():
            if key in TIME_FIELDS:
                result[key] = normalize_hhmm(value)
            elif key in SCHEDULE_ROOM_FIELDS:
                result[key] = _as_float(value)
            else:
                result[key] = value
        return result
    if section == 'controller':
        for key, value in values.items():
            if key in CONTROLLER_NUMERIC:
                result[key] = _as_float(value)
            elif key in ('podiff', 'jodiff'):
                result[key] = json.dumps(_loads(value), sort_keys=True)
            else:
                result[key] = value
        return result
    if section == 'water':
        for key, value in values.items():
            if key in ('woda', 'woda_off'):
                result[key] = _as_float(value)
            elif key == 'water_times':
                result[key] = json.dumps(_loads(value), sort_keys=True)
            else:
                result[key] = value
        return result
    if section == 'rooms':
        for room, raw in values.items():
            result[room] = json.dumps(_loads(raw), sort_keys=True)
        return result
    return dict(values)


def validate_section(section, values):
    """Validate a (normally merged) section. Returns (ok, errors)."""
    if section not in SECTIONS:
        return False, [f'unknown section {section!r}']
    if not isinstance(values, dict):
        return False, ['values must be an object']

    errors = []
    allowed = _allowed_fields(section)
    if allowed is not None:
        for key in values:
            if key not in allowed:
                errors.append(f'unknown field {key!r} for section {section!r}')

    if section == 'schedule':
        for key, value in values.items():
            if key in TIME_FIELDS:
                try:
                    normalize_hhmm(value)
                except (TypeError, ValueError):
                    errors.append(f'{key} must be a HH:MM time, got {value!r}')
            elif key in SCHEDULE_ROOM_FIELDS:
                try:
                    if _as_float(value) < 0:
                        errors.append(f'{key} must not be negative')
                except (TypeError, ValueError):
                    errors.append(f'{key} must be a number, got {value!r}')

    elif section == 'controller':
        for key, value in values.items():
            if key in CONTROLLER_NUMERIC:
                try:
                    number = _as_float(value)
                except (TypeError, ValueError):
                    errors.append(f'{key} must be a number, got {value!r}')
                    continue
                if key in ('max_sensor_age_s', 'loop_interval_s') and number <= 0:
                    errors.append(f'{key} must be greater than zero')
                elif key not in ('max_sensor_age_s', 'loop_interval_s') and number < 0:
                    errors.append(f'{key} must not be negative')
            elif key in ('podiff', 'jodiff'):
                try:
                    table = _loads(value)
                except (TypeError, ValueError):
                    errors.append(f'{key} must be valid JSON')
                    continue
                if not isinstance(table, dict):
                    errors.append(f'{key} must be a JSON object of threshold:settemp')
                    continue
                for threshold, settemp in table.items():
                    try:
                        _as_float(threshold)
                        _as_float(settemp)
                    except (TypeError, ValueError):
                        errors.append(f'{key} contains invalid entry {threshold!r}: {settemp!r}')
            elif key == 'fallback_mode' and value not in FALLBACK_MODES:
                errors.append(f'fallback_mode must be one of {FALLBACK_MODES}')
            elif key == 'room_priority' and value not in DEFAULT_ROOMS:
                errors.append(f'room_priority must be one of {DEFAULT_ROOMS}')

    elif section == 'water':
        for key, value in values.items():
            if key in ('woda', 'woda_off'):
                try:
                    if _as_float(value) < 0:
                        errors.append(f'{key} must not be negative')
                except (TypeError, ValueError):
                    errors.append(f'{key} must be a number, got {value!r}')
            elif key == 'water_times':
                try:
                    windows = _loads(value)
                except (TypeError, ValueError):
                    errors.append('water_times must be valid JSON')
                    continue
                if not isinstance(windows, list):
                    errors.append('water_times must be a JSON list')
                    continue
                for index, window in enumerate(windows):
                    if not isinstance(window, dict):
                        errors.append(f'water_times[{index}] must be an object')
                        continue
                    extra = set(window) - {'start', 'end'}
                    if extra:
                        errors.append(f'water_times[{index}] has unknown keys {sorted(extra)}')
                    for key in ('start', 'end'):
                        if key not in window:
                            errors.append(f'water_times[{index}] is missing {key!r}')
                            continue
                        try:
                            normalize_hhmm(window[key])
                        except (TypeError, ValueError):
                            errors.append(
                                f'water_times[{index}].{key} must be a HH:MM time')

    elif section == 'rooms':
        for room, raw in values.items():
            if not isinstance(room, str) or not room.strip():
                errors.append('room names must be non-empty strings')
                continue
            try:
                room_config = _loads(raw)
            except (TypeError, ValueError):
                errors.append(f'room {room!r} must be valid JSON')
                continue
            if not isinstance(room_config, dict):
                errors.append(f'room {room!r} must be a JSON object')
                continue
            extra = set(room_config) - ROOM_FIELDS
            missing = ROOM_FIELDS - set(room_config)
            if extra:
                errors.append(f'room {room!r} has unknown fields {sorted(extra)}')
            if missing:
                errors.append(f'room {room!r} is missing fields {sorted(missing)}')
            for key in ROOM_FIELDS & set(room_config):
                if not isinstance(room_config[key], str) or not room_config[key].strip():
                    errors.append(f'room {room!r}.{key} must be a non-empty string')

    return not errors, errors


def read_section(section, connection=None):
    client = get_influx_client(DB_NAME, connection)
    try:
        query = (f'SELECT * FROM "config" WHERE "section" = \'{section}\' '
                 f'ORDER BY time DESC LIMIT 1')
        result = client.query(query)
    finally:
        client.close()
    points = list(result.get_points())
    if not points:
        return None
    point = points[0]
    allowed = _allowed_fields(section)
    if allowed is None:
        # Rooms have dynamic names; exclude keys that belong to other sections.
        excluded = (TIME_FIELDS | SCHEDULE_ROOM_FIELDS
                    | set(CONTROLLER_DEFAULTS) | set(WATER_DEFAULTS))
    else:
        excluded = set()

    result = {}
    for key, value in point.items():
        if value is None or key in ('time', 'section', 'measurement'):
            continue
        if allowed is not None and key not in allowed:
            continue
        if key in excluded:
            continue
        result[key] = value
    return result


def _seed_schedule(connection):
    try:
        point = read_latest(DB_NAME, 'time_measurement', connection)
    except Exception:
        log.exception('could not read legacy time_measurement for seeding')
        return None
    if not point:
        return None

    values = {}
    for key in TIME_FIELDS:
        if point.get(key) is not None:
            try:
                values[key] = normalize_hhmm(point[key])
            except (TypeError, ValueError):
                log.warning('ignoring invalid legacy time %s=%r', key, point[key])
    for room in DEFAULT_ROOMS:
        for period in PERIODS:
            key = f'{room}{period}Hour'
            if point.get(key) is not None:
                try:
                    values[key] = _as_float(point[key])
                except (TypeError, ValueError):
                    log.warning('ignoring invalid legacy value %s=%r', key, point[key])
    if not values:
        return None

    try:
        saved = save_config(connection, 'schedule', values)
        log.info('seeded config/schedule from legacy time_measurement')
        return saved
    except Exception:
        log.exception('failed to persist seeded config/schedule; using in memory')
        return values


def load_config(connection=None):
    conn = connection or DEFAULT_CONNECTION
    config = {}
    for section in SECTIONS:
        stored = read_section(section, conn)
        if stored is None and section == 'schedule':
            stored = _seed_schedule(conn)
        try:
            merged = _merge_section(section, DEFAULTS[section], stored or {})
            config[section] = _normalize_section(section, merged)
        except (TypeError, ValueError):
            log.exception('invalid stored config for %r; falling back to defaults', section)
            config[section] = _normalize_section(section, DEFAULTS[section])
    return config


def save_config(connection, section, values):
    if section not in SECTIONS:
        raise ConfigError([f'unknown section {section!r}'])
    if not isinstance(values, dict):
        raise ConfigError(['values must be an object'])

    current = read_section(section, connection) or {}
    try:
        merged = _merge_section(section, DEFAULTS[section], current)
        merged = _merge_section(section, merged, values)
        merged = _normalize_section(section, merged)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigError([str(exc)]) from exc

    ok, errors = validate_section(section, merged)
    if not ok:
        raise ConfigError(errors)

    point = {'measurement': 'config', 'tags': {'section': section}, 'fields': merged}
    push_to_db(DB_NAME, [point], connection)
    return merged


def schedule_for_now(schedule, now=None):
    """Return (period_name, {room: setpoint}) for the given moment."""
    schedule = schedule or DEFAULTS['schedule']
    current_time = (now or datetime.now()).time()

    times = {}
    for key in TIME_FIELDS:
        try:
            times[key] = parse_hhmm(schedule.get(key, DEFAULTS['schedule'][key]))
        except (TypeError, ValueError):
            times[key] = parse_hhmm(DEFAULTS['schedule'][key])

    segments = (
        ('Morning', 'MorningHour', 'DayHour'),
        ('Day', 'DayHour', 'EveningHour'),
        ('Evening', 'EveningHour', 'NightHour'),
        ('Night', 'NightHour', 'MorningHour'),
    )
    period = None
    for name, start_key, end_key in segments:
        if is_time_in_range(times[start_key], times[end_key], current_time):
            period = name
            break
    if period is None:
        log.warning('no schedule period matches %s; using Night', current_time)
        period = 'Night'

    setpoints = {}
    for room in DEFAULT_ROOMS:
        key = f'{room}{period}Hour'
        try:
            setpoints[room] = _as_float(schedule.get(key, 0.0))
        except (TypeError, ValueError):
            setpoints[room] = 0.0
    return period, setpoints


__all__ = [
    'PERIODS', 'DEFAULT_ROOMS', 'PERIOD_TIME_FIELDS', 'TIME_FIELDS',
    'ROOM_FIELDS', 'ROOM_DEFAULTS', 'SCHEDULE_DEFAULTS',
    'CONTROLLER_DEFAULTS', 'WATER_DEFAULTS', 'DEFAULTS', 'SECTIONS',
    'ConfigError', 'validate_section', 'read_section', 'load_config',
    'save_config', 'schedule_for_now',
]

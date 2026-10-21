"""InfluxDB helpers shared by all services."""

import logging
import re
from datetime import datetime, timezone

from influxdb import InfluxDBClient

log = logging.getLogger(__name__)

DB_NAME = 'heat'

DEFAULT_CONNECTION = {
    'URL': '192.168.0.230',
    'PORT': 8086,
    'DBUSER': 'username',
    'DBPASS': 'password',
}

# Kept for backwards compatibility with the old libs module.
connection = dict(DEFAULT_CONNECTION)


def get_influx_client(db=DB_NAME, conn=None):
    conn = conn or DEFAULT_CONNECTION
    return InfluxDBClient(
        host=conn['URL'],
        port=conn['PORT'],
        database=db,
        username=conn['DBUSER'],
        password=conn['DBPASS'],
        ssl=False,
        verify_ssl=False,
    )


def push_to_db(db, json_body, connection=None):
    client = get_influx_client(db, connection)
    try:
        response = client.write_points(json_body)
        if not response:
            log.error('Failed to write %d point(s) to InfluxDB', len(json_body))
        return response
    finally:
        client.close()


def read_from_db(db, measurment, connection=None, limit=1):
    client = get_influx_client(db, connection)
    try:
        query = f'SELECT * FROM "{measurment}" ORDER BY time DESC LIMIT {int(limit)}'
        return client.query(query)
    finally:
        client.close()


def read_latest(db, measurement, connection=None):
    result = read_from_db(db, measurement, connection, 1)
    points = list(result.get_points())
    return points[0] if points else None


_TIME_RE = re.compile(
    r'^(?P<base>\d{4}-\d{2}-\d{2})[T ](?P<clock>\d{2}:\d{2}:\d{2})'
    r'(?:\.(?P<frac>\d+))?(?P<tz>Z|[+-]\d{2}:?\d{2})?$'
)


def parse_time(value):
    """Parse the timestamp strings emitted by influxdb-python (ns precision safe)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    match = _TIME_RE.match(str(value).strip())
    if not match:
        raise ValueError(f'unsupported InfluxDB time: {value!r}')
    fraction = (match.group('frac') or '')[:6].ljust(6, '0')
    tz = match.group('tz') or ''
    if tz == 'Z':
        tz = '+00:00'
    elif tz and ':' not in tz:
        tz = f'{tz[:3]}:{tz[3:]}'
    text = f"{match.group('base')}T{match.group('clock')}.{fraction}{tz}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def age_seconds(value, now=None):
    if value is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - parse_time(value)).total_seconds())


def measurments_preparation_sent(topic, type, body, connection=None):
    """Legacy ebusd value parser/writer (kept for watcher/back-compat)."""
    match type:
        case 'float':
            value = float(body.decode())
        case 'floatColon':
            value = float(body.decode().split(';')[0])
        case 'int':
            value = body.decode()
        case 'onoff':
            value = 1 if body.decode() == 'on' else 0
        case _:
            raise ValueError(f'unknown ebusd value type {type!r}')
    data = [{'measurement': topic, 'fields': {'value': value}}]
    push_to_db(DB_NAME, data, connection)
    log.debug('%s value = %s', topic, value)
    return value


__all__ = [
    'DB_NAME', 'DEFAULT_CONNECTION', 'connection', 'get_influx_client',
    'push_to_db', 'read_from_db', 'read_latest', 'parse_time', 'age_seconds',
    'measurments_preparation_sent',
]

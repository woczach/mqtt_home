"""Schedule/config editor and status API."""

import json
import logging
import os
from datetime import datetime, timezone

import flask

from libs import (DB_NAME, DEFAULT_CONNECTION, SECTIONS, ConfigError,
                  age_seconds, load_config, read_latest, save_config)

logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
log = logging.getLogger('frontend')

app = flask.Flask(__name__)
connection = DEFAULT_CONNECTION

BOILER_TOPICS = (
    'FlowTemp', 'FlowTempDesired', 'HwcTemp', 'HwcTempDesired',
    'StorageTemp', 'StorageTempDesired', 'WaterPressure', 'ReturnTemp',
    'HeatingSwitch', 'HwcSwitch',
)


def _loads(value):
    return json.loads(value) if isinstance(value, str) else value


def _max_sensor_age(config):
    try:
        return float(config['controller'].get('max_sensor_age_s', 900))
    except (TypeError, ValueError):
        return 900.0


def _latest_measurement(measurement, value_name='value', now=None):
    point = read_latest(DB_NAME, measurement, connection)
    if not point:
        return {'value': None, 'time': None, 'age_s': None}
    return {
        'value': point.get(value_name),
        'time': point.get('time'),
        'age_s': age_seconds(point.get('time'), now),
    }


@app.route('/')
def index():
    return flask.render_template('index.html')


@app.route('/healthz')
def healthz():
    return flask.jsonify({'ok': True})


@app.get('/api/config')
def api_get_config():
    try:
        return flask.jsonify(load_config(connection))
    except Exception as exc:
        log.exception('could not read config')
        return flask.jsonify({'error': str(exc)}), 500


@app.put('/api/config')
def api_put_config():
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict):
        return flask.jsonify({'errors': ['request body must be a JSON object']}), 400

    try:
        if 'section' in payload:
            values = payload.get('values', {})
            if not isinstance(values, dict):
                return flask.jsonify(
                    {'errors': ['values must be an object']}), 400
            save_config(connection, payload['section'], values)
        else:
            unknown = set(payload) - set(SECTIONS)
            if unknown:
                return flask.jsonify(
                    {'errors': [f'unknown section(s): {sorted(unknown)}']}), 400
            for section in SECTIONS:
                if section in payload:
                    values = payload[section]
                    if not isinstance(values, dict):
                        return flask.jsonify(
                            {'errors': [f'{section} must be an object']}), 400
                    save_config(connection, section, values)
        return flask.jsonify(load_config(connection))
    except ConfigError as exc:
        log.warning('rejected config update: %s', exc.errors)
        return flask.jsonify({'errors': exc.errors}), 400
    except Exception as exc:
        log.exception('could not save config')
        return flask.jsonify({'error': str(exc)}), 500


@app.get('/api/status')
def api_status():
    try:
        config = load_config(connection)
    except Exception as exc:
        log.exception('could not read config for status')
        return flask.jsonify({'error': str(exc)}), 500

    now = datetime.now(timezone.utc)
    max_age = _max_sensor_age(config)

    rooms = {}
    for room, raw in config['rooms'].items():
        try:
            room_config = _loads(raw)
            measurement = room_config['measurement']
            value_name = room_config.get('value_name', 'value')
        except (TypeError, ValueError, KeyError):
            log.exception('invalid room config for %s', room)
            rooms[room] = {'measurement': None, 'value': None, 'time': None,
                           'age_s': None, 'stale': True}
            continue
        latest = _latest_measurement(measurement, value_name, now)
        age = latest['age_s']
        rooms[room] = {
            'measurement': measurement,
            'value': latest['value'],
            'time': latest['time'],
            'age_s': age,
            'stale': age is None or age > max_age,
        }

    boiler = {}
    for name in BOILER_TOPICS:
        latest = _latest_measurement(f'ebusd/bai/{name}', 'value', now)
        boiler[name] = latest

    try:
        last_decision = read_latest(DB_NAME, 'decisions', connection)
    except Exception:
        log.exception('could not read last decision')
        last_decision = None

    water_config = config['water']
    override_until = float(water_config.get('override_until', 0) or 0)
    water = {
        'woda': float(water_config.get('woda', 0.0)),
        'woda_off': float(water_config.get('woda_off', 0.0)),
        'override_active': override_until > now.timestamp(),
        'override_until': override_until,
        'override_temp': float(water_config.get('override_temp', 55.0)),
    }

    return flask.jsonify({
        'now': now.isoformat(),
        'max_sensor_age_s': max_age,
        'rooms': rooms,
        'boiler': boiler,
        'water': water,
        'last_decision': last_decision,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)

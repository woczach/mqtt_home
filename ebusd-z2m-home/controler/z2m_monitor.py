"""Heating controller: read Influx config/temps, decide, publish valves + boiler."""

import json
import logging
import os
import time

from libs import (DB_NAME, DEFAULT_BROKER, DEFAULT_PORT, age_seconds, connection,
                  connect_mqtt, decide, load_config, new_client_id, publish,
                  push_to_db, read_latest, schedule_for_now)

log = logging.getLogger('controller')

BROKER = DEFAULT_BROKER
PORT = DEFAULT_PORT
BOILER_TOPIC = 'ebusd/BAI/SetModeOverride/set'
# SetModeOverride is not held indefinitely by the boiler; re-assert every loop
# (the old controller also published it every loop).
BOILER_REPUBLISH_EVERY = 1
DRY_RUN = os.environ.get('DRY_RUN', '').lower() in ('1', 'true', 'yes', 'on')

_mqtt_client = None


def get_mqtt_client():
    global _mqtt_client
    if _mqtt_client is None:
        try:
            client = connect_mqtt(new_client_id('controller'), BROKER, PORT)
            client.loop_start()
            _mqtt_client = client
        except Exception:
            log.exception('could not connect to MQTT broker %s:%s', BROKER, PORT)
            return None
    return _mqtt_client


def _room_config(raw):
    value = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(value, dict):
        raise ValueError(f'invalid room config: {raw!r}')
    return value


def fetch_temps(config):
    latest = {}
    for room, raw in config['rooms'].items():
        try:
            room_config = _room_config(raw)
        except (TypeError, ValueError):
            log.exception('invalid config for room %s', room)
            latest[room] = {'value': None, 'age_s': None}
            continue
        measurement = room_config.get('measurement')
        value_name = room_config.get('value_name', 'value')
        try:
            point = read_latest(DB_NAME, measurement, connection)
        except Exception:
            log.exception('could not read latest temperature for %s (%s)',
                          room, measurement)
            point = None
        if not point:
            latest[room] = {'value': None, 'age_s': None}
            continue
        latest[room] = {
            'value': point.get(value_name),
            'age_s': age_seconds(point.get('time')),
        }
    return latest


def _zigbee_address(rooms_config, room):
    try:
        return _room_config(rooms_config.get(room, {})).get('zigbee')
    except (TypeError, ValueError):
        return None


def publish_valves(config, decision, last_valves, config_changed):
    for room, entry in decision['rooms'].items():
        action = entry['action']
        if action not in ('open', 'close'):
            continue
        if not config_changed and last_valves.get(room) == action:
            continue

        address = _zigbee_address(config['rooms'], room)
        if not address:
            log.error('no zigbee address configured for room %s', room)
            continue

        message = json.dumps({'current_heating_setpoint': str(entry['target'])})
        topic = f'zigbee2mqtt/{address}/set'
        if DRY_RUN:
            log.info('[DRY_RUN] %s -> %s', topic, message)
            last_valves[room] = action
            continue

        client = get_mqtt_client()
        if client is None:
            continue
        if publish(client, topic, message):
            log.info('valve %s: %s (setpoint %s -> %s)', room, action,
                     entry['setpoint'], entry['target'])
            last_valves[room] = action


def publish_boiler(decision, loop_number, last_override):
    override = decision['boiler']['override']
    due = (loop_number == 1 or override != last_override
           or loop_number % BOILER_REPUBLISH_EVERY == 0)
    if not due:
        return last_override, False

    if DRY_RUN:
        log.info('[DRY_RUN] %s -> %s', BOILER_TOPIC, override)
        return override, True

    client = get_mqtt_client()
    if client is None:
        return last_override, False
    if publish(client, BOILER_TOPIC, override):
        log.info('boiler override: %s (settemp %s, piec_off %s)', override,
                 decision['boiler']['settemp'], decision['boiler']['piec_off'])
        return override, True
    return last_override, False


def decision_fields(decision, loop_number):
    fields = {
        'period': decision.get('period') or '',
        'settemp': float(decision['boiler']['settemp']),
        'piec_off': int(decision['boiler']['piec_off']),
        'water_active': bool(decision['water']['active']),
        'water_override': bool(decision['water'].get('override', False)),
        'water_override_until': float(decision['water'].get('override_until', 0.0)),
        'woda_temp': float(decision['water']['temp']),
        'woda': float(decision['water'].get('woda', 0.0)),
        'woda_off': float(decision['water'].get('woda_off', 0.0)),
        'fallback_active': bool(decision['fallback_active']),
        'reason': decision.get('reason', ''),
        'valid_rooms': ','.join(decision.get('valid_rooms', [])),
        'stale_rooms': ','.join(decision.get('stale_rooms', [])),
        'loop': int(loop_number),
        'dry_run': bool(DRY_RUN),
    }
    for room, entry in decision['rooms'].items():
        fields[f'{room}_setpoint'] = float(entry['setpoint'])
        fields[f'{room}_stale'] = bool(entry['stale'])
        fields[f'{room}_action'] = entry['action']
        if entry.get('temp') is not None:
            fields[f'{room}_temp'] = float(entry['temp'])
        if entry.get('age_s') is not None:
            fields[f'{room}_age_s'] = float(entry['age_s'])
        if entry.get('diff') is not None:
            fields[f'{room}_diff'] = float(entry['diff'])
        if entry.get('valve') is not None:
            fields[f'{room}_valve'] = entry['valve']
        if entry.get('target') is not None:
            fields[f'{room}_target'] = float(entry['target'])
    return fields


def write_decision(decision, loop_number):
    point = [{
        'measurement': 'decisions',
        'fields': decision_fields(decision, loop_number),
    }]
    try:
        push_to_db(DB_NAME, point, connection)
    except Exception:
        log.exception('could not write decision to InfluxDB')


def main():
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    last_valves = {}
    last_override = None
    last_config_signature = None
    previous_interval = 120.0
    loop_number = 0

    log.info('controller starting%s', ' (DRY RUN)' if DRY_RUN else '')

    while True:
        try:
            config = load_config(connection)
        except Exception:
            log.exception('could not load config from InfluxDB; keeping previous decision')
            time.sleep(previous_interval)
            continue

        try:
            interval = max(10.0, float(
                config['controller'].get('loop_interval_s', previous_interval)))
        except (TypeError, ValueError):
            interval = previous_interval
        previous_interval = interval

        signature = json.dumps(config, sort_keys=True)
        config_changed = signature != last_config_signature
        if config_changed:
            last_valves.clear()
            last_config_signature = signature

        try:
            latest_temps = fetch_temps(config)
            schedule = schedule_for_now(config['schedule'])
            decision = decide(schedule, config['rooms'], latest_temps,
                              config['controller'], config['water'])
        except Exception:
            log.exception('could not compute decision; keeping previous decision')
            time.sleep(interval)
            continue

        loop_number += 1
        log.info('period=%s settemp=%s piec_off=%s water=%s fallback=%s reason=%s',
                 decision.get('period'), decision['boiler']['settemp'],
                 decision['boiler']['piec_off'],
                 'on' if decision['water']['active'] else 'off',
                 decision['fallback_active'], decision['reason'])
        for room, entry in decision['rooms'].items():
            log.info('  %s: temp=%s age=%s setpoint=%s diff=%s stale=%s action=%s',
                     room, entry['temp'], entry['age_s'], entry['setpoint'],
                     entry['diff'], entry['stale'], entry['action'])

        publish_valves(config, decision, last_valves, config_changed)
        last_override, _ = publish_boiler(decision, loop_number, last_override)
        write_decision(decision, loop_number)

        time.sleep(interval)


if __name__ == '__main__':
    main()

"""MQTT -> InfluxDB watcher with a self-healing boiler poll watchdog."""

import json
import logging
import os
import threading
import time

from libs import (DEFAULT_BROKER, DEFAULT_PORT, connection, connect_mqtt,
                  measurments_preparation_sent, new_client_id, publish,
                  push_to_db)

log = logging.getLogger('watcher')

BROKER = DEFAULT_BROKER
PORT = DEFAULT_PORT
DB_NAME = 'heat'

SILENCE_TIMEOUT = 5 * 60
WATCHDOG_INTERVAL = 10
MIN_RETRY_DELAY = 60
MAX_RETRY_DELAY = 300
LAST_SEEN_FILE = os.environ.get('LAST_SEEN_FILE', '/tmp/last_seen')

SUBSCRIPTIONS = ['zigbee2mqtt/+', 'ebusd/bai/+', 'esp/+', 'tele/+/SENSOR']

topics = {
    "FlowTempDesired": 'float',      # 40.00
    "HwcTempDesired": 'float',       # 42.00
    "FlowTemp": 'floatColon',        # 44.62;ok
    "HwcTemp": 'floatColon',         # -13.50;cutoff
    "HwcSwitch": 'onoff',            # on
    "HeatingSwitch": 'onoff',        # on
    "PrEnergyCountHc1": 'int',       # 7685762
    "PrEnergyCountHwc1": 'int',      # 791793
    "StorageTempDesired": 'float',   # 42.00
    "StorageTemp": 'floatColon',     # 42.44;ok
    "WaterPressure": 'floatColon',   # 0.956;ok
    "ReturnTemp": 'floatColon',      # 43.81;64834;ok
}

_state_lock = threading.Lock()
last_seen = {topic: time.monotonic() for topic in topics}
retry_state = {topic: {'next': 0.0, 'delay': float(MIN_RETRY_DELAY)}
               for topic in topics}
_last_file_write = 0.0


def _touch_last_seen():
    global _last_file_write
    now = time.time()
    if now - _last_file_write < 5:
        return
    _last_file_write = now
    try:
        with open(LAST_SEEN_FILE, 'w', encoding='ascii') as handle:
            handle.write(str(int(now)))
    except OSError as exc:
        log.warning('could not write %s: %s', LAST_SEEN_FILE, exc)


def _topic_seen(topic):
    with _state_lock:
        last_seen[topic] = time.monotonic()
        retry_state[topic]['next'] = 0.0
        retry_state[topic]['delay'] = float(MIN_RETRY_DELAY)


def _handle_ebusd(msg):
    if '/get' in msg.topic:
        return
    segment = msg.topic.rsplit('/', 1)[-1]
    if segment not in topics:
        return
    _topic_seen(segment)
    measurments_preparation_sent(msg.topic, topics[segment], msg.payload, connection)


def _handle_zigbee(msg):
    payload = json.loads(msg.payload.decode())
    fields = {}
    for key in ('current_heating_setpoint', 'local_temperature'):
        if key in payload:
            fields[key] = float(payload[key])
    if fields:
        push_to_db(DB_NAME, [{'measurement': msg.topic, 'fields': fields}], connection)


def _handle_esp(msg):
    value = float(msg.payload.decode())
    push_to_db(DB_NAME, [{'measurement': msg.topic, 'fields': {'value': value}}],
               connection)


def _handle_sensor(msg):
    payload = json.loads(msg.payload.decode())
    fields = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                try:
                    fields[f'{key}_{sub_key}'] = float(sub_value)
                except (TypeError, ValueError):
                    continue
    if fields:
        push_to_db(DB_NAME, [{'measurement': msg.topic, 'fields': fields}], connection)


def on_message(client, userdata, msg):
    try:
        if msg.topic.startswith('ebusd/'):
            _handle_ebusd(msg)
        elif msg.topic.startswith('zigbee2mqtt/'):
            _handle_zigbee(msg)
        elif msg.topic.startswith('esp/'):
            _handle_esp(msg)
        elif msg.topic.startswith('tele/') and msg.topic.endswith('/SENSOR'):
            _handle_sensor(msg)
    except Exception:
        log.exception('failed to process message on %s', msg.topic)
    finally:
        _touch_last_seen()


def on_connect(client, userdata, flags, rc):
    if rc != 0:
        log.error('not subscribing, connect failed with rc=%s', rc)
        return
    result = client.subscribe([(topic, 0) for topic in SUBSCRIPTIONS])
    log.info('subscribed to %s (rc=%s)', SUBSCRIPTIONS, result[0])
    now = time.monotonic()
    with _state_lock:
        for topic in topics:
            last_seen[topic] = now
            retry_state[topic]['next'] = 0.0
            retry_state[topic]['delay'] = float(MIN_RETRY_DELAY)
    for topic in topics:
        publish(client, f'ebusd/bai/{topic}/get', '?3')
    log.info('requested initial values for %d ebusd topics', len(topics))


def watchdog(client):
    disconnected_since = None
    last_disconnect_log = 0.0
    while True:
        try:
            now = time.monotonic()
            if not client.is_connected():
                if disconnected_since is None:
                    disconnected_since = now
                elif (now - disconnected_since > 60
                      and now - last_disconnect_log > 60):
                    log.error('MQTT disconnected for %.0fs; broker is unreachable',
                              now - disconnected_since)
                    last_disconnect_log = now
            else:
                disconnected_since = None

            with _state_lock:
                silent = {topic: now - seen for topic, seen in last_seen.items()}
                due = []
                for topic, age in silent.items():
                    state = retry_state[topic]
                    if age > SILENCE_TIMEOUT and now >= state['next']:
                        due.append((topic, age))
                        state['next'] = now + state['delay']
                        state['delay'] = min(state['delay'] * 2, MAX_RETRY_DELAY)
            for topic, age in due:
                log.warning('%s silent for %.0fs, requesting ?3 again', topic, age)
                publish(client, f'ebusd/bai/{topic}/get', '?3')
        except Exception:
            log.exception('watchdog iteration failed')
        time.sleep(WATCHDOG_INTERVAL)


def main():
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    client = None
    while client is None:
        try:
            client = connect_mqtt(new_client_id('watcher'), BROKER, PORT,
                                  on_connect=on_connect, on_message=on_message)
        except Exception:
            log.exception('could not connect to MQTT broker %s:%s; retrying in 5s',
                          BROKER, PORT)
            time.sleep(5)

    _touch_last_seen()
    threading.Thread(target=watchdog, args=(client,), name='watchdog',
                     daemon=True).start()

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log.info('stopping watcher')
    except Exception:
        log.exception('MQTT loop crashed; exiting so Docker can restart the container')
        raise


if __name__ == '__main__':
    main()

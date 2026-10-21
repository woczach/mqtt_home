"""MQTT helpers: one persistent client with reconnect support."""

import logging
import random

from paho.mqtt import client as mqtt_client

log = logging.getLogger(__name__)

DEFAULT_BROKER = '192.168.0.230'
DEFAULT_PORT = 11883

# Kept for backwards compatibility with the old libs module.
broker = DEFAULT_BROKER
port = DEFAULT_PORT


def new_client_id(prefix='home'):
    return f'{prefix}-{random.randint(0, 10**9)}'


def connect_mqtt(client_id=None, broker=DEFAULT_BROKER, port=DEFAULT_PORT,
                 on_connect=None, on_message=None):
    """Create, configure and connect a paho 1.x client.

    Reconnect delays are enabled so the paho network loop recovers by itself.
    """
    client_id = client_id or new_client_id()

    def _on_connect(client, userdata, flags, rc):
        if rc == 0:
            log.info('Connected to MQTT broker %s:%s as %s', broker, port, client_id)
        else:
            log.error('Failed to connect to MQTT broker %s:%s, rc=%s', broker, port, rc)
        if on_connect is not None:
            on_connect(client, userdata, flags, rc)

    def _on_disconnect(client, userdata, rc):
        if rc == 0:
            log.info('Disconnected from MQTT broker')
        else:
            log.warning('Unexpected MQTT disconnect (rc=%s); paho will reconnect', rc)

    client = mqtt_client.Client(client_id)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    if on_message is not None:
        client.on_message = on_message
    client.connect(broker, port)
    return client


def publish(client, topic, message):
    result = client.publish(topic, message)
    if result[0] == 0:
        log.debug('Sent `%s` to `%s`', message, topic)
        return True
    log.error('Failed to send message to topic %s (rc=%s)', topic, result[0])
    return False


__all__ = [
    'DEFAULT_BROKER', 'DEFAULT_PORT', 'broker', 'port', 'new_client_id',
    'connect_mqtt', 'publish',
]

# python3.6

import random
import json
from paho.mqtt import client as mqtt_client
#from influxdb_client.client.write_api import SYNCHRONOUS
import os
from influxdb import InfluxDBClient
#from influxdb_client import InfluxDBClient
import logging
token = os.environ.get("INFLUXDB_TOKEN")



DBUSER = os.environ.get('DBUSER')
DBPASS = os.environ.get('DBPASS')
DBIP = os.environ.get('DBIP')
#USER =  os.environ.get('USER')
#PASSWORD = os.environ.get('PASSWORD')
#token = os.environ.get("INFLUXDB_TOKEN")
INFLUX = {'local': (DBIP, '8086', False, False)}


def push_to_db(db, json_body):
    for address, port, ssl, verify in [INFLUX['local']]:
        url = f'http://{address}:{port}'
        org = "home"
        client = InfluxDBClient(host=address, port=port, database=db, username=DBUSER, password=DBPASS,
                                ssl=ssl, verify_ssl=verify)
        response = client.write_points(json_body)
        #write_api = client.write_api(write_options=SYNCHRONOUS)
        #response = write_api.write("heat", "home", json_body)
        if not response:
            logging.warning("Failed to write data.")
        client.close()


def push_to_db_array(db, bodies):
    for address, port, ssl, verify in [INFLUX['local']]:
        client = InfluxDBClient(host=address, port=port, database=db, username='username', password='password',
                                ssl=ssl, verify_ssl=verify)
        for json_body in bodies:
            response = client.write_points(json_body)
            if not response:
                logging.warning("Failed to write data.")
        client.close()

broker = '192.168.0.30'
port = 1883
topic = "zigbee2mqtt/+"
# Generate a Client ID with the subscribe prefix.
client_id = f'subscribe-{random.randint(0, 100)}'
# username = 'emqx'
# password = 'public'


def connect_mqtt() -> mqtt_client:
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)

    client = mqtt_client.Client(client_id)
    # client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client


def subscribe(client: mqtt_client):
    def on_message(client, userdata, msg):
        #print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        print(msg.topic)
        payload = json.loads(msg.payload.decode())
        print(payload)
        payload["measurement"] = str(msg.topic)
        print(payload)
        
        try:
            to_sent = {}
            to_sent["measurement"] = str(msg.topic)
            fields = {'current_heating_setpoint': float(payload['current_heating_setpoint']), 'local_temperature': float(payload['local_temperature'])}
            to_sent['fields'] = fields
            #to_sent["time"] = 3
            ts = []
            ts.append(to_sent)
        except:
            print("something wrong with this payload")
        print(to_sent)
        push_to_db('heat', ts)
    client.subscribe(topic)
    client.on_message = on_message


def run():
    client = connect_mqtt()
    subscribe(client)
    client.loop_forever()


if __name__ == '__main__':
    run()
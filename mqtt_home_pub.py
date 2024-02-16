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
import time


DBUSER = os.environ.get('DBUSER')
DBPASS = os.environ.get('DBPASS')
DBIP = os.environ.get('DBIP')
#USER =  os.environ.get('USER')
#PASSWORD = os.environ.get('PASSWORD')
#token = os.environ.get("INFLUXDB_TOKEN")
INFLUX = {'local': (DBIP, '8086', False, False)}



broker = '192.168.0.30'
port = 1883
topic = "ebusd/bai/FlowTemp/get"


client_id = f'publish-{random.randint(0, 100)}'



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


def publish(client):
     msg_count = 1
     while True:
         time.sleep(1)
         msg = f"messages: {msg_count}"
         result = client.publish(topic)
         # result: [0, 1]
         status = result[0]
         if status == 0:
             print(f"Send `{msg}` to topic `{topic}`")
         else:
             print(f"Failed to send message to topic {topic}")
         msg_count += 1
         if msg_count > 1:
             break


def run():
    client = connect_mqtt()
    client.loop_start()
    publish(client)
    client.loop_stop()



if __name__ == '__main__':
    run()
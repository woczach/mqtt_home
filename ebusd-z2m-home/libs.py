from paho.mqtt import client as mqtt_client
from influxdb import InfluxDBClient

def connect_mqtt(client_id, broker, port) -> mqtt_client:
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





def publish(client, topic, message):

    result = client.publish(topic, message)
    # result: [0, 1]
    status = result[0]
    if status == 0:
        print(f"Send `{message}` to topic `{topic}`")
    else:
        print(f"Failed to send message to topic {topic}")


def push_to_db(db, json_body, connection):
    #connection = {'URL': 1.1.1.1, 'PORT': 8086, "DBUUSER": "username", DBPASS: 'password}

    client = InfluxDBClient(host=connection['URL'], port=connection['port'], 
                            database=db, username=connection['DBUSER'], password=connection['DBPASS'],
                            ssl=False, verify_ssl=False)
    response = client.write_points(json_body)
    #write_api = client.write_api(write_options=SYNCHRONOUS)
    #response = write_api.write("heat", "home", json_body)
    if not response:
        print("Failed to write data.")
    client.close()
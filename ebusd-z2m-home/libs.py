from paho.mqtt import client as mqtt_client


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
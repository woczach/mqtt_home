import random
from paho.mqtt import client as mqtt_client
import os
import time
import pika
import json 
import threading

broker = '192.168.0.30'
port = 11883
topic = "ebusd/bai/FlowTemp/get"
client_id = f'publish-{random.randint(0, 100)}'



TEMPJOZEF = 22
TEMPPOKOJ = 21
WODA = 40
WODAOFF= 0
NOC = "Y"
message_to_piec = '0;40;40;-;-;0;0;0;-;0;0;0'



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


def publish(client, topic, message):

    result = client.publish(topic, message)
    # result: [0, 1]
    status = result[0]
    if status == 0:
        print(f"Send `{message}` to topic `{topic}`")
    else:
        print(f"Failed to send message to topic {topic}")




def run(topic, message):
    client = connect_mqtt()
    client.loop_start()
    publish(client, topic, message)
    client.loop_stop()



def init():
    topics = ["ebusd/bai/FlowTempDesired/get",
                "ebusd/bai/HwcTempDesired/get",
                "ebusd/bai/FlowTemp/get",
                "ebusd/bai/HwcTemp/get",
                "ebusd/bai/HwcSwitch/get",
                "ebusd/bai/HeatingSwitch/get",
                "ebusd/bai/PrEnergyCountHc1/get",
                "ebusd/bai/PrEnergyCountHwc1/get",
                "ebusd/bai/StorageTempDesired/get ",
                "ebusd/bai/StorageTemp/get",
                "ebusd/bai/WaterPressure/get",
                "ebusd/bai/ReturnTemp/get"
        ]
    for topic in topics:
        run(topic, "'?3'")







def get_values():
    global TEMPJOZEF
    global TEMPPOKOJ
    global WODAOFF
    global NOC   
    global WODA
    if os.environ.get('TEMPJOZEF'):
        TEMPJOZEF = os.environ.get('TEMPJOZEF')
        print(TEMPJOZEF)
    if os.environ.get('TEMPPOKOJ'):
        TEMPPOKOJ = os.environ.get('TEMPPOKOJ')
        print(TEMPPOKOJ)
    if os.environ.get('WODAOFF'):
        WODAOFF = os.environ.get('WODAOFF')
        print(WODAOFF)
    if os.environ.get('NOC'):
        NOC = os.environ.get('NOC')
        print(NOC)
    if os.environ.get('WODA'):
        WODA = os.environ.get('WODA')
        print(WODA)


def regulate(temp, key):
    #TEMPJOZEF = os.environ.get('TEMPJOZEF')
    #TEMPPOKOJ = os.environ.get('TEMPPOKOJ')
    global TEMPJOZEF
    global TEMPPOKOJ
    global WODAOFF
    global WODA
    global NOC
    global message_to_piec

    
    TEMPJOZEF = 22
    TEMPPOKOJ = 21
    WODA = 40
    WODAOFF=0
    NOC = os.environ.get('NOC')
    settemp = 40
    #podiff = {2: 60, 1: 50, 0.2: 40}
    #jodiff = {2: 50, 1: 45, 0.5: 40}
    podiff = {0.25: 45, 0.5:50, 2:60}
    jodiff = {0.5: 40, 1: 45, 2: 50}

    print(f'tempjozef={TEMPJOZEF}  temppokoj={TEMPPOKOJ} noc={NOC}')
    print(f"{temp}   {key}")    

    if NOC == "Y" and key == "jo":
        worktemp = TEMPJOZEF
        items = jodiff
    elif NOC == "N" and key == "po":
        worktemp =  TEMPPOKOJ
        items = podiff 
    else:
        print("keyerror")
        return

    if temp >= worktemp:
        PIECOFF = 1      
    else:
        PIECOFF = 0
        for k,v in items.items():
            if (worktemp - temp) > k:
                settemp = v

    message_to_piec = f'0;{settemp};{WODA};-;-;{PIECOFF};0;{WODAOFF};-;0;0;0'   
    

def send_topiec():
    global message_to_piec 
    topic_piec = 'ebusd/BAI/SetModeOverride/set'
    run(topic_piec, message_to_piec)        


def sub():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='192.168.0.30'))
    channel = connection.channel()

#    channel.queue_declare(queue='all')

    def callback(ch, method, properties, body):

            
        if method.routing_key == "tele.tasmota_B80F1C.SENSOR":
            regulate(json.loads(body.decode('utf-8'))['DS18B20']['Temperature'] , "jo")
        if method.routing_key == "rpi.temp":
            regulate(json.loads(body.decode('utf-8')), "po")

        
        #print(f"-> Received {body}")
        #print(f"-> prop {properties}")
        #print(f"-> ch {ch}")
        #print(f"->  met {method.routing_key}")
        #print()

    channel.basic_consume(queue='all', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()


sub()

import random
from libs import connect_mqtt, publish, measurments_preparation_sent
import pika
from time import sleep
import threading


broker = '192.168.0.230'
port = 11883
topic = "FlowTemp"
client_id = f'publish-{random.randint(0, 100)}'
timeout = 5 * 60

topics = {
    "FlowTempDesired": 'float',      # 40.00
    "HwcTempDesired": 'float',       # 42.00
    "FlowTemp": 'floatColon',        #  44.62;ok  
    "HwcTemp": 'floatColon',         # -13.50;cutoff
    "HwcSwitch": 'onoff',             #on
    "HeatingSwitch": 'onoff',         # on
    "PrEnergyCountHc1": 'int',       #7685762 
    "PrEnergyCountHwc1": 'int',      # 791793
    "StorageTempDesired ": 'float',  #42.00
    "StorageTemp": 'floatColon',     # 42.44;ok
    "WaterPressure": 'floatColon',   # 0.956;ok
    "ReturnTemp": 'floatColon'      #  43.81;64834;ok   
}
# body {"Time":"2024-10-10T10:03:32","DS18B20":{"Id":"0313949744B2","Temperature":20.6},"TempUnit":"C"}
# body 21.75
# topics = [ "FlowTempDesired",  # 40.00
#             "HwcTempDesired", #  42.00
#             "FlowTemp", #  44.62;ok  
#             "HwcTemp", # -13.50;cutoff
#             "HwcSwitch", #on
#             "HeatingSwitch", # on
#             "PrEnergyCountHc1", # 7685762 
#             "PrEnergyCountHwc1",  # 791793
#             "StorageTempDesired ",  #42.00
#             "StorageTemp",  # 42.44;ok
#             "WaterPressure", # 0.956;ok
#             "ReturnTemp"  #  43.81;64834;ok
#     ]

timers = {}


def check_boiler_messages():
    def init(topics_to_init):

        client = connect_mqtt(client_id, broker, port)
        client.loop_start()    
        for topic in topics_to_init:
            full_topic = f'ebusd/bai/{topic}/get'
            publish(client, full_topic, "?3")
        client.loop_stop()       
        
    global timers
    for topic in topics:
        timers[topic] = 0
    while True:
        to_reset = []
        for topic in topics:
            timers[topic] += 1
            if timers[topic] > timeout:
                print(f'ERROR {topic} have no messages retrying' )
                to_reset.append(topic)
        if to_reset:
            init(to_reset)        
        sleep(1)       




def subscribe_boiler_messages():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='192.168.0.230'))
    channel_bai = connection.channel()

#    channel.queue_declare(queue='all')

    def callback(ch, method, properties, body):
        print(f"callback method {method}")
        print(f"body {body.decode('utf-8')}")
        global timers 
        for topic, type in topics.items():
            if topic in method.routing_key:
                print(f'INFO {topic} found within {timers[topic]} clearing' )
                timers[topic] = 0
                if 'get' not in method.routing_key:
                    measurments_preparation_sent(topic, type, body)

    channel_bai.basic_consume(queue='ebus', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel_bai.start_consuming()





if __name__ == "__main__":

    t1 = threading.Thread(target=subscribe_boiler_messages)
    t2 = threading.Thread(target=check_boiler_messages)
    t1.start()
    t2.start()


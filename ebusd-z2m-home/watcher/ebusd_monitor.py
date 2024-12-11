
import random
from libs import connect_mqtt, check_boiler_messages, subscribe_mqtt_for_sending_to_influx
from paho.mqtt import client as mqtt_client
import json
import threading





topics = {
    "FlowTempDesired": 'float',      # 40.00
    "HwcTempDesired": 'float',       # 42.00
    "FlowTemp": 'floatColon',        #  44.62;ok  
    "HwcTemp": 'floatColon',         # -13.50;cutoff
    "HwcSwitch": 'onoff',             #on
    "HeatingSwitch": 'onoff',         # on
    "PrEnergyCountHc1": 'int',       #7685762 
    "PrEnergyCountHwc1": 'int',      # 791793
    "StorageTempDesired": 'float',  #42.00
    "StorageTemp": 'floatColon',     # 42.44;ok
    "WaterPressure": 'floatColon',   # 0.956;ok
    "ReturnTemp": 'floatColon'      #  43.81;64834;ok   
}













def mqtt_to_influxdb():
    broker = '192.168.0.230'
    port = 11883
    client_id = f'publish-{random.randint(0, 100)}'
    client = connect_mqtt(client_id, broker, port)
    subscribe_mqtt_for_sending_to_influx(client, topics)
    client.loop_forever()    









if __name__ == "__main__":

    t1 = threading.Thread(target=check_boiler_messages, args=(topics,))
    t2 = threading.Thread(target=mqtt_to_influxdb)
    t1.start()
    t2.start()


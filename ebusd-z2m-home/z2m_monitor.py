
import random
from libs import connect_mqtt, publish, measurments_preparation_sent, return_current_settings, return_current_temps, push_to_db
import pika
from time import sleep
import threading
import json

broker = '192.168.0.230'
port = 11883
topic = "FlowTemp"
client_id = f'publish-{random.randint(0, 100)}'
timeout = 5 * 60


OFF_VALVE_TEMP = 16.0
ON_VALVE_TEMP = 24.0
WODA = 42
WODAOFF= 0

topics_z2m = {
    'Salon': "0xa4c1384e6bcc60c6", 
    'Kuchnia': "0xa4c138d0aa4d2b86",
    'Jozef': "0xa4c138ad1d132790",
    'Jadalnia': "0xa4c13818b181eda9",
    'Sypialnia': "0x94deb8fffe2e751a"
}

podiff = {-0.25: 45, -0.5:50, -2:60}
jodiff = {-0.5: 40, -1: 45, -2: 50}


        # 'Jozef': {'measurment': 'Tasmota_switch', 'value_name': 'temperatura'},
        # 'Kuchnia': {'measurment':  'esp/sypialnia', 'value_name': 'value'},
        # 'Salon': {'measurment':  'rpi_temperatura', 'value_name': 'celsius'},
        # 'Sypialnia': {'measurment':  'esp/kuchnia', 'value_name': 'value'}


def calculate_settings(temp_diff):
    PIEC_OFF = 1
    settemp = 40

    print(temp_diff)
    close_valve = [k for k, v in temp_diff.items() if v >= 0]
    open_valve = [k  for k, v in topics_z2m.items() if k not in close_valve]
    smallest_key = min(temp_diff, key=temp_diff.get)
    smallest_value = temp_diff[smallest_key]

    if smallest_value < 0:
        PIEC_OFF = 0
        if smallest_key == 'Jozef':
            for k,v in jodiff.items():
                if (smallest_value) < k:
                    settemp = v
        else:            
            for k,v in podiff.items():
                if (smallest_value) < k:
                    settemp = v
    else:
        PIEC_OFF = 1
    
    print(f'close valve = {close_valve}, open valve = {open_valve}, smallest diff {smallest_key}, smallest value {smallest_value}')
    print(f'piec off = {PIEC_OFF}, settemp = {settemp}')
    fields = {}
    client = connect_mqtt(client_id, broker, port)
    client.loop_start()        
    for close in close_valve:
        fields[close] = OFF_VALVE_TEMP
        full_topic = f'zigbee2mqtt/{topics_z2m[close]}/set'
        message = json.dumps({"current_heating_setpoint": str(OFF_VALVE_TEMP)})
        publish(client, full_topic, message)
    for open in open_valve:
        fields[open]= ON_VALVE_TEMP        
        full_topic = f'zigbee2mqtt/{topics_z2m[open]}/set'
        message = json.dumps({"current_heating_setpoint":  str(ON_VALVE_TEMP)})
        publish(client, full_topic, str(message))
    if PIEC_OFF == 0:
        fields['Heating_temp'] = settemp
        message_to_piec = f'0;{settemp};{WODA};-;-;{PIEC_OFF};0;{WODAOFF};-;0;0;0'   
        topic_piec = 'ebusd/BAI/SetModeOverride/set'
        publish(client, topic_piec, message_to_piec)
    else:
        fields['Heating_temp'] = 0
        message_to_piec = f'0;{settemp};{WODA};-;-;{PIEC_OFF};0;{WODAOFF};-;0;0;0'   
        topic_piec = 'ebusd/BAI/SetModeOverride/set'
        publish(client, topic_piec, message_to_piec)
    client.loop_stop()     

    connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}   
    data_point = [
        {
        "measurement": "settings",
        "fields": fields
        }
    ]
    print(data_point)
    push_to_db('heat', data_point, connection) 

      


    # for pokoj, valve in topics_z2m.items():
    #     if pokoj not in temp_diff:
    #         open_valve.append(valve)
    #     else:    
    #         if temp_diff[pokoj] >= 0:
    #             close_valve.append(valve)
    #             #close_valve
    #         else:
    #             open_valve.append(valve)
    #             if temp_diff[pokoj] < smallest_diff:
    #                 smallest_diff = temp_diff[pokoj]
    #             PIEC_OFF = 0
    # if time_of_day == 'Night':
    #     temp_curve = jodiff
    # else:
    #     temp_curve = podiff

        

def regulate_temp():
    while True:

        settings, time_of_day = return_current_settings()

            
        print(settings)
        current_temps = return_current_temps()
        print(current_temps)
        temp_diff = {}
        for pokoj, set_temp in settings.items():
            print(current_temps[pokoj][0])
            if settings[pokoj] != 0:
                temp_diff[pokoj] = current_temps[pokoj][0]['value'] - set_temp
                print(f"pokoj {pokoj} set temp {set_temp} current temp  {current_temps[pokoj][0]['value']} temp {temp_diff[pokoj]}")

        calculate_settings(temp_diff)

        sleep(120)


regulate_temp()
# if __name__ == "__main__":

#     t1 = threading.Thread(target=subscribe_boiler_messages)
#     t2 = threading.Thread(target=check_boiler_messages)
#     t1.start()
#     t2.start()


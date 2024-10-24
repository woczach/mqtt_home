
import random
from libs import connect_mqtt, publish, measurments_preparation_sent, return_current_settings, return_current_temps
import pika
from time import sleep
import threading


broker = '192.168.0.230'
port = 11883
topic = "FlowTemp"
client_id = f'publish-{random.randint(0, 100)}'
timeout = 5 * 60




topics_z2m = {
    'Salon': "0xa4c1384e6bcc60c6", 
    'Kuchnia': "0xa4c138d0aa4d2b86",
    'Jozef': "0xa4c138ad1d132790",
    'Jadalnia': "0xa4c13818b181eda9",
    'Sypialnia': "0x94deb8fffe2e751a"
}

podiff = {0.25: 45, 0.5:50, 2:60}
jodiff = {0.5: 40, 1: 45, 2: 50}


        # 'Jozef': {'measurment': 'Tasmota_switch', 'value_name': 'temperatura'},
        # 'Kuchnia': {'measurment':  'esp/sypialnia', 'value_name': 'value'},
        # 'Salon': {'measurment':  'rpi_temperatura', 'value_name': 'celsius'},
        # 'Sypialnia': {'measurment':  'esp/kuchnia', 'value_name': 'value'}
  

def regulate_temp():
    while True:

        settings, time_of_day = return_current_settings()
        if time_of_day == 'Night':
            temp_curve = jodiff
        else:
            temp_curve = podiff
            
        print(settings)
        current_temps = return_current_temps()
        print(current_temps)
        temp_diff = {}
        for pokoj, set_temp in settings.items():
            print(current_temps[pokoj][0])
            if settings[pokoj] != 0:
                temp_diff[pokoj] = current_temps[pokoj][0]['value'] - set_temp
                print(f"pokoj {pokoj} set temp {set_temp} current temp  {current_temps[pokoj][0]['value']} temp {temp_diff[pokoj]}")
        PIEC_OFF = 1
        smallest_diff = 0
        close_valve = []
        open_valve = []
        for pokoj, diff in temp_diff.items():
            
            if diff >= 0:
                close_valve.append(topics_z2m[pokoj])
                #close_valve
            else:
                open_valve.append(topics_z2m[pokoj])
                if diff < smallest_diff:
                    smallest_diff = diff
                PIEC_OFF = 0
        

        sleep(120)


regulate_temp()
# if __name__ == "__main__":

#     t1 = threading.Thread(target=subscribe_boiler_messages)
#     t2 = threading.Thread(target=check_boiler_messages)
#     t1.start()
#     t2.start()


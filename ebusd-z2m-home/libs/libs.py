from paho.mqtt import client as mqtt_client
from influxdb import InfluxDBClient
from datetime import datetime, timezone, timedelta
import random
from time import sleep
import json

timeout = 5 * 60
connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}      

broker = '192.168.0.230'
port = 11883
topic = "FlowTemp"
client_id = f'publish-{random.randint(0, 100)}'
timers = {}


def subscribe_mqtt_for_sending_to_influx(client: mqtt_client, topics):
    def on_message(client, userdata, msg):
        connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}     
        print(msg.topic)

        global timers
        if 'ebusd' in msg.topic:
            try:
                for topic, type in topics.items():
                    if topic in msg.topic:
                        print(f'INFO {topic} found within {timers[topic]} clearing' )
                        timers[topic] = 0
                        if 'get' not in msg.topic:
                            measurments_preparation_sent(msg.topic, type, msg.payload)
            except Exception as e:
                print(f'ERROR in ebusd {e}')
        if 'zigbee2mqtt' in msg.topic:
            try:
                payload = json.loads(msg.payload.decode())
                fields = {'current_heating_setpoint': float(payload['current_heating_setpoint']), 'local_temperature': float(payload['local_temperature'])}
                data = [{"measurement": str(msg.topic), "fields": fields}]
                push_to_db('heat', data, connection)                  
            except Exception as e:
                print(f'ERROR in zigbee {e}')
            
        if 'esp' in msg.topic:
            try:
                payload = msg.payload.decode()
                data = [{"measurement": str(msg.topic), "fields": {'value': float(payload)}}]
                push_to_db('heat', data, connection)  
            except Exception as e:
                print(f'ERROR in esp {e}')  
        if 'SENSOR' in msg.topic:
            try:
                payload = json.loads(msg.payload.decode())
                j_data = {}
                for k,v in payload.items():
                    if(isinstance(v, dict)):
                        for k1, v1 in v.items():
                            j_data[f'{k}_{k1}'] = float(v1)
                data = [{"measurement": str(msg.topic), "fields": j_data}]
                push_to_db('heat', data, connection)  
            except Exception as e:
                print(f'ERROR in tasmota {e}')                              
    topic = ["zigbee2mqtt/+", "ebusd/bai/+", "esp/+", "tele/+/SENSOR"]
    for t in topic:
        client.subscribe(t)
    client.on_message = on_message



def check_boiler_messages(topics):

    global timers
    def init(topics_to_init):

        client = connect_mqtt(client_id, broker, port)
        client.loop_start()    
        for topic in topics_to_init:
            full_topic = f'ebusd/bai/{topic}/get'
            publish(client, full_topic, "?3")
        client.loop_stop()       
        

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


def Heating_main(temp_diff):
    topics_z2m = {
        'Salon': "0xa4c1384e6bcc60c6", 
        'Kuchnia': "0xa4c138d0aa4d2b86",
        'Jozef': "0xa4c138ad1d132790",
        'Jadalnia': "0xa4c13818b181eda9",
        'Sypialnia': "0x94deb8fffe2e751a"
    }




    OFF_VALVE_TEMP = 16.0
    ON_VALVE_TEMP = 24.0
    WODA = 42
    WODAOFF= 0    
    water_times = ['5:00', '16:00']
    PIEC_OFF = 1
    settemp = 40
    podiff = {-0.25: 45, -0.5:50, -2:60}
    jodiff = {-0.5: 40, -1: 45, -2: 50}

    print(temp_diff)
    close_valve = [k for k, v in temp_diff.items() if v >= 1]
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

        Heating_main(temp_diff)

        sleep(120)

def return_current_settings():
    current_time = datetime.now().time()
    data = read_from_db('heat', 'time_measurement', connection, 1)
    points = list(data.get_points())
    data_point = points[0]

    def is_time_in_range(start, end):
        # Check if the range spans midnight
        if start <= end:
            return start <= current_time <= end
        else:
            # Time span crosses midnight
            return current_time >= start or current_time <= end
    morning_start = datetime.strptime(data_point.get('MorningHour'), "%H:%M").time()
    day_start = datetime.strptime(data_point.get('DayHour'), "%H:%M").time()
    evening_start = datetime.strptime(data_point.get('EveningHour'), "%H:%M").time()
    night_start = datetime.strptime(data_point.get('NightHour'), "%H:%M").time()

    if is_time_in_range(morning_start, day_start):
        return {
            'Jozef': data_point.get('JozefMorningHour'),
            'Kuchnia': data_point.get('KuchniaMorningHour'),
            'Salon': data_point.get('SalonMorningHour'),
            'Sypialnia': data_point.get('SypialniaMorningHour')
        }, 'Morning'
    # Day (12:00 - 17:59)
    elif is_time_in_range(day_start, evening_start):
        return {
            'Jozef': data_point.get('JozefDayHour'),
            'Kuchnia': data_point.get('KuchniaDayHour'),
            'Salon': data_point.get('SalonDayHour'),
            'Sypialnia': data_point.get('SypialniaDayHour')
        }, 'Day'
    # Evening (18:00 - 21:59)
    elif is_time_in_range(evening_start, night_start):
        return {
            'Jozef': data_point.get('JozefEveningHour'),
            'Kuchnia': data_point.get('KuchniaEveningHour'),
            'Salon': data_point.get('SalonEveningHour'),
            'Sypialnia': data_point.get('SypialniaEveningHour')
        }, 'Evening'
    # Night (22:00 - 04:59)
    elif is_time_in_range(night_start, morning_start):
        return {
            'Jozef': data_point.get('JozefNightHour'),
            'Kuchnia': data_point.get('KuchniaNightHour'),
            'Salon': data_point.get('SalonNightHour'),
            'Sypialnia': data_point.get('SypialniaNightHour')
        }, 'Night'
    else:
        print("ERROR wrong time")
        return 'ERROR'

def return_current_temps():
    current_time = datetime.now(timezone.utc)
    rooms = {
        'Jozef': {'measurment': 'esp/tem', 'value_name': 'value'},
        'Kuchnia': {'measurment':  'esp/sypialnia', 'value_name': 'value'},
        'Salon': {'measurment':  'rpi_temperatura', 'value_name': 'celsius'},
        'Sypialnia': {'measurment':  'esp/kuchnia', 'value_name': 'value'}
    }  
    current_temperatures = {}  
    for k,v in rooms.items():
        data = read_from_db('heat', v['measurment'], connection, 5)
        points = list(data.get_points())
        current_temperatures[k] = []
        for data_point in points:
        
            influx_time = datetime.fromisoformat(data_point.get('time').replace("Z", "+00:00"))
            time_difference = current_time - influx_time
            

            current_temperatures[k].append({'value': data_point.get(v['value_name']), 'time_difference': time_difference.seconds }    )
        

    return current_temperatures   
        


def read_from_db(db, measurment, connection, limit):
    client = InfluxDBClient(host=connection['URL'], port=connection['PORT'], 
                            database=db, username=connection['DBUSER'], password=connection['DBPASS'],
                            ssl=False, verify_ssl=False)
    query = f'SELECT * FROM "{measurment}" ORDER BY time DESC LIMIT {limit}'
    result = client.query(query)
    print(result)
    return result




def push_to_db(db, json_body, connection):
    #connection = {'URL': 1.1.1.1, 'PORT': 8086, "DBUUSER": "username", DBPASS: 'password}

    client = InfluxDBClient(host=connection['URL'], port=connection['PORT'], 
                            database=db, username=connection['DBUSER'], password=connection['DBPASS'],
                            ssl=False, verify_ssl=False)
    response = client.write_points(json_body)
    #write_api = client.write_api(write_options=SYNCHRONOUS)
    #response = write_api.write("heat", "home", json_body)
    if not response:
        print("Failed to write data.")
    client.close()


def measurments_preparation_sent(topic, type, body):
    
    print(topic, type, body)
    match type:
        case 'float':
            value = float(body.decode())
        case 'floatColon':
            value = float(body.decode().split(';')[0])
        case 'int':
            value = body.decode()
        case 'onoff':
            if body.decode() == 'on':
                value = 1
            else:
                value = 0
    data = [{"measurement": topic, "fields": {'value': value}}]
    connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}            
    push_to_db('heat', data, connection)            
    print(f'{topic} value = {value}')    
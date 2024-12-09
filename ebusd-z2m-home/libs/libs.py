from paho.mqtt import client as mqtt_client
from influxdb import InfluxDBClient
from datetime import datetime, timezone, timedelta
import random
from time import sleep

timeout = 5 * 60
connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}      

broker = '192.168.0.230'
port = 11883
topic = "FlowTemp"
client_id = f'publish-{random.randint(0, 100)}'



def check_boiler_messages(topics):
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
from libs import push_to_db,read_from_db
import flask


#requests.packages.urllib3.disable_warnings() 
app = flask.Flask(__name__, static_folder='/app')

def measurments_preparation_sent(temperature=None, field=None, time_key=None, time_value=None):
    connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}   
    Winter = 1
    data = read_from_db('heat', 'time_measurement', connection, 1)
    data_point = list(data.get_points())
    print(data_point)
    data_point = [
            {
                "measurement": "time_measurement",
                "tags": {
                "MorningHour": "05:50",
                "DayHour": "06:45",
                "EveningHour": "18:00",
                "NightHour": "21:30"
                },
                "fields": {
                "JozefMorningHour": float(21.2),
                "JozefDayHour": float(20.5),
                "JozefEveningHour": float(21.2),
                "JozefNightHour": float(21.3),
                "SalonMorningHour": float(22.3),
                "SalonDayHour": float(21.8), 
                "SalonEveningHour": float(21.8),
                "SalonNightHour": float(0),
                "SypialniaMorningHour": float(0),
                "SypialniaDayHour": float(0),
                "SypialniaEveningHour": float(22.5),
                "SypialniaNightHour": float(22.5),
                "KuchniaMorningHour": float(0),
                "KuchniaDayHour": float(21),
                "KuchniaEveningHour": float(21),
                "KuchniaNightHour": float(0)
                }
            }
            ]
    if temperature and field:
        print(f'{temperature} {field}')
        data_point[0]['fields'][field] = temperature
    if time_key and time_value:
        print(f'{time_key} {time_value}')
        data_point[0]['tags'][time_key] = time_value
    #data = [{"measurement": "heat_setting", "fields": {'value': value}}]
    push_to_db('heat', data_point, connection)         

def get_data():
    connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}      

    #measurments_preparation_sent()
    Daytimes = ['Morning', 'Day', 'Evening', 'Night']
    Rooms = ['Jozef', 'Salon', 'Sypialnia', 'Kuchnia' ]

    combinations = []
    data = read_from_db('heat', 'time_measurement', connection, 1)
    points = list(data.get_points())
    data_point = points[0]
    data = []
    time_data = []
    for time in Daytimes:
        day_key = f'{time}Hour'
        day_value = data_point.get(day_key)
        time_data.append(day_value)
    for room in Rooms:
        line = []
        for time in Daytimes:

            key = f'{room}{time}Hour'
            value = data_point.get(key)
            try:
                keymax = f'{room}{time}MaxHour'
                print(keymax)
                valuemax = data_point.get(keymax)
            except:
                valuemax = 0
            line.append([value, valuemax])
            combinations.append(key)
        data.append(line) 
    print(combinations)        
    
    Daytimes.insert(0, "x") 
    print(data)
    print(time_data)
    return Daytimes, Rooms, data, time_data





@app.route('/',methods = ['GET'])
def render_site():
    Daytimes, Rooms, data, time_data = get_data()
    return flask.render_template('site2.html', x_headers=Daytimes, y_headers=Rooms, data=data, time_data=time_data )


@app.route('/post',methods = ['POST'])
def setup_temp():
    print("hello")
    try:
        RoomTime = f"{flask.request.form['RoomTime']}Hour"
        
        if 'Time_' in RoomTime:
            print("istime")
            NewTemp = flask.request.form['NewTemp']
            print(RoomTime)
            print(NewTemp)
            measurments_preparation_sent(time_key=RoomTime.split("Time_")[1], time_value=NewTemp )
        else:    
            NewTemp = float(flask.request.form['NewTemp'])
            print(f'{NewTemp} {RoomTime}')
            measurments_preparation_sent(temperature=NewTemp, field=RoomTime)
    except Exception as e: 
        print(e)
    return '200'
    #print(server)

app.run(host="0.0.0.0", port=5002)
from libs import push_to_db,read_from_db
import flask



#requests.packages.urllib3.disable_warnings() 
app = flask.Flask(__name__, static_folder='/app')

def measurments_preparation_sent(temperature, field):
    connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}   
    Winter = 1

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
    data_point[0]['fields'][field] = temperature

    #data = [{"measurement": "heat_setting", "fields": {'value': value}}]
    push_to_db('heat', data_point, connection)         

connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}      

#measurments_preparation_sent()
Daytimes = ['Morning', 'Day', 'Evening', 'Night']
Rooms = ['Jozef', 'Salon', 'Sypialnia', 'Kuchnia' ]
combinations = []
data = read_from_db('heat', 'time_measurement', connection, 1)
points = list(data.get_points())
data_point = points[0]
data = []
for room in Rooms:
    line = []
    for time in Daytimes:
        key = f'{room}{time}Hour'
        value = data_point.get(key)
        line.append(value)
        combinations.append(key)
    data.append(line) 
print(combinations)        

print(data)
# data = [
#     {'name': 'Jozef', 'age': 25, 'city': 'New York'},
#     {'name': 'Bob', 'age': 30, 'city': 'Los Angeles'},
#     {'name': 'Charlie', 'age': 35, 'city': 'Chicago'}
# ]

Daytimes.insert(0, "x")
print(Daytimes)
y_headers = ["Row 1", "Row 2", "Row 3"]


@app.route('/get',methods = ['GET'])
def render_site():
    return flask.render_template('site2.html', x_headers=Daytimes, y_headers=Rooms, data=data)


@app.route('/post',methods = ['POST'])
def setup_temp():
    print("hello")
    try:
        RoomTime = f"{flask.request.form['RoomTime']}Hour"
        NewTemp = float(flask.request.form['NewTemp'])
        print(f'{NewTemp} {RoomTime}')
        measurments_preparation_sent(NewTemp, RoomTime)
    except Exception as e: 
        print(e)
    return '200'
    #print(server)

app.run(host="0.0.0.0", port=5002)
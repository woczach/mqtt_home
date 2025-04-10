from libs import push_to_db


def measurments_preparation_sent():
    connection = {'URL': '192.168.0.230', 'PORT': 8086, "DBUSER": "username", "DBPASS": 'password'}
    Winter = 1

    data_point = [
            {
                "measurement": "time_measurement",
                "tags": {
                "MorningHour": "05:50",
                "DayHour": "07:45",
                "EveningHour": "17:30",
                "NightHour": "20:10"
                },
                "fields": {
                "JozefMorningHour": float(21.2),
                "JozefDayHour": float(21.2),
                "JozefEveningHour": float(21.2),
                "JozefNightHour": float(21.2),
                "SalonMorningHour": float(22.0),
                "SalonDayHour": float(21.5),
                "SalonEveningHour": float(21.8),
                "SalonNightHour": float(21.5),
                "SypialniaMorningHour": float(21.8),
                "SypialniaDayHour": float(0),
                "SypialniaEveningHour": float(0),
                "SypialniaNightHour": float(21.1),
                "KuchniaMorningHour": float(0),
                "KuchniaDayHour": float(0),
                "KuchniaEveningHour": float(0),
                "KuchniaNightHour": float(0)
                }
            }
            ]

    #data = [{"measurement": "heat_setting", "fields": {'value': value}}]
    push_to_db('heat', data_point, connection)


measurments_preparation_sent()

# # Define the time tags
# tags = {
#     "MorningHour": "05:50",
#     "DayHour": "06:45",
#     "EveningHour": "18:00",
#     "NightHour": "21:30"
# }

# # Define the rooms you want to use
# rooms = ["Jozef", "Salon", "Sypialnia", "Kuchnia"]

# # Create the fields dynamically based on room names and tags, but set all values to 0
# fields = {}
# for room in rooms:
#     for tag_name in tags:
#         # Create a new field using the room name and tag name, setting its value to 0
#         field_name = f"{room}{tag_name}"
#         fields[field_name] = 0

# # Create the data point for InfluxDB
# data_point = [
#     {
#         "measurement": "time_measurement",
#         "tags": tags,
#         "fields": fields
#     }
# ]

# # Example output
# print(data_point)

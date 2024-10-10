import threading
import time
import configparser



a = 0  #global variable

def thread1():
   global a
   while 1:
    config = configparser.ConfigParser()
    config.read('config.cfg')
    print(config['Common']['TEMPJOZEF'])
    print(float(config['Common']['TEMPPOKOJ']) + 1)
    print(int(config['Common']['WODAOFF']))
    print(config['Common']['NOC'])
    print(int(config['Common']['WODA']))
    print(a)
    time.sleep(1)

def thread2():
    global a
    while 1:
        a += 1
        time.sleep(1)



t1 = threading.Thread(target=thread1)
t2 = threading.Thread(target=thread2)

t1.start()
t2.start()
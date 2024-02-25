#! /usr/bin/python

from airthings import WavePlus, Sensors
import paho.mqtt.client as mqtt
import configparser
import operator
import json
import time
import uptime
import datetime

# global variables
airthings = { "Time": 0, "Uptime": 0 }

# read config
config = configparser.ConfigParser()
config.read('config.ini')
if 'MQTT' in config:
    for key in [ 'TOPIC', 'SERVER', 'PORT', 'QOS', 'TIMEOUT', 'USER', 'PASS']:
        if not config['MQTT'][key]:
            print("Missing or empty config entry MQTT/" + key)
            raise("Missing or empty config entry MQTT/" + key)
else:
    print("Missing config section MQTT")  
    raise("Missing config section MQTT")  

if 'AIRTHINGS' in config:
    for key in [ 'SERIAL']:
        if not config['AIRTHINGS'][key]:
            print("Missing or empty config entry AIRTHINGS/" + key)
            raise("Missing or empty config entry AIRTHINGS/" + key)
else:
    print("Missing config section AIRTHINGS")
    raise("Missing config section AIRTHINGS")



def airthings_tele(waveplus):
    global lasttele
    now = time.time()
    if now - lasttele > 300:

        # connect to device
        if not waveplus.connect():
            print("Not connected to Airthing")
            return False

        # read values
        sensors = waveplus.read()
        if not sensors:
            print("Failed to read values")
            return False

        # extract values
        airthings["humidity"] = str(sensors.getValue('HUMIDITY'))
        airthings["radon_st_avg"] = str(sensors.getValue('RADON_SHORT_TERM_AVG'))
        airthings["radon_lt_avg"] = str(sensors.getValue('RADON_LONG_TERM_AVG'))
        airthings["temperature"] = str(sensors.getValue('TEMPERATURE'))
        airthings["pressure"] = str(sensors.getValue('REL_ATM_PRESSURE'))
        airthings["CO2_lvl"] = str(sensors.getValue('CO2_LVL'))
        airthings["VOC_lvl"] = str(sensors.getValue('VOC_LVL'))

        get_time()
        client.publish(config['MQTT']['TOPIC'] + '/tele/STATE', json.dumps(airthings), int(config['MQTT']['QOS']))
        lasttele = now
        
        # disconnect device
        waveplus.disconnect()
    return True


def get_time():
    result = ""
    time = uptime.uptime()
    result = "%01d" % int(time / 86400)
    time = time % 86400
    result = result + "T" + "%02d" % (int(time / 3600))
    time = time % 3600
    airthings["Uptime"] = result + ":" + "%02d" % (int(time / 60)) + ":" + "%02d" % (time % 60)
    airthings["Time"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print('MQTT unexpected connect return code ' + str(rc))
    else:
        print('MQTT client connected')
        client.connected_flag = 1


def on_disconnect(client, userdata, rc):
    client.connected_flag = 0
    if rc != 0:
        print('MQTT unexpected disconnect return code ' + str(rc))
    print('MQTT client disconnected')


# Add connection flags
mqtt.Client.connected_flag = 0
mqtt.Client.reconnect_count = 0

# Initialize Airthings
waveplus = WavePlus(int(config['AIRTHINGS']['SERIAL']))

run = 1
while run:
    try:
        # Init counters
        lasttele = 0
        # Create mqtt client
        client = mqtt.Client()
        client.connected_flag = 0
        client.reconnect_count = 0
        # Register LWT message
        client.will_set(config['MQTT']['TOPIC'] + '/tele/LWT', payload="Offline", qos=0, retain=True)
        # Register connect callback
        client.on_connect = on_connect
        # Register disconnect callback
        client.on_disconnect = on_disconnect
        # Set access token
        client.username_pw_set(config['MQTT']['USER'], config['MQTT']['PASS'])
        # Run receive thread
        client.loop_start()
        # Connect to broker
        client.connect(config['MQTT']['SERVER'], int(config['MQTT']['PORT']), int(config['MQTT']['TIMEOUT']))
        time.sleep(1)
        while not client.connected_flag:
            print("MQTT waiting to connect")
            client.reconnect_count += 1
            if client.reconnect_count > 10:
                print("MQTT restarting connection!")
                raise("MQTT restarting connection!")
            time.sleep(1)
        # Sent LWT update
        client.publish(config['MQTT']['TOPIC'] + '/tele/LWT',payload="Online", qos=0, retain=True)
        # Run sending thread
        while True:
            if client.connected_flag:
                airthings_tele(waveplus)
            else:
                print("MQTT connection lost!")
                raise("MQTT connection lost!")
            time.sleep(1)
    except KeyboardInterrupt:
        # Gracefull shutwdown
        run = 0
        client.loop_stop()
        if client.connected_flag:
            client.disconnect()
    except:
        client.loop_stop()
        if client.connected_flag:
            client.disconnect()
        del client
        time.sleep(5)

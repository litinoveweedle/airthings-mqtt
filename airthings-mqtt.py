#! /usr/bin/python

from airthings import WavePlus, Sensors
import paho.mqtt.client as mqtt
import configparser
import operator
import json
import time
import uptime
import datetime
import os
import sys

# define user-defined exception
class AppError(Exception):
    "Raised on aplication error"
    pass

class MqttConnect(Exception):
    "Raised on MQTT connection failure"
    pass

# global variables
state = { "Time": 0, "Uptime": 0 }

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

if 'RUNTIME' in config:
    for key in [ 'MAX_ERROR', 'STATE_FILE']:
        if not config['RUNTIME'][key]:
            raise AppError("Missing or empty config entry RUNTIME/" + key)
else:
    raise AppError("Missing config section RUNTIME")


def airthings_tele(mode):
    global lasttele
    global airthings
    now = time.time()
    if mode or now - lasttele > 300:
        # connect to device
        if not airthings.connect():
            print("Not connected to Airthing")
            return False

        # read values
        sensors = airthings.read()
        if not sensors:
            print("Failed to read values")
            return False

        # extract values
        state["humidity"] = str(sensors.getValue('HUMIDITY'))
        state["radon_st_avg"] = str(sensors.getValue('RADON_SHORT_TERM_AVG'))
        state["radon_lt_avg"] = str(sensors.getValue('RADON_LONG_TERM_AVG'))
        state["temperature"] = str(sensors.getValue('TEMPERATURE'))
        state["pressure"] = str(sensors.getValue('REL_ATM_PRESSURE'))
        state["CO2_lvl"] = str(sensors.getValue('CO2_LVL'))
        state["VOC_lvl"] = str(sensors.getValue('VOC_LVL'))

        get_time()
        client.publish(config['MQTT']['TOPIC'] + '/tele/STATE', json.dumps(state), int(config['MQTT']['QOS']))
        lasttele = now
        
        # disconnect device
        airthings.disconnect()
    return True


def airthings_init():
    global airthings

    # Initialize Airthings
    airthings = WavePlus(int(config['AIRTHINGS']['SERIAL']))

    # Subscribe for cmnd events
    client.subscribe(config['MQTT']['TOPIC'] + '/cmnd/+', int(config['MQTT']['QOS']))


def get_time():
    result = ""
    time = uptime.uptime()
    result = "%01d" % int(time / 86400)
    time = time % 86400
    result = result + "T" + "%02d" % (int(time / 3600))
    time = time % 3600
    state["Uptime"] = result + ":" + "%02d" % (int(time / 60)) + ":" + "%02d" % (time % 60)
    state["Time"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


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


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    topic = str(msg.topic)
    payload = str(msg.payload.decode("utf-8"))
    match = re.match(r'^' + config['MQTT']['TOPIC'] + '\/cmnd\/(state|POWER|VOLUME)$', topic)
    if match:
        topic = match.group(1)
        if topic == "state" and payload == "":
            airthings_tele(1)
        else:
            print("Unknown topic: " + topic + ", message: " + payload)
    else:
        print("Unknown topic: " + topic + ", message: " + payload)


# touch state file on succesfull run
def state_file(mode):
    if mode:
        if int(config['RUNTIME']['MAX_ERROR']) > 0 and config['RUNTIME']['STATE_FILE']:
            with open(config['RUNTIME']['STATE_FILE'], 'a'):
                os.utime(config['RUNTIME']['STATE_FILE'], None)
    elif os.path.isfile(config['RUNTIME']['STATE_FILE']):
        os.remove(config['RUNTIME']['STATE_FILE'])


# Add connection flags
mqtt.Client.connected_flag = 0
mqtt.Client.reconnect_count = 0


count = 0
while True:
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
        # Registed publish message callback
        client.on_message = on_message
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
        # Init airthings
        airthings_init()
        # Run sending thread
        while True:
            if client.connected_flag:
                count = 0
                airthings_tele(0)
                state_file(1)
            else:
                print("MQTT connection lost!")
                raise("MQTT connection lost!")
            time.sleep(1)
    except BaseException as error:
        print("An exception occurred:", type(error).__name__, "–", error)
        client.loop_stop()
        del airthings
        if client.connected_flag:
            client.unsubscribe(config['MQTT']['TOPIC'] + '/cmnd/+')
            client.disconnect()
        del client
        if type(error) in [ MqttConnect ] and count <= int(config['RUNTIME']['MAX_ERROR']):
            count = count + 1
            #Try to reconnect later
            time.sleep(10)
        elif type(error) in [ KeyboardInterrupt, SystemExit ]:
            state_file(0)
            # Gracefull shutwdown
            sys.exit(0)
        else:
            #Exit with error
            sys.exit(1)

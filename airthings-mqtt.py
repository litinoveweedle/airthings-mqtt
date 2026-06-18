#! /usr/bin/python

from airthings import WavePlus
import logging
import paho.mqtt.client as mqtt
import configparser
import json
import time
import datetime
import re
import sys
import traceback
from typing import Any


# define user-defined exception
class AppError(Exception):
    "Raised on application error"

    pass


class MqttError(Exception):
    "Raised on MQTT connection failure"

    pass


# Setup logging
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# global variables
state: dict[str, int | str] = {}
state = {"Time": 0, "Uptime": 0}

# read config
config = configparser.ConfigParser()
config.read("config.ini")

if "LOGGING" in config:
    if "LEVEL" in config["LOGGING"] and config["LOGGING"]["LEVEL"]:
        log_level = config["LOGGING"]["LEVEL"].upper()
        if log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            logger.setLevel(getattr(logging, log_level))
        else:
            raise AppError("Invalid logging level " + config["LOGGING"]["LEVEL"])
else:
    logger.error("Missing config section LOGGING")
    raise AppError("Missing config section LOGGING")

if "MQTT" in config:
    for key in [
        "TOPIC",
        "SERVER",
        "PORT",
        "QOS",
        "TIMEOUT",
        "USER",
        "PASS",
        "BIRTH_TOPIC",
    ]:
        if not config["MQTT"][key]:
            logger.error("Missing or empty config entry MQTT/" + key)
            raise AppError("Missing or empty config entry MQTT/" + key)
else:
    logger.error("Missing config section MQTT")
    raise AppError("Missing config section MQTT")

if "AIRTHINGS" in config:
    for key in ["SERIAL"]:
        if not config["AIRTHINGS"][key]:
            logger.error("Missing or empty config entry AIRTHINGS/" + key)
            raise AppError("Missing or empty config entry AIRTHINGS/" + key)
else:
    logger.error("Missing config section AIRTHINGS")
    raise AppError("Missing config section AIRTHINGS")

if "RUNTIME" in config:
    for key in ["MAX_ERROR", "RESTART_DELAY", "TELE_INTERVAL"]:
        if not config["RUNTIME"][key]:
            logger.error("Missing or empty config entry RUNTIME/" + key)
            raise AppError("Missing or empty config entry RUNTIME/" + key)
else:
    logger.error("Missing config section RUNTIME")
    raise AppError("Missing config section RUNTIME")


def airthings_init():
    global airthings

    # Initialize Airthings
    airthings = WavePlus(
        int(config["AIRTHINGS"]["SERIAL"]),
        timeout=5,
    )


def airthings_tele(mode):
    global last_tele
    global airthings
    now = time.time()

    if mode == 1 or now - last_tele > int(config["RUNTIME"]["TELE_INTERVAL"]):
        # Ensure broker connectivity and fail fast if MQTT is unhealthy.
        mqtt_check()

        # Sent LWT update
        mqtt_publish("/tele/LWT", payload="Online", retain=True)

        try:
            # connect to device
            if not airthings.connect():
                logger.error("Not connected to Airthing")
                raise AppError("Not connected to Airthing")

            # read values
            sensors = airthings.read()
            if not sensors:
                logger.error("Failed to read values")
                raise AppError("Failed to read values")
        except Exception as error:
            logger.error(f"An error occurred connecting or reading Airthings: {error}")
            raise AppError(
                f"An error occurred connecting or reading Airthings: {error}"
            )
        finally:
            # disconnect device on any BLE failure
            try:
                airthings.disconnect()
            except Exception as error:
                logger.warning(f"Failed to disconnect Airthings cleanly: {error}")

        # extract values
        state["humidity"] = str(sensors.getValue("HUMIDITY"))
        state["radon_st_avg"] = str(sensors.getValue("RADON_SHORT_TERM_AVG"))
        state["radon_lt_avg"] = str(sensors.getValue("RADON_LONG_TERM_AVG"))
        state["temperature"] = str(sensors.getValue("TEMPERATURE"))
        state["pressure"] = str(sensors.getValue("REL_ATM_PRESSURE"))
        state["CO2_lvl"] = str(sensors.getValue("CO2_LVL"))
        state["VOC_lvl"] = str(sensors.getValue("VOC_LVL"))

        get_time()
        mqtt_publish("/tele/STATE", payload=json.dumps(state))
        last_tele = now
        return True
    else:
        return False


def get_uptime_seconds() -> int:
    # Support different uptime package APIs and fallback to /proc/uptime.
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            return int(float(f.read().split()[0]))
    except Exception as error:
        logger.warning(f"Could not determine system uptime: {error}")
        return 0


def get_time() -> None:
    result = ""
    uptime_seconds = get_uptime_seconds()
    result = "%01d" % int(uptime_seconds / 86400)
    uptime_seconds = uptime_seconds % 86400
    result = result + "T" + "%02d" % (int(uptime_seconds / 3600))
    uptime_seconds = uptime_seconds % 3600
    state["Uptime"] = (
        result
        + ":"
        + "%02d" % (int(uptime_seconds / 60))
        + ":"
        + "%02d" % (uptime_seconds % 60)
    )
    state["Time"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def mqtt_init() -> None:
    global client

    # Create mqtt client
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.enable_logger(logger)
    # Register LWT message
    client.will_set(
        config["MQTT"]["TOPIC"] + "/tele/LWT",
        payload="Offline",
        qos=int(config["MQTT"]["QOS"]),
        retain=True,
    )
    # Let auto-reconnect progressively if the link drops.
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    # Register connect callback
    client.on_connect = mqtt_on_connect
    # Register disconnect callback
    client.on_disconnect = mqtt_on_disconnect
    # Register publish message callback
    client.on_message = mqtt_on_message
    # Set access token
    client.username_pw_set(config["MQTT"]["USER"], config["MQTT"]["PASS"])
    # Run receive thread
    client.loop_start()
    # Connect to broker
    client.connect(
        config["MQTT"]["SERVER"],
        int(config["MQTT"]["PORT"]),
        int(config["MQTT"]["TIMEOUT"]),
    )
    time.sleep(1)
    mqtt_check()


def mqtt_check() -> None:
    global client

    if not client:
        raise MqttError("MQTT client is not initialized")

    retries = 0
    while not client.is_connected():
        if retries >= 5:
            raise MqttError("MQTT reconnect failed")
        logger.warning("MQTT is disconnected, trying to connect")
        try:
            client.reconnect()
        except Exception as error:
            logger.warning(f"MQTT reconnect attempt failed: {error}")
        retries += 1
        time.sleep(1)


def mqtt_publish(
    topic: str,
    payload: str,
    qos: int = int(config["MQTT"]["QOS"]),
    retain: bool = False,
) -> None:
    global client

    if client and client.is_connected():
        try:
            if not topic.startswith("/"):
                topic = "/" + topic
            logger.debug(
                f"Publishing MQTT message to topic {topic} with payload {payload}"
            )
            result = client.publish(
                config["MQTT"]["TOPIC"] + topic,
                payload=payload,
                qos=qos,
                retain=retain,
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise MqttError(
                    f"MQTT publish failed with code {result.rc} on topic {topic}"
                )
        except Exception as error:
            logger.error(f"Failed to publish MQTT message: {error}")
            raise MqttError(f"Failed to publish MQTT message: {error}")
    else:
        logger.error("MQTT not connected!")
        raise MqttError("MQTT not connected!")


def mqtt_cleanup() -> None:
    global client

    if client:
        client.loop_stop()
        if client.is_connected():
            # Sent LWT update
            mqtt_publish("/tele/LWT", payload="Offline", retain=True)
            client.disconnect()
        client = None


def mqtt_on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: dict,
    reason_code: int,
    properties: mqtt.Properties,
):
    if reason_code != 0:
        logger.error("MQTT unexpected connect return code " + str(reason_code))
        return
    else:
        logger.info("MQTT client connected")
        client.connected_flag = 1

    # Subscribe for cmnd events
    client.subscribe(config["MQTT"]["TOPIC"] + "/cmnd/+", int(config["MQTT"]["QOS"]))

    # Subscribe for Home Assistant birth messages
    if config["MQTT"]["BIRTH_TOPIC"]:
        client.subscribe(config["MQTT"]["BIRTH_TOPIC"], int(config["MQTT"]["QOS"]))


def mqtt_on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    flags: dict,
    reason_code: int,
    properties: mqtt.Properties,
):
    client.connected_flag = 0
    if reason_code != 0:
        logger.error("MQTT unexpected disconnect return code " + str(reason_code))
    else:
        logger.info("MQTT client disconnected")


# The callback for when a PUBLISH message is received from the server.
def mqtt_on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage):
    topic = str(msg.topic)
    payload = str(msg.payload.decode("utf-8"))

    tele = re.match(r"^" + config["MQTT"]["TOPIC"] + "/cmnd/(state)$", topic)
    birth = re.match(r"^" + config["MQTT"]["BIRTH_TOPIC"] + "$", topic)

    if tele:
        topic = tele.group(1)
        if topic == "state" and payload == "":
            airthings_tele(1)
        else:
            logger.warning("Unknown topic: " + topic + ", message: " + payload)
    elif birth:
        if config["MQTT"]["BIRTH_TOPIC"]:
            if payload.lower() == "online":
                logger.info("Home Assistant is online")
                airthings_tele(1)
            else:
                logger.info("Home Assistant is " + payload)
    else:
        logger.warning("Unknown topic: " + topic + ", message: " + payload)


client = None
restart = 0
while True:
    try:
        # Init counters
        last_tele = 0
        # Create mqtt client
        if not client:
            # Init mqtt
            mqtt_init()
        # Init airthings
        airthings_init()
        # Run sending thread
        while True:
            airthings_tele(0)
            time.sleep(1)
    except BaseException as error:
        logger.error(f"An exception occurred: {type(error).__name__} – {error}")
        if isinstance(error, (MqttError, AppError)) and (
            int(config["RUNTIME"]["MAX_ERROR"]) == 0
            or restart <= int(config["RUNTIME"]["MAX_ERROR"])
        ):
            if isinstance(error, MqttError):
                mqtt_cleanup()
            elif isinstance(error, AppError):
                pass
            restart += 1
            # Try to reconnect later
            time.sleep(int(config["RUNTIME"]["RESTART_DELAY"]))
        elif isinstance(error, (KeyboardInterrupt, SystemExit)):
            # Graceful shutdown
            logger.error("Gracefully terminating application")
            mqtt_cleanup()
            logger.error("Application terminated")
            sys.exit(0)
        else:
            # Exit with error
            logger.error("Unknown exception, aborting application")
            logger.debug(f"Exception details: {traceback.format_exc()}")
            sys.exit(1)

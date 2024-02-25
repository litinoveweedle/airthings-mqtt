#!/bin/bash

echo 'Attempting to recover Airthings service!' > /tmp/recovery_info

systemctl restart bluetooth
setcap 'cap_net_raw,cap_net_admin+eip' /usr/local/lib/python3.*/dist-packages/bluepy/bluepy-helper
systemctl reset-failed airthings-mqtt
systemctl restart airthings-mqtt

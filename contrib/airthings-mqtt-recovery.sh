#!/bin/bash


if [ -f /run/airthings/airthings.state ]
then
    echo 'Giving up to recover airthings, executing reboot!'
    exit 1
else
    echo 'Sending email to notify about airthings-mqtt service failure.'
    echo "Subject: airthings-mqtt service is down" | sendmail -v root

    /bin/hciconfig hci0 down
    systemctl stop bluetooth
    systemctl stop hciuart
    lsmod | grep -q btusb
    if [ $? -eq 0 ]
    then
        /sbin/rmmod btusb
    fi
    /sbin/modprobe btusb
    systemctl start hciuart 2>/dev/null
    systemctl start bluetooth
    sleep 5
    /bin/hciconfig hci0 up

    systemctl reset-failed airthings-mqtt.service
    systemctl restart airthings-mqtt.service
    exit 0
fi

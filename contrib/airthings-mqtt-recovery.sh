#!/bin/bash


if [ -f /run/airthings/airthings.state ]
then
    echo 'Giving up to recover airthings, executing reboot!'
    exit 1
else
    echo 'Sending email to notify about airthings-mqtt service failure.'
    echo "Subject: airthings-mqtt service is down" | sendmail -v root
 
    setcap 'cap_net_raw,cap_net_admin+eip' /usr/local/lib/python3.*/dist-packages/bluepy/bluepy-helper
    /bin/hciconfig hci0 down
    systemctl stop bluetooth
    systemctl stop hciuart
    /sbin/rmmod btusb
    /sbin/modprobe btusb
    systemctl start hciuart 2>/dev/null
    systemctl start bluetooth
    sleep 5
    /bin/hciconfig hci0 up

    systemctl reset-failed eneby-mqtt.service
    systemctl restart eneby-mqtt.service
    exit 0
fi

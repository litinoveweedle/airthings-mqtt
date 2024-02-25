Due to multiple bugs/race conditions in BT which are not fixed for long time, fix provided in this directory is required to keep raspberry Pi BTLE working.

To install it copy diretory structure to /etc/systemd file structure.

references:
https://github.com/RPi-Distro/pi-bluetooth/issues/8
https://github.com/Pack3tL0ss/ConsolePi/commit/8abebeda8811b5f93be0ebb7a7d98368cd30cc83
https://raspberrypi.stackexchange.com/questions/145499/resolved-audio-over-bluetooth-doesnt-work-when-launch-as-a-systemd-service
https://unix.stackexchange.com/questions/705326/debian-11-bluetooth-sap-driver-initialization-failed
https://stackoverflow.com/questions/70759341/error-in-bluetooth-status-raspberry-pi-failed-to-set-privacy-rejected-0x0

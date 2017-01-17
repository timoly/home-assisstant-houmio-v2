Home Assistant Houm.io v2 driver & sample configuration
- http://home-assistant.io
- http://houm.io

Install notes for Raspberry Pi 3:

journalctl -fu home-assistant@pi
sudo systemctl stop home-assistant@pi
sudo su -s /bin/bash homeassistant
source /srv/homeassistant/bin/activate
pip3 install --upgrade homeassistant
sudo systemctl start home-assistant@pi

create secrets.yaml into configuration where you fill personal configuration variables.

Installing custom driver
copy houmio.py into /home/pi/.homeassistant/custom_components/light

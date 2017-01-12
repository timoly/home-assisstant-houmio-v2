Home Assistant Houm.io v2 (http://houm.io) driver & sample configuration

Install notes for Raspberry Pi 3:

journalctl -fu home-assistant@pi
sudo systemctl stop home-assistant@pi
sudo su -s /bin/bash homeassistant
source /srv/homeassistant/bin/activate
pip3 install --upgrade homeassistant
sudo systemctl start home-assistant@pi

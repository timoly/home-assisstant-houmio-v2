#configuration.yaml

light:
  - platform: houmio
    sitekey: SITEKEY

journalctl -fu home-assistant@pi

sudo systemctl stop home-assistant@pi
sudo su -s /bin/bash homeassistant
source /srv/homeassistant/bin/activate
pip3 install --upgrade homeassistant
sudo systemctl start home-assistant@pi

import logging
import requests
import voluptuous as vol
import time
import threading

from homeassistant.components.light import (ATTR_BRIGHTNESS, Light, SUPPORT_BRIGHTNESS, SUPPORT_FLASH)
import homeassistant.helpers.config_validation as cv
from socketIO_client import SocketIO, BaseNamespace

REQUIREMENTS = ['requests==2.12.3', 'socketIO-client-2==0.7.2']

_LOGGER = logging.getLogger(__name__)

HOST = 'https://houmi.herokuapp.com'

LIGHT_BINARY = (SUPPORT_FLASH)
LIGHT_BRIGHTNESS = (SUPPORT_BRIGHTNESS)

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Houmio v2 Light platform."""

    state = {}
    siteKey = config.get('sitekey')
    state['lastUpdate'] = 0
    state['lights'] = None

    if siteKey is None:
        _LOGGER.error('sitekey is required')
        return False

    def fetchLights():
        r = requests.get("{0}/api/site/{1}".format(HOST, siteKey))

        if r.status_code != 200:
            _LOGGER.error('Could not connect to Houmio')
            return False
        else:
            return r.json()['lights']

    state['lights'] = fetchLights()

    if state['lights'] is False:
        return False

    def ready():
        _LOGGER.info('clientReady')
        socketIO.emit('clientReady', { 'siteKey': siteKey })
        socketIO.wait(seconds=5)

    def set_interval(func, sec):
        def func_wrapper():
            set_interval(func, sec)
            func()
        t = threading.Timer(sec, func_wrapper)
        t.start()
    set_interval(ready, 3600)

    class Namespace(BaseNamespace):

        def on_connect(self):
            _LOGGER.info('[Connected]')
            ready()

        def on_reconnect(self):
            _LOGGER.info('[Reconnected]')
            ready()

        def on_disconnect(self):
            _LOGGER.info('[Disconnected]')

    socketIO = SocketIO(HOST, None, Namespace)
    socketIO.wait(seconds=5)
    ready()

    def updateStatus(cb):
        now = int(time.time())
        lights = state['lights']
        if now - state['lastUpdate'] > 3:
            state['lastUpdate'] = int(time.time())
            lights = fetchLights()
            newLights = list(filter(lambda x: True if next((y for y in state['lights'] if y['_id'] == x['_id']), None) is None else False, lights))
            add_devices(HoumioLight(light, socketIO, updateStatus) for light in newLights)

        state['lights'] = lights
        cb(lights)

    add_devices(HoumioLight(light, socketIO, updateStatus) for light in state['lights'])

class HoumioLight(Light):
    """Representation of an Houmio Light."""

    def __init__(self, light, socketIO, updateStatus):
        """Initialize an HoumioLight."""
        self._light = light
        self._socketIO = socketIO
        self._updateStatus = updateStatus

    @property
    def unique_id(self):
        """Return the ID of this light."""
        return self._light['_id']

    @property
    def name(self):
        """Return the display name of this light."""
        return self._light['name'] if self._light['room'] == "" else "{0}/{1}".format(self._light['room'], self._light['name'])

    @property
    def brightness(self):
        """Brightness of the light (an integer in the range 1-255)."""
        return None if self._light['type'] == 'binary' else self._light['bri']

    @property
    def supported_features(self):
        """Flag supported features."""
        return LIGHT_BINARY if self._light['type'] == 'binary' else LIGHT_BRIGHTNESS

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._light['on'] == 1

    def action(self, data):
        _LOGGER.info('action', data)
        self._socketIO.emit('apply/light', data)
        self._socketIO.wait_for_callbacks(seconds=1)

    def turn_on(self, **kwargs):
        print("turn on", kwargs, self._light)

        self.action({
            '_id': self._light['_id'],
            'bri': kwargs.get(ATTR_BRIGHTNESS, 255),
            'on': True
        })

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        print("turn off", kwargs, self._light)
        self.action({
            '_id': self._light['_id'],
            'on': False
        })

    def update(self):
        """Fetch new state data for this light."""

        def onLights(lights):
            light = next((x for x in lights if x['_id'] == self._light['_id']), None)
            if light is not None:
                # _LOGGER.info('updating', light['name'], 'bri:', self._light['bri'], '->', light['bri'], 'state:', self._light['on'], '->', light['on'])
                self._light['bri'] = light['bri']
                self._light['on'] = light['on']

        self._updateStatus(onLights)

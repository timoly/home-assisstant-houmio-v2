import asyncio
import logging
import aiohttp
import voluptuous as vol
import time
from threading import Thread, Timer
from queue import Queue

from homeassistant.components.light import (ATTR_BRIGHTNESS, Light, SUPPORT_BRIGHTNESS, SUPPORT_FLASH)
import homeassistant.helpers.config_validation as cv
from socketIO_client import SocketIO, BaseNamespace

REQUIREMENTS = ['aiohttp==1.2.0', 'socketIO-client-2==0.7.2']

DOMAIN = 'light_houmio_v2'
# ENTITY_ID_FORMAT = DOMAIN + '.{}'

_LOGGER = logging.getLogger(__name__)

HOST = 'https://houmi.herokuapp.com'

LIGHT_BINARY = (SUPPORT_FLASH)
LIGHT_BRIGHTNESS = (SUPPORT_BRIGHTNESS)

def SocketHoumio(siteKey, emitQueue, statusQueue):
    socketio = None
    def ready():
        _LOGGER.info('clientReady')
        socketio.emit('clientReady', { 'siteKey': siteKey })

    def _receive_events_thread():
        socketio.wait()

    class Namespace(BaseNamespace):

        def on_connect(self):
            _LOGGER.info('[Connected]')
            ready()

        def on_reconnect(self):
            _LOGGER.info('[Reconnected]')
            ready()

        def on_disconnect(self):
            _LOGGER.info('[Disconnected]')

        def on_event(self, event, args):
            _LOGGER.info("on_event: {0} {1}".format(event, args))

            # TODO: new/removed light event
            if event == 'setLightState':
                statusQueue.put(args)

    socketio = SocketIO(HOST, None, Namespace)

    receive_events_thread = Thread(target=_receive_events_thread)
    receive_events_thread.daemon = True
    receive_events_thread.start()

    def set_interval(func, sec):
        def func_wrapper():
            set_interval(func, sec)
            func()
        t = Timer(sec, func_wrapper)
        t.start()
    set_interval(ready, 1800)

    while True:
        data = emitQueue.get()
        socketio.emit('apply/light', data)

def consumer(statusQueue, lights):
    while True:
        status = statusQueue.get()

        light = next((x for x in lights if x.unique_id == status['_id']), None)
        if light is not None:
            light.update(status)

@asyncio.coroutine
def fetch(session, url):
    with aiohttp.Timeout(10):
        resp = yield from session.get(url)
        return (yield from resp.json()) if resp.status == 200 else (yield from resp.release())

@asyncio.coroutine
def fetchLights(loop, siteKey):
    with aiohttp.ClientSession(loop=loop) as session:
        data = yield from fetch(session, "{0}/api/site/{1}".format(HOST, siteKey))

        if data is None:
            _LOGGER.error('Could not connect to Houmio')
            return False

        return data['lights']

@asyncio.coroutine
def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    """Setup the Houmio v2 Light platform."""

    siteKey = config.get('sitekey')

    if siteKey is None:
        _LOGGER.error('sitekey is required')
        return False

    lights = yield from fetchLights(hass.loop, siteKey)

    if lights is False:
        return False

    emitQueue = Queue()
    statusQueue = Queue()

    lights = [HoumioLight(light, emitQueue) for light in lights]

    socketHoumio = Thread(target=SocketHoumio, args=(siteKey, emitQueue, statusQueue))
    socketHoumio.start()

    statusConsumer = Thread(target=consumer, args=(statusQueue, lights))
    statusConsumer.start()

    yield from async_add_devices(lights, True)
    return True

class HoumioLight(Light):
    """Representation of an Houmio Light."""

    def __init__(self, light, emitQueue):
        """Initialize an HoumioLight."""
        # self.entity_id = ENTITY_ID_FORMAT.format(light['_id'])
        self._light = light
        self._emitQueue = emitQueue

    def update(self, status):
        _LOGGER.info("update: {0} {1}".format(status, self._light))

        if 'bri' in status:
            self._light['bri'] = status['bri']
        if 'on' in status:
            self._light['on'] = status['on']

        self.hass.loop.create_task(self.async_update_ha_state())

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
        _LOGGER.info('action: {0}'.format(data))
        self._emitQueue.put(data)

    def turn_on(self, **kwargs):
        _LOGGER.info("turn on: {0} {1}".format(kwargs, self._light))

        self.action({
            '_id': self._light['_id'],
            'bri': kwargs.get(ATTR_BRIGHTNESS, 255),
            'on': True
        })

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        _LOGGER.info("turn off: {0} {1}".format(kwargs, self._light))

        self.action({
            '_id': self._light['_id'],
            'on': False
        })

    @asyncio.coroutine
    def async_update(self):
        """new state is updated automatically based on ws events."""

import asyncio
import logging
import aiohttp
import time
from threading import Event, Thread, Timer
from queue import Queue
from functools import partial
import math

from homeassistant.components.light import (ATTR_BRIGHTNESS, ATTR_TRANSITION,
    Light, SUPPORT_BRIGHTNESS, SUPPORT_FLASH, SUPPORT_TRANSITION)
from socketIO_client import SocketIO, BaseNamespace

REQUIREMENTS = ['aiohttp==1.2.0', 'socketIO-client-2==0.7.2']

DOMAIN = 'light_houmio_v2'
# ENTITY_ID_FORMAT = DOMAIN + '.{}'

_LOGGER = logging.getLogger(__name__)

HOST = 'https://houmi.herokuapp.com'

LIGHT_BINARY = (SUPPORT_FLASH)
LIGHT_BRIGHTNESS = (SUPPORT_BRIGHTNESS | SUPPORT_TRANSITION)

TRANSITION_INTERVAL = 5

class setInterval():
    def __init__(self, func, sec):
        def func_wrapper():
            self.t = Timer(sec, func_wrapper)
            self.t.start()
            func()
        self.t = Timer(sec, func_wrapper)
        self.t.start()

    def cancel(self):
        self.t.cancel()

def SocketHoumio(siteKey, emitQueue, statusQueue):
    state = {}
    killpill = Event()

    def _receive_events_thread(stop_event):
        while not stop_event.wait(1):
            state['socketio'].wait(seconds=1)
        _LOGGER.info('Stopping socketIO wait')

    def ready():
        _LOGGER.info('clientReady')
        state['socketio'].emit('clientReady', { 'siteKey': siteKey })

    def reconnect():
        _LOGGER.info('reconnect')
        state['socketio'].disconnect()
        killpill.set()
        state['receive_events_thread'].join()
        connect()
        createReceiveEventsThread()

    def connect():
        _LOGGER.info('connect')
        state['socketio'] = SocketIO(HOST, None, Namespace)

    def createReceiveEventsThread():
        killpill.clear()
        state['receive_events_thread'] = Thread(target=_receive_events_thread, args=(killpill,))
        state['receive_events_thread'].daemon = True
        state['receive_events_thread'].start()

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

    connect()

    createReceiveEventsThread()

    setInterval(ready, 1800)

    setInterval(reconnect, 3600)

    while True:
        data = emitQueue.get()
        state['socketio'].emit('apply/light', data)

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
        self._transitionInterval = None

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

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        _LOGGER.info("turn off: {0} {1}".format(kwargs, self._light))

        if self._transitionInterval is not None:
            self._transitionInterval.cancel()

        if ATTR_TRANSITION in kwargs:
            transitionCount = math.ceil(kwargs[ATTR_TRANSITION] / TRANSITION_INTERVAL)
            step = self.step(transitionCount)
            bound_transition_down = partial(self.transition_down, step)
            self._transitionInterval = setInterval(bound_transition_down, TRANSITION_INTERVAL)
        else:
            self.action({
                '_id': self._light['_id'],
                'on': False
            })

    def turn_on(self, **kwargs):
        _LOGGER.info("turn on: {0} {1}".format(kwargs, self._light))

        if self._transitionInterval is not None:
            self._transitionInterval.cancel()

        if ATTR_TRANSITION in kwargs:
            transitionCount = math.ceil(kwargs[ATTR_TRANSITION] / TRANSITION_INTERVAL)
            step = self.step(transitionCount)
            bound_transition_up = partial(self.transition_up, step)
            self._transitionInterval = setInterval(bound_transition_up, TRANSITION_INTERVAL)
        else:
            self.action({
                '_id': self._light['_id'],
                'bri': kwargs.get(ATTR_BRIGHTNESS, 255),
                'on': True
            })

    def step(self, transitionCount):
        return math.ceil(self._light['bri'] / transitionCount)

    def transition_down(self, step):
        if self._light['bri'] <= 0 or self._light['on'] is False:
            self._transitionInterval.cancel()
            return

        bri = self._light['bri'] - step

        self.action({
            '_id': self._light['_id'],
            'bri': bri if bri >= 0 else 0,
            'on': True if bri >= 0 else False
        })

        if bri <= 0:
            self._transitionInterval.cancel()

    def transition_up(self, step):
        if self._light['bri'] >= 255 and self._light['on'] is True:
            self._transitionInterval.cancel()
            return

        bri = self._light['bri'] + step if self._light['on'] is True else step

        self.action({
            '_id': self._light['_id'],
            'bri': bri if bri <= 255 else 255,
            'on': True
        })

        if bri >= 255:
            self._transitionInterval.cancel()

    @asyncio.coroutine
    def async_update(self):
        """new state is updated automatically based on ws events."""

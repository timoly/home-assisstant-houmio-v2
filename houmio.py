import logging
import requests
import voluptuous as vol

from homeassistant.components.light import ATTR_BRIGHTNESS, Light, PLATFORM_SCHEMA
from homeassistant.const import CONF_HOST, CONF_USERNAME, CONF_PASSWORD
import homeassistant.helpers.config_validation as cv

REQUIREMENTS = ['requests==2.12.3]

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_SITEKEY): cv.string
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the Houmio v2 Light platform."""
    host = 'https://houmi.herokuapp.com/api/site'

    siteKey = config.get(CONF_SITEKEY)

    r = requests.get("{host}/{siteKey}")
    print r.text

    if r.status_code != 200:
        _LOGGER.error('Could not connect to Houmio')
        return False

    add_devices(HoumioLight(light) for light in hub.lights())


class HoumioLight(Light):
    """Representation of an Houmio Light."""

    def __init__(self, light):
        """Initialize an HoumioLight."""
        self._light = light

    @property
    def name(self):
        """Return the display name of this light."""
        return self._light.name

    @property
    def brightness(self):
        """Brightness of the light (an integer in the range 1-255).

        This method is optional. Removing it indicates to Home Assistant
        that brightness is not supported for this light.
        """
        return self._light.brightness

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._light.is_on()

    def turn_on(self, **kwargs):
        """Instruct the light to turn on.

        You can skip the brightness part if your light does not support
        brightness control.
        """
        self._light.brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        self._light.turn_on()

    def turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        self._light.turn_off()

    def update(self):
        """Fetch new state data for this light.

        This is the only method that should fetch new data for Home Assistant.
        """
        self._light.update()

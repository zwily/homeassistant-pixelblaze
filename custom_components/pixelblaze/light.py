"""Light platform for Pixelblaze."""
# pylint: disable=logging-fstring-interpolation
import logging

from .pb_monkeypatch import Pixelblaze

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    LightEntity,
    LightEntityFeature,
    ColorMode
)

from homeassistant.const import CONF_HOST, CONF_NAME

from homeassistant.util.color import color_hs_to_RGB

from .const import DOMAIN, CONFIG, PB_ATTR_HSV, PB_ATTR_RGB, EFFECT_SEQUENCER, EFFECT_SHUFFLE

_LOGGER = logging.getLogger(__name__)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the lights from config"""
    # pylint: disable=unused-argument

    _LOGGER.debug(f"Setting up platform for {DOMAIN}")

    ent_list = []
    dev_list = hass.data[DOMAIN][CONFIG]
    for dev in dev_list:
        ent_list.append(PixelblazeEntity(dev[CONF_HOST], dev[CONF_NAME]))

    add_entities(ent_list)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up lights for device"""
    dev = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([PixelblazeEntity(dev[CONF_HOST], dev[CONF_NAME])])


class PixelblazeEntity(LightEntity):
    """Representation of a Pixelblaze entity."""
    _attr_entity_registry_enabled_default = True

    def __init__(self, host, unique_id):
        """Initialize the light."""
        _LOGGER.debug(f"Initializing light for {unique_id}")

        self.id = unique_id  # pylint: disable=invalid-name
        self.host = host
        self._brightness = 0
        self._last_brightness = 64
        self._color = None
        self.color_picker_key = None
        self._effect = None
        self._effect_list = None
        self.init_pattern_list = False
        self.active_pid = None
        self.patternlist = ()
        self._pb = None
        self._color_mode = ColorMode.BRIGHTNESS

    async def async_added_to_hass(self):
        _LOGGER.debug(f"Adding to hass for {self.id}")
        self._pb = await self.hass.async_add_executor_job(Pixelblaze, self.host)

    async def async_will_remove_from_hass(self):
        _LOGGER.debug(f"Removing from hass for {self.id}")
        await self.hass.async_add_executor_job(self._pb.close)

    async def async_update(self):
        _LOGGER.debug(f"async_update for {self.id}")
        await self.hass.async_add_executor_job(self._sync_update)

    def _sync_update(self):
        # pylint: disable=arguments-differ, invalid-name
        _LOGGER.debug(f"sync_update for {self.id}")
        try:
            pb_config = self._pb.getConfigSettings()
            _LOGGER.debug(pb_config)

            if not self.init_pattern_list:
                ## DO ONCE: Get pattern list and set patterns names as the effect list
                self.update_pattern_list(self._pb)

            self._brightness = self._pb.getBrightnessSlider(pb_config) * 255

            pb_config_sequencer = self._pb.getConfigSequencer()
            if self._pb.getSequencerMode(pb_config_sequencer) == Pixelblaze.sequencerModes.Playlist:
                self._effect = EFFECT_SEQUENCER
            elif self._pb.getSequencerMode(pb_config_sequencer) == Pixelblaze.sequencerModes.ShuffleAll:
                self._effect = EFFECT_SHUFFLE
            else:
                pid = self._pb.getActivePattern(pb_config_sequencer)
                if pid != self.active_pid:
                    self.update_active_pattern(self._pb, pid)

        except Exception as e:  # pylint:disable=broad-except,invalid-name
            _LOGGER.error(
                f"Failed to update pixelblaze device {self.id}@{self.host}: Exception: {e}"
            )

    def update_pattern_list(self, pixelblaze: Pixelblaze):
        """Updates the pattern list"""
        _LOGGER.debug(f"Updating pattern list for {self.id}")
        self.patternlist = pixelblaze.getPatternList()
        p_list = list(self.patternlist.values())
        p_list.sort(key=str.lower)
        p_list.insert(0, EFFECT_SEQUENCER)
        p_list.insert(1, EFFECT_SHUFFLE)
        self._effect_list = p_list
        self.init_pattern_list = True

    def update_active_pattern(self, pixelblaze: Pixelblaze, active_pid):
        """Updates the current pattern and sets the correct supported features for this effect"""
        _LOGGER.debug(f"Updating running pattern on {self.id}")
        self.active_pid = active_pid
        if self.active_pid is not None and len(self.active_pid) > 0:
            if active_pid not in self.patternlist:
                self.update_pattern_list(pixelblaze)
            self._effect = self.patternlist[active_pid]

        if pixelblaze.getColorControlName() is None:
            self._color_mode = ColorMode.BRIGHTNESS

        else:
            self._color_mode = ColorMode.HS

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.id

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.id)},
            "name": self.id,
            "manufacturer": "Pixelblaze",
        }

    @property
    def should_poll(self):
        """No polling needed at this time"""
        return True

    @property
    def assumed_state(self):
        """Return True because unable to access real state of the entity."""
        return True

    @property
    def is_on(self):
        """Return true if device is on."""
        return self.brightness > 0

    @property
    def brightness(self):
        """Return the brightness property."""
        return self._brightness

    @property
    def hs_color(self):
        """Return the color property."""
        if self._color is None or self._color[1] == 0:
            return None
        return self._color

    @property
    def supported_features(self):
        """Flag supported features."""
        return LightEntityFeature.EFFECT

    @property
    def color_mode(self):
        return self._color_mode

    @property
    def supported_color_modes(self):
        return { self._color_mode }

    @property
    def effect(self):
        """Return the current effect for this light."""
        return self._effect

    @property
    def effect_list(self):
        """Return the list of supported effects for this light."""
        return self._effect_list

    async def async_turn_off(self, **kwargs):
        _LOGGER.debug(f"turn_off for {self.id}")
        await self.hass.async_add_executor_job(self._sync_turn_off, dict(kwargs))

    def _sync_turn_off(self, kwargs):
        """Set the brightness to 0"""

        try:
            self._pb.setBrightnessSlider(0.0, saveToFlash=True)
            self._last_brightness = self._brightness
            self.hass.add_job(self.async_write_ha_state)
        except Exception as e:  # pylint:disable=broad-except,invalid-name
            _LOGGER.error(
                f"Failed to turn_off pixelblaze device {self.id}@{self.host}: Exception: {e}"
            )

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug(f"async_turn_on for {self.id}")
        await self.hass.async_add_executor_job(self._sync_turn_on, dict(kwargs))

    def _sync_turn_on(self, kwargs):
        """Turn on (or adjust property of) the lights."""
        _LOGGER.debug(f"turn_on for {self.id}: {self._last_brightness} {kwargs}")

        try:
            if ATTR_BRIGHTNESS in kwargs:
                self._brightness = kwargs[ATTR_BRIGHTNESS]
                self._last_brightness = self._brightness
            else:
                self._brightness = self._last_brightness

            self._pb.setBrightnessSlider(self._brightness / 255, saveToFlash=True)

            if ATTR_EFFECT in kwargs:
                self._effect = kwargs[ATTR_EFFECT]
                if EFFECT_SEQUENCER == self._effect:
                    self._pb.setSequencerMode(Pixelblaze.sequencerModes.Playlist, saveToFlash=True)
                elif EFFECT_SHUFFLE == self._effect:
                    self._pb.setSequencerMode(Pixelblaze.sequencerModes.ShuffleAll, saveToFlash=True)
                else:
                    # Stop any sequencer and find the matching patternID to the name
                    self._pb.setSequencerMode(Pixelblaze.sequencerModes.Off, saveToFlash=True)
                    for pid, pname in self.patternlist.items():
                        if self._effect == pname:
                            self._pb.setActivePattern(pid, saveToFlash=True)
                            self.update_active_pattern(self._pb, pid)
                            break

            if ATTR_HS_COLOR in kwargs:
                # Only set the color if controls allow for it
                color_picker_key = self._pb.getColorControlName()
                if color_picker_key is not None:
                    self._color = kwargs[ATTR_HS_COLOR]
                    if color_picker_key.startswith(PB_ATTR_HSV):
                        hsv = (self._color[0] / 360, self._color[1] / 100, 1)
                        self._pb.setColorControl(color_picker_key, hsv, saveToFlash=True)
                    elif color_picker_key.startswith(PB_ATTR_RGB):
                        rgb = color_hs_to_RGB(*tuple(self._color))
                        self._pb.setColorControl(
                            color_picker_key,
                            (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255),
                            saveToFlash=True,
                        )
            self.hass.add_job(self.async_write_ha_state)
        except Exception as e:  # pylint:disable=broad-except,invalid-name
            _LOGGER.error(
                f"Failed to turn_on pixelblaze device {self.id}@{self.host}: Exception: {e}"
            )

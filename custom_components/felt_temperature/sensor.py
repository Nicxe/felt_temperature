import logging
import math
from collections.abc import Mapping
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.components.climate import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.weather import (
    ATTR_WEATHER_HUMIDITY,
    ATTR_WEATHER_TEMPERATURE,
    ATTR_WEATHER_TEMPERATURE_UNIT,
    ATTR_WEATHER_WIND_SPEED,
    ATTR_WEATHER_WIND_SPEED_UNIT,
    DOMAIN as WEATHER_DOMAIN,
)
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfSpeed,
    UnitOfTemperature,
    CONF_NAME,
    CONF_SOURCE,
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import (
    HomeAssistant,
    State,
    callback,
    split_entity_id,
    Event,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_call_later,
)
from homeassistant.core import CALLBACK_TYPE
from homeassistant.util.unit_conversion import SpeedConverter, TemperatureConverter

from .const import (
    ATTR_HUMIDITY_SOURCE,
    ATTR_HUMIDITY_SOURCE_VALUE,
    ATTR_TEMPERATURE_SOURCE,
    ATTR_TEMPERATURE_SOURCE_VALUE,
    ATTR_WIND_SPEED_SOURCE,
    ATTR_WIND_SPEED_SOURCE_VALUE,
    DOMAIN,
    DEFAULT_NAME,
    CONF_MODE,
    MODE_WEATHER,
    MODE_SEPARATE,
    CONF_TEMPERATURE_SOURCE,
    CONF_HUMIDITY_SOURCE,
    CONF_WIND_SOURCE,
)

_LOGGER = logging.getLogger(__name__)

RETRY_DELAY = 10  # Sekunder mellan försök om källorna inte är redo
INITIAL_DELAY = 15  # Sekunder att vänta efter HA start innan första uppdatering

_ONE_DECIMAL = Decimal("0.1")

async def async_setup_entry(
    hass: HomeAssistant, 
    entry: ConfigEntry, 
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Felt Temperature sensor entities from a config entry."""
    # Build sources list from new explicit options if available; fallback to legacy CONF_SOURCE list
    mode = entry.options.get(CONF_MODE, entry.data.get(CONF_MODE))
    sources: list[str] = []
    if mode == MODE_WEATHER:
        weather_entity = entry.options.get(CONF_TEMPERATURE_SOURCE, entry.data.get(CONF_TEMPERATURE_SOURCE))
        if weather_entity:
            sources = [weather_entity]
    elif mode == MODE_SEPARATE:
        temp_entity = entry.options.get(CONF_TEMPERATURE_SOURCE, entry.data.get(CONF_TEMPERATURE_SOURCE))
        hum_entity = entry.options.get(CONF_HUMIDITY_SOURCE, entry.data.get(CONF_HUMIDITY_SOURCE))
        wind_entity = entry.options.get(CONF_WIND_SOURCE, entry.data.get(CONF_WIND_SOURCE))
        for eid in [temp_entity, hum_entity, wind_entity]:
            if eid:
                sources.append(eid)
    else:
        sources = entry.options.get(CONF_SOURCE, entry.data.get(CONF_SOURCE, []))
    name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, DEFAULT_NAME))
    unique_id = f"{entry.entry_id}"

    async_add_entities([FeltTemperatureSensor(name, sources, unique_id)], True)


class FeltTemperatureSensor(SensorEntity):
    """Felt Temperature Sensor class using a simplified UTCI-like calculation."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer-lines"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, name: str | None, sources: list[str], unique_id: str) -> None:
        """Class initialization."""
        self._attr_name = name
        self._sources = sources
        self._attr_unique_id = unique_id

        self._temp = None
        self._humd = None
        self._wind = None
        self._temp_val = None
        self._humd_val = None
        self._wind_val = None
        self._retry_timer: CALLBACK_TYPE | None = None
        self._unsub_state_listener: CALLBACK_TYPE | None = None
        self._initial_update_done = False

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes."""
        return {
            ATTR_TEMPERATURE_SOURCE: self._temp,
            ATTR_TEMPERATURE_SOURCE_VALUE: self._temp_val,
            ATTR_HUMIDITY_SOURCE: self._humd,
            ATTR_HUMIDITY_SOURCE_VALUE: self._humd_val,
            ATTR_WIND_SPEED_SOURCE: self._wind,
            ATTR_WIND_SPEED_SOURCE_VALUE: self._wind_val,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for grouping the entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._attr_name or DEFAULT_NAME,
        )

    def _setup_sources(self) -> list[str]:
        """Set sources for entity and return list of sources to track."""
        _LOGGER.debug(
            "Running _setup_sources() to identify temperature, humidity and wind sources."
        )
        entities = set()

        # Nollställ inte redan hittade källor - men om vi upptäcker nya fuktighets-/vindkällor
        # kan vi sätta dem även om temp redan är funnen.
        
        for entity_id in self._sources:
            state: State = self.hass.states.get(entity_id)
            if not state:
                continue

            domain = split_entity_id(entity_id)[0]
            device_class = state.attributes.get(ATTR_DEVICE_CLASS)
            unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

            # Temperatur
            if (
                self._temp is None and (
                    domain == WEATHER_DOMAIN
                    or domain == CLIMATE_DOMAIN
                    or device_class == SensorDeviceClass.TEMPERATURE
                    or (unit_of_measurement in UnitOfTemperature if unit_of_measurement else False)
                    or ("temperature" in entity_id.lower())
                )
            ):
                self._temp = entity_id
                _LOGGER.debug("Found temperature source: %s", entity_id)

            # Fuktighet
            if (
                self._humd is None and (
                    domain == WEATHER_DOMAIN
                    or domain == CLIMATE_DOMAIN
                    or device_class == SensorDeviceClass.HUMIDITY
                    or (unit_of_measurement == PERCENTAGE)
                    or ("humidity" in entity_id.lower())
                )
            ):
                self._humd = entity_id
                _LOGGER.debug("Found humidity source: %s", entity_id)

            # Vind
            if (
                self._wind is None and (
                    domain == WEATHER_DOMAIN
                    or (device_class == SensorDeviceClass.WIND_SPEED)
                    or (unit_of_measurement in UnitOfSpeed if unit_of_measurement else False)
                    or ("wind" in entity_id.lower())
                )
            ):
                self._wind = entity_id
                _LOGGER.debug("Found wind source: %s", entity_id)

            entities.add(entity_id)

        return list(entities)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        @callback
        def sensor_state_listener(event) -> None:
            """Handle device state changes."""
            self.hass.add_job(self.async_schedule_update_ha_state, True)

        sources_to_watch = self._setup_sources()
        self._unsub_state_listener = async_track_state_change_event(
            self.hass, sources_to_watch, sensor_state_listener
        )

        # Vänta tills Home Assistant startat fullt innan första uppdateringen + en liten fördröjning
        @callback
        def delayed_initial_update(_):
            self.hass.add_job(self.async_schedule_update_ha_state, True)

        @callback
        def handle_ha_started(event: Event) -> None:
            async_call_later(self.hass, INITIAL_DELAY, delayed_initial_update)

        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, handle_ha_started)

    async def async_will_remove_from_hass(self) -> None:
        """Clean up when entity is removed from Home Assistant."""
        if self._unsub_state_listener is not None:
            self._unsub_state_listener()
            self._unsub_state_listener = None
        if self._retry_timer is not None:
            self._retry_timer()
            self._retry_timer = None

    @staticmethod
    def _has_state(state: str | None) -> bool:
        """Return True if state has any value."""
        return state not in [None, STATE_UNKNOWN, STATE_UNAVAILABLE, "None", ""]

    @staticmethod
    def _round_to_one_decimal(value: float | int | str | None) -> float | None:
        """Round to exactly one decimal to avoid float artifacts in state."""
        if value is None:
            return None
        try:
            d = Decimal(str(value)).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return None
        return float(d)

    def _get_temperature(self, entity_id: str | None) -> float | None:
        if entity_id is None:
            return None
        state: State = self.hass.states.get(entity_id)
        if state is None:
            return None
        domain = split_entity_id(state.entity_id)[0]
        if domain == WEATHER_DOMAIN:
            temperature = state.attributes.get(ATTR_WEATHER_TEMPERATURE)
            entity_unit = state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT)
        elif domain == CLIMATE_DOMAIN:
            temperature = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
            entity_unit = state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT) or UnitOfTemperature.CELSIUS
        else:
            temperature = state.state
            entity_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

        if not self._has_state(temperature):
            return None

        try:
            temperature = TemperatureConverter.convert(float(temperature), entity_unit, UnitOfTemperature.CELSIUS)
        except ValueError:
            _LOGGER.exception('Could not convert value "%s" to float', state)
            return None
        return float(temperature)

    def _get_humidity(self, entity_id: str | None) -> float | None:
        if entity_id is None:
            return None
        state: State = self.hass.states.get(entity_id)
        if state is None:
            return None
        domain = split_entity_id(state.entity_id)[0]
        if domain == WEATHER_DOMAIN:
            humidity = state.attributes.get(ATTR_WEATHER_HUMIDITY)
        elif domain == CLIMATE_DOMAIN:
            humidity = state.attributes.get(ATTR_CURRENT_HUMIDITY)
        else:
            humidity = state.state

        if not self._has_state(humidity):
            return None
        return float(humidity)

    def _get_wind_speed(self, entity_id: str | None) -> float | None:
        if entity_id is None:
            return 0.0
        state: State = self.hass.states.get(entity_id)
        if state is None:
            return 0.0
        domain = split_entity_id(state.entity_id)[0]
        if domain == WEATHER_DOMAIN:
            wind_speed = state.attributes.get(ATTR_WEATHER_WIND_SPEED)
            entity_unit = state.attributes.get(ATTR_WEATHER_WIND_SPEED_UNIT)
        else:
            wind_speed = state.state
            entity_unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

        if not self._has_state(wind_speed):
            return None

        try:
            wind_speed = SpeedConverter.convert(float(wind_speed), entity_unit, UnitOfSpeed.METERS_PER_SECOND)
        except ValueError:
            _LOGGER.exception('Could not convert value "%s" to float', state)
            return None
        return float(wind_speed)

    def _calculate_utci(self, ta: float, rh: float, va: float) -> float:
        """Calculate a simplified UTCI-like value."""
        e = 6.105 * math.exp((17.27 * ta) / (237.7 + ta)) * (rh / 100.0)
        utci_approx = ta + 0.33 * e - 0.70 * va - 4.00
        return utci_approx

    async def async_update(self) -> None:
        """Update sensor state."""
        temp = self._get_temperature(self._temp)
        humd = self._get_humidity(self._humd)
        wind = self._get_wind_speed(self._wind)

        # If humidity or wind is missing after startup, try _setup_sources() again
        if humd is None or (self._wind is not None and wind is None):
            _LOGGER.debug(
                "Humidity or wind missing, running _setup_sources again."
            )
            self._setup_sources()
            # Försök igen efter att ha kört _setup_sources
            temp = self._get_temperature(self._temp)
            humd = self._get_humidity(self._humd)
            wind = self._get_wind_speed(self._wind)

        self._temp_val = temp
        self._humd_val = humd
        self._wind_val = wind

        if temp is None or humd is None:
            _LOGGER.debug(
                "Sources not ready yet (temp: %s, humd: %s). Trying again in %s sec.",
                temp,
                humd,
                RETRY_DELAY,
            )
            self._attr_native_value = None

            if self._retry_timer is None:
                def retry_update(_):
                    self._retry_timer = None
                    self.hass.add_job(self.async_schedule_update_ha_state, True)

                self._retry_timer = async_call_later(self.hass, RETRY_DELAY, retry_update)
            return

        if wind is None:
            _LOGGER.warning(
                "Unable to get wind speed. Wind will be ignored in the calculation."
            )
            wind = 0.0

        if self._retry_timer is not None:
            self._retry_timer()  # Avbryter schemalagd retry
            self._retry_timer = None

        self._attr_native_value = self._round_to_one_decimal(
            self._calculate_utci(temp, humd, wind)
        )
        _LOGGER.debug(
            "New (approx) UTCI value is %s %s (temp: %s, humd: %s, wind: %s)",
            self._attr_native_value,
            self._attr_native_unit_of_measurement,
            temp,
            humd,
            wind,
        )

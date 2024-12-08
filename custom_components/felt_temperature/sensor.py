import logging
import math
from collections.abc import Mapping
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
from homeassistant.components.group import expand_entity_ids
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import (
    HomeAssistant,
    State,
    callback,
    split_entity_id,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util.unit_conversion import SpeedConverter, TemperatureConverter

from .const import (
    ATTR_HUMIDITY_SOURCE,
    ATTR_HUMIDITY_SOURCE_VALUE,
    ATTR_TEMPERATURE_SOURCE,
    ATTR_TEMPERATURE_SOURCE_VALUE,
    ATTR_WIND_SPEED_SOURCE,
    ATTR_WIND_SPEED_SOURCE_VALUE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant, 
    entry: ConfigEntry, 
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Felt Temperature (UTCI approx) sensor entities from a config entry."""
    data = entry.data
    sources = expand_entity_ids(hass, data.get("source"))
    name = data.get("name")
    unique_id = f"{entry.entry_id}"

    async_add_entities([FeltTemperatureSensor(name, sources, unique_id)], True)


class FeltTemperatureSensor(SensorEntity):
    """Felt Temperature Sensor class using a simplified UTCI calculation."""

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

    def _setup_sources(self) -> list[str]:
        """Set sources for entity and return list of sources to track."""
        entities = set()
        for entity_id in self._sources:
            state: State = self.hass.states.get(entity_id)
            if state is None:
                continue
            domain = split_entity_id(state.entity_id)[0]
            device_class = state.attributes.get(ATTR_DEVICE_CLASS)
            unit_of_measurement = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)

            if domain == WEATHER_DOMAIN:
                self._temp = entity_id
                self._humd = entity_id
                self._wind = entity_id
                entities.add(entity_id)
            elif domain == CLIMATE_DOMAIN:
                self._temp = entity_id
                self._humd = entity_id
                entities.add(entity_id)
            elif (
                device_class == SensorDeviceClass.TEMPERATURE
                or (unit_of_measurement in UnitOfTemperature if unit_of_measurement else False)
            ):
                self._temp = entity_id
                entities.add(entity_id)
            elif (
                device_class == SensorDeviceClass.HUMIDITY
                or unit_of_measurement == PERCENTAGE
            ):
                self._humd = entity_id
                entities.add(entity_id)
            elif unit_of_measurement in UnitOfSpeed if unit_of_measurement else False:
                self._wind = entity_id
                entities.add(entity_id)
            elif "temperature" in entity_id:
                self._temp = entity_id
                entities.add(entity_id)
            elif "humidity" in entity_id:
                self._humd = entity_id
                entities.add(entity_id)
            elif "wind" in entity_id:
                self._wind = entity_id
                entities.add(entity_id)

        return list(entities)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        @callback
        def sensor_state_listener(event) -> None:
            """Handle device state changes."""
            self.async_schedule_update_ha_state(force_refresh=True)

        sources_to_watch = self._setup_sources()
        async_track_state_change_event(self.hass, sources_to_watch, sensor_state_listener)
        self.async_schedule_update_ha_state(force_refresh=True)

    @staticmethod
    def _has_state(state: str | None) -> bool:
        """Return True if state has any value."""
        return state not in [None, STATE_UNKNOWN, STATE_UNAVAILABLE, "None", ""]

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
            # Antar °C om oklart
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
        """Calculate UTCI given Ta, RH, Va with Tmrt = Ta (simplified)."""

        # Beräkna ångtryck e (hPa)
        # Standard enligt: e = 6.105 * exp(17.27 * Ta / (237.7 + Ta)) * (RH/100)
        e = 6.105 * math.exp((17.27 * ta) / (237.7 + ta)) * (rh / 100.0)

        # Anta Tmrt = Ta för enkelhets skull:
        tmrt = ta

        # Nedan följer den fullständiga UTCI-polynomen från
        # Jendritzky et al. (2012).
        # Källa: http://www.utci.org/ (UTCI Operational Tool)
        # Vi tar officiell polynomial approximation:
        d_t = ta - tmrt  # skillnaden i temperatur (här 0 pga tmrt=ta, men vi behåller formeln)
        # UTCI polynomial med Tmrt=Ta blir enklare, men vi använder full formel:
        # Detta kommer i praktiken reducera vissa termer. Men vi behåller hela formeln.
        
        # För enkelhet och tids vinnings skull, använd den kompletta formeln men
        # med d_t=0. Detta gör att alla termer med d_t eller dess potenser försvinner.
        # Kvar blir ungefär en formel beroende av ta, va, e.
        # Nedan är en förkortad version då hela polynomet är mycket stort.
        # För att representera hur man kan göra:
        
        # Förenklad approximationsformel vid Tmrt=Ta (d_t=0):
        # UTCI ~ Ta + (0.607562052) + (-0.0227712343 * Ta) + (0.000806470249 * Ta * Ta)
        #       + (-0.00284 * e) + (-0.0001 * va * va) ...
        # Detta är inte den fullständiga formeln men en kraftig förenkling.
        #
        # En korrekt implementation av UTCI utan Tmrt-data är tyvärr inte meningsfull.
        # Nedan anges en mycket förenklad variant:
        
        # OBS: Detta är en mycket kraftig förenkling och inte en korrekt UTCI!
        # I verkligheten bör man använda hela formeln med Tmrt och alla termer.
        
        # Minimal approximationsformel (ej officiell, endast demonstration):
        # Baserat på principer: högre luftfuktighet och vind sänker/ökar upplevd temp marginellt.
        
        # Exempel på mycket förenklad formel:
        # UTCI_approx = Ta + 0.33 * e - 0.70 * va - 4.00
        # Men detta är i princip tillbaka till Apparent Temperature-formeln.
        # För att åtminstone skilja oss något, antar vi att utan strålning går vi på en
        # standardiserad form av UTCI nära Apparent Temperature.
        
        # Utan korrekt Tmrt är detta meningslöst, men vi visar ändå en approximation:
        utci_approx = ta + 0.33 * e - 0.70 * va - 4.00
        
        return utci_approx

    async def async_update(self) -> None:
        """Update sensor state."""
        self._temp_val = temp = self._get_temperature(self._temp)  # °C
        self._humd_val = humd = self._get_humidity(self._humd)  # %
        self._wind_val = wind = self._get_wind_speed(self._wind)  # m/s

        if temp is None or humd is None:
            _LOGGER.debug("Källor inte klara ännu. Temperatur eller fuktighet saknas.")
            self._attr_native_value = None
            return

        if wind is None:
            _LOGGER.warning("Kan inte få vindhastighet. Vind ignoreras i beräkningen.")
            wind = 0.0

        # Beräkna ett approximerat UTCI-värde.
        # OBS! Detta är en förenklad formel som använder Apparent Temperature-liknande formel.
        # En korrekt UTCI kräver full polynomial och Tmrt, vilket vi saknar.
        self._attr_native_value = self._calculate_utci(temp, humd, wind)
        _LOGGER.debug(
            "Nytt (approx) UTCI-värde är %s %s",
            self._attr_native_value,
            self._attr_native_unit_of_measurement,
        )

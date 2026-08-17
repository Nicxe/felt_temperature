"""Regression tests for issue 37."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.felt_temperature.const import (
    CONF_HUMIDITY_SOURCE,
    CONF_MODE,
    CONF_TEMPERATURE_SOURCE,
    CONF_WIND_SOURCE,
    DOMAIN,
    MODE_SEPARATE,
)

TEMPERATURE_SOURCE = "sensor.living_room_temperature"
HUMIDITY_SOURCE = "sensor.living_room_humidity"


def _entry(*, wind_source: str | None = None) -> MockConfigEntry:
    """Return a separate-source config entry."""
    data = {
        CONF_NAME: "Living room",
        CONF_MODE: MODE_SEPARATE,
        CONF_TEMPERATURE_SOURCE: TEMPERATURE_SOURCE,
        CONF_HUMIDITY_SOURCE: HUMIDITY_SOURCE,
    }
    if wind_source is not None:
        data[CONF_WIND_SOURCE] = wind_source
    return MockConfigEntry(domain=DOMAIN, title="Living room", data=data, version=2)


async def test_options_flow_accepts_missing_optional_wind_source(hass) -> None:
    """Saving separate sources without wind must not validate None as an entity."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_NAME: "Living room", CONF_MODE: MODE_SEPARATE},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "separate"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TEMPERATURE_SOURCE: TEMPERATURE_SOURCE,
            CONF_HUMIDITY_SOURCE: HUMIDITY_SOURCE,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_WIND_SOURCE] is None


async def test_late_sources_are_tracked_after_setup(hass) -> None:
    """Sources added after setup must trigger current and future updates."""
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, entry.entry_id)
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unknown"

    hass.states.async_set(
        TEMPERATURE_SOURCE,
        "20",
        {
            ATTR_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
            ATTR_UNIT_OF_MEASUREMENT: UnitOfTemperature.CELSIUS,
        },
    )
    hass.states.async_set(
        HUMIDITY_SOURCE,
        "50",
        {
            ATTR_DEVICE_CLASS: SensorDeviceClass.HUMIDITY,
            ATTR_UNIT_OF_MEASUREMENT: PERCENTAGE,
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "19.8"

    hass.states.async_set(
        TEMPERATURE_SOURCE,
        "25",
        {
            ATTR_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
            ATTR_UNIT_OF_MEASUREMENT: UnitOfTemperature.CELSIUS,
        },
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "26.2"

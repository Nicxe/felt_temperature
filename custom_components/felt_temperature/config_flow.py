from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_SOURCE
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_MODE,
    MODE_WEATHER,
    MODE_SEPARATE,
    CONF_TEMPERATURE_SOURCE,
    CONF_HUMIDITY_SOURCE,
    CONF_WIND_SOURCE,
)


class FeltTemperatureFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._data: dict = {}
        self._reconfig: bool = False
        self._reconfig_entry_id: str | None = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Store name and mode, then go to respective step
            self._data[CONF_NAME] = user_input.get(CONF_NAME, DEFAULT_NAME)
            mode = user_input.get(CONF_MODE, MODE_WEATHER)
            self._data[CONF_MODE] = mode
            if mode == MODE_WEATHER:
                return await self.async_step_weather()
            return await self.async_step_separate()

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Required(CONF_MODE, default=MODE_WEATHER): selector({
                    "select": {
                        "options": [MODE_WEATHER, MODE_SEPARATE]
                    }
                }),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_weather(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SOURCE):
                errors["base"] = "missing_weather"
            else:
                data = {
                    **self._data,
                    CONF_TEMPERATURE_SOURCE: user_input[CONF_TEMPERATURE_SOURCE],
                }
                return self.async_create_entry(
                    title=data.get(CONF_NAME, DEFAULT_NAME),
                    data=data,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SOURCE): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["weather"]},
                    }
                }),
            }
        )

        return self.async_show_form(step_id="weather", data_schema=schema, errors=errors)

    async def async_step_separate(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SOURCE):
                errors["base"] = "missing_temperature"
            elif not user_input.get(CONF_HUMIDITY_SOURCE):
                errors["base"] = "missing_humidity"
            else:
                data = {**self._data, **user_input}
                return self.async_create_entry(
                    title=data.get(CONF_NAME, DEFAULT_NAME),
                    data=data,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SOURCE): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["sensor", "climate", "weather"]},
                    }
                }),
                vol.Required(CONF_HUMIDITY_SOURCE): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["sensor", "climate", "weather"]},
                    }
                }),
                vol.Optional(CONF_WIND_SOURCE): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["sensor", "weather"]},
                    }
                }),
            }
        )

        return self.async_show_form(step_id="separate", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return FeltTemperatureOptionsFlowHandler(config_entry.entry_id)

    async def async_step_reconfigure(self, user_input=None):
        """Entry point for reconfigure flow."""
        errors = {}
        self._reconfig = True
        self._reconfig_entry_id = self.context.get("entry_id")
        config_entry = None
        if self._reconfig_entry_id:
            config_entry = self.hass.config_entries.async_get_entry(self._reconfig_entry_id)

        current_name = (config_entry.options.get(CONF_NAME)
                        if config_entry else None) or (config_entry.data.get(CONF_NAME) if config_entry else None) or DEFAULT_NAME
        current_mode = (config_entry.options.get(CONF_MODE)
                        if config_entry else None) or (config_entry.data.get(CONF_MODE) if config_entry else None) or MODE_WEATHER

        if user_input is not None:
            self._data[CONF_NAME] = user_input.get(CONF_NAME, current_name)
            mode = user_input.get(CONF_MODE, current_mode)
            self._data[CONF_MODE] = mode
            if mode == MODE_WEATHER:
                return await self.async_step_reconfigure_weather()
            return await self.async_step_reconfigure_separate()

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=current_name): cv.string,
                vol.Required(CONF_MODE, default=current_mode): selector({
                    "select": {
                        "options": [MODE_WEATHER, MODE_SEPARATE]
                    }
                }),
            }
        )

        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def async_step_reconfigure_weather(self, user_input=None):
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._reconfig_entry_id) if self._reconfig_entry_id else None
        current = None
        if config_entry:
            current = config_entry.data.get(CONF_TEMPERATURE_SOURCE) or config_entry.options.get(CONF_TEMPERATURE_SOURCE)

        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SOURCE):
                errors["base"] = "missing_weather"
            else:
                # Update entry data and reload
                new_data = {
                    **(config_entry.data if config_entry else {}),
                    **self._data,
                    CONF_TEMPERATURE_SOURCE: user_input[CONF_TEMPERATURE_SOURCE],
                }
                if config_entry:
                    self.hass.config_entries.async_update_entry(config_entry, data=new_data)
                    await self.hass.config_entries.async_reload(config_entry.entry_id)
                return self.async_abort(reason="reconfigured")

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SOURCE, default=current): selector({
                    "entity": {"multiple": False, "filter": {"domain": ["weather"]}}
                }),
            }
        )
        return self.async_show_form(step_id="weather", data_schema=schema, errors=errors)

    async def async_step_reconfigure_separate(self, user_input=None):
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._reconfig_entry_id) if self._reconfig_entry_id else None
        current_temp = current_hum = current_wind = None
        if config_entry:
            current_temp = config_entry.data.get(CONF_TEMPERATURE_SOURCE) or config_entry.options.get(CONF_TEMPERATURE_SOURCE)
            current_hum = config_entry.data.get(CONF_HUMIDITY_SOURCE) or config_entry.options.get(CONF_HUMIDITY_SOURCE)
            current_wind = config_entry.data.get(CONF_WIND_SOURCE) or config_entry.options.get(CONF_WIND_SOURCE)

        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SOURCE):
                errors["base"] = "missing_temperature"
            elif not user_input.get(CONF_HUMIDITY_SOURCE):
                errors["base"] = "missing_humidity"
            else:
                new_data = {
                    **(config_entry.data if config_entry else {}),
                    **self._data,
                    **user_input,
                }
                if config_entry:
                    self.hass.config_entries.async_update_entry(config_entry, data=new_data)
                    await self.hass.config_entries.async_reload(config_entry.entry_id)
                return self.async_abort(reason="reconfigured")

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SOURCE, default=current_temp): selector({
                    "entity": {"multiple": False, "filter": {"domain": ["sensor", "climate", "weather"]}}
                }),
                vol.Required(CONF_HUMIDITY_SOURCE, default=current_hum): selector({
                    "entity": {"multiple": False, "filter": {"domain": ["sensor", "climate", "weather"]}}
                }),
                vol.Optional(CONF_WIND_SOURCE, default=current_wind): selector({
                    "entity": {"multiple": False, "filter": {"domain": ["sensor", "weather"]}}
                }),
            }
        )
        return self.async_show_form(step_id="separate", data_schema=schema, errors=errors)


class FeltTemperatureOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Felt Temperature options."""

    def __init__(self, entry_id: str):
        """Initialize Felt Temperature options flow."""
        self._entry_id = entry_id
        self._data: dict = {}

    async def async_step_init(self, user_input=None):
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._entry_id)

        # Get current values with fallbacks
        current_name = config_entry.options.get(
            CONF_NAME, config_entry.data.get(CONF_NAME, DEFAULT_NAME)
        )
        current_mode = config_entry.options.get(
            CONF_MODE, config_entry.data.get(CONF_MODE, MODE_WEATHER)
        )

        if user_input is not None:
            self._data[CONF_NAME] = user_input.get(CONF_NAME, current_name)
            mode = user_input.get(CONF_MODE, current_mode)
            self._data[CONF_MODE] = mode
            if mode == MODE_WEATHER:
                return await self.async_step_weather()
            return await self.async_step_separate()

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=current_name): cv.string,
                vol.Required(CONF_MODE, default=current_mode): selector({
                    "select": {
                        "options": [MODE_WEATHER, MODE_SEPARATE]
                    }
                }),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def async_step_weather(self, user_input=None):
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._entry_id)
        current = config_entry.options.get(
            CONF_TEMPERATURE_SOURCE,
            config_entry.data.get(CONF_TEMPERATURE_SOURCE),
        )
        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SOURCE):
                errors["base"] = "missing_weather"
            else:
                return self.async_create_entry(title="", data={**self._data, **user_input})

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SOURCE, default=current): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["weather"]},
                    }
                }),
            }
        )
        return self.async_show_form(step_id="weather", data_schema=schema, errors=errors)

    async def async_step_separate(self, user_input=None):
        errors = {}
        config_entry = self.hass.config_entries.async_get_entry(self._entry_id)
        current_temp = config_entry.options.get(
            CONF_TEMPERATURE_SOURCE,
            config_entry.data.get(CONF_TEMPERATURE_SOURCE),
        )
        current_hum = config_entry.options.get(
            CONF_HUMIDITY_SOURCE,
            config_entry.data.get(CONF_HUMIDITY_SOURCE),
        )
        current_wind = config_entry.options.get(
            CONF_WIND_SOURCE,
            config_entry.data.get(CONF_WIND_SOURCE),
        )

        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SOURCE):
                errors["base"] = "missing_temperature"
            elif not user_input.get(CONF_HUMIDITY_SOURCE):
                errors["base"] = "missing_humidity"
            else:
                return self.async_create_entry(title="", data={**self._data, **user_input})

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SOURCE, default=current_temp): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["sensor", "climate", "weather"]},
                    }
                }),
                vol.Required(CONF_HUMIDITY_SOURCE, default=current_hum): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["sensor", "climate", "weather"]},
                    }
                }),
                vol.Optional(CONF_WIND_SOURCE, default=current_wind): selector({
                    "entity": {
                        "multiple": False,
                        "filter": {"domain": ["sensor", "weather"]},
                    }
                }),
            }
        )
        return self.async_show_form(step_id="separate", data_schema=schema, errors=errors)

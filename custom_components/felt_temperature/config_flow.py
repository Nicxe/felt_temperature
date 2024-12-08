from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_SOURCE
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import selector

from .const import DOMAIN, DEFAULT_NAME

class FeltTemperatureFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input.get(CONF_SOURCE):
                errors["base"] = "no_source"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data=user_input
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Required(CONF_SOURCE): selector({
                    "entity": {
                        "multiple": True,
                        "filter": {
                            "domain": ["sensor", "climate", "weather"]
                        }
                    }
                }),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return FeltTemperatureOptionsFlowHandler(config_entry)


class FeltTemperatureOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle Felt Temperature options."""

    def __init__(self, config_entry):
        """Initialize Felt Temperature options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_source = self.config_entry.options.get(
            CONF_SOURCE, self.config_entry.data.get(CONF_SOURCE, [])
        )
        current_name = self.config_entry.options.get(
            CONF_NAME, self.config_entry.data.get(CONF_NAME, DEFAULT_NAME)
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=current_name): cv.string,
                vol.Required(CONF_SOURCE, default=current_source): selector({
                    "entity": {
                        "multiple": True,
                        "filter": {
                            "domain": ["sensor", "climate", "weather"]
                        }
                    }
                }),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

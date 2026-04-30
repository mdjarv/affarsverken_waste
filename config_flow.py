"""Config flow for Affärsverken Waste Collection."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.storage import Store

from .api import AffarsverkenWasteApiClient, ApiError, AuthError
from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS): str,
        vol.Optional(CONF_NAME): str,
    }
)


def _normalize_address(address: str) -> str:
    return " ".join(address.split()).lower()


class AffarsverkenWasteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Affärsverken Waste Collection."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip()
            name = user_input.get(CONF_NAME, address).strip()
            user_input[CONF_ADDRESS] = address
            user_input[CONF_NAME] = name

            await self.async_set_unique_id(
                f"{DOMAIN}_{_normalize_address(address).replace(' ', '_')}"
            )
            self._abort_if_unique_id_configured()

            store = Store(self.hass, STORAGE_VERSION, f"{DOMAIN}.validate")
            client = AffarsverkenWasteApiClient(self.hass, store)
            try:
                await client.async_validate(address)
            except AuthError:
                errors["base"] = "invalid_auth"
            except ApiError as err:
                _LOGGER.warning("Validation failed for %s: %s", address, err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating address")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"{name} Waste Collection",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

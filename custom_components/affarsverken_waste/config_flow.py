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
from .helpers import normalize_address

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ADDRESS): str,
        vol.Optional(CONF_NAME): str,
    }
)


class AffarsverkenWasteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Affärsverken Waste Collection."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self._show_form()

        address = user_input[CONF_ADDRESS].strip()
        name = (user_input.get(CONF_NAME) or address).strip()

        await self.async_set_unique_id(self._unique_id_for(address))
        self._abort_if_unique_id_configured()

        error = await self._validate_address(address)
        if error is not None:
            return self._show_form(errors={"base": error})

        return self.async_create_entry(
            title=f"{name} Waste Collection",
            data={CONF_ADDRESS: address, CONF_NAME: name},
        )

    async def _validate_address(self, address: str) -> str | None:
        """Return an error key, or None on success."""
        store = Store(self.hass, STORAGE_VERSION, f"{DOMAIN}.validate")
        client = AffarsverkenWasteApiClient(self.hass, store)
        try:
            await client.async_validate(address)
        except AuthError:
            return "invalid_auth"
        except ApiError as err:
            _LOGGER.warning("Validation failed for %s: %s", address, err)
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error validating address")
            return "unknown"
        finally:
            await store.async_remove()
        return None

    def _show_form(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors or {},
        )

    @staticmethod
    def _unique_id_for(address: str) -> str:
        return f"{DOMAIN}_{normalize_address(address).replace(' ', '_')}"

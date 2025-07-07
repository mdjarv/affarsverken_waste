import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback

from . import DOMAIN # Import the domain from __init__.py

class AffarsverkenWasteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Affärsverken Waste Collection."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Here, you would typically validate the user_input against the API
            # For this simple example, we'll assume it's valid for now.
            
            address = user_input[CONF_ADDRESS]
            name = user_input.get(CONF_NAME, address) # Default name to address if not provided

            # Create a unique ID for this config entry.
            # This is important for linking the config entry to its device.
            unique_id = f"{DOMAIN}_{address.replace(' ', '_').lower()}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured() # Prevent duplicate entries for the same address

            return self.async_create_entry(
                title=f"{name} Waste Collection", # Title for the integration instance
                data=user_input, # Store the address and name in the config entry
            )

        # Show the form to the user
        data_schema = vol.Schema({
            vol.Required(CONF_ADDRESS): str,
            vol.Optional(CONF_NAME): str,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )



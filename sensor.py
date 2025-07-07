import logging
import json
import os
import urllib.parse
from datetime import datetime, timedelta, UTC

import requests
import jwt

# Import SensorDeviceClass
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.config_entries import ConfigEntry

# Home Assistant specific imports for error handling
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

# Import the DOMAIN constant from the integration's __init__.py
from . import DOMAIN

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

# --- Logging ---
_LOGGER = logging.getLogger(__name__)

# --- Configuration Constants ---
BASE_API_PATH = "https://kundapi.affarsverken.se/api/v1/open-api"
LOGIN_API_URL = f"{BASE_API_PATH}/login?BrandName=Affarsverken"
WASTE_COLLECTION_BASE_API_URL = f"{BASE_API_PATH}/waste/buildings/"
BUILDING_SEARCH_API_URL = f"{BASE_API_PATH}/waste/buildings/search"

# --- Cache Configuration ---
CONFIG_FILE = "affarsverken_config.json"
BUILDING_CACHE_LIFETIME = timedelta(days=30)

# --- Sensor Update Interval ---
SCAN_INTERVAL = timedelta(hours=12)

# --- Platform Schema for configuration.yaml ---
# This schema is primarily for YAML configuration.
# For config_flow, the validation happens in config_flow.py.
# We keep it here for completeness or if YAML setup were still supported.
PLATFORM_SCHEMA = vol.Schema({
    vol.Required("addresses"): vol.All(
        cv.ensure_list,
        [
            vol.Schema({
                vol.Required(CONF_ADDRESS): cv.string,
                vol.Optional(CONF_NAME): cv.string, # Name for this specific address entry
            })
        ]
    ),
}, extra=vol.ALLOW_EXTRA)

# --- Helper Functions for Cache Management ---
def _get_cache_file_path(hass: HomeAssistant) -> str:
    """Returns the full path to the cache file within Home Assistant's config directory."""
    return hass.config.path(CONFIG_FILE)

def _load_cache_data(hass: HomeAssistant) -> dict:
    """Loads the entire cache data from a file."""
    cache_file_path = _get_cache_file_path(hass)
    if not os.path.exists(cache_file_path):
        return {}

    try:
        with open(cache_file_path, 'r') as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        _LOGGER.warning(f"Error loading cache file '{cache_file_path}': {e}. Cache will be ignored.")
        return {}

def _save_cache_data(hass: HomeAssistant, data: dict):
    """Saves the entire cache data to a file."""
    cache_file_path = _get_cache_file_path(hass)
    try:
        with open(cache_file_path, 'w') as f:
            json.dump(data, f, indent=2)
        _LOGGER.debug(f"Cache saved to {cache_file_path}")
    except IOError as e:
        _LOGGER.error(f"Error saving cache file '{cache_file_path}': {e}. Cache will not be persisted.")

# --- API Client Class ---
class AffarsverkenWasteApiClient:
    """Handles communication with the Affärsverken API and manages caching."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the API client."""
        self.hass = hass
        self._auth_token = None
        self._token_expiration_time = None

    def _get_auth_token(self) -> str | None:
        """
        Obtains an authentication token from the login API, using persistent caching.
        The token is cached and reused until its expiration time.
        """
        cache_data = _load_cache_data(self.hass)
        cached_token = cache_data.get("token")
        expiration_str = cache_data.get("token_expiration_time")

        token_expiration_time = None
        if expiration_str:
            token_expiration_time = datetime.fromisoformat(expiration_str)
            if token_expiration_time.tzinfo is None:
                token_expiration_time = token_expiration_time.replace(tzinfo=UTC)

        if cached_token and token_expiration_time and datetime.now(UTC) < token_expiration_time:
            _LOGGER.debug("Using cached authentication token from file.")
            self._auth_token = cached_token
            self._token_expiration_time = token_expiration_time
            return cached_token

        _LOGGER.info("Cached token is expired or not available. Attempting to get a new authentication token...")
        try:
            response = requests.post(LOGIN_API_URL)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Error during authentication: {e}")
            try:
                error_details = e.response.json()
                _LOGGER.error(f"API Error Details: {json.dumps(error_details, indent=2)}")
            except (AttributeError, json.JSONDecodeError):
                _LOGGER.error(f"Raw response content on error: {e.response.text if e.response else 'No response content'}")
            return None

        token = response.text.strip()
        if not token:
            _LOGGER.error("Login successful, but no token found in plain text response.")
            _LOGGER.error(f"Full login response (text): {response.text}")
            return None

        new_token_expiration_time = None
        try:
            decoded_token = jwt.decode(token, options={"verify_signature": False})
            if "exp" in decoded_token:
                new_token_expiration_time = datetime.fromtimestamp(decoded_token["exp"], tz=UTC)
                new_token_expiration_time -= timedelta(minutes=5)
                _LOGGER.info(f"New token obtained. Expires UTC: {new_token_expiration_time.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                new_token_expiration_time = datetime.now(UTC) + timedelta(hours=1)
                _LOGGER.warning(f"New token obtained, but 'exp' claim not found. Assuming 1 hour validity. Expires UTC: {new_token_expiration_time.strftime('%Y-%m-%d %H:%M:%S')}")

        except jwt.DecodeError as e:
            _LOGGER.warning(f"Could not decode JWT to get expiration time: {e}. Assuming 1 hour validity.")
            new_token_expiration_time = datetime.now(UTC) + timedelta(hours=1)
        except Exception as e:
            _LOGGER.warning(f"Unexpected error when processing token: {e}. Assuming 1 hour validity.")
            new_token_expiration_time = datetime.now(UTC) + timedelta(hours=1)

        if new_token_expiration_time:
            cache_data["token"] = token
            cache_data["token_expiration_time"] = new_token_expiration_time.isoformat()
            _save_cache_data(self.hass, cache_data)
        
        self._auth_token = token
        self._token_expiration_time = new_token_expiration_time
        _LOGGER.debug("Successfully obtained and cached authentication token.")
        return token

    def search_building_id(self, address: str) -> str | None:
        """
        Searches for building information based on an address and returns the 'query' string.
        Uses cache for building information.
        """
        auth_token = self._get_auth_token()
        if not auth_token:
            _LOGGER.error("Authentication token not available for building search.")
            return None

        cache_data = _load_cache_data(self.hass)
        buildings_cache = cache_data.get("buildings", {})
        cached_building_info = buildings_cache.get(address)

        if cached_building_info:
            last_updated_str = cached_building_info.get("last_updated")
            query_param = cached_building_info.get("query_param")
            if last_updated_str and query_param:
                last_updated = datetime.fromisoformat(last_updated_str)
                if last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=UTC)
                if datetime.now(UTC) - last_updated < BUILDING_CACHE_LIFETIME:
                    _LOGGER.debug(f"Using cached building info for address '{address}'.")
                    return query_param

        _LOGGER.info(f"Cached building info for '{address}' is expired or not available. Attempting to search...")

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/json"
        }
        encoded_address = urllib.parse.quote_plus(address)
        full_search_url = f"{BUILDING_SEARCH_API_URL}?address={encoded_address}&_={int(datetime.now().timestamp() * 1000)}"

        _LOGGER.debug(f"Attempting to search for building ID with address: '{address}'")
        _LOGGER.debug(f"Search URL: {full_search_url}")

        try:
            response = requests.get(full_search_url, headers=headers)
            response.raise_for_status()
            search_results = response.json()

            if not search_results or not isinstance(search_results, list):
                _LOGGER.warning("Building search returned no results or unexpected format.")
                return None

            first_result = search_results[0]
            query_param = first_result.get("query")

            if not query_param:
                _LOGGER.warning(f"'query' parameter not found in search result: {first_result}")
                return None

            buildings_cache[address] = {
                "query_param": query_param,
                "last_updated": datetime.now(UTC).isoformat()
            }
            cache_data["buildings"] = buildings_cache
            _save_cache_data(self.hass, cache_data)
            
            _LOGGER.debug(f"Successfully found and cached building query parameter for '{address}': {query_param}")
            return query_param

        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Error during building search: {e}")
            try:
                error_details = e.response.json()
                _LOGGER.error(f"API Error Details: {json.dumps(error_details, indent=2)}")
            except (AttributeError, json.JSONDecodeError):
                _LOGGER.error(f"Raw response content on error: {e.response.text if e.response else 'No response content'}")
            return None

    def get_waste_data(self, address: str) -> dict | None:
        """
        Fetches waste collection data for a given address.
        """
        auth_token = self._get_auth_token()
        if not auth_token:
            _LOGGER.error("Authentication token not available for waste data fetch.")
            return None
        
        query_param = self.search_building_id(address)
        if not query_param:
            _LOGGER.error(f"Could not get building query parameter for address: {address}")
            return None

        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/json"
        }
        full_waste_api_url = f"{WASTE_COLLECTION_BASE_API_URL}{query_param}?_={int(datetime.now().timestamp() * 1000)}"

        _LOGGER.debug(f"Attempting to fetch waste data from: {full_waste_api_url}")
        _LOGGER.debug(f"Using Authorization header: {headers['Authorization']}")

        try:
            response = requests.get(full_waste_api_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _LOGGER.error(f"Error fetching waste data: {e}")
            try:
                error_details = e.response.json()
                _LOGGER.error(f"API Error Details: {json.dumps(error_details, indent=2)}")
            except (AttributeError, json.JSONDecodeError):
                _LOGGER.error(f"Raw response content on error: {e.response.text if e.response else 'No response content'}")
            return None

    def parse_collection_dates(self, data: dict) -> dict:
        """
        Parses the raw JSON response to extract relevant waste collection dates.
        """
        collection_dates = {}
        if not isinstance(data.get("services"), list):
            _LOGGER.warning("Warning: 'services' key not found or is not a list in the response data.")
            return collection_dates

        for service in data["services"]:
            title = service.get("title")
            next_pickup_str = service.get("nextPickup")

            if not (title and next_pickup_str):
                _LOGGER.warning(f"Missing 'title' or 'nextPickup' in service item: {service}. Skipping.")
                continue

            if not next_pickup_str:
                _LOGGER.info(f"No 'nextPickup' date provided for '{title}'. Skipping.")
                continue

            try:
                collection_date = datetime.strptime(next_pickup_str, "%Y-%m-%d").date()
                collection_dates[title] = collection_date
            except ValueError:
                _LOGGER.warning(f"Could not parse date '{next_pickup_str}' for type '{title}'. Skipping.")
        return collection_dates

# --- Home Assistant Sensor Setup ---
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Affärsverken Waste sensor platform from a config entry."""
    address = config_entry.data[CONF_ADDRESS]
    name = config_entry.data.get(CONF_NAME, address)

    _LOGGER.debug(f"Setting up Affärsverken Waste sensor for address: {address}")

    api_client = AffarsverkenWasteApiClient(hass)

    async def async_update_data_for_address(target_address: str = address):
        """Fetch data from API for a specific address. This is the place to handle retries and exceptions."""
        try:
            waste_data = await hass.async_add_executor_job(api_client.get_waste_data, target_address)
            if not waste_data:
                raise UpdateFailed(f"Failed to fetch waste data for {target_address}.")
            
            parsed_dates = api_client.parse_collection_dates(waste_data)
            if not parsed_dates:
                raise UpdateFailed(f"No waste collection dates parsed from data for {target_address}.")
            
            return {"parsed_dates": parsed_dates, "raw_data": waste_data}
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API for {target_address}: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"Affärsverken Waste for {address}",
        update_method=async_update_data_for_address,
        update_interval=SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()

    entities = []
    for waste_type in coordinator.data["parsed_dates"].keys():
        entities.append(AffarsverkenWasteSensor(name, address, waste_type, coordinator))
    
    add_entities(entities)

# --- Home Assistant Sensor Class ---
class AffarsverkenWasteSensor(SensorEntity):
    """Representation of an Affärsverken Waste Collection sensor."""

    def __init__(self, base_name: str, address: str, waste_type: str, coordinator: DataUpdateCoordinator):
        """Initialize the sensor."""
        self._base_name = base_name
        self._address = address
        self._waste_type = waste_type
        self.coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{self._base_name.replace(' ', '_').lower()}_{self._address.replace(' ', '_').lower()}_{self._waste_type.replace(' ', '_').lower()}"
        
        # Set device class to DATE for better representation in Home Assistant
        self._attr_device_class = SensorDeviceClass.DATE
        # No specific state class needed for a date sensor
        self._attr_icon = "mdi:trash-can" # Fallback icon if device class doesn't provide one

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._base_name} {self._waste_type}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this sensor."""
        return self._attr_unique_id

    @property
    def native_value(self):
        """Return the state of the sensor."""
        parsed_dates = self.coordinator.data["parsed_dates"]
        if self._waste_type in parsed_dates:
            # Return the datetime.date object directly
            return parsed_dates[self._waste_type]
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = {}
        parsed_dates = self.coordinator.data["parsed_dates"]
        raw_data = self.coordinator.data["raw_data"]

        if self._waste_type in parsed_dates:
            collection_date = parsed_dates[self._waste_type]
            today = datetime.now().date()
            days_until_pickup = (collection_date - today).days
            
            attributes["days_until_pickup"] = days_until_pickup
            # Keep pickup_date as a string in attributes if desired for display
            attributes["pickup_date"] = collection_date.strftime("%Y-%m-%d")
            attributes["waste_type"] = self._waste_type
            
            for service in raw_data.get("services", []):
                if service.get("title") == self._waste_type:
                    attributes["bin_size"] = service.get("binSize")
                    attributes["bin_size_unit"] = service.get("binSizeUnit")
                    attributes["pickup_frequency_description"] = service.get("pickupFrequencyDescription")
                    break

        return attributes

    @property
    def device_info(self):
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self._address)},
            "name": f"{self._base_name} Waste",
            "manufacturer": "Affärsverken",
            "model": "Waste Collection",
        }

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))



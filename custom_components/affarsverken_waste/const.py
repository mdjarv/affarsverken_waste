"""Constants for the Affärsverken Waste Collection integration."""

from datetime import timedelta

DOMAIN = "affarsverken_waste"

# API endpoints
BASE_API_PATH = "https://kundapi.affarsverken.se/api/v1/open-api"
LOGIN_API_URL = f"{BASE_API_PATH}/login?BrandName=Affarsverken"
WASTE_COLLECTION_BASE_API_URL = f"{BASE_API_PATH}/waste/buildings/"
BUILDING_SEARCH_API_URL = f"{BASE_API_PATH}/waste/buildings/search"

# HTTP / auth
REQUEST_TIMEOUT = 30
TOKEN_EXPIRY_SAFETY = timedelta(minutes=5)
TOKEN_FALLBACK_LIFETIME = timedelta(hours=1)

# Cache
BUILDING_CACHE_LIFETIME = timedelta(days=30)
STORAGE_VERSION = 1
CACHE_KEY_TOKEN = "token"
CACHE_KEY_TOKEN_EXPIRY = "token_expiration_time"
CACHE_KEY_BUILDINGS = "buildings"

# Polling
SCAN_INTERVAL = timedelta(hours=12)

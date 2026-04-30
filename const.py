"""Constants for the Affärsverken Waste Collection integration."""
from datetime import timedelta

DOMAIN = "affarsverken_waste"

BASE_API_PATH = "https://kundapi.affarsverken.se/api/v1/open-api"
LOGIN_API_URL = f"{BASE_API_PATH}/login?BrandName=Affarsverken"
WASTE_COLLECTION_BASE_API_URL = f"{BASE_API_PATH}/waste/buildings/"
BUILDING_SEARCH_API_URL = f"{BASE_API_PATH}/waste/buildings/search"

REQUEST_TIMEOUT = 30
TOKEN_EXPIRY_SAFETY = timedelta(minutes=5)
TOKEN_FALLBACK_LIFETIME = timedelta(hours=1)
BUILDING_CACHE_LIFETIME = timedelta(days=30)

SCAN_INTERVAL = timedelta(hours=12)

STORAGE_VERSION = 1

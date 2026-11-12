"""Constants for the Clairsense integration."""

from datetime import timedelta

DOMAIN = "clairsense"
# The brand people know the device by. Home Assistant heads a device with maker and
# model, so this reads "Clairsense CLS-V1M1". The legal manufacturer is ARTEQ.
MANUFACTURER = "Clairsense"

CLIENT_ID = "home-assistant"
AUTHORIZE_URL = "https://smarthome.clairsense.net/oauth/authorize"
TOKEN_URL = "https://smarthome.clairsense.net/oauth/token"
REVOKE_URL = "https://smarthome.clairsense.net/oauth/revoke"
API_URL = "https://smarthome.clairsense.net/ha/v1/devices"

SCAN_INTERVAL = timedelta(seconds=60)

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

# Home Assistant renamed the concentration units and removes the old names in
# 2027.8. The new ones do not exist in 2025.4, the oldest version supported here,
# and the two versions spell the micro sign differently, so take whichever the
# running version has instead of writing the strings out.
try:
    from homeassistant.const import UnitOfDensity, UnitOfRatio
except ImportError:
    from homeassistant.const import (
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER as UNIT_MICROGRAMS_PER_CUBIC_METER,
        CONCENTRATION_PARTS_PER_MILLION as UNIT_PARTS_PER_MILLION,
    )
else:
    UNIT_MICROGRAMS_PER_CUBIC_METER = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
    UNIT_PARTS_PER_MILLION = UnitOfRatio.PARTS_PER_MILLION

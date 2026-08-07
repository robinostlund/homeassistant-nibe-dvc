"""Constants for the NIBE DVC integration."""

from __future__ import annotations

from typing import Final

from .api import (
    AIRFLOW_AIR_SUPPLY,
    AIRFLOW_HEAT_RECOVERY,
    AIRFLOW_VENTILATION,
    MAX_MANUAL_SPEED,
    MIN_MANUAL_SPEED,
    SPEED_HIGH,
    SPEED_LOW,
)

DOMAIN: Final = "nibe_dvc"

DEFAULT_NAME: Final = "NIBE DVC"
DEFAULT_SCAN_INTERVAL: Final = 30

MANUFACTURER: Final = "NIBE"
# The protocol reports no model, so this is the verified unit. Rebadged
# Vents/Blauberg/Flexit units speak the same protocol and show the same.
MODEL: Final = "DVC 10"

# Speed step 1-3 as reported by the fan; step 4 means "manual". Both ranges are
# built from the wire values in api.py rather than restated, so the protocol
# stays described in exactly one place.
SPEED_RANGE: Final = (SPEED_LOW, SPEED_HIGH)
MANUAL_SPEED_RANGE: Final = (MIN_MANUAL_SPEED, MAX_MANUAL_SPEED)

PRESET_MODE_VENTILATION: Final = "ventilation"
PRESET_MODE_HEAT_RECOVERY: Final = "heat_recovery"
PRESET_MODE_AIR_SUPPLY: Final = "air_supply"

# Preset mode <-> airflow direction as sent on the wire.
PRESET_MODE_TO_AIRFLOW: Final[dict[str, int]] = {
    PRESET_MODE_VENTILATION: AIRFLOW_VENTILATION,
    PRESET_MODE_HEAT_RECOVERY: AIRFLOW_HEAT_RECOVERY,
    PRESET_MODE_AIR_SUPPLY: AIRFLOW_AIR_SUPPLY,
}
AIRFLOW_TO_PRESET_MODE: Final[dict[int, str]] = {
    value: key for key, value in PRESET_MODE_TO_AIRFLOW.items()
}
PRESET_MODES: Final[list[str]] = list(PRESET_MODE_TO_AIRFLOW)

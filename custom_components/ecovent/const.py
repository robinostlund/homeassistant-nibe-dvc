"""Constants for the EcoVent integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ecovent"

DEFAULT_NAME: Final = "EcoVent"
DEFAULT_PORT: Final = 4000
DEFAULT_SCAN_INTERVAL: Final = 30

MANUFACTURER: Final = "Vents"
MODEL: Final = "TwinFresh / Vento Expert"

# Speed step 1-3 as reported by the fan; step 4 means "manual".
SPEED_RANGE: Final = (1, 3)
MANUAL_SPEED_RANGE: Final = (22, 255)

PRESET_MODE_VENTILATION: Final = "ventilation"
PRESET_MODE_HEAT_RECOVERY: Final = "heat_recovery"
PRESET_MODE_AIR_SUPPLY: Final = "air_supply"

# Preset mode <-> airflow direction as sent on the wire.
PRESET_MODE_TO_AIRFLOW: Final[dict[str, int]] = {
    PRESET_MODE_VENTILATION: 0,
    PRESET_MODE_HEAT_RECOVERY: 1,
    PRESET_MODE_AIR_SUPPLY: 2,
}
AIRFLOW_TO_PRESET_MODE: Final[dict[int, str]] = {
    value: key for key, value in PRESET_MODE_TO_AIRFLOW.items()
}
PRESET_MODES: Final[list[str]] = list(PRESET_MODE_TO_AIRFLOW)

# NIBE DVC

Home Assistant integration for NIBE / Vents / Blauberg / Flexit single-room heat
recovery ventilation units with Wi-Fi (TwinFresh Expert, Vento Expert,
Roomie Dual).

Talks to the unit directly over UDP on your local network. No cloud account and
no external Python dependencies.

Supports the **v1 protocol** only (UDP port 4000).

## Configuration

**Settings → Devices & services → Add integration → NIBE DVC**

Enter the IP address of your unit; the default port is `4000`. Add the
integration once per unit — multiple fans are fully supported.

## Entities

Per unit:

- **Fan** — on/off, three speeds, and the airflow direction as a preset mode
  (`ventilation`, `heat_recovery`, `air_supply`)
- **Humidity** sensor
- **Filter**, **Alarm** and **Boost mode** binary sensors (diagnostic)
- **Reset filter timer** button (config)

Entities are only created for parameters the unit actually reports.

Press **Reset filter timer** after changing the filter and the **Filter** sensor
clears immediately. The command behind it (`0x1E`) is undocumented and was found
by probing real hardware.

## Controlling airflow

Airflow direction is the fan's preset mode, so the standard services work and
this integration adds no custom services:

```yaml
action: fan.set_preset_mode
target:
  entity_id: fan.basement_fan
data:
  preset_mode: heat_recovery
```

## Offline units

When a unit stops answering, its entities become `unavailable` — Home
Assistant's standard signal for "no fresh data". Each poll retries three times
first, so a single dropped packet does not flap the state.

# EcoVent Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/robinostlund/home_assistant_ecovent)

Home Assistant integration for Vents / Blauberg / Flexit / NIBE single-room heat
recovery ventilation units with Wi-Fi.

Talks to the unit directly over UDP on your local network — no cloud account and
no external Python dependencies.

Requires Home Assistant **2026.8.0** or newer. Supports the **v1 protocol** only
(UDP port 4000).

## Installation

**HACS** — add `robinostlund/home_assistant_ecovent` as a custom repository with
category "Integration", install, restart.

**Manual** — copy `custom_components/ecovent` into your `custom_components`
folder and restart.

## Configuration

**Settings → Devices & services → Add integration → EcoVent**

Enter the unit's IP address; the default port is `4000`. Add the integration
once per unit — multiple fans are supported, each as its own device.

If a unit changes IP, use **Reconfigure** on the existing entry rather than
re-adding it, so entities and history survive.

## Entities

| Entity | Type | Notes |
| --- | --- | --- |
| Fan | `fan` | On/off, three speeds, airflow direction as preset mode |
| Humidity | `sensor` | Relative humidity |
| Filter | `binary_sensor` | Diagnostic — on when the filter needs replacing |
| Alarm | `binary_sensor` | Diagnostic |
| Boost mode | `binary_sensor` | Diagnostic |
| Reset filter timer | `button` | Config — press after changing the filter |

Entities are only created for parameters the unit actually reports.

Airflow direction is the fan's **preset mode**, so the standard services work
and the integration registers none of its own:

```yaml
action: fan.set_preset_mode
target:
  entity_id: fan.basement_fan
data:
  preset_mode: heat_recovery   # ventilation | heat_recovery | air_supply
```

When a unit stops answering, its entities become `unavailable`. Each poll
retries three times first, so a single dropped UDP packet does not flap the
state.

## Tested hardware

- **NIBE DVC 10** — verified end to end against live hardware (status, speed,
  airflow, humidity, filter, alarm, and filter timer reset)
- **Vents TwinFresh Expert RW1-50** (master/slave pair) — the original target

Identical units from Blauberg and Flexit use the same protocol and should work:

- [Flexit Roomie Dual](https://www.flexit.no/en/products/single_room_ventilator/single_room_ventilator_roomie_dual/single_room_ventilator_roomie_dual/)
- [Blauberg VENTO Expert A50-1 W](https://blaubergventilatoren.de/en/product/vento-expert-a50-1-w)

## Troubleshooting

```yaml
logger:
  logs:
    custom_components.ecovent: debug
```

Download **diagnostics** from the device page for every raw parameter the unit
reports, including ones no entity exposes yet.

## Development

```bash
pip install -r requirements-test.txt
pytest                                    # hardware tests skip themselves
ECOVENT_TEST_HOST=192.0.2.50 pytest       # include them
```

The UDP protocol, including parts undocumented elsewhere, is written up in
[PROTOCOL.md](PROTOCOL.md).

## Credits

Original integration and protocol work by
[@aglehmann](https://github.com/aglehmann).

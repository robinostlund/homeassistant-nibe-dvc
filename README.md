# NIBE DVC Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/robinostlund/homeassistant-nibe-dvc)

Home Assistant integration for Vents / Blauberg / Flexit / NIBE single-room heat
recovery ventilation units with Wi-Fi.

Talks to the unit directly over UDP on your local network — no cloud account and
no external Python dependencies.

Requires Home Assistant **2026.8.0** or newer. Supports the **v1 protocol** only
(UDP port 4000).

> **Upgrading from the `ecovent` version?** The integration domain changed from
> `ecovent` to `nibe_dvc`, so this is a clean break: remove the old integration
> and delete `custom_components/ecovent` before installing this one, then add it
> again from the UI. Entity history under the old ids is not carried over.

## Installation

**HACS** — add `robinostlund/homeassistant-nibe-dvc` as a custom repository with
category "Integration", install, restart.

**Manual** — copy `custom_components/nibe_dvc` into your `custom_components`
folder and restart.

## Configuration

**Settings → Devices & services → Add integration → NIBE DVC**

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
| Wi-Fi network | `sensor` | Diagnostic — the SSID the unit is joined to |
| Humidity trigger | `binary_sensor` | Diagnostic — humidity is over the boost threshold |
| External sensor | `binary_sensor` | Diagnostic — the NO-contact input, e.g. a wired CO2 sensor |
| Analog sensor | `binary_sensor` | Diagnostic — the 0-10 V input, if enabled |
| Boost humidity threshold | `number` | Config — %RH that triggers boost (40-80) |
| Boost run-on time | `number` | Config — how long boost continues after the trigger clears |
| Reset filter timer | `button` | Config — press after changing the filter |

### Boost

A triggered sensor drives the unit to **maximum speed**, outranking Party and
Night mode. When the trigger clears, the run-on timer counts down and only then
does the fan return to its previous speed. Both settings are exposed as `number`
entities, so an automation can tighten the humidity threshold at night or
lengthen the run-on after a shower.

The fan entity reports **100%** during boost. The unit's own `speed` value keeps
reporting the *configured* step throughout, so trusting it alone would show 33%
while the fan is flat out.

### CO2

There is no built-in CO2 sensor and no ppm reading. A CO2 sensor is an external
accessory wired to the NO-contact input (any model) or the 0-10 V input
(DVC 10-50W(L) only); the unit reports only that the threshold was crossed. It
appears as the **External sensor** or **Analog sensor** binary sensor, and it
triggers boost exactly like the built-in humidity sensor.

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

> **Security note:** these units serve their Wi-Fi password in plaintext over
> unauthenticated UDP to anyone on the network. The integration reads that frame
> for the SSID sensor but discards the password immediately, so it never appears
> in state, diagnostics or logs. Still worth putting the unit on a VLAN.

## Troubleshooting

```yaml
logger:
  logs:
    custom_components.nibe_dvc: debug
```

Download **diagnostics** from the device page for every raw parameter the unit
reports, including ones no entity exposes yet.

## Development

```bash
pip install -r requirements-test.txt
pytest                                    # hardware tests skip themselves
NIBE_DVC_TEST_HOST=192.0.2.50 pytest       # include them
```

The UDP protocol, including parts undocumented elsewhere, is written up in
[PROTOCOL.md](PROTOCOL.md).

## Credits

Original integration and protocol work by
[@aglehmann](https://github.com/aglehmann).

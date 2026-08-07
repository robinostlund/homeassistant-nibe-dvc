# EcoVent Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/robinostlund/home_assistant_ecovent)

Home Assistant custom integration for Vents / Blauberg / Flexit single-room heat
recovery ventilation units with Wi-Fi.

The integration speaks the units' UDP protocol directly on your local network —
no cloud account, and **no external Python dependencies**.

Requires Home Assistant **2026.8.0** or newer.

> Supports the **v1 protocol** only (UDP port 4000, `mobile`/`master` framing).
> Newer units that expose only an HTTP or v2 protocol are not supported.

## Installation

### HACS

1. In HACS, add the custom repository `robinostlund/home_assistant_ecovent`
   with category "Integration".
2. Search for "EcoVent", install it, then restart Home Assistant.

### Manual

Copy `custom_components/ecovent` into your Home Assistant `custom_components`
folder and restart.

## Configuration

Everything is configured from the UI:

**Settings → Devices & services → Add integration → EcoVent**

Enter the IP address of your unit; the default port is `4000`.

**Multiple units** are supported — add the integration once per unit. Each one
becomes its own device with its own entities.

If a unit later changes IP address, use **Reconfigure** on the existing entry
instead of deleting and re-adding it, so the entities and their history survive.

## Entities

Each unit becomes one device with the following entities:

| Entity | Type | Notes |
| --- | --- | --- |
| Fan | `fan` | On/off, three speeds, airflow direction as preset mode |
| Humidity | `sensor` | Relative humidity, `%`, measurement |
| Filter | `binary_sensor` | Diagnostic, `problem` — on when the unit wants the filter replaced |
| Alarm | `binary_sensor` | Diagnostic, `problem` device class |
| Boost mode | `binary_sensor` | Diagnostic |

Entities are only created if the unit actually reports that parameter, so units
without a humidity sensor or filter timer do not get empty entities.

### Resetting the filter indicator

**There is no way to reset the filter timer over the network on v1 units, so
this integration deliberately offers no reset button.**

This was tested against real hardware rather than assumed. The v1 protocol uses
the parameter id as the command byte, so writing to the filter parameter looks
plausible — but it does not work:

| Sent | Result |
| --- | --- |
| `0x01` status | answers with a status frame |
| `0x04 0x01` set speed | answers with a status frame |
| `0x06 0x00` set airflow | answers with a status frame |
| `0x12 0x00` clear filter | **no response, no effect** |
| `0x12 0x01` set filter | **no response, no effect** |

The filter end-of-life parameter is read-only. Reset the indicator on the unit
itself instead — on the TwinFresh Expert series, flip the 8th DIP switch on the
access panel to the right and then back to the left. The `Filter` binary sensor
will clear at the next poll.

### Controlling airflow direction

The airflow direction is exposed as the fan's **preset mode**, so the standard
fan services work — this integration registers no custom services.

```yaml
action: fan.set_preset_mode
target:
  entity_id: fan.basement_fan
data:
  preset_mode: heat_recovery   # ventilation | heat_recovery | air_supply
```

Speed uses the standard percentage API (33% / 66% / 100% for low / medium / high):

```yaml
action: fan.set_percentage
target:
  entity_id: fan.basement_fan
data:
  percentage: 66
```

## Behaviour when the unit goes offline

Home Assistant's own convention is used: when the unit stops answering, every
entity of that device becomes **`unavailable`**. Automations can test for this
with `is_state('fan.basement_fan', 'unavailable')`.

There is deliberately **no "connected" binary sensor** — such an entity would
itself become unavailable at exactly the moment it was supposed to report a
problem, so it cannot tell you anything that availability does not.

Each poll retries 3 times with a 5 second timeout before the device is
considered unreachable, so a single dropped UDP packet does not flap the state.

## Troubleshooting

Enable debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.ecovent: debug
```

Download **diagnostics** from the device page to see every raw parameter the
unit reports, including ones no entity exposes yet (operation mode, filter
timer, relay and 0-10 V sensor status, timers).

## Development

```bash
pip install -r requirements-test.txt
pytest
```

To also run the tests that talk to real hardware:

```bash
ECOVENT_TEST_HOST=192.0.2.50 pytest
```

## Protocol

The unit answers a status request, and every write command, with a full status
frame:

```
request:  b"mobile" + <cmd> <value> + b"\r\n"
response: b"master" + <param> <payload...> ...
```

`custom_components/ecovent/api.py` is a self-contained asyncio implementation of
this. It replaces the `pyEcovent` package, which used blocking socket I/O with a
15 second timeout — unusable inside Home Assistant's event loop.

## Tested hardware

- **NIBE DVC 10** — verified end to end against live hardware during the 2.0.0
  rewrite (status, speed, airflow, humidity, filter and alarm reporting)
- Vents TwinFresh Expert RW1-50 (master/slave pair) — the original target

Identical units from Blauberg and Flexit are expected to work:

- [Flexit Roomie Dual](https://www.flexit.no/en/products/single_room_ventilator/single_room_ventilator_roomie_dual/single_room_ventilator_roomie_dual/)
- [Blauberg VENTO Expert A50-1 W](https://blaubergventilatoren.de/en/product/vento-expert-a50-1-w)

## Credits

Original integration and protocol work by
[@aglehmann](https://github.com/aglehmann).

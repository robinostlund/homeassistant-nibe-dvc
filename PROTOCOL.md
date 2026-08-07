# EcoVent v1 UDP protocol

Notes on the protocol spoken by Vents / Blauberg / Flexit / NIBE single-room
ventilation units on UDP port 4000. Parts of this are not documented anywhere
else and were found by probing a live NIBE DVC 10.

## Framing

```
request:   b"mobile" + <command> <value> + b"\r\n"
response:  b"master" + <param> <payload...> <param> <payload...> ...
```

Responses carry no footer. Each parameter is a one byte id followed by a fixed
payload length, so an unknown id makes the rest of the frame unparseable — the
client stops there and keeps what it decoded rather than raising.

## Read commands

All three ignore their value byte and answer in ~30 ms. A sweep of every command
byte from `0x00` to `0x40` found these and nothing else.

| Command | Returns |
| --- | --- |
| `0x01` | **status** — state, speed, manual speed, airflow, humidity, alarm, filter, boost |
| `0x02` | **configuration** — humidity threshold, sensor enables, timers, 0-10 V threshold, cloud |
| `0x24` | **network settings** — SSID, Wi-Fi password, IP. See the warning below |

`0x02` is not implemented by any other client found; it was discovered while
probing. A real config frame decodes as an exact fit:

```
0b 4b            humidity_sensor_threshold = 75
15 01            humidity_sensor_enabled   = 1
16 01            relay_sensor_enabled      = 1
17 00            sensor_10v_enabled        = 0
0f 00 70 80      night_mode_timer
10 00 38 40      party_mode_timer
11 00 02 58      deactivation_timer
19 32            sensor_10v_threshold      = 50
1f 01            cloud_activation          = 1
```

**Three byte values are big-endian seconds**, not packed hours/minutes/seconds.
The frame above decodes to exactly 8 h, 4 h and 10 min, which is what confirms
the encoding:

| Parameter | Bytes | Seconds | |
| --- | --- | --- | --- |
| night_mode_timer | `00 70 80` | 28800 | 8 h |
| party_mode_timer | `00 38 40` | 14400 | 4 h |
| deactivation_timer | `00 02 58` | 600 | 10 min |

## Write commands

| Command | Effect | Answers? |
| --- | --- | --- |
| `0x03 0x00` | toggle power (no explicit on/off) | yes |
| `0x04 <1-3>` | set speed step | yes |
| `0x05 <22-255>` | set manual speed, switches unit to manual (speed reads 4) | **no** |
| `0x06 <0-2>` | set airflow: ventilation / heat recovery / air supply | yes |
| `0x0B <n>` | set humidity threshold, 40-80 %RH | **no** |
| `0x11 <3 bytes>` | set boost run-on delay, big-endian seconds, 0-24 h | **no** |
| `0x15 <0-1>` | enable/disable humidity sensor | no |
| `0x16 <0-1>` | enable/disable external NO-contact input | no |
| `0x1E 0x00` | **reset the filter replacement timer** | yes |

**Payloads are not limited to one byte.** `0x11 00 03 84` sets the run-on delay
to 900 s and is confirmed by re-reading the config frame. This is what makes the
3-byte timers writable at all.

### Three things that will bite you

1. **A command that acts does not necessarily answer.** `0x05` and `0x0B` both
   apply their change with no response at all. Never read "no response" as "no
   effect" — verify by re-reading the status and config frames.

2. **The filter reset is `0x1E`, not `0x12`.** `0x12` is the filter parameter's
   id in the *status* frame, but writing to it is silently ignored with every
   value tried (`0x00`, `0x01`, `0x02`, `0xFF`). The command and parameter
   spaces are not interchangeable.

3. **The unit validates values.** `0x04 0xFF` and `0x04 0x00` are both rejected
   (speed is 1-3) while still answering with a status frame. Unrecognised
   command bytes stay silent instead.

## `0x24` — network settings (security warning)

> **`0x24` returns the unit's Wi-Fi password in plaintext to anyone on the
> network.** The protocol has no authentication of any kind, so a single
> unsolicited UDP datagram to port 4000 is enough. Nothing can be done about it
> from the integration side, but it is worth knowing that these units should not
> sit on a network you would not trust with the Wi-Fi credentials — a VLAN is
> the sensible mitigation.
>
> **This integration does send `0x24`**, once per entry setup, to populate the
> Wi-Fi network sensor. `parse_network_response()` reads the password field only
> to step over it and never assigns it anywhere that outlives the parse, so it
> reaches neither the coordinator, the entities, diagnostics nor the log. Tests
> pin that behaviour — keep them if you touch this code.

Unlike the other two frames this one is footer-terminated and uses
length-prefixed strings:

| Id | Field | Encoding |
| --- | --- | --- |
| `0x20` | Wi-Fi SSID | 1 byte length, then ASCII |
| `0x21` | Wi-Fi password | 1 byte length, then ASCII |
| `0x22` | unknown, empty on the test unit | 1 byte length, then ASCII |
| `0x23` | device IP address | 4 raw bytes |

## No temperature sensor

There is **no temperature reading in the v1 protocol on this family of unit**,
which is worth recording because a heat recovery unit plausibly ought to have
one. Two independent lines of evidence:

**1. The v2 protocol documentation says this family has none.** The
[ecovent_v2 protocol notes](https://github.com/gody01/ecovent_v2/blob/main/protocol.md)
place temperature at parameters `0x001E`-`0x0022`, but only for the **Freshbox /
Micra** (`0x0200`) and **Breezy / Freshpoint** (`0x1100`-`0x1800`) families —
units that have a reheater or a room controller. The **Vento Expert / TwinFresh
Expert** family (`0x0300`, `0x0400`, `0x0500`), which is what the NIBE DVC 10 is,
has no temperature rows at all. Even the far richer v2 protocol exposes no
temperature for these units, because the hardware has no sensor: they recover
heat with a ceramic regenerator reversing on a timer, not by modulating on
measured temperature.

Note the v2 temperature ids collide numerically with v1's *network* parameters
(`0x20` SSID, `0x21` password, `0x22`, `0x23` IP). That is a coincidence of two
unrelated numbering schemes, not a mapping — do not read v2 ids into v1 frames.

**2. An exhaustive sweep found nothing.** Every command byte `0x00`-`0xFF` was
probed while diffing the status, config and network frames after each one. The
result: three read commands (`0x01`, `0x02`, `0x24`), a handful of writes, and
everything else silent. All three frames parse to an exact byte fit with no
spare room. `0x07` — the obvious gap next to humidity at `0x08` — is silent for
every one of 22 values tried, and none of the read commands page on their value
byte.

## Status parameters

| Id | Name | Bytes | Notes |
| --- | --- | --- | --- |
| `0x03` | state | 1 | 0 off, 1 on |
| `0x04` | speed | 1 | 1 low, 2 medium, 3 high, 4 manual |
| `0x05` | manual speed | 1 | 22-255 |
| `0x06` | airflow | 1 | 0 ventilation, 1 heat recovery, 2 air supply |
| `0x08` | humidity | 1 | % RH |
| `0x09` | operation mode | 1 | |
| `0x0C` | alarm status | 1 | |
| `0x0D` | relay sensor status | 1 | |
| `0x0E` | party/night countdown | 3 | |
| `0x12` | filter end-of-life | 1 | 1 = replace filter. Read-only |
| `0x13` | humidity sensor triggered | 1 | |
| `0x14` | boost mode | 1 | **not boolean** — see below |
| `0x1A` | 0-10 V sensor status | 1 | |
| `0x25` | 0-10 V current status | 1 | |

## Boost mode

Boost is triggered by a *sensor* crossing its threshold — humidity, the relay
input, or the 0-10 V input — not by a direct command. Observed by temporarily
lowering the humidity threshold below the current reading:

```
threshold 75 -> 0 :  humidity_sensor_triggered 0->1,  boost 0->1
threshold 0 -> 75 :  humidity_sensor_triggered 1->0,  boost 1->2
power cycle       :  boost 2->0
```

The DVC 10 manual settles what the probing could only suggest:

- The unit goes to **maximum speed** when a sensor trips, and boost **outranks
  Party and Night mode**.
- When the trigger clears, the **turn-off delay timer** (`0x11`,
  *frånslagsfördröjningstimer*) counts down and only then does the fan return to
  its *previous* speed. Range **0 to 24 hours, default 30 minutes**.
- Because it returns to the *previous* speed, `speed` keeps reporting the
  configured step for the whole boost. A client deriving a percentage from
  `speed` alone under-reports actual airflow — the integration returns 100 %
  whenever `boost` is non-zero.
- That also explains `boost = 2`: it is the run-on countdown, during which the
  fan is **still at maximum speed**. So treating any non-zero value as
  "boosting" is correct, and the earlier power cycle was unnecessary — the test
  unit's delay is 600 s and only 90 s had elapsed.

Three inputs can trigger boost, each independently enableable:

| Input | Enable | Threshold | Triggered flag |
| --- | --- | --- | --- |
| Built-in humidity sensor | `0x15` | `0x0B` (40-80 %RH) | `0x13` |
| External NO contact | `0x16` | — (contact closes) | `0x0D` |
| External 0-10 V analog | `0x17` | `0x19` | `0x1A` |

## CO2 sensing

The DVC 10 has **no built-in CO2 sensor and reports no CO2 concentration**. The
manual lists a CO2 sensor only as an *external* accessory wired to one of the
two trigger inputs above — the NO contact (any model) or the 0-10 V analog input
(DVC 10-50W(L) only). Either way the unit reports a single "threshold exceeded"
flag, never a ppm value, so there is nothing to expose as a measurement. A wired
CO2 sensor shows up as the **External sensor** or **Analog sensor** binary
sensor.

## Behaviour notes

- Every command that answers returns a **full status frame**, so a write and its
  confirmation are a single round trip. No separate poll is needed.
- Responses arrive in roughly 30 ms on a local network. The client uses a 5 s
  timeout with 3 retries purely to ride out lost UDP packets.
- Unreachable hosts surface as ICMP port unreachable on a connected UDP socket,
  so failure is immediate rather than waiting for the timeout.
- **The unit occasionally answers with the wrong frame type.** During sweeping, a
  `0x24` request came back with a status frame; the next read was correct. A
  client must therefore not assume the reply matches the request. This one is
  handled safely by accident of design: a status parse of a network frame hits
  the unknown parameter `0x23` immediately, decodes nothing, and raises
  `EcoventProtocolError`, which the retry loop treats as a lost packet.

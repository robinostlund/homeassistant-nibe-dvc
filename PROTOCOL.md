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

Both ignore their value byte and answer in ~30 ms.

| Command | Returns |
| --- | --- |
| `0x01` | **status** — state, speed, manual speed, airflow, humidity, alarm, filter, boost |
| `0x02` | **configuration** — humidity threshold, sensor enables, timers, 0-10 V threshold, cloud |

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

## Write commands

| Command | Effect | Answers? |
| --- | --- | --- |
| `0x03 0x00` | toggle power (no explicit on/off) | yes |
| `0x04 <1-3>` | set speed step | yes |
| `0x05 <22-255>` | set manual speed, switches unit to manual (speed reads 4) | **no** |
| `0x06 <0-2>` | set airflow: ventilation / heat recovery / air supply | yes |
| `0x0B <n>` | set humidity threshold | **no** |
| `0x15 <0-1>` | enable/disable humidity sensor | no |
| `0x1E 0x00` | **reset the filter replacement timer** | yes |

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

Two open questions:

- **`speed` does not change while boost is active.** It keeps reporting the
  configured step, so a client that derives a percentage from `speed` will
  under-report actual airflow during boost.
- **`boost` takes at least three values (0, 1, 2).** `2` appears to be a
  post-boost run-on or lockout; it persisted for 90 s and was cleared by a power
  cycle. It may clear on its own, plausibly on the `deactivation_timer`. The
  integration currently treats the value as a boolean, which may misreport `2`.

## Behaviour notes

- Every command that answers returns a **full status frame**, so a write and its
  confirmation are a single round trip. No separate poll is needed.
- Responses arrive in roughly 30 ms on a local network. The client uses a 5 s
  timeout with 3 retries purely to ride out lost UDP packets.
- Unreachable hosts surface as ICMP port unreachable on a connected UDP socket,
  so failure is immediate rather than waiting for the timeout.

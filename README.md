# Klydoclock for Home Assistant

Local control of a [Klydoclock](https://www.klydoclock.com) from Home Assistant.
No cloud, no account: the integration talks to the clock over ADB on your
network.

This is an unofficial community project. It is not affiliated with or endorsed
by Klydo.

## What you get

| Entity | Description |
|---|---|
| Sensor **Klydo** | Name of the klydo on display; attributes: id, artist, favorite, feed position |
| Sensor **Artist** | Creator of the current klydo |
| Binary sensor **Favorite** | On while the current klydo is a favorite |
| Select **Display mode** | Bright, Medium, Dim, Night (red), Off |
| Select **Favorite klydo** | Jump to one of your favorites (see below) |
| Switch **Display** | Display off / back on at full brightness |
| Buttons | Next klydo, Previous klydo, Toggle favorite, Info, Settings, Sleep key |
| Sensors **Brightness level**, **Favorites** | App brightness level, number of favorites; the favorites' ids and names as attributes |
| Diagnostic sensors | Screen state, night mode, mode |

There is also an action **klydoclock.show_klydo** that walks the clock to any
klydo it knows, by name or id.

## How it works

The clock is an Android 8.1 device running a single app. Its ADB port (5555)
is open on the local network and allows root.

- **Control** replays the keys of the original remote (`input keyevent`).
- **State** is read every 10 seconds from the app's settings store; klydo and
  artist names come from the app's database.
- **Display mode** steps through the sleep-key cycle
  (bright → medium → dim → night → off → bright) and checks after every press
  that the clock followed.

## Selecting a klydo

The app has no interface to jump straight to a specific klydo; it only offers
next and previous. **Favorite klydo** and `klydoclock.show_klydo` therefore
walk through the feed with next/previous keys (batched, verified after every
batch) until the wanted klydo is on display:

```yaml
actions:
  - action: klydoclock.show_klydo
    data:
      klydo: "Steamboat Willie"   # or a klydo id
```

Worth knowing:

- The clock must be in **FEED mode** (its normal state), and the klydo must be
  in the feed. In the firmware this was developed against, the feed contains
  every klydo on the clock.
- Each step takes a moment; a jump across the feed can take up to half a
  minute. Nearby klydos arrive in a few seconds.
- Every klydo passed on the way counts as briefly viewed in the app's
  statistics.

## Requirements

- Klydoclock with Clock OS 600 or newer (developed against app version 632)
- Home Assistant 2025.2 or newer, on the same network as the clock
- A fixed IP address for the clock (DHCP reservation in your router)

## Installation

### HACS

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/micdis/ha-klydoclock`, type **Integration**
3. Install **Klydoclock** and restart Home Assistant

### Manual

Copy `custom_components/klydoclock` into the `custom_components` folder of
your Home Assistant configuration and restart.

## Setup

Settings → Devices & services → Add integration → **Klydoclock**, then enter
the IP address of the clock. The port stays at 5555.

## Example

Turn the display off when nobody is home:

```yaml
triggers:
  - trigger: state
    entity_id: zone.home
    to: "0"
actions:
  - action: select.select_option
    target:
      entity_id: select.klydoclock_display_mode
    data:
      option: "off"
```

## Security note

The clock accepts ADB connections with root access from any device on your
network, with or without this integration. Anyone on that network can take
over the clock. Consider placing it in a separate IoT network that only Home
Assistant can reach.

## Limitations

- Relies on internals of the clock's app. A firmware update can break it.
- The clock's own automatic night mode can interfere with display modes set
  from Home Assistant. Disable one of the two.
- Changing the display mode takes about half a second per step, and the
  intermediate modes are briefly visible.

## License

MIT

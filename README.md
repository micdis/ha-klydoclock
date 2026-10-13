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

There are also two actions: **klydoclock.show_klydo** walks the clock to any
klydo in its feed or favorites, by name or id, and **klydoclock.set_mode**
switches between FEED and FAVORITE mode.

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
step through a list with next/previous keys (batched, verified after every
batch) until the wanted klydo is on display. In FEED mode the keys walk the
feed, in FAVORITE mode the favorites.

```yaml
actions:
  - action: klydoclock.show_klydo
    data:
      klydo: "Steamboat Willie"   # or a klydo id
      mode: favorite              # optional: feed or favorite
```

Without `mode`, the current list is used if it holds the klydo, otherwise the
feed, otherwise the favorites. If the clock is in another mode (for example
EXPLORE), it is switched first.

### Switching the mode

`klydoclock.set_mode` (and `show_klydo` when it needs to) opens the home menu
with the settings key, turns the selection to FEED or FAVORITES with
left/right and confirms with Enter. The menu has no accessibility text, so the
integration takes a screenshot after every step and reads which entry is
selected from the bright arc on the rim; a screenshot only counts as the menu
if it also shows the menu's black centre and plain grey ring. FEED is the
entry at 12 o'clock, FAVORITES the next one clockwise. If the menu does not
look as expected, the integration turns back to the entry it opened on and
confirms that, because a menu left alone for about a minute falls back to FEED.

EXPLORE cannot be selected this way: entering it asks for a category.

The info key opens a ring menu of the same look (with a delete entry at
6 o'clock). The integration tells the two apart by their icon layout and never
presses Enter in it. Like the home menu, it falls back to FEED when left open.

In night mode the first key press only wakes the display. Navigation, mode
changes and the buttons Next, Previous and Toggle favorite therefore leave
night mode first and return to it when they are done. Info and Settings open
screens meant to be used, so they leave the display awake. The Sleep key works
in night mode and is sent as it is. With the display off, navigation and mode
changes refuse to run, while the buttons send their key as before.

A button press also cancels a navigation that is still running.

Worth knowing:

- In the firmware this was developed against, the feed contains every klydo
  on the clock.
- Switching into FAVORITE mode starts at the last favorite.
- Selecting another klydo while a navigation is still running cancels the
  running one; the newest selection wins.
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

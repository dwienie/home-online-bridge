# Home Online Bridge

Control a **Home Online** domotica system from **Home Assistant**, fully local, no cloud, no MQTT.

This repository has two parts that work together:

| Part | What it is | Where it runs |
|---|---|---|
| [ESPHome firmware](#part-1--esphome-firmware) (`esphome/`) | An ESP32 that talks to the Home Online controller over RS232 | On the ESP32 |
| [Home Assistant integration](#part-2--home-assistant-integration) (`custom_components/home_online_bridge/`) | Creates the lights, covers, switches and sensors in Home Assistant | In Home Assistant |

```
Home Online controller --RS232--> TTL-to-RS232 module --TTL--> ESP32 --WiFi (ESPHome API)--> Home Assistant
```

The ESP32 knows nothing about your installation. It only passes serial lines to Home Assistant and back.
All names and types are configured in Home Assistant, in the UI.

**Supported slave types**

| Home Online slave | Home Assistant entity |
|---|---|
| Dimmer | `light` (brightness, with calibration) |
| Curtain / blind | `cover` (open, close, set position) |
| Relay | `switch` |
| Sensor (read-only) | `binary_sensor` |

**Current version:** 1.2.0 (see [CHANGELOG](CHANGELOG.md)). The version is in
`custom_components/home_online_bridge/manifest.json`, and Home Assistant / HACS show it.

> Not affiliated with Home Online. Use at your own risk: you are connecting a device to your home automation controller.

---

## Part 1 – ESPHome firmware

### What you need

- An **ESP32 board**, for example a WEMOS D1 R32 (the ESP32 board with the Arduino Uno shape) or any ESP32 dev board.
- A **TTL to RS232 module** (MAX3232 chip), like this one: <https://nl.aliexpress.com/item/1005006807931160.html>.
  Check that your module has the pins `VCC`, `GND`, `TXD`, `RXD` on the TTL side and a DB9 connector on the RS232 side.
- An **RS232 cable** from the module to the Home Online controller (see [the cable](#the-rs232-cable)).
- ESPHome (the Home Assistant add-on, or `pip install esphome`) and a 2.4 GHz WiFi network.

### Wiring the module to the ESP32

The bridge uses a hardware serial port of the ESP32 on pins `GPIO16` (RX) and `GPIO17` (TX). ESPHome picks the
UART number itself; the pins are what matters. UART0 (USB) is not used, because logging over serial is switched off
in the YAML (`logger: baud_rate: 0`):

| TTL-to-RS232 module | ESP32 (WEMOS D1 R32) |
|---|---|
| `VCC` | `3V3` (3.3 V) |
| `GND` | `GND` |
| `RXD` | `GPIO17` (ESP32 TX) |
| `TXD` | `GPIO16` (ESP32 RX) |

**The RXD/TXD wiring between module and ESP32 depends on your RS232 cable.** Only the `RXD`, `TXD` and `GND`
lines of the serial cable are used (no handshake lines such as RTS/CTS). Whether you must wire the module as in the
table above, or swap `RXD` and `TXD` towards the ESP32 (`RXD` to `GPIO16` and `TXD` to `GPIO17`), depends on the cable
you use between the controller and the module:

| Your cable | Module to ESP32 |
|---|---|
| Straight cable (pin 2 to 2, 3 to 3) | wire as in the table, or swap if nothing arrives |
| Crossed / null-modem cable (pin 2 to 3, 3 to 2) | the opposite of the straight cable |

Start with the table above. If the "Controller online" sensor stays off, **swap the two data wires**
(`RXD` and `TXD`) between the module and the ESP32 and try again. This costs nothing and cannot damage the module.
Do not change anything on the RS232 side while testing.

> **Power:** a MAX3232 works at 3.3 V. Do not power the module from 5 V while connecting its TTL pins to the ESP32,
> unless your module explicitly says it has 3.3 V compatible TTL outputs.

The pins are set in `esphome/home-online-bridge.yaml` (`uart:` section). If you use other pins, change them there.

### The RS232 cable

1. **Connect an RS232 cable from the Home Online controller to the TTL-to-RS232 module.**
2. **Male or female?** That depends on the cable you have. The module's DB9 connector and the controller's RS232
   connector each have a gender, and a cable needs the opposite on each end. Check both connectors first and buy or
   use a cable (or a gender changer) that fits.
3. **Make sure the cable fits the RS232 connection of the controller.** Check the connector type (usually DB9) and
   whether it is male or female before you plug anything in. Do not force a connector.
4. Only three lines are used: `RXD` (DB9 pin 2), `TXD` (DB9 pin 3) and `GND` (DB9 pin 5). Check the pinout of
   your controller's RS232 connector in its manual.
5. Straight or crossed (null-modem) cable: both exist, and which one you have decides how you wire `RXD`/`TXD`
   from the module to the ESP32 (see the table above). If you have no data, swap those two wires.

### Set the Home Online controller to 19200 baud

The Home Online system must communicate at **19200 baud**. Set this in the Home Online software / controller settings.
The ESP32 is configured for 19200 baud, 8 data bits, no parity, 1 stop bit (8N1).

### Flash the ESP32

1. Copy `esphome/secrets.example.yaml` to `esphome/secrets.yaml` and fill it in:
   - `wifi_ssid`, `wifi_password`: your WiFi.
   - `api_encryption_key`: generate one with `openssl rand -base64 32` (or let ESPHome generate one).
   - `ota_password`: choose a password for wireless updates.

   `secrets.yaml` is git-ignored. Never commit it or share it.
2. **Set your board.** Open `esphome/home-online-bridge.yaml` and set `board:` in the `esp32:` section to the board
   you have. `esp32dev` works for the WEMOS D1 R32 and most generic ESP32 boards. Other boards are listed at
   <https://esphome.io/components/esp32.html>.
3. In the same file, `external_components:` loads the component from this GitHub repository (option A). If you
   copied the whole repository to your computer instead, use the local option B described in the comments.
4. Flash the first time over USB: `esphome run home-online-bridge.yaml`. Later updates can be done wireless.
5. In Home Assistant, the node shows up under *Settings > Devices & services* as an ESPHome device. Click **Add**
   and enter the API encryption key.

The node has a **"Controller online"** sensor. It turns on when the controller answers over serial and turns off
about 20 seconds after the controller stops responding.

---

## Part 2 – Home Assistant integration

### Install with HACS (custom repository)

> **Home Assistant 2026.11 and newer:** HACS is now called **Marketplace** in Home Assistant. Wherever these steps
> say "HACS", open **Marketplace** instead. The menu items (custom repositories, download) work the same way.

1. Install [HACS](https://hacs.xyz) if you have not done so.
2. HACS > three-dot menu > **Custom repositories**.
3. Repository: `https://github.com/dwienie/home-online-bridge`, category: **Integration**. Click **Add**.
4. Find **Home Online Bridge** in HACS, click **Download**, and **restart Home Assistant**.

### Install manually

Copy the folder `custom_components/home_online_bridge` to `<your HA config>/custom_components/home_online_bridge`
and restart Home Assistant.

### Set up

1. *Settings > Devices & services > Add integration > **Home Online Bridge***.
2. Enter the **ESPHome node name**: `home_online_bridge` (the name of the device with `-` replaced by `_`).
3. The integration starts empty. Add your slaves as described below.

### Add your slaves (the mapping)

The numbers in the mapping are the **slave numbers** you see in the **Home Online software**.

*Settings > Devices & services > Home Online Bridge > **Configure***:

- **Add a mapping**: enter the slave number, a name, and the type (dimmer, curtain, relay, sensor).
- **Add from IDs seen on serial**: when a slave changes state (you press a wall switch), the number appears in this list.
  This is the easy way to find out which number is which: press the switch, then pick the new number and name it.
- **Import slaves from a Domati .bin file**: read the export of the Home Online software and add many slaves in one go
  (see [below](#import-slaves-from-a-bin-file)).
- **Edit / remove** a mapping.
- **Ignore IDs seen on serial**: hide numbers you never want to map.
- Finish with **Save and apply**. No restart is needed.

| Type | Entity | Notes |
|---|---|---|
| Dimmer | `light` | brightness 0-255 is converted to 0-100 % of the controller. A plain turn-on returns to the last level. |
| Curtain | `cover` | position 100 = open, 0 = closed. Verify the direction on one curtain first. |
| Relay | `switch` | on = 1, off = 0 |
| Sensor | `binary_sensor` | any non-zero value = on |

The entity's unique id is the slave number, so renaming a mapping keeps its history.
All entities are *unavailable* while the node is offline or the "Controller online" sensor is off.
Groups: use Home Assistant light groups.

### Import slaves from a .bin file

Instead of adding slaves one by one, you can read the **.bin file that you export from the Home Online software**
and add the slaves you want in a single action. The file lists every slave of your installation, with its number,
name and module, so you do not have to find the numbers by pressing switches.

*Settings > Devices & services > Home Online Bridge > **Configure** > **Import slaves from a Domati .bin file***:

1. **Choose the .bin file** from your computer. It is only read to list the slaves; it is not stored.
   Inputs and buttons are hidden by default (there are usually a lot of them); tick the box to show them too.
2. **Select the slaves to add.** Each entry is shown as `ID · name (module)`, for example
   `384 · Output 1 (Bedieningspaneel Living) · output`. When the file says whether a slave is an **input** or an
   **output**, that is added at the end. Nothing is selected by default.
   Slaves that are already mapped (or ignored) are not offered again, so you cannot map a slave twice.
3. **Choose the type per slave** (dimmer, curtain, relay, sensor). The type is pre-filled with a suggestion based on the
   file; change it where it is wrong. The name from the file is used as the name of the mapping and can be changed
   later with **Edit a mapping**.
4. Finish with **Save and apply**, like any other change.

Notes:

- The slave numbers are calculated from the module list in the file. If they cannot be verified (for example because
  of an unknown module type), you get a warning first and you can cancel. Check a few slaves after importing.
- Dimmers get the default calibration range; see [Dimmer calibration](#dimmer-calibration-where-the-lamp-starts-and-where-it-is-at-full-brightness).
- The .bin file contains the names of your installation. Do not publish it, and do not attach it to issues.

### Dimmer calibration: where the lamp starts, and where it is at full brightness

Many lamps (LED drivers especially) do not light up below a certain dimmer level, and reach their full brightness
before the dimmer reaches 100 %. Without calibration, the bottom and top of the Home Assistant slider are wasted.

Each dimmer has two settings:

- **Dimmer minimum (%)**: the lowest controller level where the lamp still gives light.
- **Dimmer maximum (%)**: the controller level where the lamp is at 100 % of its brightness.

Home Assistant 1 % then maps to the minimum, and 100 % maps to the maximum, with a smooth range in between.
Defaults are 8 and 100. Set them in *Configure > Edit a mapping*, or calibrate live with the entities below.

#### Calibrate live with the dimmer's own entities

Every dimmer also gets five extra entities. They are named after the mapping, so for a dimmer called `Zit` you find
`Zit minimum`, `Zit calibration` and so on (search for the name in *Settings > Devices & services > Entities*, or open
*Settings > Devices & services > Home Online Bridge > entities*). The minimum, maximum and the two buttons are in
category *Configuration*; the calibration slider is a normal control.

| Entity | Type | What it does |
|---|---|---|
| `<name> minimum` | number (%) | The calibrated minimum. Changing it applies immediately and is saved in the mapping. |
| `<name> maximum` | number (%) | The calibrated maximum. Changing it applies immediately and is saved in the mapping. |
| `<name> calibration` | number (0-100) | Sends a raw controller level straight to the dimmer, **bypassing the calibration**. |
| `<name> calibration as minimum` | button | Takes the current raw level as the new minimum. |
| `<name> calibration as maximum` | button | Takes the current raw level as the new maximum. |

Calibrate one dimmer:

1. Find the five entities of the dimmer (see above), for example in a dashboard card.
2. **Minimum:** start with the *calibration* slider at 0 and raise it until the lamp **just** lights. Press
   *calibration as minimum*.
3. **Maximum:** set the slider to 100 and lower it step by step. At the highest level where the lamp **still gets
   brighter**, press *calibration as maximum*. (If the lamp is still brighter at 100, the maximum stays 100.)
4. Check: slide the light in Home Assistant to 1 % (barely on) and 100 % (full brightness).

The minimum must stay lower than the maximum; otherwise you get an error and nothing changes. No reload and no
*Save and apply* are needed. The helpers, script and dashboard below do the same job by hand and are no longer
needed if you use these entities.

#### Alternative: a calibration dashboard with helpers

This sends a raw value straight to a slave, without any calibration applied, so you can watch the lamp.

1. *Settings > Devices & services > Helpers*, create two helpers (or add them in `configuration.yaml`):

   ```yaml
   input_number:
     hob_calibrate_level:
       name: Calibration level
       min: 0
       max: 100
       step: 1
       unit_of_measurement: "%"
       mode: slider
     hob_calibrate_slave:
       name: Calibration slave number
       min: 0
       max: 999
       step: 1
       mode: box
   ```

   If you already have an `input_number:` block, add both entries under it.

2. Create a script *Settings > Automations & scenes > Scripts > Add script > Edit in YAML*:

   ```yaml
   alias: Home Online calibration send
   sequence:
     - action: esphome.home_online_bridge_send
       data:
         id: "{{ states('input_number.hob_calibrate_slave') | int }}"
         value: "{{ states('input_number.hob_calibrate_level') | int }}"
         percent: true
   ```

   `esphome.home_online_bridge_send` is the action of your ESP32 node. If you named the node differently, the
   action name is `esphome.<node name with underscores>_send`.

3. Create a dashboard (*Edit dashboard > Raw configuration editor* or add a manual card):

   ```yaml
   type: entities
   title: Dimmer calibration
   entities:
     - entity: input_number.hob_calibrate_slave
     - entity: input_number.hob_calibrate_level
     - type: button
       name: Send to dimmer
       tap_action:
         action: perform-action
         perform_action: script.turn_on
         target:
           entity_id: script.home_online_calibration_send
   ```

   (The entity id of the script is shown in its settings. Adjust it if yours differs.)

4. Calibrate one dimmer:
   - Fill in the dimmer's slave number.
   - **Minimum:** start at 0, then raise the level and press *Send* each time. The level where the lamp **just** lights
     is the minimum. Write it down.
   - **Maximum:** set 100, then lower the level step by step. The highest level where the lamp **still gets brighter**
     is the maximum. (If the lamp is still brighter at 100, the maximum is 100.)
   - Enter both numbers in *Configure > Edit a mapping* for that dimmer and **Save and apply**.
5. Check: slide the light in Home Assistant to 1 % (barely on) and 100 % (full brightness).

Do this per dimmer: different lamps need different values.

---

## Security and privacy

- This repository contains **no personal data**: no names, no slave numbers, no passwords, no WiFi details.
  Your mappings are stored only inside your own Home Assistant.
- `secrets.yaml` (WiFi, API key, OTA password) is in `.gitignore`. Keep it that way. Never paste it in an issue.
- The ESPHome API is encrypted with your own key, and OTA updates are password protected.
- Do not expose the ESP32 to the internet. Keep it on your local network.
- When you report an issue, remove your IP addresses, node names and slave names from logs first.

## Developing

```
python -m pytest -v tests                       # tests for the Home Assistant logic
cd esphome/tests && g++ -std=c++17 -I../components/home_online_bridge test_serial_protocol.cpp -o t && ./t
cd esphome && esphome compile home-online-bridge.yaml
```

## License

MIT, see [LICENSE](LICENSE).

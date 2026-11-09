# Changelog

## 1.1.0
- Import slaves from a Domati `.bin` file (exported from the Home Online software): *Configure > Import slaves from a Domati .bin file*. Choose the slaves you want and add them as mappings in one action. The slaves are listed with their number, name and module (and input/output when the file says so); slaves that are already mapped are not offered again. A type is suggested per slave and can be changed. The file is not stored.
- Adds the `file_upload` dependency (needed to upload the file).
- Firmware: pause 500 ms between the handshake `o` and `O`. Sent back-to-back, the controller sometimes ignored the `O`, never started its heartbeat, and "Controller online" kept flapping.

## 1.0.0
- First public release: ESPHome serial bridge + Home Assistant integration (dimmers, curtains, relays, sensors).

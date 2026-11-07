# Changelog

## Unreleased
- Firmware: pause 500 ms between the handshake `o` and `O`. Sent back-to-back, the controller sometimes ignored the `O`, never started its heartbeat, and "Controller online" kept flapping.

## 1.0.0
- First public release: ESPHome serial bridge + Home Assistant integration (dimmers, curtains, relays, sensors).

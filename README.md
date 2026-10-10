# Home Assistant - MelView

A Home Assistant integration for Mitsubishi Electric air conditioners on
MelView ("Wi-Fi Control", the Australian and New Zealand service). Each unit
becomes a climate entity (power, mode, target temperature, fan speed, room
temperature, and outside temperature where the unit reports it), and each zone
of a ducted unit a switch.

This is a fork of [haggis663/ha-melview](https://github.com/haggis663/ha-melview)
(itself a fork of [zacharyrs/ha-melview](https://github.com/zacharyrs/ha-melview)),
reworked for current Home Assistant:

- fully async on one aiohttp session, so it never blocks the event loop
  (haggis663#11)
- one coordinator polls every unit every 30s; entities only read its cache
- local control works again: the command MelView encodes for the unit's own
  adapter is sent to it (haggis663#6 - the coroutine was never awaited)
- setting a temperature sets the target, not the room temperature
- modes, fan speeds and temperature limits come from what each unit reports
- reauthentication when the MelView password changes
- no YAML setup; add it in the UI

## Installing

HACS > Integrations > custom repositories: add
`https://github.com/jameswbaxter/ha-melview` as an Integration, download
MelView, restart Home Assistant, then add the MelView integration.

**Local control** also sends each command straight to the unit's Wi-Fi
adapter on your network, so it responds without waiting on the cloud. Status
always comes from the cloud.

## License

This project is licensed under the WTF License

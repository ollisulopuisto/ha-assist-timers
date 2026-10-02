# Changelog

All notable changes to this project are documented here. Versions follow [Calendar Versioning](https://calver.org/): `vYY.MM.DD.N`.

## [v26.10.02.2] - 2026-10-02

- Brand icon for the integration (shown in HACS and in Home Assistant's integration list).

## [v26.10.02.1] - 2026-10-02

First public release, extracted from a private Home Assistant setup where it ran in production.

- Lists the timers of every Assist satellite (`sensor.assist_timers`) from Home Assistant's own timer manager, with no firmware changes.
- Set a timer on a chosen satellite from the dashboard (`script.assist_timer_start`): form, or 1 / 5 / 10 min quick picks on a default satellite.
- Tap a timer to pause or resume it; tap a ringing one to stop the ring (`assist_timer_ring` integration).
- Gauge and list cards for button-card, header badges for Mushroom, English and Finnish following the UI language.
- "Done" state until the ring is dismissed (`sensor.assist_timers_finished`).
- `sensor.assist_timers_alexa` for Simple Timer Card.

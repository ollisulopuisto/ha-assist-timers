"""assist_timer_ring.restore: palauttaa tallennetut ajastimet HA:n käynnistyksessä (3.11.2026).

HA:n TimerManager on muistissa, joten restart tyhjentää listan. Palvelu luo jokaisen tallennetun
ajastimen uudelleen jäljellä olevalla ajalla samalle laitteelle ja nimellä. HA antaa uudelle
ajastimelle uuden id:n, joten satelliitille lähtee STARTED uudella id:llä. Pausoitu ajastin
palautetaan tauolle. Tuntematon laite tai ei-positiivinen aika ohitetaan eikä kaada palvelua.
"""

import pytest
from homeassistant.components.intent import TimerEventType, async_register_timer_handler
from homeassistant.components.intent.const import TIMER_DATA
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


@pytest.fixture
async def satellite(hass: HomeAssistant):
    assert await async_setup_component(hass, "intent", {})
    assert await async_setup_component(hass, "assist_timer_ring", {"assist_timer_ring": {}})
    events = []
    async_register_timer_handler(hass, "pe", lambda event, timer: events.append((event, timer.id, timer.is_active)))
    return events


async def test_restore_recreates_running_timer_with_name_and_remaining_time(hass: HomeAssistant, satellite) -> None:
    await hass.services.async_call(
        "assist_timer_ring", "restore",
        {"timers": [{"device_id": "pe", "name": "pasta", "seconds": 120, "paused": False}]},
        blocking=True,
    )
    timers = hass.data[TIMER_DATA].timers
    assert len(timers) == 1
    timer = next(iter(timers.values()))
    assert timer.name == "pasta"
    assert timer.device_id == "pe"
    assert timer.is_active
    assert 115 <= timer.seconds_left <= 120
    assert satellite[-1][0] == TimerEventType.STARTED


async def test_restore_keeps_paused_timer_paused(hass: HomeAssistant, satellite) -> None:
    await hass.services.async_call(
        "assist_timer_ring", "restore",
        {"timers": [{"device_id": "pe", "name": "pyykki", "seconds": 600, "paused": True}]},
        blocking=True,
    )
    timer = next(iter(hass.data[TIMER_DATA].timers.values()))
    assert timer.name == "pyykki"
    assert not timer.is_active


async def test_restore_skips_unknown_device_and_expired_timers(hass: HomeAssistant, satellite) -> None:
    await hass.services.async_call(
        "assist_timer_ring", "restore",
        {"timers": [
            {"device_id": "tuntematon", "name": "x", "seconds": 300, "paused": False},
            {"device_id": "pe", "name": "y", "seconds": 0, "paused": False},
            {"device_id": "pe", "name": "z", "seconds": -5, "paused": False},
            {"device_id": "pe", "name": "ok", "seconds": 60, "paused": False},
        ]},
        blocking=True,
    )
    names = sorted(t.name for t in hass.data[TIMER_DATA].timers.values())
    assert names == ["ok"]

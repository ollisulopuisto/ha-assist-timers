"""assist_timer_ring.cancel: peru yksi ajastin id:llä (kojelaudan X-nappi).

HA:n TimerManager.cancel_timer poistaa ajastimen ja ilmoittaa CANCELLED satelliitille.
Palvelu on kääre samalle by_id-reitille kuin pause/unpause.
"""

import json
from pathlib import Path

import pytest
from homeassistant.components.intent import TimerEventType, async_register_timer_handler
from homeassistant.components.intent.const import TIMER_DATA
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component

BASE = Path(__file__).parent.parent / "custom_components/assist_timer_ring"


@pytest.fixture
async def satellite_timers(hass: HomeAssistant):
    assert await async_setup_component(hass, "intent", {})
    assert await async_setup_component(hass, "assist_timer_ring", {"assist_timer_ring": {}})
    events = []
    async_register_timer_handler(hass, "pe", lambda event, timer: events.append((event, timer.id, timer.is_active)))
    await intent.async_handle(hass, "test", intent.INTENT_START_TIMER, {"minutes": {"value": 5}}, device_id="pe")
    return events[0][1], events


async def test_cancel_removes_timer_and_tells_satellite(hass: HomeAssistant, satellite_timers) -> None:
    timer_id, events = satellite_timers
    manager = hass.data[TIMER_DATA]
    await hass.services.async_call("assist_timer_ring", "cancel", {"timer_id": timer_id}, blocking=True)
    assert events[-1][0] == TimerEventType.CANCELLED
    assert events[-1][1] == timer_id
    assert timer_id not in manager.timers


async def test_cancel_unknown_timer_raises(hass: HomeAssistant, satellite_timers) -> None:
    with pytest.raises(HomeAssistantError, match="Timer nope not found"):
        await hass.services.async_call("assist_timer_ring", "cancel", {"timer_id": "nope"}, blocking=True)


def test_cancel_is_in_services_yaml_and_both_translations() -> None:
    import yaml

    services = yaml.safe_load((BASE / "services.yaml").read_text(encoding="utf-8"))
    assert "cancel" in services and "timer_id" in services["cancel"]["fields"]
    for lang in ("en", "fi"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        assert "cancel" in tr["services"], f"{lang}.json: services.cancel puuttuu"
        assert "timer_id" in tr["services"]["cancel"]["fields"], f"{lang}.json: timer_id-kenttä puuttuu"

"""custom_components/assist_timer_ring: stop a satellite's timer ring from HA.

HA's media_player.media_stop sends STOP to the ESPHome *media* pipeline; the timer
ring plays on the *announcement* pipeline, so it keeps ringing. This service sends
STOP with announcement=true, which is what the Voice PE firmware itself does.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import homeassistant
import pytest
from aioesphomeapi import MediaPlayerCommand
from homeassistant.components.media_player import DATA_COMPONENT, MediaPlayerEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component


class FakeEsphomePlayer(MediaPlayerEntity):
    """Carries the same private fields as HA's EsphomeMediaPlayer."""

    _attr_name = "Keittiö media player"
    _attr_unique_id = "pe-media"

    def __init__(self) -> None:
        self._key = 1234
        self._client = MagicMock()
        self._static_info = SimpleNamespace(device_id=0)


class OtherPlayer(MediaPlayerEntity):
    _attr_name = "Sonos"
    _attr_unique_id = "sonos"


@pytest.fixture
async def players(hass: HomeAssistant):
    assert await async_setup_component(hass, "media_player", {})
    esphome, other = FakeEsphomePlayer(), OtherPlayer()
    await hass.data[DATA_COMPONENT].async_add_entities([esphome, other])
    assert await async_setup_component(hass, "assist_timer_ring", {"assist_timer_ring": {}})
    await hass.async_block_till_done()
    return esphome, other


async def test_stop_targets_the_announcement_pipeline(hass: HomeAssistant, players) -> None:
    esphome, _ = players
    await hass.services.async_call("assist_timer_ring", "stop", {"entity_id": esphome.entity_id}, blocking=True)
    esphome._client.media_player_command.assert_called_once_with(
        1234, command=MediaPlayerCommand.STOP, announcement=True, device_id=0
    )


async def test_non_esphome_player_is_refused(hass: HomeAssistant, players) -> None:
    _, other = players
    with pytest.raises(HomeAssistantError, match="ESPHome"):
        await hass.services.async_call("assist_timer_ring", "stop", {"entity_id": other.entity_id}, blocking=True)


def test_ha_esphome_media_player_still_has_the_fields_we_use() -> None:
    """Fails when an HA upgrade renames the private fields this integration relies on."""
    src = (Path(homeassistant.__file__).parent / "components/esphome/media_player.py").read_text()
    stop = src[src.index("async def async_media_stop") :][:400]
    for needed in ("self._client.media_player_command(", "self._key", "self._static_info.device_id"):
        assert needed in stop, needed


@pytest.fixture
async def satellite_timers(hass: HomeAssistant):
    """Real intent TimerManager with one ESPHome-like satellite listening."""
    from homeassistant.components.intent import async_register_timer_handler
    from homeassistant.helpers import intent

    assert await async_setup_component(hass, "intent", {})
    assert await async_setup_component(hass, "assist_timer_ring", {"assist_timer_ring": {}})
    events = []
    async_register_timer_handler(hass, "pe", lambda event, timer: events.append((event, timer.id, timer.is_active)))
    await intent.async_handle(hass, "test", intent.INTENT_START_TIMER, {"minutes": {"value": 5}}, device_id="pe")
    timer_id = events[0][1]
    return timer_id, events


async def test_pause_and_unpause_by_timer_id(hass: HomeAssistant, satellite_timers) -> None:
    from homeassistant.components.intent import TimerEventType

    timer_id, events = satellite_timers
    await hass.services.async_call("assist_timer_ring", "pause", {"timer_id": timer_id}, blocking=True)
    assert events[-1] == (TimerEventType.UPDATED, timer_id, False)
    await hass.services.async_call("assist_timer_ring", "unpause", {"timer_id": timer_id}, blocking=True)
    assert events[-1] == (TimerEventType.UPDATED, timer_id, True)


async def test_pause_unknown_timer_raises(hass: HomeAssistant, satellite_timers) -> None:
    with pytest.raises(HomeAssistantError, match="Timer nope not found"):
        await hass.services.async_call("assist_timer_ring", "pause", {"timer_id": "nope"}, blocking=True)


def test_translations_cover_services_and_errors() -> None:
    """English and Finnish translation files carry the same keys."""
    import json

    base = Path(__file__).parent.parent / "custom_components/assist_timer_ring/translations"
    en, fi = (json.loads((base / f"{lang}.json").read_text()) for lang in ("en", "fi"))

    def keys(d, prefix=""):
        return {prefix + k for k, v in d.items()} | {x for k, v in d.items() if isinstance(v, dict) for x in keys(v, f"{prefix}{k}.")}

    assert keys(en) == keys(fi)
    assert set(en["services"]) == {"stop", "pause", "unpause"}
    assert set(en["exceptions"]) == {"not_esphome", "timer_not_found"}

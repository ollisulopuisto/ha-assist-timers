"""Render the header badge templates with HA's real template engine."""

from pathlib import Path

import pytest
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import MockConfigEntry

BADGES = yaml.safe_load((Path(__file__).parent.parent / "cards" / "header-badges.yaml").read_text())


def timer(**kw):
    base = {"id": "t", "name": "", "device_id": "", "is_active": True, "total_seconds_left": 0}
    return base | kw


async def render(hass: HomeAssistant, badge: dict) -> dict[str, str]:
    return {k: Template(badge[k], hass).async_render(parse_result=False).strip() for k in ("content", "label", "color")}


@pytest.fixture
def kitchen(hass: HomeAssistant) -> str:
    entry = MockConfigEntry(domain="esphome")
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("esphome", "kitchen")}, name="Home Assistant Voice 0a1b2c"
    )
    area = ar.async_get(hass).async_create("Keittiö")
    return registry.async_update_device(device.id, name_by_user="Keittiön Voice PE", area_id=area.id).id


async def test_badges_sorted_and_formatted(hass: HomeAssistant, kitchen: str) -> None:
    hass.states.async_set(
        "sensor.assist_timers",
        "3",
        {
            "timers": [
                timer(name="uuni", total_seconds_left=3725, is_active=False),
                timer(name="pasta", total_seconds_left=185, device_id=kitchen),
                timer(total_seconds_left=9),
            ]
        },
    )
    first, second, third = [await render(hass, b) for b in BADGES[:3]]
    assert first == {"content": "0:09", "label": "", "color": "orange"}
    assert second == {"content": "pasta 3:05", "label": "Keittiö", "color": "orange"}
    assert third == {"content": "uuni 1:02:05 ⏸", "label": "", "color": "grey"}


async def test_badges_visible_only_for_existing_timers() -> None:
    assert [b["visibility"][0]["above"] for b in BADGES[:3]] == [0, 1, 2]
    assert BADGES[3]["visibility"][0] == {"condition": "numeric_state", "entity": "sensor.assist_timers_finished", "above": 0}


@pytest.mark.parametrize("state", [("0", {"timers": []}), ("unavailable", {})])
async def test_no_timers_renders_empty(hass: HomeAssistant, state) -> None:
    hass.states.async_set("sensor.assist_timers", *state)
    for badge in BADGES[:3]:
        assert (await render(hass, badge))["content"] == ""


async def test_finished_badge(hass: HomeAssistant, kitchen: str) -> None:
    hass.states.async_set(
        "sensor.assist_timers_finished",
        "2",
        {"finished": [{"id": "a", "name": "pasta", "device_id": kitchen}, {"id": "b", "name": "", "device_id": ""}]},
    )
    assert await render(hass, BADGES[3]) == {"content": "pasta done", "label": "Keittiö", "color": "green"}


async def test_finished_badge_unnamed(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.assist_timers_finished", "1", {"finished": [{"id": "b", "name": "", "device_id": ""}]})
    assert (await render(hass, BADGES[3]))["content"] == "Done"


async def test_finished_badge_tap_dismisses() -> None:
    assert BADGES[3]["tap_action"] == {"action": "perform-action", "perform_action": "script.assist_timers_dismiss"}

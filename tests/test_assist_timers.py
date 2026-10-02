"""End-to-end tests for the assist_timers.yaml package against a real HA core.

The satellite is simulated the same way ESPHome registers one: a timer handler
for its device_id. Timers are started through the real HassStartTimer intent,
the package's rest sensor polls the real /api/intent/handle view over HTTP with
a real access token, and edits go through the package's rest_command.
"""

from pathlib import Path

import pytest
from homeassistant.components.intent import TimerEventType, async_register_timer_handler
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import Secrets, load_yaml

PACKAGE = Path(__file__).parent.parent / "packages" / "assist_timers.yaml"
SENSOR = "sensor.assist_timers"
KITCHEN = "device-kitchen"
# The rest coordinator's refresh debouncer outlives a test; harmless here.
pytestmark = pytest.mark.parametrize("expected_lingering_timers", [True])
LIVING_ROOM = "device-living-room"


@pytest.fixture
async def setup(hass: HomeAssistant, hass_client, hass_access_token, tmp_path, socket_enabled):
    """Set up intent + the package, pointed at HA's own test HTTP server."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "intent", {})
    client = await hass_client()

    events: list[tuple[str, TimerEventType, str]] = []
    for device_id in (KITCHEN, LIVING_ROOM):
        async_register_timer_handler(
            hass,
            device_id,
            lambda event, timer, device_id=device_id: events.append((device_id, event, timer.name)),
        )

    async def start(device_id: str, name: str | None = None, minutes: int = 5) -> None:
        slots = {"minutes": {"value": minutes}}
        if name:
            slots["name"] = {"value": name}
        await intent.async_handle(hass, "test", intent.INTENT_START_TIMER, slots, device_id=device_id)

    async def load(token: str = hass_access_token) -> None:
        (tmp_path / "secrets.yaml").write_text(
            f'assist_timers_intent_url: "{client.make_url("/api/intent/handle")}"\n'
            f'assist_timers_bearer: "Bearer {token}"\n'
        )
        (tmp_path / PACKAGE.name).write_text(PACKAGE.read_text())
        package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
        assert await async_setup_component(hass, "rest", {"rest": package["rest"]})
        assert await async_setup_component(hass, "rest_command", {"rest_command": package["rest_command"]})
        await hass.async_block_till_done()

    async def refresh() -> None:
        await hass.services.async_call("homeassistant", "update_entity", {"entity_id": SENSOR}, blocking=True)
        await hass.async_block_till_done()

    async def command(intent_name: str, data: dict) -> dict:
        res = await hass.services.async_call(
            "rest_command",
            "assist_timer_intent",
            {"intent": intent_name, "data": data},
            blocking=True,
            return_response=True,
        )
        await hass.async_block_till_done()
        return res

    return {"start": start, "load": load, "refresh": refresh, "command": command, "events": events}


async def test_no_timers(hass: HomeAssistant, setup) -> None:
    await setup["load"]()
    state = hass.states.get(SENSOR)
    assert state.state == "0"
    assert state.attributes["timers"] == []


async def test_lists_timers_from_all_satellites(hass: HomeAssistant, setup) -> None:
    await setup["start"](KITCHEN, "pasta", 10)
    await setup["start"](LIVING_ROOM, None, 3)
    await setup["load"]()

    state = hass.states.get(SENSOR)
    assert state.state == "2"
    timers = {t["device_id"]: t for t in state.attributes["timers"]}
    assert timers.keys() == {KITCHEN, LIVING_ROOM}
    assert timers[KITCHEN]["name"] == "pasta"
    assert timers[KITCHEN]["is_active"] is True
    assert 590 <= timers[KITCHEN]["total_seconds_left"] <= 600
    assert timers[LIVING_ROOM]["name"] == ""
    assert timers[LIVING_ROOM]["id"]


async def test_new_timer_appears_on_next_poll(hass: HomeAssistant, setup) -> None:
    await setup["load"]()
    assert hass.states.get(SENSOR).state == "0"
    await setup["start"](KITCHEN, "uuni", 20)
    await setup["refresh"]()
    assert hass.states.get(SENSOR).state == "1"


async def test_pause_reaches_satellite_and_sensor(hass: HomeAssistant, setup) -> None:
    await setup["start"](KITCHEN, "pasta", 10)
    await setup["load"]()

    res = await setup["command"](intent.INTENT_PAUSE_TIMER, {"name": "pasta"})
    assert res["status"] == 200
    assert res["content"]["response_type"] != "error"
    assert (KITCHEN, TimerEventType.UPDATED, "pasta") in setup["events"]

    await setup["refresh"]()
    assert hass.states.get(SENSOR).attributes["timers"][0]["is_active"] is False


async def test_cancel_reaches_satellite_and_sensor(hass: HomeAssistant, setup) -> None:
    await setup["start"](KITCHEN, "pasta", 10)
    await setup["start"](LIVING_ROOM, "sauna", 30)
    await setup["load"]()

    await setup["command"](intent.INTENT_CANCEL_TIMER, {"name": "sauna"})
    assert (LIVING_ROOM, TimerEventType.CANCELLED, "sauna") in setup["events"]

    await setup["refresh"]()
    state = hass.states.get(SENSOR)
    assert state.state == "1"
    assert state.attributes["timers"][0]["name"] == "pasta"


async def test_add_time(hass: HomeAssistant, setup) -> None:
    await setup["start"](KITCHEN, "pasta", 10)
    await setup["load"]()
    await setup["command"](intent.INTENT_INCREASE_TIMER, {"name": "pasta", "minutes": 5})
    await setup["refresh"]()
    assert hass.states.get(SENSOR).attributes["timers"][0]["total_seconds_left"] > 890


async def test_bad_token_makes_sensor_unavailable(hass: HomeAssistant, setup) -> None:
    """A rejected request must not read as 'no timers'."""
    await setup["start"](KITCHEN, "pasta", 10)
    await setup["load"](token="not-a-valid-token")
    assert hass.states.get(SENSOR).state == "unavailable"


async def test_start_timer_from_ha_on_a_satellite(hass: HomeAssistant, setup, tmp_path) -> None:
    """script.assist_timer_start: HA's timer manager starts it on the chosen satellite,
    which gets the same START event as a voice-started timer (LED ring, ring at the end)."""
    await setup["load"]()
    package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
    assert await async_setup_component(hass, "script", {"script": package["script"]})

    await hass.services.async_call(
        "script", "assist_timer_start", {"satellite": LIVING_ROOM, "minutes": 3, "name": "pasta"}, blocking=True
    )
    await hass.async_block_till_done()
    assert (LIVING_ROOM, TimerEventType.STARTED, "pasta") in setup["events"]

    await setup["refresh"]()
    [t] = hass.states.get(SENSOR).attributes["timers"]
    assert t["device_id"] == LIVING_ROOM
    assert t["name"] == "pasta"
    assert 175 <= t["total_seconds_left"] <= 180


async def test_start_timer_seconds_only_and_unnamed(hass: HomeAssistant, setup, tmp_path) -> None:
    await setup["load"]()
    package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
    assert await async_setup_component(hass, "script", {"script": package["script"]})
    await hass.services.async_call(
        "script", "assist_timer_start", {"satellite": KITCHEN, "minutes": 0, "seconds": 45}, blocking=True
    )
    await setup["refresh"]()
    [t] = hass.states.get(SENSOR).attributes["timers"]
    assert t["device_id"] == KITCHEN
    assert t["name"] == ""
    assert 40 <= t["total_seconds_left"] <= 45


async def test_start_timer_rejects_zero_duration(hass: HomeAssistant, setup, tmp_path) -> None:
    await setup["load"]()
    package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
    assert await async_setup_component(hass, "script", {"script": package["script"]})
    await hass.services.async_call("script", "assist_timer_start", {"satellite": KITCHEN, "minutes": 0}, blocking=True)
    await hass.async_block_till_done()
    assert not any(e[1] == TimerEventType.STARTED for e in setup["events"])

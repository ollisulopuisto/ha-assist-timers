"""The package's template sensors, run in real HA core.

- sensor.assist_timers_alexa: Alexa-style attributes so Simple Timer Card can show
  Assist timers. Checked against the card's own parser (tests/vendor, MIT).
- sensor.assist_timers_finished: timers that ran out in the last minute, so a
  dashboard can show "valmis" instead of the row silently vanishing.
"""

import json
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import Secrets, load_yaml
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

PACKAGE = Path(__file__).parent.parent / "packages" / "assist_timers.yaml"
VENDOR = Path(__file__).parent / "vendor" / "simple_timer_card_alexa.js"
SOURCE = "sensor.assist_timers"
ALEXA = "sensor.assist_timers_alexa"
FINISHED = "sensor.assist_timers_finished"

pytestmark = pytest.mark.parametrize("expected_lingering_timers", [True])


def timer(**kw):
    base = {
        "id": "t1",
        "name": "",
        "device_id": "",
        "is_active": True,
        "total_seconds_left": 100,
        "start_hours": 0,
        "start_minutes": 5,
        "start_seconds": 0,
    }
    return base | kw


@pytest.fixture
async def setup(hass: HomeAssistant, tmp_path):
    (tmp_path / "secrets.yaml").write_text('assist_timers_intent_url: "x"\nassist_timers_bearer: "x"\n')
    (tmp_path / PACKAGE.name).write_text(PACKAGE.read_text())
    package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
    hass.states.async_set(SOURCE, "0", {"timers": []})
    assert await async_setup_component(hass, "template", {"template": package["template"]})
    await hass.async_block_till_done()

    async def publish(timers, state=None):
        hass.states.async_set(SOURCE, state if state is not None else str(len(timers)), {"timers": timers} if timers is not None else {})
        await hass.async_block_till_done()

    return publish


def parse_like_simple_timer_card(state) -> list[dict]:
    """Run the real Simple Timer Card _parseAlexa on our entity."""
    entity = {"state": state.state, "attributes": dict(state.attributes), "last_updated": state.last_updated.isoformat()}
    js = f"""
    const {{ SimpleTimerCardAlexa }} = require({json.dumps(str(VENDOR))});
    const card = Object.assign(new SimpleTimerCardAlexa(), {{
      _sanitizeText: (s) => String(s), _cleanFriendlyName: (s) => s, _formatDurationDisplay: (ms) => `${{ms}}ms`,
    }});
    process.stdout.write(JSON.stringify(card._parseAlexa({json.dumps(ALEXA)}, {json.dumps(entity, default=str)}, {{}})));
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


async def test_alexa_sensor_parses_in_simple_timer_card(hass: HomeAssistant, setup) -> None:
    entry = MockConfigEntry(domain="esphome")
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    device = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("esphome", "k")}, name="Voice PE")
    registry.async_update_device(device.id, name_by_user="Keittiö")

    await setup(
        [
            timer(id="a", name="pasta", device_id=device.id, total_seconds_left=185, start_minutes=10),
            timer(id="b", is_active=False, total_seconds_left=3600, start_hours=2, start_minutes=0),
        ]
    )
    polled_ms = dt_util.as_timestamp(hass.states.get(SOURCE).last_updated) * 1000

    state = hass.states.get(ALEXA)
    assert state.state == "2"
    rows = {r["id"]: r for r in parse_like_simple_timer_card(state)}

    assert rows["a"]["label"] == "pasta · Keittiö"
    assert rows["a"]["paused"] is False
    assert abs(rows["a"]["end"] - (polled_ms + 185_000)) < 1000
    assert rows["a"]["duration"] == 600_000

    assert rows["b"]["label"] == "Timer"
    assert rows["b"]["paused"] is True
    assert rows["b"]["end"] == 3_600_000  # paused: remaining ms
    assert rows["b"]["duration"] == 7_200_000


async def test_alexa_sensor_follows_source_availability(hass: HomeAssistant, setup) -> None:
    await setup(None, state="unavailable")
    assert hass.states.get(ALEXA).state == "unavailable"


async def test_finished_timer_is_listed_for_a_minute(
    hass: HomeAssistant, setup, freezer: FrozenDateTimeFactory
) -> None:
    await setup([timer(id="a", name="pasta", total_seconds_left=4), timer(id="b", name="uuni", total_seconds_left=900)])
    freezer.tick(timedelta(seconds=5))
    await setup([timer(id="b", name="uuni", total_seconds_left=895)])

    state = hass.states.get(FINISHED)
    assert state.state == "1"
    assert [f["name"] for f in state.attributes["finished"]] == ["pasta"]

    # Kept across later updates (the sensor carries its own history in `this`).
    freezer.tick(timedelta(seconds=15))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    await setup([timer(id="b", name="uuni", total_seconds_left=880)])
    assert hass.states.get(FINISHED).state == "1"

    freezer.tick(timedelta(seconds=50))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(FINISHED).state == "0"


async def test_cancelled_timer_is_not_finished(hass: HomeAssistant, setup, freezer: FrozenDateTimeFactory) -> None:
    await setup([timer(id="a", name="pasta", total_seconds_left=300)])
    freezer.tick(timedelta(seconds=5))
    await setup([])
    assert hass.states.get(FINISHED).state == "0"


async def test_paused_timer_disappearing_is_not_finished(
    hass: HomeAssistant, setup, freezer: FrozenDateTimeFactory
) -> None:
    await setup([timer(id="a", is_active=False, total_seconds_left=3)])
    freezer.tick(timedelta(seconds=5))
    await setup([])
    assert hass.states.get(FINISHED).state == "0"


async def test_poll_failure_is_not_finished(hass: HomeAssistant, setup, freezer: FrozenDateTimeFactory) -> None:
    """Timers vanishing because the sensor went unavailable did not ring."""
    await setup([timer(id="a", total_seconds_left=2)])
    freezer.tick(timedelta(seconds=5))
    await setup(None, state="unavailable")
    assert hass.states.get(FINISHED).state == "0"


@pytest.fixture
def satellite(hass: HomeAssistant) -> tuple[str, str]:
    """A Voice PE-like device with its media player (the timer ring plays there)."""
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(domain="esphome")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("esphome", "pe")})
    player = er.async_get(hass).async_get_or_create(
        "media_player", "esphome", "pe-media", device_id=device.id, config_entry=entry
    ).entity_id
    hass.states.async_set(player, "idle")
    return device.id, player


async def tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_finished_stays_until_ring_is_dismissed(
    hass: HomeAssistant, setup, satellite, freezer: FrozenDateTimeFactory
) -> None:
    device_id, player = satellite
    await setup([timer(id="a", name="pasta", device_id=device_id, total_seconds_left=3)])
    await tick(hass, freezer, 3)
    hass.states.async_set(player, "playing")  # ring starts
    await tick(hass, freezer, 2)
    await setup([])
    assert hass.states.get(FINISHED).state == "1"

    await tick(hass, freezer, 120)  # still ringing after two minutes
    assert hass.states.get(FINISHED).state == "1"

    hass.states.async_set(player, "idle")  # dismissed on the satellite
    await tick(hass, freezer, 5)
    assert hass.states.get(FINISHED).state == "0"


async def test_ring_dismissed_before_poll_noticed(
    hass: HomeAssistant, setup, satellite, freezer: FrozenDateTimeFactory
) -> None:
    """Ring stopped within the 5 s poll gap: still counts as dismissed."""
    device_id, player = satellite
    await setup([timer(id="a", device_id=device_id, total_seconds_left=1)])
    await tick(hass, freezer, 1)
    hass.states.async_set(player, "playing")
    await tick(hass, freezer, 2)
    hass.states.async_set(player, "idle")
    await tick(hass, freezer, 2)
    await setup([])
    await tick(hass, freezer, 5)
    assert hass.states.get(FINISHED).state == "0"


async def test_ringing_gives_up_after_15_minutes(
    hass: HomeAssistant, setup, satellite, freezer: FrozenDateTimeFactory
) -> None:
    """Voice PE stops ringing by itself after 15 min; so does the badge."""
    device_id, player = satellite
    await setup([timer(id="a", device_id=device_id, total_seconds_left=2)])
    await tick(hass, freezer, 2)
    hass.states.async_set(player, "playing")
    await tick(hass, freezer, 3)
    await setup([])
    await tick(hass, freezer, 14 * 60)
    assert hass.states.get(FINISHED).state == "1"
    await tick(hass, freezer, 61)
    assert hass.states.get(FINISHED).state == "0"


async def test_dismiss_script_stops_ringing_satellites(
    hass: HomeAssistant, setup, satellite, tmp_path, freezer: FrozenDateTimeFactory
) -> None:
    """Tapping a finished timer in HA stops the ring on the satellite's media player;
    the finished entry then clears by itself."""
    from pytest_homeassistant_custom_component.common import async_mock_service

    device_id, player = satellite
    stops = async_mock_service(hass, "assist_timer_ring", "stop")
    package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
    assert await async_setup_component(hass, "script", {"script": package["script"]})

    await setup([timer(id="a", device_id=device_id, total_seconds_left=2)])
    await tick(hass, freezer, 2)
    hass.states.async_set(player, "playing")
    await tick(hass, freezer, 3)
    await setup([])
    assert hass.states.get(FINISHED).state == "1"

    await hass.services.async_call("script", "assist_timers_dismiss", blocking=True)
    await hass.async_block_till_done()
    assert [c.data["entity_id"] for c in stops] == [[player]]

    hass.states.async_set(player, "idle")  # what the stop does on the device
    # Longer than the /2 s re-check, whatever the sub-second phase of the test clock.
    await tick(hass, freezer, 5)
    assert hass.states.get(FINISHED).state == "0"


async def test_dismiss_script_without_finished_timers_does_nothing(hass: HomeAssistant, setup, tmp_path) -> None:
    from pytest_homeassistant_custom_component.common import async_mock_service

    stops = async_mock_service(hass, "assist_timer_ring", "stop")
    package = load_yaml(tmp_path / PACKAGE.name, Secrets(tmp_path))
    assert await async_setup_component(hass, "script", {"script": package["script"]})
    await hass.services.async_call("script", "assist_timers_dismiss", blocking=True)
    assert stops == []

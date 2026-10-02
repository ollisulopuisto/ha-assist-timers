"""cards/timer-gauge.yaml: one half-circle gauge per timer, mm:ss in the middle."""

import json
import re
import subprocess

import pytest
import yaml


def card_js() -> str:
    with open("cards/timer-gauge.yaml") as f:
        card = yaml.safe_load(f)
    return card["custom_fields"]["timers"].strip().removeprefix("[[[").removesuffix("]]]")


def render(entity, hass=None, age_s: float = 0.0, states=None) -> str:
    js = f"""
    const entity = {json.dumps(entity)};
    if (entity) entity.last_updated = new Date(Date.now() - {age_s * 1000}).toISOString();
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(card_js())});
    process.stdout.write(String(fn({json.dumps(states or {})}, entity, {{}}, {json.dumps({"language": "fi", **(hass or {})})}, {{}}, () => '', {{}})));
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    return res.stdout


def gauges(html: str) -> list[dict]:
    out = []
    for state, progress, body in re.findall(
        r'<div class="gauge" data-state="(\w+)" data-progress="([\d.]+)"[^>]*>(.*?)<!--/gauge-->', html, re.S
    ):
        text = " ".join(re.sub(r"<[^>]+>", " ", body).split())
        out.append({"state": state, "progress": float(progress), "text": text})
    return out


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", "", html, flags=re.S)).split())


HASS = {"devices": {"dev1": {"name": "Voice PE", "area_id": "keittio"}}, "areas": {"keittio": {"name": "Keittiö"}}}


def timer(**kw):
    base = {"id": "t1", "name": "", "device_id": "dev1", "is_active": True, "total_seconds_left": 185,
            "start_hours": 0, "start_minutes": 10, "start_seconds": 0}
    return base | kw


def sensor(timers, state=None):
    return {"state": state if state is not None else str(len(timers)), "attributes": {"timers": timers}}


def test_running_gauge_shows_minutes_and_seconds():
    [g] = gauges(render(sensor([timer(name="pasta", total_seconds_left=412)]), HASS, age_s=5))
    assert g["state"] == "running"
    assert g["text"] == "6:47 pasta Keittiö"
    assert g["progress"] == pytest.approx(407 / 600 * 100, abs=0.5)


def test_unnamed_gauge_is_titled_by_duration_and_hours_shown():
    [g] = gauges(render(sensor([timer(start_hours=2, start_minutes=0, total_seconds_left=3725)]), HASS))
    assert g["text"] == "1:02:05 2 h Keittiö"


def test_paused_and_ending_states():
    out = gauges(render(sensor([timer(id="a", is_active=False, total_seconds_left=100),
                                timer(id="b", total_seconds_left=6)])))
    assert [g["state"] for g in out] == ["ending", "paused"]
    assert out[1]["text"].startswith("1:40")


def test_finished_gauge_is_full_and_says_valmis():
    states = {"sensor.assist_timers_finished": {"attributes": {"finished": [{"id": "x", "name": "munat", "device_id": "dev1"}]}}}
    [g] = gauges(render(sensor([]), HASS, states=states))
    assert g["state"] == "done"
    assert g["progress"] == 100
    assert g["text"] == "Valmis munat Keittiö · napauta kuitataksesi"


def test_empty_and_unavailable():
    assert gauges(render(sensor([]))) == []
    assert text(render(sensor([]))) == "Aseta ajastin 1 min 5 min 10 min"
    assert "ei saatavilla" in text(render(sensor([], state="unavailable")))


def test_names_are_html_escaped():
    out = render(sensor([timer(name="<img src=x onerror=alert(1)>")]))
    assert "<img" not in out


def test_empty_gauge_draws_no_dots():
    """Round caps on a zero-length dash drew a dot at each end of the track."""
    out = render(sensor([timer(id="z", total_seconds_left=0), timer(id="h", total_seconds_left=300)]))
    zero, half = re.findall(r'<div class="gauge".*?<!--/gauge-->', out, re.S)
    assert 'class="arc"' not in zero
    gap = float(re.search(r'stroke-dasharray="[\d.]+ ([\d.]+)"', half).group(1))
    assert gap > 100  # the dash pattern must not repeat at the far end



VISIBLE_WHEN_TIMERS = [
    {
        "condition": "or",
        "conditions": [
            {"condition": "numeric_state", "entity": "sensor.assist_timers", "above": 0},
            {"condition": "numeric_state", "entity": "sensor.assist_timers_finished", "above": 0},
        ],
    }
]


@pytest.mark.parametrize("path", ["cards/timer-list.yaml", "cards/timer-gauge.yaml"])
def test_card_always_visible(path):
    """Shown even with no timers: tapping it is how a timer is set from HA."""
    with open(path) as f:
        card = yaml.safe_load(f)
    assert "visibility" not in card



def render_card(path, entity):
    with open(path) as f:
        card = yaml.safe_load(f)
    code = card["custom_fields"]["timers"].strip().removeprefix("[[[").removesuffix("]]]")
    js = f"""
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(code)});
    process.stdout.write(String(fn.call(null, {{}}, {json.dumps(entity)}, {{}}, {{"language": "fi"}}, {{}}, () => '', {{}})));
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    return res.stdout


def click(path, action, timer_id=None, services=None):
    return click_with(path, {"action": action, "timerId": timer_id}, services)


def click_with(path, dataset, services=None):
    """Render as button-card does (this = the card), press an item, then run the card's tap_action:
    button-card swallows the item's own click, so the press is remembered on pointerdown."""
    with open(path) as f:
        card = yaml.safe_load(f)
    code = card["custom_fields"]["timers"].strip().removeprefix("[[[").removesuffix("]]]")
    tap = card["tap_action"]["javascript"].strip().removeprefix("[[[").removesuffix("]]]")
    entity = {"state": "0", "last_updated": "2026-10-02T06:00:00Z", "attributes": {"timers": []}}
    js = f"""
    const calls = [];
    const listeners = {{}};
    const card = {{
      shadowRoot: {{ addEventListener: (type, fn, capture) => {{
        (listeners[type] ||= []).push(fn); if (!capture) calls.push(['not-capture', type]); }} }},
      _hass: {{ language: 'fi', callService: (d, s, data) => calls.push(['service', d, s, data]),
                services: {json.dumps(services or {})} }},
    }};
    globalThis.window = {{ browser_mod: {{ showPopup: (o) => {{
      calls.push(['popup', o.title, o.content.map((c) => [c.name, c.default ?? null])]);
      o.right_button_action({{ minutes: 2, seconds: 0, satellite: 'kitchen', name: 'pasta' }});
    }} }} }};
    const args = [{{}}, {json.dumps(entity)}, {{}}, {{}}, {{}}, () => '', {{}}];
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(code)});
    fn.call(card, ...args);
    fn.call(card, ...args);  // re-render: still one listener
    if ((listeners.pointerdown || []).length !== 1) calls.push(['listeners', (listeners.pointerdown || []).length]);
    listeners.pointerdown[0]({{ composedPath: () => [{{}}, {{ dataset: {json.dumps(dataset)} }}] }});
    const tap = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                             "'use strict'; " + {json.dumps(tap)});
    tap.call(card, ...args);
    // a later tap on empty card space does nothing
    listeners.pointerdown[0]({{ composedPath: () => [{{}}] }});
    tap.call(card, ...args);
    process.stdout.write(JSON.stringify({{ calls }}));
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


CARDS = ["cards/timer-list.yaml", "cards/timer-gauge.yaml"]


@pytest.mark.parametrize("path", CARDS)
def test_click_running_timer_pauses_it(path):
    out = click(path, "pause", "t1")
    assert out == {"calls": [["service", "assist_timer_ring", "pause", {"timer_id": "t1"}]]}


@pytest.mark.parametrize("path", CARDS)
def test_click_paused_timer_resumes_it(path):
    assert click(path, "unpause", "t1")["calls"] == [["service", "assist_timer_ring", "unpause", {"timer_id": "t1"}]]


@pytest.mark.parametrize("path", CARDS)
def test_click_ringing_timer_dismisses(path):
    assert click(path, "dismiss")["calls"] == [["service", "script", "assist_timers_dismiss", {}]]


@pytest.mark.parametrize("path", CARDS)
def test_click_new_opens_popup_and_sets_timer(path):
    services = {"script": {"assist_timer_start": {"fields": {"satellite": {"default": "kitchen", "selector": {"device": {}}}}}}}
    out = click(path, "new", services=services)
    assert out["calls"] == [
        ["popup", "Aseta ajastin", [["minutes", 5], ["seconds", 0], ["satellite", "kitchen"], ["name", None]]],
        ["service", "script", "assist_timer_start", {"minutes": 2, "seconds": 0, "satellite": "kitchen", "name": "pasta"}],
    ]


@pytest.mark.parametrize("path", CARDS)
def test_tap_runs_the_pressed_items_action(path):
    with open(path) as f:
        card = yaml.safe_load(f)
    assert card["tap_action"]["action"] == "javascript"


def test_gauges_carry_their_click_action():
    states = {"sensor.assist_timers_finished": {"attributes": {"finished": [{"id": "d", "name": "", "device_id": ""}]}}}
    out = render(sensor([timer(id="r", total_seconds_left=300), timer(id="p", is_active=False, total_seconds_left=400)]),
                 states=states)
    actions = re.findall(r'data-action="(\w+)"(?: data-timer-id="([^"]*)")?', out)
    assert actions == [("dismiss", ""), ("pause", "r"), ("unpause", "p"), ("new", "")]


def test_empty_card_click_sets_a_timer():
    assert 'data-action="new"' in render(sensor([]))


@pytest.mark.parametrize("path", CARDS)
def test_quick_chip_sets_timer_on_default_satellite(path):
    services = {"script": {"assist_timer_start": {"fields": {"satellite": {"default": "kitchen"}}}}}
    with open(path) as f:
        pass
    out = click_with(path, {"action": "quick", "minutes": "5"}, services)
    assert out["calls"] == [["service", "script", "assist_timer_start", {"minutes": 5, "satellite": "kitchen"}]]


@pytest.mark.parametrize("path", CARDS)
def test_quick_chip_without_default_satellite_asks(path):
    out = click_with(path, {"action": "quick", "minutes": "10"}, {})
    assert out["calls"][0][0] == "popup"
    assert ["minutes", 10] in out["calls"][0][2]


@pytest.mark.parametrize("path", CARDS)
def test_idle_state_has_quick_chips(path):
    out = render_card(path, {"state": "0", "attributes": {"timers": []}})
    assert re.findall(r'data-action="quick" data-minutes="(\d+)"', out) == ["1", "5", "10"]


def test_english_gauges_and_popup():
    hass = {"language": "en", **HASS}
    states = {"sensor.assist_timers_finished": {"attributes": {"finished": [{"id": "d", "name": "", "device_id": "dev1"}]}}}
    out = gauges(render(sensor([timer(is_active=False, total_seconds_left=60)]), hass, states=states))
    assert out[0]["text"] == "Done Timer Keittiö · tap to dismiss"
    assert out[1]["text"] == "1:00 10 min Keittiö · paused"
    assert "New timer" in text(render(sensor([timer()]), hass))

import json
import re
import subprocess

import yaml


def card_js() -> str:
    with open("cards/timer-list.yaml") as f:
        card = yaml.safe_load(f)
    return card["custom_fields"]["timers"].strip().removeprefix("[[[").removesuffix("]]]")


def render(entity, hass=None, age_s: float = 0.0, states=None) -> str:
    """Evaluate the card template like button-card does, with the sensor updated age_s ago."""
    js = f"""
    const entity = {json.dumps(entity)};
    if (entity) entity.last_updated = new Date(Date.now() - {age_s * 1000}).toISOString();
    const hass = {json.dumps({"language": "fi", **(hass or {})})};
    const states = {json.dumps(states or {})};
    for (const s of Object.values(states)) {{
      for (const f of s.attributes?.finished || []) f.finished_at = Date.now() / 1000 - f.finished_at;
    }}
    // button-card evaluates a template as a function body with these parameters,
    // so the template must not redeclare any of them.
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(card_js())});
    process.stdout.write(String(fn(states, entity, {{}}, hass, {{}}, () => '', {{}})));
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    return res.stdout


def rows(html: str) -> list[dict]:
    """Each timer row as {state, text, progress}; text is the visible text, whitespace-collapsed."""
    out = []
    for state, body in re.findall(r'<div class="row" data-state="(\w+)"[^>]*>(.*?)<!--/row-->', html, re.S):
        body_no_style = re.sub(r"<style.*?</style>", "", body, flags=re.S)
        text = " ".join(re.sub(r"<[^>]+>", " ", body_no_style).split())
        bar = re.search(r'class="fill" style="width:\s*([\d.]+)%', body)
        out.append({"state": state, "text": text, "progress": float(bar.group(1)) if bar else None})
    return out


def text(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style.*?</style>", "", html, flags=re.S)).split())


HASS = {
    "devices": {"dev1": {"name": "Voice PE", "name_by_user": "Keittiön Voice", "area_id": "keittio"}},
    "areas": {"keittio": {"name": "Keittiö"}},
}


def timer(**kw):
    base = {
        "id": "t1",
        "name": "",
        "device_id": "dev1",
        "is_active": True,
        "total_seconds_left": 185,
        "start_hours": 0,
        "start_minutes": 10,
        "start_seconds": 0,
    }
    return base | kw


def sensor(timers, state=None):
    return {"state": state if state is not None else str(len(timers)), "attributes": {"timers": timers}}


def test_unavailable_is_not_shown_as_empty():
    assert "ei saatavilla" in text(render(sensor([], state="unavailable")))


def test_missing_entity():
    assert "ei saatavilla" in text(render(None))


def test_no_timers():
    out = render(sensor([]))
    assert rows(out) == []
    assert text(out) == "Aseta ajastin 1 min 5 min 10 min"


def test_running_timer_row():
    [row] = rows(render(sensor([timer(name="pasta", total_seconds_left=185)]), HASS, age_s=10))
    assert row["state"] == "running"
    assert row["text"] == "pasta Keittiö · 10 min 2:55"
    assert row["progress"] == pytest_approx(175 / 600 * 100)


def test_unnamed_timer_is_titled_by_its_duration():
    [row] = rows(render(sensor([timer(start_hours=1, start_minutes=30, total_seconds_left=59)]), HASS))
    assert row["text"] == "1 h 30 min Keittiö 0:59"


def test_paused_timer_does_not_count_down():
    [row] = rows(render(sensor([timer(name="uuni", is_active=False, total_seconds_left=3665, start_hours=2, start_minutes=0)]), age_s=30))
    assert row["state"] == "paused"
    assert row["text"] == "uuni 2 h · tauolla 1:01:05"


def test_last_ten_seconds_are_flagged():
    [row] = rows(render(sensor([timer(total_seconds_left=8)])))
    assert row["state"] == "ending"


def test_room_falls_back_to_device_name():
    hass = {"devices": {"dev1": {"name": "Voice PE", "name_by_user": None}}, "areas": {}}
    [row] = rows(render(sensor([timer(name="pasta", start_minutes=5, total_seconds_left=60)]), hass))
    assert row["text"] == "pasta Voice PE · 5 min 1:00"


def test_sorted_by_time_left_and_clamped_at_zero():
    timers = [timer(id="a", name="b", total_seconds_left=300), timer(id="b", name="a", total_seconds_left=3)]
    out = rows(render(sensor(timers), age_s=4))
    assert [r["text"].split()[0] for r in out] == ["a", "b"]
    assert out[0]["text"].endswith("0:00")
    assert out[1]["text"].endswith("4:56")


def test_stale_data_flagged_when_running():
    assert "vanhentunut" in text(render(sensor([timer(name="pasta")]), age_s=120))


def test_names_are_html_escaped():
    out = render(sensor([timer(name="<img src=x onerror=alert(1)>")]))
    assert "<img" not in out
    assert "&lt;img" in out


def finished(*items):
    """sensor.assist_timers_finished; finished_at given as seconds ago."""
    return {"sensor.assist_timers_finished": {"state": str(len(items)), "attributes": {"finished": list(items)}}}


def test_finished_timer_shows_valmis_first():
    states = finished({"id": "x", "name": "pasta", "device_id": "dev1", "finished_at": 10})
    out = rows(render(sensor([timer(name="uuni", total_seconds_left=65)]), HASS, states=states))
    assert [r["state"] for r in out] == ["done", "running"]
    assert out[0]["text"] == "pasta Keittiö · napauta kuitataksesi Valmis"


def test_finished_only():
    [row] = rows(render(sensor([]), states=finished({"id": "x", "name": "", "device_id": "", "finished_at": 5})))
    assert row["text"] == "Ajastin napauta kuitataksesi Valmis"


def test_finished_shown_while_sensor_lists_it():
    """The sensor drops the entry when the ring is dismissed; the card must not
    hide a still-ringing timer on its own clock."""
    out = rows(render(sensor([]), states=finished({"id": "x", "name": "pasta", "device_id": "", "finished_at": 300})))
    assert [r["state"] for r in out] == ["done"]


def test_tablet_clock_skew_is_cancelled_after_next_poll():
    """The tablet clock runs 4 s ahead of HA. Once a poll is seen arriving, the
    card measures that offset and counts from HA's clock, not the tablet's."""
    js = f"""
    let now = 1_800_000_000_000;
    Date.now = () => now;
    const skew = 4000;
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                           "'use strict'; " + {json.dumps(card_js())});
    const show = (polledAt, left) => fn({{}}, {{ state: '1', last_updated: new Date(polledAt).toISOString(),
      attributes: {{ timers: [{{ id: 'a', name: 'pasta', device_id: '', is_active: true, total_seconds_left: left,
        start_minutes: 2 }}] }} }},
      {{}}, {{}}, {{}}, () => '', {{}});
    const out = [];
    // Page opens; HA (clock = now - skew) polled just now with 100 s left.
    out.push(show(now - skew, 100));
    // Next poll arrives 5 s later with 95 s left; the card sees it immediately.
    now += 5000; out.push(show(now - skew, 95));
    // 2 s later, no new poll.
    now += 2000; out.push(show(now - 2000 - skew, 95));
    process.stdout.write(JSON.stringify(out));
    """
    res = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    first, synced, later = (rows(h)[0]["text"].split()[-1] for h in json.loads(res.stdout))
    assert first == "1:36"  # before any sync the 4 s skew still shows
    assert synced == "1:35"
    assert later == "1:33"


def pytest_approx(v):
    import pytest

    return pytest.approx(v, abs=0.5)



def test_rows_carry_their_click_action():
    states = {"sensor.assist_timers_finished": {"attributes": {"finished": [{"id": "d", "name": "", "device_id": ""}]}}}
    out = render(sensor([timer(id="r", total_seconds_left=300), timer(id="p", is_active=False, total_seconds_left=400)]),
                 states=states)
    actions = re.findall(r'data-action="(\w+)"(?: data-timer-id="([^"]*)")?', out)
    assert actions == [("dismiss", ""), ("pause", "r"), ("unpause", "p"), ("new", "")]
    assert 'data-action="new"' in render(sensor([]))


def test_english_ui():
    hass = {"language": "en", **HASS}
    states = {"sensor.assist_timers_finished": {"attributes": {"finished": [{"id": "d", "name": "", "device_id": "dev1"}]}}}
    out = rows(render(sensor([timer(name="pasta", is_active=False, total_seconds_left=60)]), hass, states=states))
    assert out[0]["text"] == "Timer Keittiö · tap to dismiss Done"
    assert out[1]["text"] == "pasta Keittiö · 10 min · paused 1:00"
    assert text(render(sensor([]), {"language": "en"})) == "Set a timer 1 min 5 min 10 min"
    assert "unavailable" in text(render(sensor([], state="unavailable"), {"language": "en"}))


def test_unknown_language_falls_back_to_english():
    assert text(render(sensor([]), {"language": "sv"})) == "Set a timer 1 min 5 min 10 min"

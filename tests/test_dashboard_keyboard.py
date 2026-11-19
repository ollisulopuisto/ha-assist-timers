"""Keyboard support shared by both cards: focus keys and surviving button-card's re-render."""

import json
import subprocess

import pytest
import yaml

CARDS = ["cards/timer-list.yaml", "cards/timer-gauge.yaml"]


def code(path: str) -> str:
    with open(path) as f:
        card = yaml.safe_load(f)
    return (
        card["custom_fields"]["timers"].strip().removeprefix("[[[").removesuffix("]]]")
    )


def render(path: str, entity: dict, states: dict | None = None) -> str:
    js = f"""
    const entity = {json.dumps(entity)};
    entity.last_updated = new Date().toISOString();
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(code(path))});
    process.stdout.write(String(fn({json.dumps(states or {})}, entity, {{}},
      {{"language": "en"}}, {{}}, () => '', {{}})));
    """
    res = subprocess.run(
        ["node", "-e", js], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stderr
    return res.stdout


def timer(**kw):
    base = {
        "id": "r",
        "name": "pasta",
        "device_id": "",
        "is_active": True,
        "total_seconds_left": 300,
        "start_minutes": 5,
    }
    return base | kw


def sensor(timers):
    return {
        "state": str(len(timers)),
        "last_updated": "2026-11-19T12:00:00Z",
        "attributes": {"timers": timers},
    }


def restore(
    path: str, *, focus_key: str, still_inside: bool = False, elsewhere: bool = False
) -> bool:
    """Evaluate the template with a control focused, then simulate button-card's re-render
    replacing the HTML, and return whether focus was put back on that same control."""
    js = f"""
    const frames = [];
    globalThis.setTimeout = (fn) => frames.push(fn);
    const body = {{}};
    globalThis.document = {{ body, activeElement: body }};
    const focused = {{ dataset: {{ focusKey: {json.dumps(focus_key)} }} }};
    const target = {{ dataset: {{ focusKey: {json.dumps(focus_key)} }},
      focus: () => (globalThis.refocused = true) }};
    const root = {{ activeElement: focused, addEventListener: () => {{}},
      querySelectorAll: () => [target] }};
    const card = {{ shadowRoot: root, _hass: {{ language: 'en', services: {{}} }} }};
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(code(path))});
    fn.call(card, {{}}, {json.dumps(sensor([timer()]))}, {{}}, {{"language": "en"}}, {{}}, () => '', {{}});
    root.activeElement = {"target" if still_inside else "null"};
    if ({json.dumps(elsewhere)}) document.activeElement = {{ tagName: 'BUTTON-CARD' }};
    frames.forEach((frame) => frame());
    process.stdout.write(JSON.stringify({{ refocused: !!globalThis.refocused }}));
    """
    res = subprocess.run(
        ["node", "-e", js], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)["refocused"]


@pytest.mark.parametrize("path", CARDS)
def test_each_control_has_a_stable_focus_key(path):
    states = {
        "sensor.assist_timers_finished": {
            "attributes": {"finished": [{"id": "d", "name": "eggs", "device_id": ""}]}
        }
    }
    out = render(path, sensor([timer()]), states=states)
    for key in ("done-d", "timer-r", "new"):
        assert f'data-focus-key="{key}"' in out
    idle = render(path, sensor([]))
    for key in ("new", "quick-1", "quick-5", "quick-10"):
        assert f'data-focus-key="{key}"' in idle


@pytest.mark.parametrize("path", CARDS)
def test_focus_returns_to_the_same_control_after_the_one_second_rerender(path):
    """button-card replaces the custom field's HTML every tick; focusing a row and
    waiting one tick used to drop focus to <body>."""
    assert restore(path, focus_key="timer-r") is True


@pytest.mark.parametrize("path", CARDS)
def test_focus_restore_does_not_steal_focus_from_another_control(path):
    assert restore(path, focus_key="timer-r", still_inside=True) is False


@pytest.mark.parametrize("path", CARDS)
def test_focus_restore_does_not_pull_focus_back_from_another_card(path):
    assert restore(path, focus_key="timer-r", elsewhere=True) is False


def activate(path: str, action: str) -> dict:
    """Press Enter on a row and return its action/label after the optimistic update."""
    js = f"""
    const listeners = {{}};
    const attrs = {{}};
    const target = {{
      dataset: {{ action: {json.dumps(action)}, timerId: 'r' }}, style: {{}},
      querySelector: (sel) => sel === '.title' ? {{ textContent: 'pasta' }} : {{ setAttribute: () => {{}} }},
      setAttribute: (k, v) => (attrs[k] = v),
    }};
    const card = {{
      shadowRoot: {{ addEventListener: (type, fn) => (listeners[type] ||= []).push(fn) }},
      _hass: {{ language: 'en', services: {{}}, callService: () => {{}} }},
    }};
    const fn = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', 'helpers',
                            "'use strict'; " + {json.dumps(code(path))});
    fn.call(card, {{}}, {json.dumps(sensor([timer()]))}, {{}}, {{"language": "en"}}, {{}}, () => '', {{}});
    listeners.keydown[0]({{ key: 'Enter', composedPath: () => [target],
      preventDefault: () => {{}} }});
    process.stdout.write(JSON.stringify({{ action: target.dataset.action,
      label: attrs['aria-label'] }}));
    """
    res = subprocess.run(
        ["node", "-e", js], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


@pytest.mark.parametrize("path", CARDS)
def test_optimistic_pause_updates_the_accessible_name(path):
    """The label must say what the next press does, not what the last one did."""
    assert activate(path, "pause") == {"action": "unpause", "label": "Resume pasta"}
    assert activate(path, "unpause") == {"action": "pause", "label": "Pause pasta"}

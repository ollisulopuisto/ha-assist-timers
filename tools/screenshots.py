"""Render the cards to docs/screenshots/ with the real card templates in headless Chrome.

The templates run exactly as button-card runs them; only the surroundings (theme colours,
ha-icon via the MDI webfont) are stand-ins for Home Assistant's frontend.

    uv run python tools/screenshots.py [path/to/chrome]
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
CHROME = sys.argv[1] if len(sys.argv) > 1 else "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

THEMES = {
    "dark": "--card:#1c1c1e;--bg:#111318;--primary-color:#03a9f4;--primary-text-color:#e1e1e1;"
    "--secondary-text-color:#9b9b9b;--divider-color:rgba(225,225,225,.12);--warning-color:#ff9800;--success-color:#43a047",
    "light": "--card:#ffffff;--bg:#f0f2f5;--primary-color:#03a9f4;--primary-text-color:#212121;"
    "--secondary-text-color:#727272;--divider-color:rgba(0,0,0,.12);--warning-color:#ff9800;--success-color:#43a047",
}
HASS = {
    "language": "en",
    "devices": {"k": {"name": "Voice PE", "area_id": "kitchen"}, "l": {"name": "Voice PE 2", "area_id": "living"}},
    "areas": {"kitchen": {"name": "Kitchen"}, "living": {"name": "Living room"}},
}


def timer(**kw):
    base = {"id": "x", "name": "", "device_id": "k", "is_active": True, "total_seconds_left": 0,
            "start_hours": 0, "start_minutes": 0, "start_seconds": 0}
    return base | kw


BUSY = [
    timer(id="a", name="pasta", total_seconds_left=412, start_minutes=10),
    timer(id="b", device_id="l", total_seconds_left=8, start_minutes=1),
    timer(id="c", name="oven", is_active=False, total_seconds_left=2925, start_hours=1),
]
RINGING = [{"id": "d", "name": "eggs", "device_id": "l"}]

SHOTS = [  # file, card, timers, ringing, theme, width
    ("gauge-dark.png", "timer-gauge.yaml", BUSY, RINGING, "dark", 430),
    ("gauge-light.png", "timer-gauge.yaml", BUSY, RINGING, "light", 430),
    ("list-dark.png", "timer-list.yaml", BUSY, RINGING, "dark", 400),
    ("idle-dark.png", "timer-gauge.yaml", [], [], "dark", 430),
]


def page(card_file, timers, ringing, theme, width):
    js = yaml.safe_load((ROOT / "cards" / card_file).read_text())["custom_fields"]["timers"]
    js = js.strip().removeprefix("[[[").removesuffix("]]]")
    entity = {"state": str(len(timers)), "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "attributes": {"timers": timers}}
    states = {"sensor.assist_timers_finished": {"attributes": {"finished": ringing}}}
    return f"""<!doctype html><meta charset=utf-8>
<link rel=stylesheet href="https://cdnjs.cloudflare.com/ajax/libs/MaterialDesign-Webfont/7.4.47/css/materialdesignicons.min.css">
<style>body{{{THEMES[theme]};background:var(--bg);margin:0;padding:20px;font-family:Roboto,-apple-system,"Segoe UI",sans-serif}}
.card{{background:var(--card);border-radius:16px;width:{width}px;padding:12px 16px;box-shadow:0 1px 3px rgba(0,0,0,.15)}}</style>
<script>customElements.define("ha-icon",class extends HTMLElement{{connectedCallback(){{this.style.display="inline-flex";
this.innerHTML=`<i class="mdi ${{this.getAttribute("icon").replace(":","-")}}" style="font-size:22px;line-height:1"></i>`}}}});</script>
<div class=card id=c></div><script>
document.getElementById("c").innerHTML = new Function("states","entity","user","hass","variables","html","helpers",
  "'use strict';" + {json.dumps(js)})({json.dumps(states)}, {json.dumps(entity)}, {{}}, {json.dumps(HASS)}, {{}}, () => "", {{}});
</script>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for name, card, timers, ringing, theme, width in SHOTS:
            html = Path(tmp) / "page.html"
            html.write_text(page(card, timers, ringing, theme, width))
            # window = card (width + 2 x 16 px padding) + 2 x 20 px page margin
            height = 112 if not timers else (300 if "gauge" in card else 345)
            subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                            f"--window-size={width + 32 + 40},{height}", f"--screenshot={OUT / name}", html.as_uri()],
                           check=True, capture_output=True)
            print("wrote", (OUT / name).relative_to(ROOT))


if __name__ == "__main__":
    main()

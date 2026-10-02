import subprocess


def test_yamllint():
    """yamllint should pass without any errors."""
    res = subprocess.run(["uv", "run", "yamllint", "--strict", "."], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"yamllint failed:\n{res.stdout}\n{res.stderr}"



def test_readme_links_every_card_and_the_package():
    from pathlib import Path

    readme = Path("README.md").read_text()
    for path in ("cards/timer-list.yaml", "cards/timer-gauge.yaml", "cards/header-badges.yaml", "packages/assist_timers.yaml"):
        assert path in readme, path


def test_readme_images_work_outside_github():
    """HACS renders the README on its own page, where relative image paths break."""
    import re
    from pathlib import Path

    prefix = "https://raw.githubusercontent.com/ollisulopuisto/ha-assist-timers/main/"
    srcs = re.findall(r'<img src="([^"]+)"', Path("README.md").read_text())
    assert srcs
    for src in srcs:
        assert src.startswith(prefix), src
        assert Path(src.removeprefix(prefix)).exists(), src

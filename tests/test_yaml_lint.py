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

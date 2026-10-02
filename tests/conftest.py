from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    """Load custom_components/ from this directory. The test harness ships its own
    `custom_components` package, which shadows ours unless we extend its path."""
    import custom_components

    ours = str(Path(__file__).parent.parent / "custom_components")
    if ours not in custom_components.__path__:
        custom_components.__path__.insert(0, ours)

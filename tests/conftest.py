import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-install", action="store_true", default=False,
        help="run tests that need a real installed Helix Stadium (its res/ catalog)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-install"):
        return
    skip = pytest.mark.skip(reason="needs --run-install (a real Helix Stadium install)")
    for item in items:
        if "install" in item.keywords:
            item.add_marker(skip)

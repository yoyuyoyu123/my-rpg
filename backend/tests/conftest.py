"""Even TestClient lifespan startup must never migrate the player's database."""
import asyncio
import os
from tempfile import TemporaryDirectory

_test_data = None
_previous_data_dir = None


def pytest_configure(config):
    global _test_data, _previous_data_dir
    _test_data = TemporaryDirectory(prefix="wuji-pytest-")
    _previous_data_dir = os.environ.get("WUJI_DATA_DIR")
    os.environ["WUJI_DATA_DIR"] = _test_data.name


def pytest_unconfigure(config):
    import sys
    module = sys.modules.get("app.db.session")
    try:
        if module is not None:
            asyncio.run(module.engine.dispose())
        if _test_data is not None:
            _test_data.cleanup()
    finally:
        if _previous_data_dir is None:
            os.environ.pop("WUJI_DATA_DIR", None)
        else:
            os.environ["WUJI_DATA_DIR"] = _previous_data_dir

import sys
import asyncio
import pytest
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

INGESTION_ROOT = Path(__file__).resolve().parent.parent


def _load_ingestion_app():
    original_path = list(sys.path)
    original_app_modules = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}

    # Remove the backend root so it cannot shadow the ingestion app
    for p in list(sys.path):
        if p.endswith("backend") or p.endswith("backend\\"):
            sys.path.remove(p)

    # Ensure the ingestion root is importable and takes precedence
    if str(INGESTION_ROOT) not in sys.path:
        sys.path.insert(0, str(INGESTION_ROOT))

    # Remove any previously imported backend app/submodules so the ingestion app is loaded
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]

    from app.main import app as ingestion_app
    return ingestion_app, original_path, original_app_modules


def _restore_imports(original_path, original_app_modules):
    sys.path[:] = original_path
    # Remove any app modules that were imported during ingestion tests
    for mod_name in list(sys.modules.keys()):
        if mod_name == "app" or mod_name.startswith("app."):
            del sys.modules[mod_name]
    # Restore original app modules (if any existed before ingestion tests ran)
    sys.modules.update(original_app_modules)


@pytest.fixture(scope="module")
def ingestion_app():
    app, original_path, original_app_modules = _load_ingestion_app()
    yield app
    _restore_imports(original_path, original_app_modules)

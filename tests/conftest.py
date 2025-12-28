import sys
import types
import pytest

@pytest.fixture(scope="session", autouse=True)
def docker_stub():
    """Provide a minimal 'docker' module stub so importing main.py works even without docker-py installed."""
    if "docker" in sys.modules:
        return

    docker = types.ModuleType("docker")

    class _DummyImages:
        def build(self, *args, **kwargs):
            # Mimic docker-py return shape: (image, logs)
            return object(), []

    class _DummyContainers:
        def get(self, *args, **kwargs):
            raise Exception("containers.get not available in tests")

    class _DummyClient:
        images = _DummyImages()
        containers = _DummyContainers()

    def from_env():
        return _DummyClient()

    docker.from_env = from_env
    sys.modules["docker"] = docker


# Ensure project root is importable (so `import services...` works reliably across environments)
import os as _os
_project_root = _os.path.dirname(_os.path.dirname(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

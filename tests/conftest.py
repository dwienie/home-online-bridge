import sys
import types
from pathlib import Path

# Make `custom_components.home_online_bridge.<module>` importable without executing the package __init__
# (which needs Home Assistant), so the pure-logic modules can be tested with plain pytest.
_pkg_dir = Path(__file__).parent.parent / "custom_components" / "home_online_bridge"
for name, path in (("custom_components", _pkg_dir.parent), ("custom_components.home_online_bridge", _pkg_dir)):
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    sys.modules[name] = mod

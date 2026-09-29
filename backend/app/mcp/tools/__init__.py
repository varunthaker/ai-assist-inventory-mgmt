"""Tool registry.

Every module in this package that defines a module-level `register(server)`
function is discovered and registered automatically at startup. Adding a new
tool therefore means adding one file here — no edits to server.py, and no edits
to the agent, which discovers tools over the wire at runtime.
"""

import importlib
import pkgutil
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def register_all(server) -> list[str]:
    """Import every tool module and call its register(server). Returns module names."""
    registered: list[str] = []
    for module_info in pkgutil.iter_modules([str(_PACKAGE_DIR)]):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{module_info.name}")
        register = getattr(module, "register", None)
        if register is None:
            continue
        register(server)
        registered.append(module_info.name)
    return registered

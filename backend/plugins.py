"""Only operator-installed Python files are eligible for execution."""
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import re

from procedures import aggregate, compare, normalize

BUILTINS = {"normalize": normalize, "compare": compare, "aggregate": aggregate}


def plugin_dir():
    return Path(os.getenv("BALANCER_PLUGINS", "plugins")).resolve()


def plugin_file(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid plugin name: {name}")
    root = plugin_dir()
    path = (root / f"{name}.py").resolve()
    if path.parent != root or not path.is_file():
        raise ValueError(f"Plugin file not found: {name}.py")
    return path


def available_checks():
    return available("check")


def available(role):
    names = []
    for path in plugin_dir().glob(f"{role}_*.py"):
        try:
            plugin_file(path.stem)
        except ValueError:
            continue
        names.append(path.stem)
    return sorted(names)


def source_path(name, role):
    if name == "builtin" and role in BUILTINS:
        return Path(BUILTINS[role].__file__)
    return plugin_file(name)


def load(name, role):
    if name == "builtin" and role in BUILTINS:
        return BUILTINS[role]
    path = plugin_file(name)
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


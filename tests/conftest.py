"""Test bootstrap.

Two jobs:

1. Put the repo root on ``sys.path`` so the integration is importable as
   ``custom_components.affarsverken_waste``.

2. Stub out ``homeassistant.*`` modules. The integration's ``__init__.py``
   imports from HomeAssistant — Python evaluates that file whenever we
   import any submodule (helpers, parsers, etc.). Installing the full
   ~100 MB ``homeassistant`` package just to test pure functions is
   disproportionate; ``MagicMock`` stubs let those imports succeed without
   exercising any HA code paths.

   This works because the pure modules under test (helpers, parsers,
   const) never touch HA themselves — the stubs only need to satisfy
   ``__init__.py``'s import side effects.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_STUB_MODULES = [
    "aiohttp",
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.sensor",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.util",
    "homeassistant.util.dt",
    "voluptuous",
]

for _name in _STUB_MODULES:
    sys.modules.setdefault(_name, MagicMock(name=_name))

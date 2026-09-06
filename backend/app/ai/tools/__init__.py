"""Importing this package populates `app.ai.tools.registry.TOOL_REGISTRY` —
each tool module registers its tools as a side effect of being imported.
"""

from __future__ import annotations

from app.ai.tools import guide as _guide  # noqa: F401
from app.ai.tools import recording as _recording  # noqa: F401

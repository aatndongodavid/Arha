"""Imports every module's tasks so the worker registers them."""

from arha.modules.analytics import tasks as _analytics  # noqa: F401
from arha.modules.billing import tasks as _billing  # noqa: F401
from arha.modules.integrations import tasks as _integrations  # noqa: F401
from arha.modules.payments import tasks as _payments  # noqa: F401
from arha.modules.submissions import tasks as _submissions  # noqa: F401

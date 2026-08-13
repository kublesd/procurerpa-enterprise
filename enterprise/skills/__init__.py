"""Composable procurement RPA skills.

Importing the package loads all seven built-in skills into the registry.
"""

from . import auth_skills as _auth_skills  # noqa: F401
from . import extraction_skills as _extraction_skills  # noqa: F401
from . import interaction_skills as _interaction_skills  # noqa: F401

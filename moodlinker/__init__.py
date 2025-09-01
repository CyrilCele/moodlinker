"""
Expose the project's Celery app for worker discovery.

This module intentionally re-exports the Celery application instance created
in `moodlinker.celery` under the name `celery_app`. Having this top-level symbol
is the conventional way Celery CLI tools discover the app when you run commands
like `celery -A moodlinker worker`.

Keep this file minimal and import-safe - it should not execute heavy logic.
"""

# Import the Celery application instance created in moodlinker/celery.py
# We import it here and re-export it so tools and other modules can do:
#       from moodlinker import celery_app
# rather than importing the celery module directly.
from moodlinker.celery import app as celery_app  # noqa:F401

# Export only the symbol that external code should depend on.
# `__all__` documents the public surface of this module and prevents
# wildcard imports from exposing other names.
__all__ = ("celery_app",)

"""
App configuration for the `tracker` Django application.

This module defines `TrackerConfig`, the AppConfig subclass that:
    - Declares the app's name and default auto field.
    - Imports the module that registers signal handlers once the app registry
      is ready (via the `ready()` hook).

Importing signal modules inside `ready()` (instead of at module top-level)
avoids registration / import-order problems during Django startup and tests.
"""

from django.apps import AppConfig
import importlib
import logging

logger = logging.getLogger(__name__)


class TrackerConfig(AppConfig):
    """
    AppConfig for the `tracker` app.

    Purpose:
        Ensure the Django app registry knows about the `tracker` application,
        provide app-level configuration, and register signal handlers when the
        app is ready (so receivers are attached exactly once).

    Attributes:
        default_auto_field (str): The default primary key field type for models in this app.
        name (str): The dotted Python path to the application.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "tracker"

    def ready(self) -> None:
        """
        Called by Django when the applcation registry is fully populated.

        This method's job is to import `tracker.signals` so that any
        signal receiver decorators there (e.g., `@receiver(post_save, ...)`)
        run and register handlers. Importing here ensures the model registry and
        app cache are initialized; importing signals at module import time can
        cause import cycles or register handlers too early.

        Args:
            self (TrackerConfig): instance of this AppConfig.

        Returns:
            None

        Raises:
            ModuleNotFoundError: If the `tracker.signals` module cannot be found.
            ImportError: If `tracker.signals` exists but raises an ImportError during import.
            Any other exception raised by `tracker.signals` will propagate unless caught.

        Example:
            In settings.py:
                INSTALLED_APP = [
                    'tracker.apps.TrackerConfig',
                    ...
                ]

            Once Django starts, `TrackerConfig.ready()` is invoked and signal handlers
            defined in `tracker/signals.py` are imported and registered.

        Important notes / edge cases:
            - Do not perform database queries, long-running tasks, or network calls here.
              The ready() hook can run multiple times in development (autorelated) and in test
              environments, so side effects are risky.
            - If `tracker.signals` raises during import, the error will surface during startup.
              Consider logging or handling ImportError if you prefer a softer failure.
        """
        from tracker import signals  # noqa: F401

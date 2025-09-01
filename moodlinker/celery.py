"""
Celery application factory for the `moodlinker` Django project.

This module performs the minimal, canonical Celery setup for a Django project:
1. Ensure Django settings are available via DJANGO_SETTINGS_MODULE.
2. Create a Celery app instance named after the project.
3. Load configuration from Django settings using the "CELERY" namespace.
4. Autodiscover tasks across installed Django apps.

Keep this file lightweight and import-safe - it is imported by the Celery CLI
(e.g. `celery -A moodlinker worker -l info`) and by Django wsgi/ASGI startup.
"""

import os
from celery import Celery

# 1) Ensure Django settings module is set before Django or Celery try to import settings.
#    Using setdefault allows an environment variable to override this in deployment.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moodlinker.settings")

# 2) Create the Celery application instance.
#    The string "moodlinker" is the main name for the app; it is used in logging and task names.
app = Celery("moodlinker")

# 3) Instruct Celery to read configuration from Django settings.
#    Using namespace="CELERY" means that Djano settings like CELERY_BROKER_URL will be read.
#    This keeps Celery-specific settings grouped under the CELERY_ prefix in settings.py.
app.config_from_object("django.conf:settings", namespace="CELERY")

# 4) Auto-discover task modules in all installed Django apps.
#    Celery will import '<app>.tasks' for each app in INSTALLED_APPS by default.
#    Keep this line so that task decorators (@shared_task / @app.task) are registered.
app.autodiscover_tasks()

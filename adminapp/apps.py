import os
from django.apps import AppConfig

class AdminappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'adminapp'

    def ready(self):
        # Prevent duplicate scheduler runs during dev server reload
        if os.environ.get("RUN_MAIN") == "true":
            from .scheduler import start_scheduler
            start_scheduler()

# Esto asegurará que la aplicación Celery siempre se importe cuando
# se inicie Django para que task_shared utilice esta aplicación.
from .celery import app as celery_app

__all__ = ('celery_app',)

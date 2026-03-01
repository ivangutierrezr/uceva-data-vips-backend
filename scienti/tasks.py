import logging
from celery import shared_task
from django.core.management import call_command
from django.db import transaction

logger = logging.getLogger(__name__)

@shared_task(name="scienti.tasks.run_scraping_pipeline")
def run_scraping_pipeline():
    """
    Tarea de Celery programada para ejecutar el proceso completo de Scraping
    y sincronización con Minciencias.
    
    Llama el comando de Django `sync_scienti` internamente para re-utilizar
    toda la lógica de infraestructura y casos de uso previamente construida.
    """
    logger.info("Iniciando tarea programada: run_scraping_pipeline")
    
    try:
        # Llamamos al comando sin dry-run para que persista los datos en DB
        call_command('sync_scienti')
        logger.info("Tarea programada finalizada con éxito: run_scraping_pipeline")
        return "Scraping pipeline completado"
    except Exception as e:
        logger.error(f"Error procesando la tarea de scraping: {str(e)}")
        raise e

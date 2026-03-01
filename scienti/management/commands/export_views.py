from django.core.management.base import BaseCommand
from scienti.application.use_cases.sql_view_exporter import export_views

class Command(BaseCommand):
    help = "Export pre-defined SQL views to CSV files"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Iniciando exportación de vistas SQL..."))
        export_views()
        self.stdout.write(self.style.SUCCESS("Exportación de vistas completada exitosamente."))

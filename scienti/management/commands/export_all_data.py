from django.core.management.base import BaseCommand
from scienti.application.use_cases.bulk_data_exporter import export_all_data

class Command(BaseCommand):
    help = "Export all database entities to CSV files"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Iniciando exportación de todos los datos..."))
        export_all_data()
        self.stdout.write(self.style.SUCCESS("Exportación completada exitosamente."))

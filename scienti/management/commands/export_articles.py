from django.core.management.base import BaseCommand
from scienti.application.use_cases.article_exporter import export_data_csv

class Command(BaseCommand):
    help = "Export articles to CSV files grouped by criteria"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Iniciando exportación de artículos..."))
        export_data_csv()
        self.stdout.write(self.style.SUCCESS("Exportación completada exitosamente."))

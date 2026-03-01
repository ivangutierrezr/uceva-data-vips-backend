from django.core.management.base import BaseCommand
from scienti.application.use_cases.duplicate_analyzer import analyze_duplicates

class Command(BaseCommand):
    help = "Find and export duplicated records in the database"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Iniciando análisis de duplicados..."))
        reports = analyze_duplicates()
        for report in reports:
            self.stdout.write(self.style.NOTICE(report))
        self.stdout.write(self.style.SUCCESS("Análisis completado."))

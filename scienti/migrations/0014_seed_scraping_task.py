# Generated manually
from django.db import migrations

def create_periodic_task(apps, schema_editor):
    try:
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        # Create crontab schedule: First day of the month at 00:00 (Midnight)
        schedule, created = CrontabSchedule.objects.get_or_create(
            minute='0',
            hour='0',
            day_of_week='*',
            day_of_month='1',
            month_of_year='*',
            timezone='America/Bogota'
        )
        
        # Create periodic task
        PeriodicTask.objects.update_or_create(
            name='Sincronización mensual con Minciencias',
            defaults={
                'crontab': schedule,
                'task': 'scienti.tasks.run_scraping_pipeline',
                'description': 'Ejecuta el proceso de scraping el 1er día de cada mes'
            }
        )
    except Exception as e:
        # Silently fail if models aren't ready (e.g. during an initial test install)
        pass

class Migration(migrations.Migration):

    dependencies = [
        ('scienti', '0013_researchgroup_city_obj_researchgroup_department_obj'),
    ]

    operations = [
        migrations.RunPython(create_periodic_task),
    ]

import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Crea un superusuario automáticamente de manera no interactiva leyendo variables de entorno'

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@uceva.edu.co')
        password = os.getenv('DJANGO_SUPERUSER_PASSWORD', 'admin1234')

        if not User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f'Creando superusuario {username}...'))
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS('Superusuario creado correctamente.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'El superusuario {username} ya existe. Ignorando.'))

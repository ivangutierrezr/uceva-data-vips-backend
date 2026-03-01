from django.contrib import admin
from django.apps import apps

# Registramos todos los modelos de la app 'scienti' automáticamente
app_models = apps.get_app_config('scienti').get_models()

for model in app_models:
    try:
        admin.site.register(model)
    except admin.sites.AlreadyRegistered:
        pass

"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from scienti.views import get_stats, get_cooperation_map, get_country_details

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/stats/', get_stats, name='get_stats'),
    path('api/map/', get_cooperation_map, name='get_cooperation_map'),
    path('api/country/<str:country_id>/', get_country_details, name='get_country_details'),
]


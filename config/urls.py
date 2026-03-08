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
from scienti.views import (
    get_stats,
    get_cooperation_map,
    get_country_details,
    global_search,
    get_researcher_detail,
    export_researcher_detail_excel,
    get_article_detail,
    get_book_detail,
    get_book_chapter_detail,
    get_group_detail,
    export_group_detail_excel,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/stats/', get_stats, name='get_stats'),
    path('api/map/', get_cooperation_map, name='get_cooperation_map'),
    path('api/country/<str:country_id>/', get_country_details, name='get_country_details'),
    path('api/search/', global_search, name='global_search'),
    path('api/researchers/<str:researcher_id>/', get_researcher_detail, name='get_researcher_detail'),
    path('api/researchers/<str:researcher_id>/export/', export_researcher_detail_excel, name='export_researcher_detail_excel'),
    path('api/groups/<str:group_id>/', get_group_detail, name='get_group_detail'),
    path('api/groups/<str:group_id>/export/', export_group_detail_excel, name='export_group_detail_excel'),
    path('api/articles/<str:article_id>/', get_article_detail, name='get_article_detail'),
    path('api/books/<str:book_id>/', get_book_detail, name='get_book_detail'),
    path('api/chapters/<str:chapter_id>/', get_book_chapter_detail, name='get_book_chapter_detail'),
]


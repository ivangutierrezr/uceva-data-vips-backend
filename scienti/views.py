from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import models
from django.db.models import Count, Q
from django.db.models.functions import ExtractYear
from .models import Researcher, Article, Thesis, Book, BookChapter, Country, ResearchGroup, ScientificEvent, ResearchLine
from .infrastructure.utils.country_coords import COUNTRY_COORDINATES
import unicodedata

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.category(c).startswith('Mn')])


@api_view(['GET'])
def get_stats(request):
    researchers_count = Researcher.objects.count()
    
    # Count unique productions based on Title + Year to avoid duplicates from multiple groups
    articles_count = Article.objects.values('title', 'year').distinct().count()
    theses_count = Thesis.objects.values('title', 'year').distinct().count()
    
    books_count = Book.objects.values('title', 'year').distinct().count()
    chapters_count = BookChapter.objects.values('chapter_title', 'book_title', 'year').distinct().count()
    books_chapters_count = books_count + chapters_count
    
    events_count = ScientificEvent.objects.annotate(
        event_year=ExtractYear('start_date')
    ).values('title', 'event_year').distinct().count()
    
    # Thesis breakdown by type (using distinct title to avoid duplicates)
    thesis_qs = Thesis.objects.values('thesis_type').annotate(count=Count('title', distinct=True)).order_by('-count')
    thesis_breakdown = [
        {'label': t['thesis_type'] or 'Sin Clasificar', 'value': t['count']} 
        for t in thesis_qs
    ]

    # Researcher breakdown by category
    researcher_qs = Researcher.objects.values('category').annotate(count=Count('id')).order_by('-count')
    researcher_breakdown = [
        {'label': r['category'] or 'Sin Categoría', 'value': r['count']}
        for r in researcher_qs
    ]

    # Events breakdown (3 sections) - using distinct title for consistency
    events_by_type = ScientificEvent.objects.values('event_type').annotate(count=Count('title', distinct=True)).order_by('-count')[:5]
    events_by_scope = ScientificEvent.objects.values('scope').annotate(count=Count('title', distinct=True)).order_by('-count')
    
    # Process participation type manually to handle comma-separated values
    participation_counts = {}
    
    # Get distinct event participations to avoid double counting shared events
    # We select title/year/participation_type distinct combinations
    unique_participations = ScientificEvent.objects.annotate(
        event_year=ExtractYear('start_date')
    ).exclude(
        participation_type__isnull=True
    ).exclude(
        participation_type=''
    ).values('title', 'event_year', 'participation_type').distinct()
    
    for row in unique_participations:
        p_string = row['participation_type']
        if not p_string: continue
        # Split by comma
        parts = p_string.split(',')
        for part in parts:
            clean_part = part.strip()
            if not clean_part: continue
            # Normalize casing to Title Case to group "Ponente" and "ponente"
            clean_part = clean_part.title()
            participation_counts[clean_part] = participation_counts.get(clean_part, 0) + 1

    # Convert dict to sorted list
    participation_list = [
        {'participation_type': k, 'count': v} 
        for k, v in participation_counts.items()
    ]
    participation_list.sort(key=lambda x: x['count'], reverse=True)
    
    # Limit to top 10 for display
    participation_list = participation_list[:10]

    events_sections = [
        {
            "title": "Por Tipo",
            "items": [{'label': x['event_type'] or 'N/A', 'value': x['count']} for x in events_by_type]
        },
        {
            "title": "Por Ámbito",
            "items": [{'label': (x['scope'] if x['scope'] and x['scope'].lower() != 'null' else 'Otro'), 'value': x['count']} for x in events_by_scope]
        },
        {
            "title": "Por Participación",
            "items": [{'label': x['participation_type'] or 'N/A', 'value': x['count']} for x in participation_list]
        }
    ]

    data = [
        { 
            'label': 'Investigadores', 
            'value': str(researchers_count), 
            'breakdown': researcher_breakdown
        },
        { 'label': 'Artículos', 'value': str(articles_count) },
        { 
            'label': 'Tesis de Grado', 
            'value': str(theses_count),
            'breakdown': thesis_breakdown 
        },
        { 'label': 'Libros & Capítulos', 'value': str(books_chapters_count) },
        {
            'label': 'Eventos Científicos',
            'value': str(events_count),
            'sections': events_sections
        }
    ]
    
    return Response(data)

@api_view(['GET'])
def get_cooperation_map(request):
    """
    Returns list of countries involved in Articles, with coordinates.
    """
    # 1. Get Countries with at least 1 article
    countries_qs = Country.objects.annotate(
        article_count=Count('articles')
    ).filter(article_count__gt=0).order_by('-article_count')
    
    hubs = []
    
    for c in countries_qs:
        name_lower = c.name.lower().strip()
        
        # Simple coordinate lookup
        coords = None
        if name_lower in COUNTRY_COORDINATES:
             coords = COUNTRY_COORDINATES[name_lower]
        
        # If found, add to hubs
        if coords:
            # Override Colombia info as main hub
            is_col = name_lower == 'colombia'
            hub = {
                "lat": coords['lat'],
                "lng": coords['lng'],
                "id": str(c.id),
                "name": c.name.title(), # Use title case for nice tooltips
                "name_clean": remove_accents(c.name).title(), # Cleaned for 3D Text
                "value": c.article_count,
                "info": "Nodo Central UCEVA" if is_col else f"{c.article_count} Artículos conjuntos", 
                "summary": "Sede Principal UCEVA" if is_col else "Cooperación activa en investigación.",
                "link": f"/reporte/{c.name}"
            }
            if is_col:
                hubs.insert(0, hub) # Ensure Colombia is first
            else:
                hubs.append(hub)
    
    # Fallback if Colombia not in DB (unlikely)
    if not any(h['name'].lower() == 'colombia' for h in hubs):
         hubs.insert(0, {
            "lat": 4.5709, "lng": -74.2973,
            "id": "colombia-main",
            "name": "Colombia",
            "name_clean": "Colombia",
            "value": 100,
            "info": "Nodo Central UCEVA",
            "summary": "Sede Principal",
            "link": "/reporte/colombia"
         })

    return Response(hubs)

from scienti.models import Country, Researcher, Article, Thesis, Book, BookChapter, ResearchGroup

@api_view(['GET'])
def get_country_details(request, country_id):
    import urllib.parse
    
    # Ensure proper decoding of URL parameter
    country_id = urllib.parse.unquote(country_id)
    country = None

    
    # Try UUID lookup first
    try:
        import uuid
        uuid_obj = uuid.UUID(country_id)
        country = Country.objects.filter(id=uuid_obj).first()
    except (ValueError, TypeError):
        pass
    
    # If not UUID, try Name lookup (slug/name from URL)
    if not country:
        # Basic cleanup: spaces and dashes
        raw_name = country_id.strip()
        name_spaced = raw_name.replace('-', ' ')
        
        # 1. Try exact/insensitive match on raw input
        country = Country.objects.filter(name__iexact=raw_name).first()
        
        # 2. Try match with spaces instead of dashes
        if not country:
            country = Country.objects.filter(name__iexact=name_spaced).first()
            
        # 3. Fuzzy match (accent insensitive manually) for SQLite limitations
        if not country:
            # Get all countries and find match in Python (Table is small < 200 rows)
            search_normalized = remove_accents(name_spaced).lower()
            
            all_countries = Country.objects.all()
            for c in all_countries:
                c_norm = remove_accents(c.name).lower()
                if c_norm == search_normalized:
                    country = c
                    break
            
            # 4. Try partial match if still not found (e.g. "Estados Unidos" vs "Estados Unidos de America")
            if not country:
                 for c in all_countries:
                    c_norm = remove_accents(c.name).lower()
                    if search_normalized in c_norm or c_norm in search_normalized:
                        # Only match if length difference isn't huge to avoid false positives
                        if len(search_normalized) > 3: 
                            country = c
                            break
            
    if not country:
        return Response({"error": f"Country '{country_id}' not found"}, status=404)

    # Calculate stats
    articles_qs = Article.objects.filter(country=country)
    books_qs = Book.objects.filter(country=country)
    
    # Try to find chapters via Book title match (best effort)
    # Get titles of books published in this country
    book_titles_in_country = books_qs.values_list('title', flat=True)
    chapters_qs = BookChapter.objects.filter(book_title__in=book_titles_in_country)
    
    articles_count = articles_qs.count()
    books_count = books_qs.count()
    chapters_count = chapters_qs.count()
    
    # Thesis doesn't have country
    thesis_count = 0 

    recent_articles = articles_qs.order_by('-year', '-title')[:3].values(
        'title', 'year', 'journal__name', 'doi'
    )
    
    recent_books = books_qs.order_by('-year', '-title')[:3].values(
        'title', 'year', 'isbn'
    )

    researcher_ids = Article.objects.filter(country=country).values_list('authors__researcher', flat=True)
    researcher_ids = [rid for rid in researcher_ids if rid]
    
    book_researcher_ids = Book.objects.filter(country=country).values_list('authors__researcher', flat=True)
    
    all_researcher_ids = list(researcher_ids) + list(book_researcher_ids)
    all_researcher_ids = [rid for rid in all_researcher_ids if rid]
    
    stats_researchers = Researcher.objects.filter(id__in=all_researcher_ids).distinct().count()

    top_researchers_qs = Researcher.objects.filter(
        id__in=all_researcher_ids
    ).annotate(
        relevant_pubs=Count('articleauthor', filter=models.Q(articleauthor__article__country=country)) + 
                      Count('bookauthor', filter=models.Q(bookauthor__book__country=country))
    ).order_by('-relevant_pubs')[:5]
    
    top_researchers = [
        {
            "name": r.name.title(),
            "category": r.category or ""
        }
        for r in top_researchers_qs
    ]

    grp_ids_art = Article.objects.filter(country=country).values_list('group_id', flat=True)
    
    grp_ids_bk = Book.objects.filter(country=country).values_list('group_id', flat=True)
    
    grp_ids_evt = ScientificEvent.objects.filter(country_obj=country).values_list('group_id', flat=True)
    
    all_grp_ids = set(list(grp_ids_art) + list(grp_ids_bk) + list(grp_ids_evt))
    
    research_lines = ResearchLine.objects.filter(
        groups__id__in=all_grp_ids
    ).values_list('name', flat=True).distinct().order_by('name')

    areas = list(research_lines)
    
    if not areas:
        top_groups_qs = ResearchGroup.objects.filter(id__in=all_grp_ids).annotate(
            count=Count('articles', filter=models.Q(articles__country=country)) + 
                  Count('books', filter=models.Q(books__country=country))
        ).order_by('-count')[:3]
        areas = [g.name for g in top_groups_qs]

    def clean_text(t):
        if not t: return ""
        t = t.replace('\x93', '"').replace('\x94', '"')
        t = t.replace('', '"').replace('', '"')
        t = t.replace('“', '"').replace('”', '"')
        return t

    _r_articles = []
    for a in recent_articles:
        if 'title' in a: a['title'] = clean_text(a['title'])
        _r_articles.append(a)

    _r_books = []
    for b in recent_books:
        if 'title' in b: b['title'] = clean_text(b['title'])
        _r_books.append(b)

    return Response({
        "name": country.name.title(),
        "info": "",
        "stats": {
            "articles": articles_count,
            "books": books_count,
            "chapters": chapters_count,
            "thesis": thesis_count,
            "researchers": stats_researchers
        },
        "topResearchers": top_researchers,
        "areas": areas,
        "chart": [
            { "name": 'Articulos', "value": articles_count, "color": '#10b981' },
            { "name": 'Libros', "value": books_count, "color": '#3b82f6' },
            { "name": 'Capítulos', "value": chapters_count, "color": '#f59e0b' },
        ],
        "recentArticles": _r_articles,
        "recentBooks": _r_books
    })




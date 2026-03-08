from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import HttpResponse
from django.db import models
from django.db.models import Count, Q, F, Value
from django.db.models.functions import ExtractYear
from django.db.models.functions import Coalesce, Lower
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.utils import timezone
from .models import (
    Researcher,
    Article,
    ArticleCategory,
    Thesis,
    Book,
    BookChapter,
    Country,
    ResearchGroup,
    ScientificEvent,
    ResearchLine,
    ArticleAuthor,
    BookAuthor,
    ChapterAuthor,
    ThesisTutor,
    ThesisStudent,
)
from .infrastructure.utils.country_coords import COUNTRY_COORDINATES
import re
import unicodedata

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.category(c).startswith('Mn')])


def normalize_identifier(value):
    if not value:
        return ""
    return re.sub(r'[^a-z0-9]', '', remove_accents(value).lower())


def normalize_doi(value):
    if not value:
        return ""
    return normalize_identifier(value)


ACCENTED_CHARS = 'áàäâãéèëêíìïîóòöôõúùüûñç'
PLAIN_CHARS = 'aaaaaeeeeiiiiooooouuuunc'


def normalized_text_annotation(field_name):
    """Builds a lowercase accent-insensitive SQL expression for text search."""
    return Lower(
        models.Func(
            Lower(Coalesce(F(field_name), Value(''), output_field=models.TextField())),
            Value(ACCENTED_CHARS),
            Value(PLAIN_CHARS),
            function='TRANSLATE',
            output_field=models.TextField(),
        )
    )


def unique_by_id(items):
    """Deduplicates response rows preserving original order."""
    seen = set()
    unique_items = []
    for item in items:
        item_id = item.get('id')
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_items.append(item)
    return unique_items


def _normalize_text_key(value):
    return normalize_identifier(str(value or ''))


def _append_unique_thesis_row(target_rows, row, related_field):
    key = (
        _normalize_text_key(row.get('title')),
        row.get('year') or None,
        _normalize_text_key(row.get('thesisType')),
        _normalize_text_key(row.get('institution')),
    )

    for existing in target_rows:
        existing_key = (
            _normalize_text_key(existing.get('title')),
            existing.get('year') or None,
            _normalize_text_key(existing.get('thesisType')),
            _normalize_text_key(existing.get('institution')),
        )
        if existing_key == key:
            merged = list(dict.fromkeys((existing.get(related_field) or []) + (row.get(related_field) or [])))
            existing[related_field] = merged
            return

    row[related_field] = list(dict.fromkeys(row.get(related_field) or []))
    target_rows.append(row)


def identifier_annotation(field_name):
    # Normalizes DOI/ISSN/ISBN in DB (remove non-alphanumeric chars).
    return Lower(
        models.Func(
            Coalesce(F(field_name), Value(''), output_field=models.TextField()),
            Value('[^a-zA-Z0-9]'),
            Value(''),
            Value('g'),
            function='REGEXP_REPLACE',
            output_field=models.TextField(),
        )
    )


@api_view(['GET'])
def global_search(request):
    query = (request.query_params.get('q') or "").strip()
    if not query:
        return Response(
            {"error": "Query parameter 'q' is required."},
            status=400,
        )

    per_type_limit = request.query_params.get('limit', '10')
    try:
        per_type_limit = max(1, min(int(per_type_limit), 50))
    except ValueError:
        per_type_limit = 10

    query_identifier = normalize_identifier(query)
    query_doi = normalize_doi(query)
    query_normalized = remove_accents(query).lower()

    article_ids_by_author = ArticleAuthor.objects.annotate(
        normalized_author_name=normalized_text_annotation('author_name'),
        normalized_researcher_name=normalized_text_annotation('researcher__name'),
    ).filter(
        Q(normalized_author_name__icontains=query_normalized) |
        Q(normalized_researcher_name__icontains=query_normalized)
    ).values_list('article_id', flat=True)

    book_ids_by_author = BookAuthor.objects.annotate(
        normalized_author_name=normalized_text_annotation('author_name'),
        normalized_researcher_name=normalized_text_annotation('researcher__name'),
    ).filter(
        Q(normalized_author_name__icontains=query_normalized) |
        Q(normalized_researcher_name__icontains=query_normalized)
    ).values_list('book_id', flat=True)

    chapter_ids_by_author = ChapterAuthor.objects.annotate(
        normalized_author_name=normalized_text_annotation('author_name'),
        normalized_researcher_name=normalized_text_annotation('researcher__name'),
    ).filter(
        Q(normalized_author_name__icontains=query_normalized) |
        Q(normalized_researcher_name__icontains=query_normalized)
    ).values_list('chapter_id', flat=True)

    researchers_qs = (
        Researcher.objects.annotate(
            normalized_name=normalized_text_annotation('name'),
        )
        .filter(
            Q(normalized_name__icontains=query_normalized) |
            Q(name__icontains=query) |
            Q(code_rh__icontains=query)
        )
        .order_by('name')[:per_type_limit]
    )

    groups_qs = (
        ResearchGroup.objects.annotate(
            normalized_name=normalized_text_annotation('name'),
        )
        .filter(
            Q(normalized_name__icontains=query_normalized) |
            Q(name__icontains=query) |
            Q(code__icontains=query) |
            Q(leader__icontains=query)
        )
        .order_by('name')[:per_type_limit]
    )

    articles_qs = (
        Article.objects.select_related('journal', 'group')
        .annotate(
            normalized_issn=identifier_annotation('issn'),
            normalized_journal_issn=identifier_annotation('journal__issn'),
            normalized_doi=identifier_annotation('doi'),
            normalized_title=normalized_text_annotation('title'),
            normalized_journal_name=normalized_text_annotation('journal__name'),
        )
        .filter(
            Q(normalized_title__icontains=query_normalized) |
            Q(normalized_journal_name__icontains=query_normalized) |
            Q(id__in=article_ids_by_author) |
            Q(title__icontains=query) |
            Q(doi__icontains=query) |
            Q(issn__icontains=query) |
            Q(journal__name__icontains=query) |
            Q(journal__issn__icontains=query) |
            Q(normalized_issn=query_identifier) |
            Q(normalized_journal_issn=query_identifier) |
            Q(normalized_doi=query_doi)
        )
        .distinct()
        .order_by('-year', 'title')[:per_type_limit]
    )

    books_qs = (
        Book.objects.select_related('publisher', 'group')
        .annotate(
            normalized_isbn=identifier_annotation('isbn'),
            normalized_title=normalized_text_annotation('title'),
        )
        .filter(
            Q(normalized_title__icontains=query_normalized) |
            Q(id__in=book_ids_by_author) |
            Q(title__icontains=query) |
            Q(isbn__icontains=query) |
            Q(normalized_isbn=query_identifier)
        )
        .distinct()
        .order_by('-year', 'title')[:per_type_limit]
    )

    chapters_qs = (
        BookChapter.objects.select_related('publisher', 'group')
        .annotate(
            normalized_isbn=identifier_annotation('isbn'),
            normalized_chapter_title=normalized_text_annotation('chapter_title'),
            normalized_book_title=normalized_text_annotation('book_title'),
        )
        .filter(
            Q(normalized_chapter_title__icontains=query_normalized) |
            Q(normalized_book_title__icontains=query_normalized) |
            Q(id__in=chapter_ids_by_author) |
            Q(chapter_title__icontains=query) |
            Q(book_title__icontains=query) |
            Q(isbn__icontains=query) |
            Q(normalized_isbn=query_identifier)
        )
        .distinct()
        .order_by('-year', 'chapter_title')[:per_type_limit]
    )

    researchers = [
        {
            'id': str(r.id),
            'name': r.name,
            'category': r.category,
            'codeRh': r.code_rh,
            'detailPath': f'/investigadores/{r.id}',
        }
        for r in researchers_qs
    ]

    groups = [
        {
            'id': str(g.id),
            'name': g.name,
            'code': g.code,
            'leader': g.leader,
            'category': g.category,
            'detailPath': f'/groups/{g.id}',
        }
        for g in groups_qs
    ]

    articles = [
        {
            'id': str(a.id),
            'title': a.title,
            'year': a.year,
            'doi': a.doi,
            'issn': a.issn or (a.journal.issn if a.journal else None),
            'journal': a.journal.name if a.journal else None,
            'groupName': a.group.name if a.group else None,
            'detailPath': f'/articulos/{a.id}',
        }
        for a in articles_qs
    ]

    books = [
        {
            'id': str(b.id),
            'title': b.title,
            'year': b.year,
            'isbn': b.isbn,
            'publisher': b.publisher.name if b.publisher else None,
            'groupName': b.group.name if b.group else None,
            'detailPath': f'/libros/{b.id}',
        }
        for b in books_qs
    ]

    book_chapters = [
        {
            'id': str(c.id),
            'chapterTitle': c.chapter_title,
            'bookTitle': c.book_title,
            'year': c.year,
            'isbn': c.isbn,
            'publisher': c.publisher.name if c.publisher else None,
            'groupName': c.group.name if c.group else None,
            'detailPath': f'/capitulos/{c.id}',
        }
        for c in chapters_qs
    ]

    # Defensive dedupe for joins with authors and other related records.
    researchers = unique_by_id(researchers)
    groups = unique_by_id(groups)
    articles = unique_by_id(articles)
    books = unique_by_id(books)
    book_chapters = unique_by_id(book_chapters)

    return Response(
        {
            'query': query,
            'totals': {
                'researchers': len(researchers),
                'groups': len(groups),
                'articles': len(articles),
                'books': len(books),
                'bookChapters': len(book_chapters),
                'all': len(researchers) + len(groups) + len(articles) + len(books) + len(book_chapters),
            },
            'results': {
                'researchers': researchers,
                'groups': groups,
                'articles': articles,
                'books': books,
                'bookChapters': book_chapters,
            },
        }
    )


@api_view(['GET'])
def get_researcher_detail(request, researcher_id):
    researcher = Researcher.objects.filter(id=researcher_id).first()
    if not researcher:
        return Response({'error': 'Researcher not found'}, status=404)

    return Response(_build_researcher_detail_payload(researcher))


def _build_researcher_detail_payload(researcher):
    groups = ResearchGroup.objects.filter(members__researcher=researcher).distinct().order_by('name')

    articles = Article.objects.filter(authors__researcher=researcher).select_related('journal', 'group', 'product_type_obj').distinct().order_by('-year', 'title')
    books = Book.objects.filter(authors__researcher=researcher).select_related('publisher', 'group').distinct().order_by('-year', 'title')
    chapters = BookChapter.objects.filter(authors__researcher=researcher).select_related('publisher', 'group').distinct().order_by('-year', 'chapter_title')

    article_ids = [a.id for a in articles]
    book_ids = [b.id for b in books]
    chapter_ids = [c.id for c in chapters]

    article_author_counts = dict(
        ArticleAuthor.objects.filter(article_id__in=article_ids)
        .values('article_id')
        .annotate(total=Count('id'))
        .values_list('article_id', 'total')
    )
    book_author_counts = dict(
        BookAuthor.objects.filter(book_id__in=book_ids)
        .values('book_id')
        .annotate(total=Count('id'))
        .values_list('book_id', 'total')
    )
    chapter_author_counts = dict(
        ChapterAuthor.objects.filter(chapter_id__in=chapter_ids)
        .values('chapter_id')
        .annotate(total=Count('id'))
        .values_list('chapter_id', 'total')
    )

    article_categories_by_id = {}
    article_categories_qs = (
        ArticleCategory.objects.filter(article_id__in=article_ids)
        .select_related('source')
        .values('article_id', 'year', 'category', 'source__name')
    )
    for row in article_categories_qs:
        article_categories_by_id.setdefault(row['article_id'], []).append(row)

    def resolve_article_category(article):
        rows = article_categories_by_id.get(article.id, [])
        if not rows:
            return {
                'category': 'N/R',
                'source': None,
            }

        target_year = article.year
        if target_year is not None:
            filtered = [r for r in rows if r.get('year') == target_year]
            if filtered:
                rows = filtered

        by_source = {}
        for row in rows:
            source_name = (row.get('source__name') or '').upper().strip() or 'OTRA FUENTE'
            current = by_source.get(source_name)
            if not current or (row.get('year') or 0) >= (current.get('year') or 0):
                by_source[source_name] = row

        selected = None
        selected_source = None

        publindex_row = by_source.get('PUBLINDEX')
        scimago_row = by_source.get('SCIMAGO')

        if publindex_row and publindex_row.get('category'):
            selected = publindex_row.get('category')
            selected_source = 'Publindex'
        elif scimago_row and scimago_row.get('category'):
            selected = scimago_row.get('category')
            selected_source = 'Scimago'

        if selected:
            return {
                'category': str(selected),
                'source': selected_source,
            }

        return {
            'category': 'N/R',
            'source': None,
        }

    thesis_tutor_links = ThesisTutor.objects.filter(researcher=researcher).select_related('thesis').order_by('-thesis__year', 'thesis__title', 'order')
    thesis_student_links = ThesisStudent.objects.filter(researcher=researcher).select_related('thesis').order_by('-thesis__year', 'thesis__title')

    tutor_thesis_ids = [link.thesis_id for link in thesis_tutor_links]
    student_thesis_ids = [link.thesis_id for link in thesis_student_links]
    thesis_ids = list(set(tutor_thesis_ids + student_thesis_ids))

    thesis_map = {
        thesis.id: thesis
        for thesis in Thesis.objects.filter(id__in=thesis_ids).select_related('institution_obj').order_by('-year', 'title')
    }

    thesis_students_by_thesis = {}
    thesis_students_qs = ThesisStudent.objects.filter(thesis_id__in=thesis_ids).order_by('order', 'student_name')
    for student in thesis_students_qs:
        thesis_students_by_thesis.setdefault(student.thesis_id, []).append(student.student_name)

    thesis_as_director = []
    thesis_as_cotutor = []
    thesis_as_student = []

    for link in thesis_tutor_links:
        thesis = thesis_map.get(link.thesis_id)
        if not thesis:
            continue
        thesis_row = {
            'id': str(thesis.id),
            'title': thesis.title,
            'year': thesis.year,
            'thesisType': thesis.thesis_type,
            'institution': thesis.institution_obj.name if thesis.institution_obj else thesis.institution,
            'students': thesis_students_by_thesis.get(thesis.id, []),
        }
        if link.order == 0:
            _append_unique_thesis_row(thesis_as_director, thesis_row, 'students')
        else:
            _append_unique_thesis_row(thesis_as_cotutor, thesis_row, 'students')

    for link in thesis_student_links:
        thesis = thesis_map.get(link.thesis_id)
        if not thesis:
            continue
        _append_unique_thesis_row(
            thesis_as_student,
            {
                'id': str(thesis.id),
                'title': thesis.title,
                'year': thesis.year,
                'thesisType': thesis.thesis_type,
                'institution': thesis.institution_obj.name if thesis.institution_obj else thesis.institution,
                'tutors': [
                    t.tutor_name
                    for t in ThesisTutor.objects.filter(thesis=thesis).order_by('order', 'tutor_name')
                ],
            },
            'tutors',
        )

    def unique_articles(items):
        seen = set()
        unique_rows = []
        for item in items:
            key = (
                _normalize_text_key(item.title),
                item.year or None,
                _normalize_text_key(item.doi),
                _normalize_text_key(item.issn or (item.journal.issn if item.journal else None)),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(item)
        return unique_rows

    def unique_books(items):
        seen = set()
        unique_rows = []
        for item in items:
            key = (
                _normalize_text_key(item.title),
                item.year or None,
                _normalize_text_key(item.isbn),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(item)
        return unique_rows

    def unique_chapters(items):
        seen = set()
        unique_rows = []
        for item in items:
            key = (
                _normalize_text_key(item.chapter_title),
                _normalize_text_key(item.book_title),
                item.year or None,
                _normalize_text_key(item.isbn),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_rows.append(item)
        return unique_rows

    unique_article_rows = unique_articles(list(articles))[:200]
    unique_book_rows = unique_books(list(books))[:200]
    unique_chapter_rows = unique_chapters(list(chapters))[:200]

    return {
        'id': str(researcher.id),
        'name': researcher.name,
        'codeRh': researcher.code_rh,
        'category': researcher.category,
        'educationLevel': researcher.education_level,
        'city': researcher.city,
        'department': researcher.department,
        'university': researcher.university,
        'cvlacUrl': researcher.cvlac_url,
        'groups': [
            {
                'id': str(group.id),
                'name': group.name,
                'code': group.code,
            }
            for group in groups
        ],
        'products': {
            'articles': [
                {
                    'id': str(article.id),
                    'title': article.title,
                    'year': article.year,
                    'category': resolved_category['category'],
                    'categorySource': resolved_category['source'],
                    'issn': article.issn or (article.journal.issn if article.journal else None),
                    'doi': article.doi,
                    'researchersCount': article_author_counts.get(article.id, 0),
                    'detailPath': f'/articulos/{article.id}',
                }
                for article in unique_article_rows
                for resolved_category in [resolve_article_category(article)]
            ],
            'books': [
                {
                    'id': str(book.id),
                    'title': book.title,
                    'year': book.year,
                    'isbn': book.isbn,
                    'publisher': book.publisher.name if book.publisher else None,
                    'researchersCount': book_author_counts.get(book.id, 0),
                    'detailPath': f'/libros/{book.id}',
                }
                for book in unique_book_rows
            ],
            'bookChapters': [
                {
                    'id': str(chapter.id),
                    'chapterTitle': chapter.chapter_title,
                    'bookTitle': chapter.book_title,
                    'year': chapter.year,
                    'isbn': chapter.isbn,
                    'publisher': chapter.publisher.name if chapter.publisher else None,
                    'researchersCount': chapter_author_counts.get(chapter.id, 0),
                    'detailPath': f'/capitulos/{chapter.id}',
                }
                for chapter in unique_chapter_rows
            ],
        },
        'theses': {
            'asDirector': thesis_as_director,
            'asCotutor': thesis_as_cotutor,
            'asStudent': thesis_as_student,
        },
    }


@api_view(['GET'])
def export_researcher_detail_excel(request, researcher_id):
    researcher = Researcher.objects.filter(id=researcher_id).first()
    if not researcher:
        return Response({'error': 'Researcher not found'}, status=404)

    data = _build_researcher_detail_payload(researcher)

    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    # Frontend primary tone: hsl(162 47% 18%) ~= #184336
    header_fill = PatternFill(start_color='184336', end_color='184336', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)
    title_font = Font(size=18, bold=True, color='184336')
    thin_border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB'),
    )

    def style_table_header(sheet, total_columns):
        for col_idx in range(1, total_columns + 1):
            cell = sheet.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = thin_border
        sheet.freeze_panes = 'A2'

    def auto_fit_columns(sheet, min_width=12, max_width=60):
        for col_cells in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col_cells[0].column)
            for cell in col_cells:
                cell_value = '' if cell.value is None else str(cell.value)
                max_len = max(max_len, len(cell_value))
            sheet.column_dimensions[col_letter].width = max(min(max_len + 2, max_width), min_width)

    cover_sheet = workbook.create_sheet('Portada', 0)
    code_rh = (researcher.code_rh or 'SIN-CODIGO').strip()
    researcher_name = (researcher.name or 'Investigador').strip()

    cover_sheet.merge_cells('A1:E1')
    cover_sheet['A1'] = 'Ficha de Investigador'
    cover_sheet['A1'].font = title_font
    cover_sheet['A1'].alignment = Alignment(horizontal='center', vertical='center')

    cover_sheet['A3'] = 'Código RH'
    cover_sheet['B3'] = code_rh
    cover_sheet['A4'] = 'Nombre del Investigador'
    cover_sheet['B4'] = researcher_name
    cover_sheet['A5'] = 'Categoría'
    cover_sheet['B5'] = researcher.category or 'N/A'
    cover_sheet['A6'] = 'Formación'
    cover_sheet['B6'] = researcher.education_level or 'N/A'
    cover_sheet['A7'] = 'Fecha de generación'
    cover_sheet['B7'] = timezone.localtime().strftime('%Y-%m-%d %H:%M')

    for row in range(3, 8):
        label_cell = cover_sheet[f'A{row}']
        value_cell = cover_sheet[f'B{row}']
        label_cell.font = Font(bold=True, color='184336')
        label_cell.fill = PatternFill(start_color='E6F1EE', end_color='E6F1EE', fill_type='solid')
        label_cell.alignment = Alignment(horizontal='left', vertical='center')
        label_cell.border = thin_border
        value_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        value_cell.border = thin_border

    cover_sheet.column_dimensions['A'].width = 28
    cover_sheet.column_dimensions['B'].width = 60
    cover_sheet.row_dimensions[1].height = 30

    ws_articles = workbook.create_sheet('Articulos')
    ws_articles.append(['Título', 'Año', 'Categoría', 'Fuente', 'ISSN', 'DOI', 'No. Investigadores'])
    for row in data['products']['articles']:
        category_value = (row.get('category') or '').strip() if isinstance(row.get('category'), str) else row.get('category')
        category_value = category_value if category_value else 'N/R'
        source_value = (row.get('categorySource') or '').strip() if isinstance(row.get('categorySource'), str) else row.get('categorySource')
        source_value = source_value if source_value else 'N/R'

        if category_value == 'N/R':
            source_value = 'N/R'

        ws_articles.append([
            row['title'],
            row.get('year'),
            category_value,
            source_value,
            row.get('issn'),
            row.get('doi'),
            row.get('researchersCount'),
        ])
    style_table_header(ws_articles, 7)
    auto_fit_columns(ws_articles)

    ws_books = workbook.create_sheet('Libros')
    ws_books.append(['Título', 'Año', 'ISBN', 'Editorial', 'No. Investigadores'])
    for row in data['products']['books']:
        ws_books.append([
            row['title'],
            row.get('year'),
            row.get('isbn'),
            row.get('publisher'),
            row.get('researchersCount'),
        ])
    style_table_header(ws_books, 5)
    auto_fit_columns(ws_books)

    ws_chapters = workbook.create_sheet('Capitulos')
    ws_chapters.append(['Capítulo', 'Libro', 'Año', 'ISBN', 'Editorial', 'No. Investigadores'])
    for row in data['products']['bookChapters']:
        ws_chapters.append([
            row.get('chapterTitle'),
            row.get('bookTitle'),
            row.get('year'),
            row.get('isbn'),
            row.get('publisher'),
            row.get('researchersCount'),
        ])
    style_table_header(ws_chapters, 6)
    auto_fit_columns(ws_chapters)

    ws_theses = workbook.create_sheet('Tesis')
    ws_theses.append(['Rol', 'Título', 'Año', 'Tipo', 'Institución', 'Relacionados'])

    for row in data['theses']['asDirector']:
        ws_theses.append(['Director', row.get('title'), row.get('year'), row.get('thesisType'), row.get('institution'), ', '.join(row.get('students', []))])
    for row in data['theses']['asCotutor']:
        ws_theses.append(['Cotutor', row.get('title'), row.get('year'), row.get('thesisType'), row.get('institution'), ', '.join(row.get('students', []))])
    for row in data['theses']['asStudent']:
        ws_theses.append(['Estudiante', row.get('title'), row.get('year'), row.get('thesisType'), row.get('institution'), ', '.join(row.get('tutors', []))])
    style_table_header(ws_theses, 6)
    auto_fit_columns(ws_theses)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_code = re.sub(r'[\\/:*?"<>|]+', '-', code_rh).strip() or 'SIN-CODIGO'
    safe_name = re.sub(r'[\\/:*?"<>|]+', ' ', researcher_name).strip() or 'Investigador'
    safe_name = re.sub(r'\s+', ' ', safe_name)
    filename = f"Ficha-CodigoRH-{safe_code}-{safe_name}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
def get_article_detail(request, article_id):
    article = Article.objects.select_related('group', 'journal', 'country', 'city').filter(id=article_id).first()
    if not article:
        return Response({'error': 'Article not found'}, status=404)

    authors = ArticleAuthor.objects.filter(article=article).select_related('researcher').order_by('order', 'author_name')
    related_articles = Article.objects.filter(group=article.group).exclude(id=article.id).distinct().order_by('-year', 'title')[:15]

    return Response(
        {
            'id': str(article.id),
            'title': article.title,
            'year': article.year,
            'doi': article.doi,
            'doiSuffix': article.doi_suffix,
            'issn': article.issn,
            'volume': article.volume,
            'issue': article.issue,
            'pages': article.pages,
            'productType': article.product_type,
            'group': {
                'id': str(article.group.id),
                'name': article.group.name,
                'code': article.group.code,
            } if article.group else None,
            'journal': {
                'id': str(article.journal.id),
                'name': article.journal.name,
                'issn': article.journal.issn,
            } if article.journal else None,
            'location': {
                'country': article.country.name if article.country else None,
                'city': article.city.name if article.city else None,
            },
            'authors': [
                {
                    'name': author.author_name,
                    'isGroupMember': author.is_group_member,
                    'researcherId': str(author.researcher.id) if author.researcher else None,
                    'researcherPath': f'/investigadores/{author.researcher.id}' if author.researcher else None,
                }
                for author in authors
            ],
            'related': {
                'articlesFromGroup': [
                    {
                        'id': str(item.id),
                        'title': item.title,
                        'year': item.year,
                        'detailPath': f'/articulos/{item.id}',
                    }
                    for item in related_articles
                ]
            }
        }
    )


@api_view(['GET'])
def get_book_detail(request, book_id):
    book = Book.objects.select_related('group', 'publisher', 'country', 'city').filter(id=book_id).first()
    if not book:
        return Response({'error': 'Book not found'}, status=404)

    authors = BookAuthor.objects.filter(book=book).select_related('researcher').order_by('order', 'author_name')
    related_chapters_qs = BookChapter.objects.filter(group=book.group).filter(
        Q(isbn=book.isbn) |
        Q(book_title__iexact=book.title)
    ).distinct().order_by('-year', 'chapter_title')

    related_books = Book.objects.filter(group=book.group).exclude(id=book.id).distinct().order_by('-year', 'title')[:15]

    return Response(
        {
            'id': str(book.id),
            'title': book.title,
            'year': book.year,
            'isbn': book.isbn,
            'productType': book.product_type,
            'group': {
                'id': str(book.group.id),
                'name': book.group.name,
                'code': book.group.code,
            } if book.group else None,
            'publisher': {
                'id': str(book.publisher.id),
                'name': book.publisher.name,
            } if book.publisher else None,
            'location': {
                'country': book.country.name if book.country else None,
                'city': book.city.name if book.city else None,
            },
            'authors': [
                {
                    'name': author.author_name,
                    'isGroupMember': author.is_group_member,
                    'researcherId': str(author.researcher.id) if author.researcher else None,
                    'researcherPath': f'/investigadores/{author.researcher.id}' if author.researcher else None,
                }
                for author in authors
            ],
            'related': {
                'chapters': [
                    {
                        'id': str(chapter.id),
                        'chapterTitle': chapter.chapter_title,
                        'bookTitle': chapter.book_title,
                        'year': chapter.year,
                        'detailPath': f'/capitulos/{chapter.id}',
                    }
                    for chapter in related_chapters_qs[:30]
                ],
                'booksFromGroup': [
                    {
                        'id': str(item.id),
                        'title': item.title,
                        'year': item.year,
                        'detailPath': f'/libros/{item.id}',
                    }
                    for item in related_books
                ],
            },
        }
    )


@api_view(['GET'])
def get_book_chapter_detail(request, chapter_id):
    chapter = BookChapter.objects.select_related('group', 'publisher').filter(id=chapter_id).first()
    if not chapter:
        return Response({'error': 'Book chapter not found'}, status=404)

    authors = ChapterAuthor.objects.filter(chapter=chapter).select_related('researcher').order_by('order', 'author_name')
    related_books_qs = Book.objects.filter(group=chapter.group).filter(
        Q(isbn=chapter.isbn) |
        Q(title__iexact=chapter.book_title)
    ).distinct().order_by('-year', 'title')

    related_chapters_qs = BookChapter.objects.filter(group=chapter.group).exclude(id=chapter.id).filter(
        Q(isbn=chapter.isbn) |
        Q(book_title__iexact=chapter.book_title)
    ).distinct().order_by('-year', 'chapter_title')

    return Response(
        {
            'id': str(chapter.id),
            'chapterTitle': chapter.chapter_title,
            'bookTitle': chapter.book_title,
            'year': chapter.year,
            'isbn': chapter.isbn,
            'productType': chapter.product_type,
            'group': {
                'id': str(chapter.group.id),
                'name': chapter.group.name,
                'code': chapter.group.code,
            } if chapter.group else None,
            'publisher': {
                'id': str(chapter.publisher.id),
                'name': chapter.publisher.name,
            } if chapter.publisher else None,
            'authors': [
                {
                    'name': author.author_name,
                    'isGroupMember': author.is_group_member,
                    'researcherId': str(author.researcher.id) if author.researcher else None,
                    'researcherPath': f'/investigadores/{author.researcher.id}' if author.researcher else None,
                }
                for author in authors
            ],
            'related': {
                'books': [
                    {
                        'id': str(book.id),
                        'title': book.title,
                        'year': book.year,
                        'detailPath': f'/libros/{book.id}',
                    }
                    for book in related_books_qs[:20]
                ],
                'chaptersFromSameBook': [
                    {
                        'id': str(item.id),
                        'chapterTitle': item.chapter_title,
                        'year': item.year,
                        'detailPath': f'/capitulos/{item.id}',
                    }
                    for item in related_chapters_qs[:20]
                ],
            },
        }
    )


def _build_group_detail_payload(group):
    # Researchers associated
    # group.members relates to GroupMember
    members = group.members.select_related('researcher').all()
    member_researcher_ids = {m.researcher_id for m in members if m.researcher_id}
    researchers_data = [
        {
            'id': str(m.researcher.id),
            'name': m.researcher.name,
            'codeRh': m.researcher.code_rh,
            'category': m.researcher.category,
            'membershipType': m.membership_type,
            'status': m.status,
            'detailPath': f'/investigadores/{m.researcher.id}',
        }
        for m in members
        if m.researcher
    ]

    # Articles
    articles = Article.objects.filter(group=group).order_by('-year', 'title')[:200]
    
    article_ids = [a.id for a in articles]
    
    article_categories_by_id = {}
    article_categories_qs = (
        ArticleCategory.objects.filter(article_id__in=article_ids)
        .select_related('source')
        .values('article_id', 'year', 'category', 'source__name')
    )
    for row in article_categories_qs:
        article_categories_by_id.setdefault(row['article_id'], []).append(row)

    def resolve_article_category(article):
        rows = article_categories_by_id.get(article.id, [])
        if not rows:
            return {
                'category': 'N/R',
                'source': None,
            }

        target_year = article.year
        if target_year is not None:
            filtered = [r for r in rows if r.get('year') == target_year]
            if filtered:
                rows = filtered

        by_source = {}
        for row in rows:
            source_name = (row.get('source__name') or '').upper().strip() or 'OTRA FUENTE'
            current = by_source.get(source_name)
            if not current or (row.get('year') or 0) >= (current.get('year') or 0):
                by_source[source_name] = row

        selected = None
        selected_source = None

        publindex_row = by_source.get('PUBLINDEX')
        scimago_row = by_source.get('SCIMAGO')

        if publindex_row and publindex_row.get('category'):
            selected = publindex_row.get('category')
            selected_source = 'Publindex'
        elif scimago_row and scimago_row.get('category'):
            selected = scimago_row.get('category')
            selected_source = 'Scimago'

        if selected:
            return {
                'category': str(selected),
                'source': selected_source,
            }

        return {
            'category': 'N/R',
            'source': None,
        }
    
    # Calculate researchers explicitly grouped by product, getting names instead of just counts
    article_authors_qs = ArticleAuthor.objects.filter(article_id__in=article_ids).values('article_id', 'author_name', 'researcher_id').order_by('order')
    article_authors_by_id = {}
    for aa in article_authors_qs:
        article_authors_by_id.setdefault(aa['article_id'], []).append({
            'name': aa['author_name'],
            'isGroupMember': aa['researcher_id'] in member_researcher_ids if aa['researcher_id'] else False
        })

    articles_data = [
        {
            'id': str(a.id),
            'title': a.title,
            'year': a.year,
            'category': resolve_article_category(a)['category'],
            'categorySource': resolve_article_category(a)['source'],
            'doi': a.doi,
            'issn': a.issn,
            'authors': article_authors_by_id.get(a.id, []),
            'detailPath': f'/articulos/{a.id}'
        }
        for a in articles
    ]

    # Books
    books = Book.objects.filter(group=group).order_by('-year', 'title')[:200]
    book_ids = [b.id for b in books]
    book_authors_qs = BookAuthor.objects.filter(book_id__in=book_ids).values('book_id', 'author_name', 'researcher_id').order_by('order')
    book_authors_by_id = {}
    for ba in book_authors_qs:
        book_authors_by_id.setdefault(ba['book_id'], []).append({
            'name': ba['author_name'],
            'isGroupMember': ba['researcher_id'] in member_researcher_ids if ba['researcher_id'] else False
        })

    books_data = [
        {
            'id': str(b.id),
            'title': b.title,
            'year': b.year,
            'isbn': b.isbn,
            'authors': book_authors_by_id.get(b.id, []),
            'detailPath': f'/libros/{b.id}'
        }
        for b in books
    ]

    # Chapters
    chapters = BookChapter.objects.filter(group=group).order_by('-year', 'chapter_title')[:200]
    chapter_ids = [c.id for c in chapters]
    chapter_authors_qs = ChapterAuthor.objects.filter(chapter_id__in=chapter_ids).values('chapter_id', 'author_name', 'researcher_id').order_by('order')
    chapter_authors_by_id = {}
    for ca in chapter_authors_qs:
        chapter_authors_by_id.setdefault(ca['chapter_id'], []).append({
            'name': ca['author_name'],
            'isGroupMember': ca['researcher_id'] in member_researcher_ids if ca['researcher_id'] else False
        })

    chapters_data = [
        {
            'id': str(c.id),
            'chapterTitle': c.chapter_title,
            'bookTitle': c.book_title,
            'year': c.year,
            'isbn': c.isbn,
            'authors': chapter_authors_by_id.get(c.id, []),
            'detailPath': f'/capitulos/{c.id}'
        }
        for c in chapters
    ]

    # Theses
    theses = Thesis.objects.filter(group=group).order_by('-year', 'title')[:200]
    thesis_ids = [t.id for t in theses]
    thesis_authors_by_id = {}

    tutors_qs = ThesisTutor.objects.filter(thesis_id__in=thesis_ids).values('thesis_id', 'tutor_name', 'researcher_id').order_by('order')
    for tq in tutors_qs:
        thesis_authors_by_id.setdefault(tq['thesis_id'], []).append({
            'name': tq['tutor_name'],
            'isGroupMember': tq['researcher_id'] in member_researcher_ids if tq['researcher_id'] else False,
            'role': 'Tutor/Director'
        })

    students_qs = ThesisStudent.objects.filter(thesis_id__in=thesis_ids).values('thesis_id', 'student_name', 'researcher_id').order_by('order')
    for sq in students_qs:
        thesis_authors_by_id.setdefault(sq['thesis_id'], []).append({
            'name': sq['student_name'],
            'isGroupMember': sq['researcher_id'] in member_researcher_ids if sq['researcher_id'] else False,
            'role': 'Estudiante'
        })

    theses_data = [
        {
            'id': str(t.id),
            'title': t.title,
            'year': t.year,
            'thesisType': t.thesis_type,
            'institution': t.institution_obj.name if t.institution_obj else t.institution,
            'authors': thesis_authors_by_id.get(t.id, []),
            # we skip detailPath since we typically don't have thesis detail pages yet, but we could
        }
        for t in theses
    ]

    return {
        'id': str(group.id),
        'code': group.code,
        'name': group.name,
        'leader': group.leader,
        'category': group.category,
        'formationDateInfo': group.formation_date_info,
        'department': group.department,
        'city': group.city,
        'certificationStatus': group.certification_status,
        'website': group.website,
        'email': group.email,
        'classificationValidity': group.classification_validity,
        'researchers': researchers_data,
        'products': {
            'articles': articles_data,
            'books': books_data,
            'bookChapters': chapters_data,
            'theses': theses_data,
        }
    }

@api_view(['GET'])
def get_group_detail(request, group_id):
    group = ResearchGroup.objects.filter(id=group_id).first()
    if not group:
        return Response({'error': 'Group not found'}, status=404)

    return Response(_build_group_detail_payload(group))

@api_view(['GET'])
def export_group_detail_excel(request, group_id):
    group = ResearchGroup.objects.filter(id=group_id).first()
    if not group:
        return Response({'error': 'Group not found'}, status=404)

    data = _build_group_detail_payload(group)

    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    # Frontend primary tone: hsl(162 47% 18%) ~= #184336
    header_fill = PatternFill(start_color='184336', end_color='184336', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)
    title_font = Font(size=18, bold=True, color='184336')
    thin_border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB'),
    )

    def style_table_header(sheet, total_columns):
        for col_idx in range(1, total_columns + 1):
            cell = sheet.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = thin_border
        sheet.freeze_panes = 'A2'

    def auto_fit_columns(sheet, min_width=12, max_width=60):
        for col_cells in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col_cells[0].column)
            for cell in col_cells:
                cell_value = '' if cell.value is None else str(cell.value)
                max_len = max(max_len, len(cell_value))
            sheet.column_dimensions[col_letter].width = max(min(max_len + 2, max_width), min_width)

    cover_sheet = workbook.create_sheet('Portada', 0)
    group_code = (group.code or 'SIN-CODIGO').strip()
    group_name = (group.name or 'Grupo').strip()

    cover_sheet.merge_cells('A1:E1')
    cover_sheet['A1'] = 'Ficha de Grupo de Investigación'
    cover_sheet['A1'].font = title_font
    cover_sheet['A1'].alignment = Alignment(horizontal='center', vertical='center')

    cover_sheet['A3'] = 'Código MinCiencias'
    cover_sheet['B3'] = group_code
    cover_sheet['A4'] = 'Nombre del Grupo'
    cover_sheet['B4'] = group_name
    cover_sheet['A5'] = 'Categoría'
    cover_sheet['B5'] = group.category or 'N/A'
    cover_sheet['A6'] = 'Líder'
    cover_sheet['B6'] = group.leader or 'N/A'
    cover_sheet['A7'] = 'Fecha de generación'
    cover_sheet['B7'] = timezone.localtime().strftime('%Y-%m-%d %H:%M')

    for row in range(3, 8):
        label_cell = cover_sheet[f'A{row}']
        value_cell = cover_sheet[f'B{row}']
        label_cell.font = Font(bold=True, color='184336')
        label_cell.fill = PatternFill(start_color='E6F1EE', end_color='E6F1EE', fill_type='solid')
        label_cell.alignment = Alignment(horizontal='left', vertical='center')
        label_cell.border = thin_border
        value_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        value_cell.border = thin_border

    cover_sheet.column_dimensions['A'].width = 28
    cover_sheet.column_dimensions['B'].width = 60
    cover_sheet.row_dimensions[1].height = 30

    ws_researchers = workbook.create_sheet('Investigadores')
    ws_researchers.append(['Código RH', 'Nombre', 'Categoría', 'Tipo Vinculación', 'Estado'])
    for row in data['researchers']:
        status_text = 'Activo' if row.get('status') == 'ACTIVE' else ('Inactivo' if row.get('status') == 'INACTIVE' else row.get('status'))
        ws_researchers.append([
            row.get('codeRh') or 'N/A',
            row.get('name'),
            row.get('category') or 'N/A',
            row.get('membershipType') or 'N/A',
            status_text or 'N/A'
        ])
    style_table_header(ws_researchers, 5)
    auto_fit_columns(ws_researchers)

    ws_articles = workbook.create_sheet('Artículos')
    ws_articles.append(['Título', 'Año', 'Categoría', 'Fuente', 'ISSN', 'DOI', 'Investigadores del Grupo', 'Otros Investigadores'])
    for row in data['products']['articles']:
        category_value = (row.get('category') or '').strip() if isinstance(row.get('category'), str) else row.get('category')
        category_value = category_value if category_value else 'N/R'
        source_value = (row.get('categorySource') or '').strip() if isinstance(row.get('categorySource'), str) else row.get('categorySource')
        source_value = source_value if source_value else 'N/R'

        if category_value == 'N/R':
            source_value = 'N/R'

        ws_articles.append([
            row['title'],
            row.get('year'),
            category_value,
            source_value,
            row.get('issn'),
            row.get('doi'),
            ', '.join([a.get('name', '') for a in row.get('authors', []) if a.get('isGroupMember')]),
            ', '.join([a.get('name', '') for a in row.get('authors', []) if not a.get('isGroupMember')]),
        ])
    style_table_header(ws_articles, 8)
    auto_fit_columns(ws_articles)

    ws_books = workbook.create_sheet('Libros')
    ws_books.append(['Título', 'Año', 'ISBN', 'Investigadores del Grupo', 'Otros Investigadores'])
    for row in data['products']['books']:
        ws_books.append([
            row['title'],
            row.get('year'),
            row.get('isbn'),
            ', '.join([a.get('name', '') for a in row.get('authors', []) if a.get('isGroupMember')]),
            ', '.join([a.get('name', '') for a in row.get('authors', []) if not a.get('isGroupMember')]),
        ])
    style_table_header(ws_books, 5)
    auto_fit_columns(ws_books)

    ws_chapters = workbook.create_sheet('Capítulos')
    ws_chapters.append(['Capítulo', 'Libro', 'Año', 'ISBN', 'Investigadores del Grupo', 'Otros Investigadores'])
    for row in data['products']['bookChapters']:
        ws_chapters.append([
            row.get('chapterTitle'),
            row.get('bookTitle'),
            row.get('year'),
            row.get('isbn'),
            ', '.join([a.get('name', '') for a in row.get('authors', []) if a.get('isGroupMember')]),
            ', '.join([a.get('name', '') for a in row.get('authors', []) if not a.get('isGroupMember')]),
        ])
    style_table_header(ws_chapters, 6)
    auto_fit_columns(ws_chapters)

    ws_theses = workbook.create_sheet('Tesis')
    ws_theses.append(['Título', 'Año', 'Tipo', 'Institución', 'Involucrados del Grupo', 'Involucrados Externos'])
    for row in data['products']['theses']:
        ws_theses.append([
            row.get('title'),
            row.get('year'),
            row.get('thesisType'),
            row.get('institution'),
            '\n'.join([f"{a.get('name', '')} - {a.get('role', '')}".strip(' -') for a in row.get('authors', []) if a.get('isGroupMember')]),
            '\n'.join([f"{a.get('name', '')} - {a.get('role', '')}".strip(' -') for a in row.get('authors', []) if not a.get('isGroupMember')]),
        ])
    style_table_header(ws_theses, 6)
    auto_fit_columns(ws_theses)

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    safe_code = re.sub(r'[\\/:*?"<>|]+', '-', group_code).strip() or 'SIN-CODIGO'
    safe_name = re.sub(r'[\\/:*?"<>|]+', ' ', group_name).strip() or 'Grupo'
    safe_name = re.sub(r'\s+', ' ', safe_name)
    filename = f"Ficha-Grupo-{safe_code}-{safe_name}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

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




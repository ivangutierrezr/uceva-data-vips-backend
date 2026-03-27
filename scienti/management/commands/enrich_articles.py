import os
import re
import pandas as pd
from django.core.management.base import BaseCommand
from django.conf import settings
from scienti.models import Article, ArticleCategory, ArticleCategorySource

def normalize_category(raw: str) -> str:
    """Normalize a raw category value to a simple string when possible."""
    if not raw:
        return raw
    return str(raw).strip()

class Command(BaseCommand):
    help = 'Enrich articles with categories from Publindex datasets only'

    def handle(self, *args, **options):
        self.stdout.write("Starting Article Enrichment Process...")

        publindex_source, _ = ArticleCategorySource.objects.get_or_create(name='PUBLINDEX')

        deleted_scimago_categories, _ = ArticleCategory.objects.filter(source__name='SCIMAGO').delete()
        ArticleCategorySource.objects.filter(name='SCIMAGO').delete()
        if deleted_scimago_categories:
            self.stdout.write(
                self.style.WARNING(
                    f"Removed {deleted_scimago_categories} existing article category rows from SCIMAGO to keep Publindex as the only source."
                )
            )
        
        self.stdout.write("Loading Articles from DB (Year > 2019)...")
        articles = Article.objects.filter(year__gt=2019).exclude(issn__isnull=True).exclude(issn__exact='').values('id', 'issn', 'year')
        
        issn_map = {}
        count = 0 
        for art in articles:
            raw_issn = art['issn']
            clean_val = self.clean_issn(raw_issn)
            year = art['year']
            
            if clean_val:
                if clean_val not in issn_map:
                    issn_map[clean_val] = []
                issn_map[clean_val].append({'id': art['id'], 'year': year})
                count += 1
        
        self.stdout.write(f"Loaded {count} articles with valid ISSNs and Year > 2019.")

        base_dir = settings.BASE_DIR
        publindex_dir = os.path.join(base_dir, 'datasets', 'publindex')
        self.process_directory(publindex_dir, publindex_source, issn_map)

        self.stdout.write(self.style.SUCCESS("Enrichment process completed successfully."))

    def clean_issn(self, text):
        if not text:
            return ""
        return re.sub(r'\D', '', str(text))

    def process_directory(self, directory_path, source, issn_map):
        if not os.path.exists(directory_path):
            self.stdout.write(self.style.WARNING(f"Directory not found: {directory_path}"))
            return

        files = sorted([f for f in os.listdir(directory_path) if f.endswith('.xlsx') or f.endswith('.xls') or f.endswith('.csv')])
        
        self.stdout.write(f"Processing {source.name} files: {files}")
        
        for filename in files:
            years_covered = []
            
            clean_name = os.path.splitext(filename)[0] # remove extension
            
            if '-' in clean_name:
                parts = clean_name.split('-')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    start_y = int(parts[0])
                    end_y = int(parts[1])
                    years_covered = list(range(start_y, end_y + 1))
                else: 
                     self.stdout.write(self.style.ERROR(f"Skipping file {filename}: Cannot parse year from filename."))
                     continue
            elif clean_name.isdigit():
                years_covered = [int(clean_name)]
            else:
                self.stdout.write(self.style.ERROR(f"Skipping file {filename}: Format error (expected YYYY or YYYY-YYYY)."))
                continue
            
            file_path = os.path.join(directory_path, filename)
            self.process_file(file_path, years_covered, source, issn_map)

    def process_file(self, file_path, years_covered, source, issn_map):
        self.stdout.write(f"  -> Reading {file_path} for years {years_covered}...")
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error reading {file_path}: {e}"))
            return

        df.columns = [str(c).strip().lower() for c in df.columns]

        issn_col = next((col for col in df.columns if 'issn' in str(col)), None)
        category_col = next(
            (col for col in df.columns if str(col).strip().lower() in {'categoria', 'categoría'}),
            None,
        )

        if issn_col is None or category_col is None:
             self.stdout.write(self.style.WARNING(f"    Skipping {file_path}: Missing columns. Found: {df.columns.tolist()[:5]}..."))
             return

        matches_count = 0
        
        for _, row in df.iterrows():
            try:
                raw_issns = str(row[issn_col])
                raw_cat = row[category_col]
            except KeyError:
                continue
            
            if pd.isna(raw_cat) or raw_cat == '' or raw_cat == '-':
                continue

            parts = re.split(r'[;,]', raw_issns)
            
            matched_articles = [] # List of dicts {id, year}
            
            for part in parts:
                clean_part = self.clean_issn(part)
                if clean_part and clean_part in issn_map:
                     matched_articles.extend(issn_map[clean_part])
            
            valid_articles = [art for art in matched_articles if art['year'] in years_covered]
            
            for art in valid_articles:
                obj, created = ArticleCategory.objects.update_or_create(
                    article_id=art['id'],
                    source=source,
                    year=art['year'], # Use the article's year
                    defaults={'category': normalize_category(str(raw_cat))}
                )
                matches_count += 1
        
        self.stdout.write(f"    -> Processed. Matched and saved {matches_count} categories.")

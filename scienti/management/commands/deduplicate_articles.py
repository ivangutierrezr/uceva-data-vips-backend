import re

from django.core.management.base import BaseCommand
from django.utils import timezone

from scienti.models import Article

try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

class Command(BaseCommand):
    help = 'Deduplicate articles based on Title, ISSN, Year, Country and DOI'

    def handle(self, *args, **options):
        self.stdout.write("Starting Article Deduplication...")

        articles_qs = Article.objects.all().select_related('country', 'journal')
        self.stdout.write(f"Analyzing {articles_qs.count()} articles...")
        
        articles_list = list(articles_qs)
        processed_ids = set()
        deleted_count = 0

        title_groups = {}
        for art in articles_list:
            norm = self.normalize_text(art.title)
            if not norm: continue
            if norm not in title_groups: title_groups[norm] = []
            title_groups[norm].append(art)
        
        self.stdout.write("--> Phase 1: Deduplicating by Exact Normalized Title...")
        count_p1 = self.process_groups(title_groups, processed_ids)
        deleted_count += count_p1
        self.stdout.write(f"    Phase 1 deleted {count_p1} articles.")

        doi_groups = {}
        for art in articles_list:
            if art.id in processed_ids: continue
            if not art.doi or len(art.doi) < 5: continue
            
            clean_doi = art.doi.strip().lower()
            if clean_doi not in doi_groups: doi_groups[clean_doi] = []
            doi_groups[clean_doi].append(art)
        
        self.stdout.write("--> Phase 2: Deduplicating by DOI...")
        count_p2 = self.process_groups(doi_groups, processed_ids, method="doi")
        deleted_count += count_p2
        self.stdout.write(f"    Phase 2 deleted {count_p2} articles.")

        if fuzz:
            self.stdout.write("--> Phase 3: Fuzzy Title Matching ( > 90% Similarity )...")
            survivors = [a for a in articles_list if a.id not in processed_ids]
            count_p3 = 0
            
            fuzzy_blocks = {}
            for art in survivors:
                norm = self.normalize_text(art.title)
                if len(norm) < 5: continue
                key = norm[:10] # First 10 chars as block key
                if key not in fuzzy_blocks: fuzzy_blocks[key] = []
                fuzzy_blocks[key].append(art)
            
            for key, block in fuzzy_blocks.items():
                if len(block) < 2: continue
                # Pairwise check in block
                
                local_survivors = []
                for candidate in block:
                    is_dup = False
                    for i, survivor in enumerate(local_survivors):
                        # Fuzzy Check
                        ratio = fuzz.ratio(self.normalize_text(candidate.title), self.normalize_text(survivor.title))
                        
                        year_c = candidate.year or 0
                        year_s = survivor.year or 0
                        current_year = timezone.now().year + 1
                        invalid_c = year_c > current_year
                        invalid_s = year_s > current_year
                        
                        threshold = 90
                        if (invalid_c and not invalid_s) or (invalid_s and not invalid_c):
                            threshold = 80 # Lower threshold if we are fixing a bad date
                        
                        if ratio > threshold: 
                             winner = self.pick_better_record(candidate, survivor)
                             if winner == candidate:
                                 self.delete_article(survivor)
                                 processed_ids.add(survivor.id)
                                 local_survivors[i] = candidate
                                 count_p3 += 1
                             else:
                                 self.delete_article(candidate)
                                 processed_ids.add(candidate.id)
                                 count_p3 += 1
                             is_dup = True
                             break
                    if not is_dup:
                        local_survivors.append(candidate)
            
            deleted_count += count_p3
            self.stdout.write(f"    Phase 3 deleted {count_p3} articles.")

        self.stdout.write("--> Phase 4: Sanitizing Invalid Years...")
        current_year = timezone.now().year + 1
        invalid_year_count = 0
        
        final_survivors = Article.objects.filter(year__gt=current_year)
        for art in final_survivors:
             old_year = art.year
             art.year = None 
             art.save()
             self.stdout.write(f"    Sanitized Article '{art.title[:30]}...' Year {old_year} -> None")
             invalid_year_count += 1
             
        self.stdout.write(f"    Phase 4 sanitized {invalid_year_count} articles.")

        self.stdout.write(self.style.SUCCESS(f"Deduplication Complete. Total Deleted: {deleted_count}"))

    def process_groups(self, groups, processed_ids, method="title"):
        deleted = 0
        for key, candidates in groups.items():
            # Filter out already deleted
            valid_candidates = [c for c in candidates if c.id not in processed_ids]
            if len(valid_candidates) < 2: continue

            survivors = []
            for candidate in valid_candidates:
                is_duplicate = False
                for i, survivor in enumerate(survivors):
                    is_dup_logic = False
                    if method == "doi":
                        is_dup_logic = True
                    else:
                        is_dup_logic = self.are_duplicates(candidate, survivor)
                    
                    if is_dup_logic:
                        is_duplicate = True
                        winner = self.pick_better_record(candidate, survivor)
                        
                        if winner == candidate:
                            self.delete_article(survivor)
                            processed_ids.add(survivor.id)
                            survivors[i] = candidate
                            deleted += 1
                        else:
                            self.delete_article(candidate)
                            processed_ids.add(candidate.id)
                            deleted += 1
                        break 
                
                if not is_duplicate:
                    survivors.append(candidate)
        return deleted

    def delete_article(self, article):
        article.delete()


    def normalize_text(self, text):
        if not text:
            return ""
        # Lowercase, remove special chars, keep alphanumeric
        return re.sub(r'[^a-zA-Z0-9]', '', text.lower())

    def are_duplicates(self, a, b):
        return True

    def pick_better_record(self, a, b):
        current_year = timezone.now().year + 1
        
        year_a = a.year or 0
        year_b = b.year or 0
        
        valid_a = 0 < year_a <= current_year
        valid_b = 0 < year_b <= current_year
        
        if valid_a and not valid_b: return a
        if valid_b and not valid_a: return b

        if valid_a and valid_b and year_a != year_b:
            return a if year_a > year_b else b
            
        country_a = a.country.name.lower() if a.country else ''
        country_b = b.country.name.lower() if b.country else ''
        
        usa_a = 'estados unidos' in country_a or 'usa' in country_a
        usa_b = 'estados unidos' in country_b or 'usa' in country_b
        if usa_a and not usa_b: return a
        if usa_b and not usa_a: return b
        
        col_a = 'colombia' in country_a
        col_b = 'colombia' in country_b
        # If one is Foreign (not Col) and other is Col, keep Foreign
        if not col_a and col_b: return a
        if not col_b and col_a: return b

        doi_a = a.doi.strip() if a.doi else ''
        doi_b = b.doi.strip() if b.doi else ''
        
        if doi_a and not doi_b: return a
        if doi_b and not doi_a: return b
        
        return self.get_more_complete(a, b)

    def get_more_complete(self, a, b):
        score_a = 0
        score_b = 0
        
        fields = ['doi', 'volume', 'issue', 'pages', 'issn', 'product_type']
        for f in fields:
            if getattr(a, f): score_a += 1
            if getattr(b, f): score_b += 1
            
        if score_a > score_b: return a
        if score_b > score_a: return b
        
        return a if a.id > b.id else b


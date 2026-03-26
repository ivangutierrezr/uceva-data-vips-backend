from django.core.management.base import BaseCommand
from scienti.models import Researcher
import requests
from bs4 import BeautifulSoup
import re
import time

# ---------------------------------------------------------------------------
# Category short-name map: datos.gov.co returns full Spanish strings.
# We normalize them to the short codes used throughout the app.
# ---------------------------------------------------------------------------
CATEGORY_NORMALIZE = {
    'investigador emérito':        'Emérito',
    'investigador senior':         'Senior',
    'investigador asociado':       'Asociado',
    'investigador junior':         'Junior',
}

def _normalize_category(raw: str) -> str:
    """Return short category label from a full MinCiencias classification string."""
    if not raw:
        return raw
    lower = raw.lower().strip()
    for key, short in CATEGORY_NORMALIZE.items():
        if key in lower:
            return short
    # Fallback: return first word title-cased
    return raw.split()[0].title()


class Command(BaseCommand):
    help = (
        'Enriches researcher data. '
        'Primary source: datos.gov.co (MinCiencias open data, most recent convocatoria). '
        'Fallback source: CvLAC page (for researchers not found in datos.gov.co).'
    )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting researcher enrichment process...'))

        all_researchers = list(Researcher.objects.all())
        valid_researchers = [r for r in all_researchers if r.code_rh and r.code_rh.isdigit()]
        researchers_map = {r.code_rh: r for r in valid_researchers}
        ids_to_process = list(researchers_map.keys())

        self.stdout.write(
            f"Found {len(ids_to_process)} valid researchers (with numeric ID) out of {len(all_researchers)} total."
        )

        # ------------------------------------------------------------------ #
        # STEP 1 — datos.gov.co (Socrata) — primary / most up-to-date source  #
        # ------------------------------------------------------------------ #
        batch_size = 50
        base_url = "https://www.datos.gov.co/resource/bqtm-4y2h.json"
        updated_count = 0
        errors_count = 0
        enriched_ids: set[str] = set()   # track who got data from step 1

        for i in range(0, len(ids_to_process), batch_size):
            batch_ids = ids_to_process[i:i + batch_size]
            quoted_ids = [f"'{pid}'" for pid in batch_ids]
            id_list_str = ",".join(quoted_ids)

            query_params = {
                "$select": "id_persona_pr, nme_clasificacion_pr, nme_niv_form_pr, ano_convo, nme_municipio_res_pr, nme_departamento_res_pr",
                "$where": f"id_persona_pr in ({id_list_str})",
                "$order": "ano_convo DESC",
                "$limit": 5000,
            }

            try:
                response = requests.get(base_url, params=query_params, timeout=15)
                response.raise_for_status()
                data = response.json()

                processed_in_batch: set[str] = set()
                for record in data:
                    remote_id = record.get('id_persona_pr')
                    if remote_id not in researchers_map or remote_id in processed_in_batch:
                        continue

                    researcher = researchers_map[remote_id]
                    category_raw = record.get('nme_clasificacion_pr')
                    education_val = record.get('nme_niv_form_pr')
                    city_val     = record.get('nme_municipio_res_pr')
                    dept_val     = record.get('nme_departamento_res_pr')

                    fields: list[str] = []
                    if category_raw:
                        normalized = _normalize_category(category_raw)
                        if researcher.category != normalized:
                            researcher.category = normalized
                            fields.append('category')
                        enriched_ids.add(remote_id)   # found in datos.gov.co

                    if education_val and researcher.education_level != education_val:
                        researcher.education_level = education_val
                        fields.append('education_level')
                    if city_val and researcher.city != city_val:
                        researcher.city = city_val
                        fields.append('city')
                    if dept_val and researcher.department != dept_val:
                        researcher.department = dept_val
                        fields.append('department')

                    if fields:
                        researcher.save(update_fields=fields)
                        updated_count += 1
                        if updated_count % 10 == 0:
                            self.stdout.write(
                                f"Updated: {researcher.name} -> {researcher.category} | {education_val}"
                            )

                    processed_in_batch.add(remote_id)

                time.sleep(0.5)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error in batch {i}: {e}"))
                errors_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Step 1 (datos.gov.co) completed. Updated: {updated_count}. Errors: {errors_count}'
            )
        )

        # ------------------------------------------------------------------ #
        # STEP 2 — CvLAC fallback — historical source for gaps               #
        # Only runs for researchers that still have no category after step 1. #
        # ------------------------------------------------------------------ #
        missing = [
            r for r in all_researchers
            if not r.category and r.cvlac_url
        ]
        self.stdout.write(
            f"Step 2 (CvLAC fallback): {len(missing)} researchers still missing category."
        )

        cvlac_updated = 0
        cvlac_errors  = 0

        for researcher in missing:
            try:
                resp = requests.get(researcher.cvlac_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')

                category_val   = self._cvlac_field(soup, 'Categoría')
                education_val  = self._cvlac_education(soup)

                fields: list[str] = []
                if category_val:
                    normalized = _normalize_category(category_val)
                    if researcher.category != normalized:
                        researcher.category = normalized
                        fields.append('category')
                if education_val and not researcher.education_level:
                    researcher.education_level = education_val
                    fields.append('education_level')

                if fields:
                    researcher.save(update_fields=fields)
                    cvlac_updated += 1
                    self.stdout.write(
                        f"  [CvLAC] {researcher.name} -> {researcher.category} | {researcher.education_level}"
                    )

                time.sleep(0.3)

            except Exception as e:
                cvlac_errors += 1
                self.stdout.write(self.style.WARNING(f"  [CvLAC] Error for {researcher.name}: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f'Step 2 (CvLAC) completed. Updated: {cvlac_updated}. Errors: {cvlac_errors}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Process completed. Total updated: {updated_count + cvlac_updated}.'
            )
        )

    # ---------------------------------------------------------------------- #
    # CvLAC helpers                                                           #
    # ---------------------------------------------------------------------- #

    def _cvlac_field(self, soup: BeautifulSoup, label: str) -> str:
        """Find a table row by its label text and return the adjacent cell value."""
        for td in soup.find_all('td'):
            if td.get_text(strip=True) == label:
                sibling = td.find_next_sibling('td')
                if sibling:
                    return sibling.get_text(separator=' ', strip=True)
        return ''

    def _cvlac_education(self, soup: BeautifulSoup) -> str:
        """
        Extract the highest academic degree from the CvLAC page.
        Looks for the 'Formación' / 'Estudios' table section.
        Returns a normalized string like 'Doctorado', 'Maestría/Magister', etc.
        """
        DEGREE_MAP = [
            ('doctorado',           'Doctorado'),
            ('phd',                 'Doctorado'),
            ('postdoctorado',       'Postdoctorado'),
            ('maestría',            'Maestría/Magister'),
            ('magister',            'Maestría/Magister'),
            ('especialización',     'Especialización'),
            ('especialista',        'Especialización'),
            ('pregrado',            'Pregrado'),
            ('universitario',       'Pregrado'),
        ]
        text = soup.get_text().lower()
        for keyword, label in DEGREE_MAP:
            if keyword in text:
                return label
        return ''

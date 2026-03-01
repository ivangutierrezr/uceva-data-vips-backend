from django.core.management.base import BaseCommand
from django.db import transaction
from scienti.models import (
    ResearchGroup, Researcher, GroupMember,
    Article, Book, BookChapter, Thesis,
    ArticleAuthor, BookAuthor, ChapterAuthor,
    ThesisTutor, ThesisStudent,
    ScientificEvent, EventInstitution,
    Institution, ProductType, AcademicProgram,
    Country, Department, City, Journal, Publisher,
    ResearchLine, KnowledgeArea, NationalProgram
)
import requests
from bs4 import BeautifulSoup
import datetime
import re
import hashlib
import unicodedata
import time

class Command(BaseCommand):
    help = 'Sincroniza los datos de grupos de investigación desde Scienti (Minciencias)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Ejecuta todo el proceso de extraccion simulando la insercion para reportar cuantas filas se crearian, pero revierte todo al final (no guarda en base de datos).',
        )

    def handle(self, *args, **options):
        from django.apps import apps
        from django.core.management import call_command
        from django.db import transaction
        
        is_dry_run = options.get('dry_run')
        app_models = apps.get_app_config('scienti').get_models()
        
        initial_counts = {}
        if is_dry_run:
            self.stdout.write(self.style.WARNING("=================================================="))
            self.stdout.write(self.style.WARNING("====== MODO DRY RUN ACTIVO (SIMULACION) ========"))
            self.stdout.write(self.style.WARNING("=================================================="))
            self.stdout.write(self.style.NOTICE("Calculando estado base de las tablas..."))
            for model in app_models:
                initial_counts[model.__name__] = model.objects.count()
        
        try:
            with transaction.atomic():
                self.stdout.write(self.style.SUCCESS('Iniciando proceso de sincronizacion con Scienti...'))
                scraper = ScientiScraper(self.stdout, self.style)
                scraper.run()
                self.stdout.write(self.style.SUCCESS('Sincronizacion de grupos completada.'))

                # Call Enrich Researchers Command
                self.stdout.write(self.style.WARNING('Iniciando enriquecimiento de investigadores...'))
                call_command('enrich_researchers')
                self.stdout.write(self.style.SUCCESS('Enriquecimiento completado exitosamente.'))
                
                if is_dry_run:
                    self.stdout.write(self.style.WARNING("\n================ REPORTE DE VOLUMEN (DRY-RUN) ================"))

                    changes_found = False
                    for model in app_models:
                        final_count = model.objects.count()
                        initial = initial_counts[model.__name__]
                        diff = final_count - initial
                        if diff > 0:
                            self.stdout.write(self.style.SUCCESS(f"{model.__name__:<25} | Antes: {initial:<8} | Despues: {final_count:<8} | Insertados (Diff): +{diff:<8}"))
                            changes_found = True
                    
                    if not changes_found:
                        self.stdout.write(self.style.NOTICE("Ninguna tabla recibiria registros nuevos."))
                    
                    self.stdout.write(self.style.WARNING("=============================================================="))
                    
                    self.stdout.write(self.style.ERROR("REVIRTIENDO TRANSACCION PARA NO MODIFICAR BD..."))
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.SUCCESS("Rollback completado. La base de datos sigue intacta."))
                    
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error durante el proceso: {e}"))
            raise e

class ScientiScraper:
    BASE_URL = "https://scienti.minciencias.gov.co/ciencia-war/busquedaGrupoXInstitucionGrupos.do"
    COD_INST = "935"  # UCEVA
    MAX_ROWS = 100
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # --- DEBUG SETTINGS ---
    # Set to True to limit the number of processed items for testing
    DEBUG_MODE = False
    MAX_DEBUG_ITEMS = 15
    # ----------------------

    def __init__(self, stdout, style):
        self.stdout = stdout
        self.style = style
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _log(self, msg):
        self.stdout.write(msg)

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        return " ".join(text.split())

    def _to_title_case(self, text: str) -> str:
        if not text:
            return ""
        try:
            import string
            return string.capwords(text.lower())
        except:
            return text.title()

    def _normalize_key(self, text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize('NFD', text)
        cleaned_text = "".join(c for c in normalized if unicodedata.category(c) != 'Mn')
        cleaned_text = cleaned_text.upper().strip()
        cleaned_text = re.sub(r'[^A-Z0-9]', '', cleaned_text)
        return cleaned_text

    def _parse_location_string(self, text: str):
        """
        Parses location string like "City, Country", "City - Dept - Country" 
        or "City - Dept".
        Returns (city_name, dept_name, country_name)
        """
        if not text: return None, None, None
        
        # Normalize separators: replace " - " with ","
        normalized_text = text.replace(" - ", ",").replace(" – ", ",")
        
        parts = [p.strip() for p in normalized_text.split(',') if p.strip()]
        
        city = None
        dept = None
        country = None
        
        if len(parts) >= 3:
            # City, Dept, Country
            city = parts[0]
            dept = parts[1]
            country = parts[-1] 
        elif len(parts) == 2:
            # Ambiguity: "City, Country" or "City, Dept"
            # Heuristic: Check if second part is a known country or looks like one
            candidate_second = parts[1]
            
            # Known countries list (could be expanded)
            known_countries = ["Colombia", "Estados Unidos", "España", "Brasil", "México", "Argentina", "Chile", "Perú", "Ecuador", "Francia", "Alemania", "Italia", "Reino Unido"]
            
            is_country = False
            if candidate_second in known_countries:
                is_country = True
            elif candidate_second.lower() in ["usa", "ee.uu", "eeuu", "uk"]:
                is_country = True
            
            if is_country:
                city = parts[0]
                country = parts[1]
            else:
                # Assume City, Dept (implies Country=Colombia usually, but we leave country None or explicit)
                # If we assume default Colombia for dept, we can do it here, but let's stick to what's written
                city = parts[0]
                dept = parts[1]
                # Optional: verification if dept is known
                
        elif len(parts) == 1:
            city = parts[0]
            
        return city, dept, country

    def _build_article_id(self, article_data: dict, cod_grupo: str) -> str:
        parts = [
            "ARTICULO_REVISTA",
            cod_grupo if cod_grupo else "",
            self._normalize_key(article_data.get('title', '')),
            self._normalize_key(article_data.get('issn', '')),
            str(article_data.get('year', '')),
            self._normalize_key(article_data.get('doi', '')),
            self._normalize_key(article_data.get('journal', '')),
            self._normalize_key(article_data.get('country', ''))
        ]
        base_string = "|".join(parts)
        sha256_hash = hashlib.sha256(base_string.encode('utf-8')).hexdigest()
        return f"ART-{sha256_hash[:10].upper()}"

    def _build_book_id(self, book_data: dict, cod_grupo: str) -> str:
        parts = [
            "LIBRO",
            cod_grupo if cod_grupo else "",
            self._normalize_key(book_data.get('product_type', '')),
            self._normalize_key(book_data.get('title', '')),
            str(book_data.get('year', '')),
            self._normalize_key(book_data.get('isbn', '')),
            self._normalize_key(book_data.get('publisher', '')),
            self._normalize_key(book_data.get('country', ''))
        ]
        base_string = "|".join(parts)
        sha256_hash = hashlib.sha256(base_string.encode('utf-8')).hexdigest()
        return f"LIB-{sha256_hash[:10].upper()}"

    def _build_chapter_id(self, chapter_data: dict, cod_grupo: str) -> str:
        parts = [
            "CAPITULO", 
            cod_grupo if cod_grupo else "",
            self._normalize_key(chapter_data.get('product_type', '')),
            self._normalize_key(chapter_data.get('chapter_title', '')),
            self._normalize_key(chapter_data.get('book_title', '')),
            self._normalize_key(chapter_data.get('isbn', '')),
            str(chapter_data.get('year', '')),
            self._normalize_key(chapter_data.get('publisher', ''))
        ]
        base_string = "|".join(parts)
        sha256_hash = hashlib.sha256(base_string.encode('utf-8')).hexdigest()
        return f"CAP-{sha256_hash[:10].upper()}"
    
    def _build_thesis_id(self, thesis_data: dict, cod_grupo: str, index: int = 0) -> str:
        # Generate a truly unique ID for every thesis found in a group list
        # We include everything that makes it distinct in that list context
        parts = [
            "TESIS",
            str(cod_grupo), 
            self._normalize_key(thesis_data.get('title', '')),
            self._normalize_key(thesis_data.get('nombre_estudiante', '')),
            str(thesis_data.get('year', '')),
            # Adding index to ensure uniqueness even for identical data entries in the same group list
            str(index)
        ]
        
        base_string = "|".join(parts)
        sha256_hash = hashlib.sha256(base_string.encode('utf-8')).hexdigest()
        return f"TES-{sha256_hash[:10].upper()}"
    
    def _build_event_id(self, event_data: dict, cod_grupo: str) -> str:
        parts = [
            "EVENTO",
            self._normalize_key(event_data.get('name', '')),
            str(event_data.get('start_date', '')), 
            self._normalize_key(event_data.get('event_type', '')),
        ]
        base_string = "|".join(parts)
        sha256_hash = hashlib.sha256(base_string.encode('utf-8')).hexdigest()
        return f"EVA-{sha256_hash[:10].upper()}"

    def _build_external_author_id(self, author_name: str) -> str:
        if not author_name:
            return "AE-UNKNOWN"
        normalized_name = self._normalize_key(author_name)
        sha256_hash = hashlib.sha256(normalized_name.encode('utf-8')).hexdigest()
        return f"AE-{sha256_hash[:10].upper()}"

    def _get_page_content(self, page_number: int = 1):
        params = {
            'codInst': self.COD_INST,
            'grupos_tr_': 'true',
            'grupos_p_': page_number,
            'grupos_mr_': self.MAX_ROWS
        }
        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            response.encoding = 'ISO-8859-1'
            return response.text
        except requests.RequestException as e:
            self._log(self.style.ERROR(f"Error petición página {page_number}: {e}"))
            return None

    def _normalize_date(self, date_text: str):
        """
        Convert dates like "Julio 2023", "4 2023" to a datetime.date object (first day of month)
        Usage: For Thesis start/end date fields which are DateFields in DB.
        """
        if not date_text:
            return None
        
        # Mapping spanish months
        months = {
            'enero': '01', 'febrero': '02', 'febreo': '02', 'marzo': '03', 'abril': '04',
            'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
            'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
        }
        
        text = date_text.strip().lower()
        
        # 1. Try finding YYYY
        year_match = re.search(r'(\d{4})', text)
        if not year_match:
            return None
        year = int(year_match.group(1))

        # 2. Try finding month name
        month = 1 # Default to Jan if only year present? Or maybe None?
        found_month = False
        for m_name, m_num in months.items():
            if m_name in text:
                month = int(m_num)
                found_month = True
                break
        
        # 3. If no month name, try finding numeric month (1-12) before or after year
        # e.g. "4 2023" or "2023-04" or "2023/4"
        if not found_month:
            # Look for 1 or 2 digits that are NOT the year
            # Remove the year from text to avoid false match
            text_no_year = text.replace(str(year), '').strip()
            # Simple check for a number 1-12
            month_match = re.search(r'\b(1[0-2]|0?[1-9])\b', text_no_year)
            if month_match:
                month = int(month_match.group(1))
        
        try:
            return datetime.date(year, month, 1)
        except ValueError:
            return None


    def run(self):
        page = 1
        has_more_data = True
        
        while has_more_data:
            self._log(f"Procesando página {page} de Grupos...")
            html = self._get_page_content(page)
            if not html:
                break
                
            soup = BeautifulSoup(html, 'html.parser')
            rows = soup.find_all('tr')
            groups_found = 0
            
            for tr in rows:
                text_content = tr.get_text()
                # Validación básica de fila de grupo
                if not re.search(r'COL\d{7}', text_content):
                    continue
                
                group_data = self._extract_group_basic_data(tr)
                if group_data:
                    self._process_group(group_data)
                    groups_found += 1
                    
                    if self.DEBUG_MODE:
                         self._log(self.style.WARNING(f"MODO DEBUG: Deteniendo después del primer grupo."))
                         has_more_data = False
                         break
            
            if groups_found == 0:
                self._log("    -> No se encontraron grupos en esta página. Finalizando paginación.")
                has_more_data = False
            else:
                # Verificar si llegamos al total de registros reportados por la tabla (Resultados X - Y de Z)
                status_bar = soup.find('tr', class_='statusBar')
                if status_bar:
                    status_text = status_bar.get_text(strip=True)
                    # Patrón esperado: "Resultados 1 - 50 de 120." o "Resultados 1 - 16 de 16."
                    match_total = re.search(r'de\s+(\d+)', status_text)
                    match_range = re.search(r'- (\d+) de', status_text)
                    
                    if match_total and match_range:
                        total_records = int(match_total.group(1))
                        last_shown = int(match_range.group(1))
                        
                        self._log(f"    -> Estado paginación: Mostrando hasta {last_shown} de {total_records}")
                        
                        if last_shown >= total_records:
                            self._log("    -> Se han recorrido todos los registros disponibles.")
                            has_more_data = False
                        else:
                            page += 1
                            time.sleep(1)
                    else:
                        # Si no podemos parsear la barra de estado, seguimos la lógica antigua (mientras haya grupos)
                        page += 1
                        time.sleep(1)
                else:
                    page += 1
                    time.sleep(1)

    def _extract_group_basic_data(self, tr) -> dict:
        cells = tr.find_all('td')
        if len(cells) < 2:
            return None
            
        texts = [self._clean_text(td.get_text()) for td in cells]
        full_text = " ".join(texts)
        
        if "15 50 100" in full_text: # Controles de paginación
            return None
            
        match_cod = re.search(r'COL\d{7}', full_text)
        if not match_cod:
            return None
            
        cod_grupo = match_cod.group(0).upper()
        
        # Buscar nombre y líder
        idx_cod = -1
        for i, text in enumerate(texts):
            if cod_grupo in text:
                idx_cod = i
                break
        
        nombre_grupo = "N/A"
        lider = "N/A"
        if idx_cod != -1:
            if idx_cod + 1 < len(texts):
                nombre_grupo = self._to_title_case(texts[idx_cod + 1])
            if idx_cod + 2 < len(texts):
                lider = self._to_title_case(self._clean_text(texts[idx_cod + 2].replace("Líder:", "")))
                
        # Categoría
        categoria = "Sin Clasificar"
        grp_pattern = re.compile(r'Categor[ií]a\s*([A-Z0-9]+)', re.IGNORECASE)
        for text in texts:
            if "Categoría" in text or "Reconocido" in text:
                match_cat = grp_pattern.search(text)
                if match_cat:
                    categoria = match_cat.group(1)
                elif "Reconocido" in text:
                    categoria = "Reconocido"
                break
        
        # Link GrupLAC
        link = tr.find('a', href=True)
        gruplac_url = link['href'] if link else ""
        
        return {
            "cod_grupo": cod_grupo,
            "nombre_grupo": nombre_grupo,
            "categoria_grupo": categoria,
            "lider": lider,
            "gruplac_url": gruplac_url
        }

    def _process_group(self, group_data):
        cod_grupo = group_data['cod_grupo']
        self._log(f"  -> Sincronizando Grupo: {cod_grupo} - {group_data['nombre_grupo'][:30]}...")

        # 1. Guardar/Actualizar Grupo
        grupo_obj, created = ResearchGroup.objects.update_or_create(
            code=cod_grupo,
            defaults={
                "name": group_data['nombre_grupo'],
                "category": group_data['categoria_grupo'],
                "leader": group_data['lider'],
                "gruplac_url": group_data['gruplac_url']
            }
        )

        # 2. Scrapear detalles (Miembros y Productos)
        if group_data['gruplac_url']:
            # Eliminamos el try-except para que el script falle inmediatamente ante un error
            self._scrape_group_details(grupo_obj, group_data['gruplac_url'])

    def _scrape_group_details(self, grupo_obj, url):
        response = self.session.get(url, timeout=30)
        response.encoding = 'ISO-8859-1'
        soup = BeautifulSoup(response.text, 'html.parser')

        # --- NEW: Parse Extended Group Data ---
        try:
            self._log("     -> Ampliando datos básicos del grupo...")
            # Look for the "Datos básicos" table
            basic_data_table = None
            for table in soup.find_all('table'):
                if "Datos básicos" in table.get_text():
                    basic_data_table = table
                    break
            
            if basic_data_table:
                # Iterate rows to find specific fields
                rows = basic_data_table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) < 2: continue
                    
                    label = self._clean_text(cells[0].get_text()).lower()
                    value_cell = cells[1]
                    value_text = self._clean_text(value_cell.get_text())

                    if "formación" in label:
                        # "Año: 2004 Mes: 4" -> "2004 - 4"
                        # Or take as is
                        grupo_obj.formation_date_info = value_text
                    
                    elif "departamento - ciudad" in label:
                        # "VALLE DEL CAUCA - TULUÁ"
                        parts = value_text.split("-")
                        dept_name = ""
                        city_name = ""
                        
                        if len(parts) >= 2:
                            dept_name = self._to_title_case(parts[0].strip())
                            city_name = self._to_title_case(parts[1].strip())
                        else:
                            dept_name = self._to_title_case(value_text)
                            
                        grupo_obj.department = dept_name
                        grupo_obj.city = city_name
                        
                        # --- NORMALIZATION LOGIC START ---
                        # 1. Handle Department
                        # Use iexact to match "Valle del Cauca" with "Valle Del Cauca"
                        d_obj = Department.objects.filter(name__iexact=dept_name).first()
                        if not d_obj and dept_name:
                            # Create new Department linked to Colombia (default)
                            col_obj, _ = Country.objects.get_or_create(name="Colombia")
                            d_obj = Department.objects.create(name=dept_name, country=col_obj)
                        grupo_obj.department_obj = d_obj
                        
                        # 2. Handle City
                        if city_name:
                            # Try finding city in that department first
                            c_qs = City.objects.filter(name__iexact=city_name)
                            if d_obj:
                                c_qs = c_qs.filter(department=d_obj)
                            
                            c_obj = c_qs.first()
                            
                            if not c_obj:
                                # Create new City
                                col_obj, _ = Country.objects.get_or_create(name="Colombia")
                                c_obj = City.objects.create(
                                    name=city_name, 
                                    department=d_obj,
                                    country=col_obj
                                )
                            grupo_obj.city_obj = c_obj
                        # --- NORMALIZATION LOGIC END ---

                    elif "certificado" in label:
                        grupo_obj.certification_status = value_text

                    elif "página web" in label:
                        link = value_cell.find('a', href=True)
                        if link and link['href'] and link['href'] != "null":
                            grupo_obj.website = link['href']
                    
                    elif "e-mail" in label:
                        link = value_cell.find('a', href=True)
                        if link and "mailto:" in link['href']:
                            grupo_obj.email = link['href'].replace("mailto:", "").strip()
                        else:
                            grupo_obj.email = value_text
                            
                    elif "clasificación" in label and "vigencia" in label:
                         grupo_obj.classification_validity = value_text
                    
                    elif "área de conocimiento" in label:
                        # "Ciencias Sociales -- Derecho -- Derecho"
                        areas = value_text.split("--")
                        grupo_obj.knowledge_areas.clear()
                        for area in areas:
                            clean_area = self._to_title_case(area.strip())
                            if clean_area:
                                ka_obj, _ = KnowledgeArea.objects.get_or_create(name=clean_area)
                                grupo_obj.knowledge_areas.add(ka_obj)

                    elif "programa nacional" in label:
                        # "Ciencia, Tecnología e Innovación..., Otro..."
                        is_secondary = "secundario" in label
                        programs = [p.strip() for p in value_text.split(",")]
                        
                        target_m2m = grupo_obj.secondary_national_programs if is_secondary else grupo_obj.national_programs
                        target_m2m.clear()
                        
                        for prog in programs:
                            if not prog or prog.lower() == "no aplica": continue
                            clean_prog = self._to_title_case(prog)
                            np_obj, _ = NationalProgram.objects.get_or_create(name=clean_prog)
                            target_m2m.add(np_obj)

                grupo_obj.save()
        except Exception as e:
             self._log(self.style.ERROR(f"Error parseando datos básicos extendidos: {e}"))

        # --- NEW: Parse Research Lines ---
        try:
            self._log("     -> Procesando Líneas de Investigación...")
            lines_table = None
            for table in soup.find_all('table'):
                if "Líneas de investigación declaradas por el grupo" in table.get_text():
                    lines_table = table
                    break
            
            if lines_table:
                # Clear existing
                grupo_obj.research_lines.clear()
                
                rows = lines_table.find_all('tr')
                for row in rows:
                    # Skip header
                    if row.find('td', class_='celdaEncabezado'): continue
                    
                    cell = row.find('td')
                    if not cell: continue
                    
                    line_text = self._clean_text(cell.get_text())
                    # Remove "1.- " or "10.-" prefix
                    clean_line = re.sub(r'^\d+[\.\-]+\s*', '', line_text).strip()
                    clean_line = self._to_title_case(clean_line)
                    
                    if clean_line:
                        rl_obj, _ = ResearchLine.objects.get_or_create(name=clean_line)
                        grupo_obj.research_lines.add(rl_obj)

        except Exception as e:
            self._log(self.style.ERROR(f"Error parseando líneas de investigación: {e}"))


        # Mapa para cachear IDs de integrantes en memoria y usarlos al vincular autores
        # Clave: Nombre Normalizado, Valor: Instancia Integrante (o solo ID/cod_rh)
        members_map = {} 

        # --- A. INTEGRANTES ---
        self._log("     -> Procesando Integrantes...")
        
        # Buscar tabla de integrantes
        target_table = None
        for table in soup.find_all('table'):
            if "Integrantes del grupo" in table.get_text():
                target_table = table
                break
        
        if not target_table:
            # Fallback
            for table in soup.find_all('table'):
                headers = [th.get_text().strip() for th in table.find_all('td', class_='celdaEncabezado')]
                if "Nombre" in headers and "Vinculación" in headers:
                    target_table = table
                    break
        
        if target_table:
            rows = target_table.find_all('tr')
            for row in rows:
                if row.find('td', class_='celdaEncabezado'): continue
                cols = row.find_all('td')
                if len(cols) < 2: continue
                
                first_cell_text = self._clean_text(cols[0].get_text())
                if "Nombre" == first_cell_text: continue
                
                # Nombre y Link
                raw_name = re.sub(r'^\d+[\.\-\s]*', '', first_cell_text).strip()
                nombre_title = self._to_title_case(raw_name)
                
                link_cvlac = cols[0].find('a', href=True)
                cvlac_url = link_cvlac['href'] if link_cvlac else ""
                
                cod_rh = ""
                if cvlac_url:
                    m = re.search(r'cod_rh=(\d+)', cvlac_url)
                    if m: cod_rh = m.group(1)
                
                # Datos de vinculación
                vinculacion = self._to_title_case(self._clean_text(cols[1].get_text())) if len(cols) > 1 else ""
                horas = self._clean_text(cols[2].get_text()) if len(cols) > 2 else ""
                periodo = self._clean_text(cols[3].get_text()) if len(cols) > 3 else ""
                estado = "ACTIVE" if "Actual" in periodo or not periodo else "INACTIVE"
                
                # -- Guardar Integrante (Maestro) --
                if cod_rh:
                    identificador = cod_rh
                else:
                    identificador = f"NORH-{self._normalize_key(nombre_title)}"
                
                integrante_obj, _ = Researcher.objects.update_or_create(
                    code_rh=identificador, 
                    defaults={
                        "name": nombre_title,
                        "cvlac_url": cvlac_url
                    }
                )
                
                # -- Guardar Relación Integrante-Grupo --
                GroupMember.objects.update_or_create(
                    group=grupo_obj,
                    researcher=integrante_obj,
                    defaults={
                        "membership_type": vinculacion,
                        "dedication_hours": horas,
                        "period": periodo,
                        "status": estado
                    }
                )
                
                # Map para autores
                key_name = self._normalize_key(nombre_title)
                members_map[key_name] = integrante_obj

        # --- B. PRODUCTOS (Artículos, Libros, Capítulos) ---
        
        def process_authors(product_instance, author_names_list, ModelAutorClass, fk_field_name):
            processed_ids = []
            
            for index, name in enumerate(author_names_list):
                key = self._normalize_key(name)
                member_obj = members_map.get(key)
                
                es_integrante = False
                ext_id = None
                
                if member_obj:
                    es_integrante = True
                else:
                    ext_id = self._build_external_author_id(name)
                
                defaults = {
                    "is_group_member": es_integrante,
                    "author_name": name, # Original name
                    "order": index
                }
                
                if es_integrante:
                    # Buscamos por integrante
                    obj, _ = ModelAutorClass.objects.update_or_create(
                        **{fk_field_name: product_instance, "researcher": member_obj},
                        defaults=defaults
                    )
                else:
                    obj, _ = ModelAutorClass.objects.update_or_create(
                        **{fk_field_name: product_instance, "author_name": name, "researcher__isnull": True},
                        defaults=defaults
                    )
                
                processed_ids.append(obj.id)

            # Eliminar autores que ya no están en la lista (Huérfanos)
            ModelAutorClass.objects.filter(**{fk_field_name: product_instance}).exclude(id__in=processed_ids).delete()

        # Helper para procesar Tutores y Estudiantes
        def process_thesis_actors(thesis_instance, names_list, ModelClass, fk_field_name, name_field):
            processed_ids = []
            for index, name in enumerate(names_list):
                name = name.strip()
                if not name: continue
                
                key = self._normalize_key(name)
                member_obj = members_map.get(key)
                
                defaults = {
                     name_field: name,
                     "order": index
                }
                
                if member_obj:
                    # Intenta vincular con integrante si existe
                    obj, _ = ModelClass.objects.update_or_create(
                         **{fk_field_name: thesis_instance, "researcher": member_obj},
                         defaults=defaults
                    )
                else:
                    # Solo texto
                    obj, _ = ModelClass.objects.update_or_create(
                        **{fk_field_name: thesis_instance, name_field: name, "researcher__isnull": True},
                        defaults=defaults
                    )
                processed_ids.append(obj.id)
            
            # Limpiar huérfanos
            ModelClass.objects.filter(**{fk_field_name: thesis_instance}).exclude(id__in=processed_ids).delete()


        # 1. Artículos
        self._log("     -> Procesando Artículos...")
        articulos_data = self._extract_articles_from_soup(soup)
        if self.DEBUG_MODE:
             self._log(f"        DEBUG: Limitando artículos a {self.MAX_DEBUG_ITEMS}")
             articulos_data = articulos_data[:self.MAX_DEBUG_ITEMS]
        for art in articulos_data:
            art_id = self._build_article_id(art, grupo_obj.code)
            autores_nombres = art.pop("autores", [])
            
            # Resolver FKs
            pais_obj = None
            ciudad_obj = None
            if art.get('country'):
                # Try to detect if it's "City, Country"
                raw = art.get('country')
                if ',' in raw:
                    parts = raw.split(',', 1)
                    city_str = parts[0].strip()
                    country_str = parts[1].strip()
                    pais_obj, _ = Country.objects.get_or_create(name=country_str)
                    ciudad_obj, _ = City.objects.get_or_create(name=city_str, country=pais_obj)
                else:
                    pais_obj, _ = Country.objects.get_or_create(name=raw)
            
            revista_obj = None
            if art.get('journal'):
                # Usar update_or_create para guardar el ISSN si viene
                revista_obj, _ = Journal.objects.update_or_create(
                    name=art.get('journal'),
                    defaults={'issn': art.get('issn')}
                )
            
            # --- NORMALIZATION: ProductType ---
            product_type_str = art.get('product_type', '')
            product_type_obj = None
            if product_type_str:
                product_type_obj, _ = ProductType.objects.get_or_create(
                    name=product_type_str,
                    defaults={"category": "Article"}
                )

            articulo_obj, _ = Article.objects.update_or_create(
                hash_id=art_id,
                defaults={
                    "group": grupo_obj,
                    "title": art.get('title', '')[:500], # Truuncate if needed
                    "country": pais_obj,
                    "city": ciudad_obj,
                    "journal": revista_obj,
                    "year": int(art.get('year')) if art.get('year') and art.get('year').isdigit() else None,
                    "volume": art.get('volume', ''),
                    "issue": art.get('fasciculo', ''),
                    "pages": art.get('paginas', ''),
                    "doi": art.get('doi', ''),
                    "doi_suffix": art.get('doi_suffix', ''),
                    "issn": art.get('issn', ''),
                    "product_type": product_type_str,
                    "product_type_obj": product_type_obj
                }
            )
            process_authors(articulo_obj, autores_nombres, ArticleAuthor, 'article')

        # 2. Libros
        self._log("     -> Procesando Libros...")
        libros_data = self._extract_books_from_soup(soup)
        if self.DEBUG_MODE:
             self._log(f"        DEBUG: Limitando libros a {self.MAX_DEBUG_ITEMS}")
             libros_data = libros_data[:self.MAX_DEBUG_ITEMS]

        for book in libros_data:
            book_id = self._build_book_id(book, grupo_obj.code)
            autores_nombres = book.pop("autores", [])
            
            pais_obj = None
            ciudad_obj = None
            if book.get('country'):
                raw = book.get('country')
                if ',' in raw:
                    parts = raw.split(',', 1)
                    city_str = parts[0].strip()
                    country_str = parts[1].strip()
                    # Only treat as city if both parts are substantial
                    if len(city_str) > 2 and len(country_str) > 2:
                        pais_obj, _ = Country.objects.get_or_create(name=country_str)
                        ciudad_obj, _ = City.objects.get_or_create(name=city_str, country=pais_obj)
                    else:
                        pais_obj, _ = Country.objects.get_or_create(name=raw)
                else:
                    pais_obj, _ = Country.objects.get_or_create(name=raw)
            
            editorial_obj = None
            if book.get('publisher'):
                editorial_obj, _ = Publisher.objects.get_or_create(name=book.get('publisher'))

            # --- NORMALIZATION: ProductType ---
            product_type_str = book.get('product_type', '')
            product_type_obj = None
            if product_type_str:
                product_type_obj, _ = ProductType.objects.get_or_create(
                    name=product_type_str,
                    defaults={"category": "Book"}
                )

            libro_obj, _ = Book.objects.update_or_create(
                hash_id=book_id,
                defaults={
                    "group": grupo_obj,
                    "title": book.get('title', '')[:500],
                    "year": int(book.get('year')) if book.get('year') and book.get('year').isdigit() else None,
                    "isbn": book.get('isbn', ''),
                    "publisher": editorial_obj,
                    "country": pais_obj,
                    "city": ciudad_obj,
                    "product_type": product_type_str,
                    "product_type_obj": product_type_obj
                }
            )
            process_authors(libro_obj, autores_nombres, BookAuthor, 'book')
            
        # 3. Capítulos
        self._log("     -> Procesando Capítulos...")
        cap_data = self._extract_chapters_from_soup(soup)
        if self.DEBUG_MODE:
             self._log(f"        DEBUG: Limitando capítulos a {self.MAX_DEBUG_ITEMS}")
             cap_data = cap_data[:self.MAX_DEBUG_ITEMS]

        for cap in cap_data:
            cap_id = self._build_chapter_id(cap, grupo_obj.code)
            autores_nombres = cap.pop("autores", [])
            
            editorial_obj = None
            if cap.get('publisher'):
                editorial_obj, _ = Publisher.objects.get_or_create(name=cap.get('publisher'))
            
            # --- NORMALIZATION: ProductType ---
            product_type_str = cap.get('product_type', '')
            product_type_obj = None
            if product_type_str:
                product_type_obj, _ = ProductType.objects.get_or_create(
                    name=product_type_str,
                    defaults={"category": "Chapter"}
                )

            cap_obj, _ = BookChapter.objects.update_or_create(
                hash_id=cap_id,
                defaults={
                    "group": grupo_obj,
                    "chapter_title": cap.get('chapter_title', '')[:500],
                    "book_title": cap.get('book_title', '')[:500],
                    "year": int(cap.get('year')) if cap.get('year') and cap.get('year').isdigit() else None,
                    "isbn": cap.get('isbn', ''),
                    "publisher": editorial_obj,
                    "product_type": product_type_str,
                    "product_type_obj": product_type_obj
                }
            )
            process_authors(cap_obj, autores_nombres, ChapterAuthor, 'chapter')

        # 4. Tesis (Trabajos dirigidos)
        self._log("     -> Procesando Tesis/Trabajos Dirigidos...")
        thesis_data = self._extract_thesis_from_soup(soup)
        if self.DEBUG_MODE:
             self._log(f"        DEBUG: Limitando tesis a {self.MAX_DEBUG_ITEMS}")
             thesis_data = thesis_data[:self.MAX_DEBUG_ITEMS]

        # Flush strategy: If we want to fully refresh/link correctly without stale data for this group
        # we could delete all thesises for this group, but that kills analytics history if IDs change.
        # Since hash_id is stable, update_or_create is preferred.
        # But user asked to "Delete info from DB". The safest way is to wipe the slate clean per group or globally.
        # Given the instruction context, I will assume a global flush is handled elsewhere or manual action
        # BUT here, let's normalize the new field.

        for idx, t in enumerate(thesis_data):
            t_id = self._build_thesis_id(t, grupo_obj.code, idx)
            tutores = t.pop("tutores", [])
            estudiantes_raw = t.pop("nombre_estudiante", "")
            estudiantes = [self._to_title_case(x.strip()) for x in estudiantes_raw.split(',') if x.strip()]
            
            # --- NORMALIZATION: Institution & Thesis Type & Academic Program ---
            inst_name = t.get('institution', '')
            institution_obj = None
            if inst_name:
                institution_obj, _ = Institution.objects.get_or_create(name=inst_name)
            
            thesis_type_str = t.get('thesis_type', '')
            thesis_type_obj = None
            if thesis_type_str:
                thesis_type_obj, _ = ProductType.objects.get_or_create(
                    name=thesis_type_str, 
                    defaults={"category": "Thesis"}
                )
            
            academic_program_str = t.get('academic_program', '')
            academic_program_obj = None
            if academic_program_str:
                academic_program_obj, _ = AcademicProgram.objects.get_or_create(name=academic_program_str)

            thesis_obj, _ = Thesis.objects.update_or_create(
                hash_id=t_id,
                defaults={
                    "group": grupo_obj,
                    "title": t.get('title', '')[:500],
                    "period": t.get('period', ''),
                    "year": int(t.get('year')) if t.get('year') and str(t.get('year')).isdigit() else None,
                    "start_date": t.get('start_date'),
                    "end_date": t.get('end_date'),
                    "guidance_type": t.get('guidance_type', ''),
                    "academic_program": academic_program_str,
                    "academic_program_obj": academic_program_obj,
                    "number_of_pages": t.get('number_of_pages', ''),
                    "grade": t.get('grade', ''),
                    "institution": inst_name,
                    "institution_obj": institution_obj,
                    "thesis_type": thesis_type_str,
                    "thesis_type_obj": thesis_type_obj
                }
            )
            process_thesis_actors(thesis_obj, tutores, ThesisTutor, 'thesis', 'tutor_name')
            process_thesis_actors(thesis_obj, estudiantes, ThesisStudent, 'thesis', 'student_name')

        # 5. Scientific Events
        self._log("     -> Procesando Eventos Científicos...")
        events_data = self._extract_scientific_events(soup)
        if self.DEBUG_MODE:
             self._log(f"        DEBUG: Limitando eventos a {self.MAX_DEBUG_ITEMS}")
             events_data = events_data[:self.MAX_DEBUG_ITEMS]

        for e in events_data:
            e_id = self._build_event_id(e, grupo_obj.code)
            institutions = e.pop("institutions", [])
            
            # --- NORMALIZATION: Location (City, Dept, Country) ---
            location_raw = e.get('city', '') # This is the full location string from scraper
            c_name, d_name, co_name = self._parse_location_string(location_raw)
            
            country_obj = None
            dept_obj = None
            city_obj = None
            
            if co_name:
                country_obj, _ = Country.objects.get_or_create(name=self._to_title_case(co_name))
            
            if d_name:
                dept_defaults = {}
                if country_obj:
                    dept_defaults['country'] = country_obj
                dept_obj, _ = Department.objects.get_or_create(
                    name=self._to_title_case(d_name), 
                    defaults=dept_defaults
                )
            
            if c_name:
                city_defaults = {}
                if country_obj: city_defaults['country'] = country_obj
                if dept_obj: city_defaults['department'] = dept_obj
                
                # Try to get existing city first
                city_qs = City.objects.filter(name__iexact=c_name)
                if country_obj:
                    city_qs = city_qs.filter(country=country_obj)
                
                if city_qs.exists():
                     city_obj = city_qs.first()
                     # Update rels if missing
                     if not city_obj.department and dept_obj:
                         city_obj.department = dept_obj
                         city_obj.save()
                else:
                    city_obj = City.objects.create(
                        name=self._to_title_case(c_name),
                        **city_defaults
                    )

            event_obj, _ = ScientificEvent.objects.update_or_create(
                hash_id=e_id,
                defaults={
                   "group": grupo_obj,
                   "title": e.get('name', '')[:500],
                   "event_type": e.get('event_type', ''),
                   "city": location_raw, # Store raw string for backup
                   "city_obj": city_obj,
                   "department_obj": dept_obj,
                   "country_obj": country_obj,
                   "start_date": e.get('start_date'),
                   "end_date": e.get('end_date'),
                   "scope": e.get('scope', ''),
                   "participation_type": e.get('participation_type', '')
                }
            )

            # Sync Institutions
            # Strategy: Delete existing for this event and recreate to handle updates/removals
            event_obj.institutions.all().delete()
            for inst in institutions:
                institution_obj, _ = Institution.objects.get_or_create(name=inst['name'])
                
                EventInstitution.objects.create(
                    event=event_obj,
                    institution_name=inst['name'],
                    institution_obj=institution_obj,
                    relationship_type=inst['relationship']
                )

    # --- EXTRACTORS ---
    def _extract_articles_from_soup(self, soup):
        articles = []
        headers = soup.find_all('td', class_='celdaEncabezado')
        target_header = None
        for h in headers:
            if re.search(r'Art[ií]culos\s+publicados', h.get_text(), re.IGNORECASE):
                target_header = h
                break
        if not target_header: return []

        parent_tr = target_header.find_parent('tr')
        if not parent_tr: return []
        siblings = parent_tr.find_next_siblings('tr')
        
        for sib in siblings:
            if sib.find('td', class_='celdaEncabezado'): break
            tds = sib.find_all('td')
            content_td = None
            for td in tds:
                if re.match(r'^\s*\d+\.\-', td.get_text(strip=True)):
                    content_td = td
                    break
            if not content_td: continue

            full_html = str(content_td)
            # Use separator <br> to handle line breaks reliably, then split by newlines
            text_content = content_td.get_text(separator="\n")
            text_lines = [l.strip() for l in text_content.split('\n') if l.strip()]
            
            # 1. Product Type
            subtipo_producto = "ARTICLE"
            strong_tag = content_td.find('strong')
            if strong_tag:
                 subtipo_producto = strong_tag.get_text().strip().rstrip(':').strip()

            # 2. Title
            titulo = ""
            m_titulo = re.search(r'</strong>\s*:?\s*(.*?)\s*<br', full_html, re.IGNORECASE | re.DOTALL)
            if m_titulo:
                titulo = BeautifulSoup(m_titulo.group(1), 'html.parser').get_text().strip()
            else:
                 # Fallback: remove the leading number and type
                 if text_lines:
                     clean_line = re.sub(r'^\d+\.\-', '', text_lines[0])
                     titulo = clean_line.replace(subtipo_producto, '').strip(' :')

            # Initialize variables
            anio = ""
            doi = ""
            sufijo_doi = ""
            volumen = ""
            fasciculo = ""
            paginas = ""
            issn = ""
            revista = ""
            pais = ""
            autores = []

            # DOI extraction strategy (Regex on FULL HTML content of the cell to avoid split issues)
            # Pattern: matches "DOI:" or "DOI" followed optionally by tags/spaces, then the DOI value
            # Added support for interrupted DOIs (newlines/tags inside)
            # e.g. 10.1234/ <br> 5678
            # OPTIMIZED: Uses non-greedy matching and limits characters to avoid backtracking issues
            m_doi_full = re.search(r'DOI:?[\s<>/a-z]*?([1][0]\.[\d\.]+(?:[\s<>]|%s)*[:/](?:[\s<>]|%s)*[^\s<"]+)' % (r'<[^>]*>', r'<[^>]*>'), full_html, re.IGNORECASE)
            
            # If complex regex fails, try simpler one
            if not m_doi_full:
                 m_doi_full = re.search(r'DOI:?\s*([1][0]\.\d+/[^\s<]+)', full_html, re.IGNORECASE)

            if m_doi_full:
                 raw_doi = m_doi_full.group(1)
                 # Clean up the captured DOI (remove tags and newlines)
                 clean_doi = re.sub(r'<[^>]+>', '', raw_doi)
                 clean_doi = re.sub(r'\s+', '', clean_doi)
                 
                 found_doi = clean_doi.rstrip('.')
                 # Validate common DOI chars
                 if '10.' in found_doi:
                     if '/' in found_doi:
                        # Split on the first slash ONLY
                        parts = found_doi.split('/', 1)
                        doi = parts[0] # Prefix (10.xxxx)
                        sufijo_doi = parts[1] # Suffix (everything after first slash)
                     else:
                        doi = found_doi

            # 3. Iterative Parsing over lines
            for line in text_lines:
                # Authors
                if line.startswith("Autores:"):
                    clean = line.replace("Autores:", "").strip()
                    autores = [self._to_title_case(x.strip()) for x in clean.split(',') if x.strip()]
                    continue

                # Metadata Line(s) usually contain ISSN or city/country + Journal
                # Example: "Reino Unido, MIGRATION LETTERS ISSN: 1741-8984, 2023 vol:20 fasc: 9 págs: 653 - 666, DOI:..."
                
                # Country and Journal often appear at the start of a line containing ISSN
                if "ISSN:" in line:
                    parts = line.split("ISSN:")
                    pre_issn_part = parts[0].strip()
                    
                    # Extract ISSN
                    # ISSN format: dddd-dddd or dddd-dddX
                    m_issn = re.search(r'([0-9]{4}-[0-9]{3}[0-9X])', parts[1])
                    if m_issn:
                        issn = m_issn.group(1)
                    
                    # Try to extract Country and Journal from pre_issn_part
                    # Common format: "Country, JOURNAL NAME" or just "JOURNAL NAME"
                    if pre_issn_part:
                        if ',' in pre_issn_part:
                            loc_parts = pre_issn_part.split(',')
                            # Assume first part is country/city, rest is journal
                            pais = loc_parts[0].strip()
                            revista = ",".join(loc_parts[1:]).strip().rstrip(',')
                        else:
                            revista = pre_issn_part

                # Year
                # Look for 4 digits bounded by word boundaries
                if not anio:
                    m_anio = re.search(r'\b(19|20)\d{2}\b', line)
                    if m_anio:
                         # Ensure it's not part of ISSN or DOI if possible, but regex \b helps
                         anio = m_anio.group(0)

                # DOI
                if "DOI:" in line and not doi:
                    # DOI can be complex. Grab until end of line or comma
                    m_doi = re.search(r'DOI:\s*([^,\s]+)', line, re.IGNORECASE)
                    if m_doi:
                        temp_doi = m_doi.group(1).rstrip('.')
                        if '/' in temp_doi:
                            parts = temp_doi.split('/', 1)
                            doi = parts[0]
                            sufijo_doi = parts[1]
                        else:
                            doi = temp_doi

                # Volume
                # Matches: vol: 20, vol. 20, v. 20
                if not volumen:
                    m_vol = re.search(r'(?:vol\.?|v\.?)\s*:?\s*([^,:\s]+)', line, re.IGNORECASE)
                    if m_vol: volumen = m_vol.group(1)

                # Issue/Fascicle
                # Matches: fasc: 9, n. 9, no. 9
                if not fasciculo:
                    m_fasc = re.search(r'(?:fasc\.?|n\.?|no\.?)\s*:?\s*([^,:\s]+)', line, re.IGNORECASE)
                    if m_fasc: fasciculo = m_fasc.group(1)

                # Pages
                # Matches: págs: 653 - 666, p. 10-20, pp. 10-20
                if not paginas:
                    m_pags = re.search(r'(?:p[áa]gs?\.?|pp?\.?)\s*:?\s*([\d\s\-]+)', line, re.IGNORECASE)
                    if m_pags: paginas = m_pags.group(1).strip()

            articles.append({
                "product_type": self._to_title_case(subtipo_producto),
                "title": self._to_title_case(titulo),
                "country": self._to_title_case(pais),
                "journal": self._to_title_case(revista),
                "issn": issn,
                "year": anio,
                "volume": volumen,
                "fasciculo": fasciculo,
                "paginas": paginas,
                "doi": doi,
                "doi_suffix": sufijo_doi,
                "autores": autores
            })
        return articles

    def _extract_books_from_soup(self, soup):
        books = []
        target_headers = []
        for h in soup.find_all('td', class_='celdaEncabezado'):
            txt = h.get_text()
            if "Libros publicados" in txt or "Otros Libros publicados" in txt:
                target_headers.append(h)
        
        for h in target_headers:
            parent_tr = h.find_parent('tr')
            if not parent_tr: continue
            siblings = parent_tr.find_next_siblings('tr')
            for sib in siblings:
                if sib.find('td', class_='celdaEncabezado'): break
                tds = sib.find_all('td')
                content_td = None
                for td in tds:
                    if re.match(r'^\s*\d+\.\-', td.get_text(strip=True)):
                        content_td = td
                        break
                if not content_td: continue
                
                full_html = str(content_td)
                text_content = content_td.get_text(separator="\n")
                text_lines = [l.strip() for l in text_content.split('\n') if l.strip()]
                
                # 1. Product Type
                subtipo = "BOOK"
                strong_tag = content_td.find('strong')
                if strong_tag:
                    subtipo = strong_tag.get_text().strip().rstrip(':').strip()
                
                # 2. Title
                titulo = ""
                m_titulo = re.search(r'</strong>\s*:?\s*(.*?)\s*<br', full_html, re.IGNORECASE | re.DOTALL)
                if m_titulo:
                    titulo = BeautifulSoup(m_titulo.group(1), 'html.parser').get_text().strip()
                else:
                    if text_lines: 
                        titulo = re.sub(r'^\d+\.\-', '', text_lines[0]).replace(subtipo, '').strip(' :')

                # Initialize variables
                anio = ""
                isbn = ""
                editorial = ""
                pais = ""
                autores = []

                # 3. Iterative Parsing
                for i, line in enumerate(text_lines):
                    # Authors
                    if line.startswith("Autores:"):
                        clean = line.replace("Autores:", "").strip()
                        autores = [self._to_title_case(x.strip()) for x in clean.split(',') if x.strip()]
                        continue

                    # Metadata
                    # Example: Colombia, 2022, ISBN: 978-..., Ed. ...
                    
                    # Country often comes first if it exists as "Country, Year" or "City, Country"
                    # But reliable parsing is hard without defined structure.
                    # We assume parsing 'Location, Year' pattern
                    
                    # Heuristic for Country based on lines ending in comma before Year
                    # E.g. "Colombia," on its own line
                    if not pais and line.endswith(',') and len(line) < 50:
                         # Check if it looks like a location (Capitalized)
                         clean_loc = line.rstrip(',').strip()
                         if clean_loc and clean_loc[0].isupper() and not any(char.isdigit() for char in clean_loc):
                             # Avoid "Vol 1," or "Ed. X,"
                             if "Ed." not in clean_loc and "Vol" not in clean_loc:
                                 pais = clean_loc

                    # Year
                    if not anio:
                        m_anio = re.search(r'\b(19|20)\d{2}\b', line)
                        if m_anio: 
                            anio = m_anio.group(0)
                        
                            # If we found year, check if country is before it in the same line
                            # "Colombia, 2022"
                            pre_year = line[:m_anio.start()]
                            if pre_year and ',' in pre_year:
                                # "Colombia, "
                                # take the last part before comma
                                parts = pre_year.rsplit(',', 1)
                                possible_country = parts[0].strip().rstrip(',')
                                if possible_country and len(possible_country) < 50: # Sanity check
                                    pais = possible_country
                            elif pre_year.strip().endswith(','):
                                # If line was "Colombia, 2022" -> pre_year "Colombia, "
                                temp_pais = pre_year.strip().rstrip(',')
                                if temp_pais: pais = temp_pais
                            # If pais still empty, check PREVIOUS line if it ended in comma
                            elif not pais and i > 0:
                                prev_line = text_lines[i-1]
                                if prev_line.strip().endswith(','):
                                    # "Colombia,"
                                    temp_pais = prev_line.strip().rstrip(',')
                                    if temp_pais and temp_pais[0].isupper() and len(temp_pais) < 50:
                                         pais = temp_pais

                    # ISBN
                    if "ISBN" in line:
                         m_isbn = re.search(r'ISBN\s*:?\s*([0-9X\-\s]+)', line, re.IGNORECASE)
                         if m_isbn:
                             isbn = m_isbn.group(1).strip()
                    
                    # Publisher / Editorial
                    if "Ed." in line or "Editorial" in line:
                        m_ed = re.search(r'(?:Ed\.|Editorial)\s*:?\s*([^,]+)', line, re.IGNORECASE)
                        if m_ed:
                            editorial = m_ed.group(1).strip()
                
                # If country still empty, try to grab the very first word of metadata line if it looks like a location
                if not pais and len(text_lines) > 1:
                     # Second line often has location
                     # But be careful not to grab Title continuation
                     pass # Handled by heuristic above better

                books.append({
                    "product_type": self._to_title_case(subtipo),
                    "title": self._to_title_case(titulo),
                    "autores": autores,
                    "year": anio,
                    "isbn": isbn,
                    "publisher": self._to_title_case(editorial),
                    "country": self._to_title_case(pais)
                })
        return books

    def _extract_chapters_from_soup(self, soup):
        chapters = []
        target_headers = []
        for h in soup.find_all('td', class_='celdaEncabezado'):
            if "Capítulos de libro" in h.get_text():
                target_headers.append(h)
        
        for h in target_headers:
            parent_tr = h.find_parent('tr')
            if not parent_tr: continue
            siblings = parent_tr.find_next_siblings('tr')
            for sib in siblings:
                if sib.find('td', class_='celdaEncabezado'): break
                tds = sib.find_all('td')
                content_td = None
                for td in tds:
                    if re.match(r'^\s*\d+\.\-', td.get_text(strip=True)):
                        content_td = td
                        break
                if not content_td: continue
                
                full_html = str(content_td)
                text_lines = [l.strip() for l in content_td.get_text(separator="\n").split('\n') if l.strip()]
                
                subtipo = "CHAPTER"
                strong_tag = content_td.find('strong')
                if strong_tag:
                    subtipo = strong_tag.get_text().strip().rstrip(':').strip()
                
                # Titulo Capitulo
                titulo_cap = ""
                m_titulo = re.search(r'</strong>\s*:?\s*(.*?)\s*<br', full_html, re.IGNORECASE | re.DOTALL)
                if m_titulo:
                    titulo_cap = BeautifulSoup(m_titulo.group(1), 'html.parser').get_text().strip()
                
                # Metadatos
                meta_line = ""
                autores_line = ""
                
                for line in text_lines:
                    if "ISBN:" in line or "Ed." in line:
                         meta_line = line
                    elif "Autores:" in line:
                         autores_line = line
                
                anio = ""
                isbn = ""
                editorial = ""
                titulo_libro = ""
                
                if meta_line:
                    m_anio = re.search(r'\b(19\d{2}|20\d{2})\b', meta_line)
                    if m_anio: anio = m_anio.group(1)
                    
                    m_isbn = re.search(r'ISBN:\s*([0-9X\-]+)', meta_line, re.IGNORECASE)
                    if m_isbn: isbn = m_isbn.group(1).strip()
                    
                    m_ed = re.search(r'Ed\.\s*([^,]+)', meta_line, re.IGNORECASE)
                    if m_ed: editorial = m_ed.group(1).strip()
                    
                    # Pattern: , \s*2024\s*, (.*?), ISBN:
                    if anio and isbn:
                        pattern_tl = r'{}\s*,\s*(.*?),\s*ISBN:'.format(anio)
                        m_tl = re.search(pattern_tl, meta_line)
                        if m_tl:
                            titulo_libro = m_tl.group(1).strip()

                autores = []
                if autores_line:
                    clean = autores_line.replace("Autores:", "").strip()
                    autores = [self._to_title_case(x.strip()) for x in clean.split(',') if x.strip()]

                chapters.append({
                    "product_type": self._to_title_case(subtipo),
                    "chapter_title": self._to_title_case(titulo_cap),
                    "book_title": self._to_title_case(titulo_libro),
                    "autores": autores,
                    "year": anio,
                    "isbn": isbn,
                    "publisher": self._to_title_case(editorial)
                })
        return chapters

    def _extract_thesis_from_soup(self, soup):
        theses = []
        target_headers = []
        for h in soup.find_all('td', class_='celdaEncabezado'):
            txt = h.get_text(strip=True)
            # Match "Trabajos dirigidos/turorías" (typo) OR "Trabajos dirigidos/tutorías" (correct)
            if "trabajos dirigidos/turorías" in txt.lower() or "trabajos dirigidos/tutorías" in txt.lower():
                target_headers.append(h)
        
        for h in target_headers:
            parent_tr = h.find_parent('tr')
            if not parent_tr: continue
            siblings = parent_tr.find_next_siblings('tr')
            for sib in siblings:
                if sib.find('td', class_='celdaEncabezado'): break
                tds = sib.find_all('td')
                content_td = None
                for td in tds:
                    if re.match(r'^\s*\d+\.\-', td.get_text(strip=True)):
                        content_td = td
                        break
                if not content_td: continue
                
                full_html = str(content_td)
                text_content = content_td.get_text(separator="\n")
                lines = [l.strip() for l in text_content.split('\n') if l.strip()]

                if not lines: continue
                
                # 0. Thesis Type
                tipo_tesis_clean = ""
                strong_tag = content_td.find('strong')
                if strong_tag:
                    raw_type = strong_tag.get_text().strip()
                    lower_raw = raw_type.lower()
                    
                    # Replacements specifiques
                    if "trabajos dirigidos/tutorías de otro tipo" in lower_raw:
                        tipo_tesis_clean = "Otro Tipo"
                    elif "tesis de doctorado" in lower_raw:
                        tipo_tesis_clean = "Doctorado"
                    else:
                        # Prefixes Removal
                        # "Trabajo de grado de " (Singular)
                        if lower_raw.startswith("trabajo de grado de "):
                             tipo_tesis_clean = raw_type[20:].strip()
                        # "Trabajos de grado de " (Plural)
                        elif lower_raw.startswith("trabajos de grado de "):
                             tipo_tesis_clean = raw_type[21:].strip()
                        # "Trabajo de grado " (Singular short)
                        elif lower_raw.startswith("trabajo de grado "):
                             tipo_tesis_clean = raw_type[17:].strip()
                        # "Trabajos de grado " (Plural short)
                        elif lower_raw.startswith("trabajos de grado "):
                             tipo_tesis_clean = raw_type[18:].strip()
                        else:
                             tipo_tesis_clean = raw_type
                    
                    # Capitalize first letter of result
                    tipo_tesis_clean = self._to_title_case(tipo_tesis_clean)

                # 1. Title
                titulo = ""
                m_titulo = re.search(r'</strong>\s*:?\s*(.*?)\s*<br', full_html, re.IGNORECASE | re.DOTALL)
                if m_titulo:
                    titulo = BeautifulSoup(m_titulo.group(1), 'html.parser').get_text().strip()

                # Initialize variables
                periodo = ""
                tipo_orientacion = ""
                anio = None
                estudiantes = ""
                programa = ""
                num_paginas = ""
                valoracion = ""
                institucion = ""
                tutores = []
                
                # 2. Iterate lines to find patterns
                idx_est = -1
                idx_prog = -1
                
                start_date_obj = None
                end_date_obj = None
                
                for i, l in enumerate(lines):
                    # Period and Guidance Type
                    # Pattern expected: "Desde MM/YYYY hasta MM/YYYY, Tipo de orientación: XXX"
                    # But can be split across lines or just "Tipo de orientación: XXX" on its own line
                    
                    if "Tipo de orientación:" in l:
                        parts = l.split("Tipo de orientación:")
                        tipo_orientacion = parts[1].strip()
                        # If "Desde" was also in this line, handle period extraction here (already covered below but careful not to overwrite)

                    if "Desde" in l and "hasta" in l:
                        # Extract Period
                        full_period = l
                        if "Tipo de orientación:" in l:
                            period_split = l.split("Tipo de orientación:")
                            full_period = period_split[0].strip().rstrip(',')
                            # tipo_orientacion already captured above
                        else:
                             full_period = l.strip()
                        
                        periodo = full_period # save to period field
                        
                        # Extract Start Date / End Date
                        match_dates = re.search(r'Desde\s+(.+?)\s+hasta\s+([^\.,]+)', full_period, re.IGNORECASE)
                        
                        start_str = ""
                        end_str = ""
                        
                        if match_dates:
                            start_str = match_dates.group(1).strip()
                            end_str = match_dates.group(2).strip() # "Julio 2024" or "Actual" or "Enero"

                            # Transform start_str -> "MM/YYYY" using _normalize_date helper
                            s_date = self._normalize_date(start_str)
                            if s_date:
                                start_date_obj = s_date.strftime("%m/%Y")
                            else:
                                start_date_obj = start_str # Fallback to raw if parsing fails

                            # Transform end_str -> "MM/YYYY" or keep "Actual"
                            # Special case: End date is a month name without year (e.g. "Enero") -> use start date year
                            e_date = self._normalize_date(end_str)
                            if not e_date and s_date:
                                # Try to see if end_str is just a month name, if so append s_date.year
                                if end_str.lower() in ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']:
                                    new_end = f"{end_str} {s_date.year}"
                                    e_date = self._normalize_date(new_end)

                            if e_date:
                                end_date_obj = e_date.strftime("%m/%Y")
                            else:
                                end_date_obj = end_str # Fallback to raw (e.g. "Actual")
                            
                            # UNIFY PERIOD FORMAT -> "Desde MM/YYYY hasta MM/YYYY"
                            periodo = f"Desde {start_date_obj} hasta {end_date_obj}"

                            # Update anio fallback: 
                            if e_date:
                                anio = e_date.year
                            elif s_date:
                                anio = s_date.year
                        else:
                             # Fallback if regex fails but we have period text
                             pass
                        
                        # Fallback for year extraction if dates failed
                        if not anio:
                            m_anio = re.search(r'hasta\s+.*(\d{4})', periodo, re.IGNORECASE)
                            if m_anio: anio = int(m_anio.group(1))
                        
                    # Student Name
                    if "Nombre del estudiante:" in l:
                        idx_est = i
                        clean = l.replace("Nombre del estudiante:", "").strip()
                        if clean: # If name is on same line
                             estudiantes = clean

                    # Academic Program
                    if "Programa académico:" in l:
                        idx_prog = i
                        programa = l.replace("Programa académico:", "").strip()

                    # Pages and Grade
                    if "Número de páginas:" in l:
                         m_p = re.search(r'Número de páginas:\s*([^,]+)', l)
                         if m_p: num_paginas = m_p.group(1).strip()
                         
                         m_v = re.search(r'Valoración:\s*([^,]+)', l)
                         if m_v: valoracion = m_v.group(1).strip()

                    # Institution
                    if "Institución:" in l:
                        institucion = l.replace("Institución:", "").strip()
                    
                    # Tutors
                    if "Tutor(es)/Cotutor(es):" in l:
                        clean_t = l.replace("Tutor(es)/Cotutor(es):", "").strip()
                        tutores = [self._to_title_case(x.strip()) for x in clean_t.split(',') if x.strip()]

                # --- MULTILINE FALLBACK LOGIC ---
                # Checks if date parsing failed in the loop due to line breaks
                if not start_date_obj and not end_date_obj:
                     full_text_joined = " ".join(lines) 
                     # Case: "Desde 5 2021 hasta \n Mayo 2022" -> "Desde 5 2021 hasta Mayo 2022"
                     # Use wider regex on the joined string
                     m_full = re.search(r'Desde\s+(.+?)\s+hasta\s+(.+?)(?:,|$|Tipo de orientaci)', full_text_joined, re.IGNORECASE)
                     
                     if m_full:
                        s_str = m_full.group(1).strip()
                        e_str = m_full.group(2).strip()
                        
                        # Parse Start
                        s_date = self._normalize_date(s_str)
                        if s_date:
                             start_date_obj = s_date.strftime("%m/%Y")
                        else:
                             start_date_obj = s_str
                        
                        # Parse End
                        e_date = self._normalize_date(e_str)
                        if not e_date and s_date:
                             # Try to see if end_str is just a month name, if so append s_date.year
                             if e_str.lower() in ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']:
                                 new_end = f"{e_str} {s_date.year}"
                                 e_date = self._normalize_date(new_end)

                        if e_date:
                             end_date_obj = e_date.strftime("%m/%Y")
                        else:
                             end_date_obj = e_str

                        # UNIFY PERIOD FORMAT -> "Desde MM/YYYY hasta MM/YYYY" on fallback
                        periodo = f"Desde {start_date_obj} hasta {end_date_obj}"
                        
                        # Extract Year from new end string
                        if e_date:
                            anio = e_date.year
                        elif s_date:
                            anio = s_date.year

                # Handle multiline student names if not found inline
                if not estudiantes and idx_est != -1 and idx_prog != -1 and idx_prog > idx_est:
                    est_lines = lines[idx_est+1 : idx_prog]
                    estudiantes = ", ".join(est_lines)

                theses.append({
                    "title": self._to_title_case(titulo),
                    "period": periodo,
                    "year": anio,
                    "start_date": start_date_obj,
                    "end_date": end_date_obj,
                    "guidance_type": tipo_orientacion,
                    "nombre_estudiante": self._to_title_case(estudiantes),
                    "academic_program": self._to_title_case(programa),
                    "number_of_pages": num_paginas,
                    "grade": self._to_title_case(valoracion),
                    "institution": self._to_title_case(institucion),
                    "thesis_type": self._to_title_case(tipo_tesis_clean),
                    "tutores": tutores
                })
        return theses

    def _extract_scientific_events(self, soup):
        events = []
        target_headers = []
        for h in soup.find_all('td', class_='celdaEncabezado'):
            if "Eventos Científicos" in h.get_text():
                target_headers.append(h)
        
        for h in target_headers:
            parent_tr = h.find_parent('tr')
            if not parent_tr: continue
            siblings = parent_tr.find_next_siblings('tr')
            for sib in siblings:
                if sib.find('td', class_='celdaEncabezado'): break
                tds = sib.find_all('td')
                content_td = None
                for td in tds:
                    if re.match(r'^\s*\d+\.\-', td.get_text(strip=True)):
                        content_td = td
                        break
                if not content_td: continue
                
                full_html = str(content_td)
                text_content = content_td.get_text(separator="\n")
                lines = [l.strip() for l in text_content.split('\n') if l.strip()]

                if not lines: continue

                # 1. Extraction Logic
                # Pattern: <strong>Type</strong> : Event Name <br>
                event_type = ""
                event_name = ""
                
                strong_tag = content_td.find('strong')
                if strong_tag:
                    event_type = strong_tag.get_text().strip()
                
                # Name Extraction Strategy
                # Regex on full HTML is often safest for "text between strong and br"
                # Updated to handle multiline with DOTALL and <br/br>
                m_name = re.search(r'</strong>\s*:?\s*(.*?)(?:<br|</br)', full_html, re.IGNORECASE | re.DOTALL)
                if m_name:
                    soup_name = BeautifulSoup(m_name.group(1), 'html.parser')
                    event_name = soup_name.get_text().strip()
                    event_name = " ".join(event_name.split())
                
                # Fallback if regex failed
                if not event_name:
                     idx_colon = -1
                     for i, l in enumerate(lines):
                         if l.strip().startswith(':'):
                             idx_colon = i
                             break
                         if ':' in l and i < 2: 
                             idx_colon = i
                             break
                     
                     if idx_colon != -1:
                         name_parts = []
                         if lines[idx_colon].strip() == ':':
                             pass
                         elif ':' in lines[idx_colon]:
                             parts = lines[idx_colon].split(':', 1)
                             if len(parts) > 1 and parts[1].strip():
                                name_parts.append(parts[1].strip())
                         for j in range(idx_colon + 1, len(lines)):
                             l = lines[j]
                             if "desde" in l.lower() and "hasta" in l.lower():
                                 break
                             if "desde" in l.lower() and re.search(r'\d{4}', l): 
                                 break
                             name_parts.append(l)
                         event_name = " ".join(name_parts)

                # Location and Dates
                city = ""
                start_date = None
                end_date = None
                
                start_date_str = ""
                end_date_str = ""
                
                for i, l in enumerate(lines):
                    if "desde" in l.lower():
                        parts = re.split(r'\bdesde\b', l, flags=re.IGNORECASE)
                        if len(parts) > 1:
                            city_candidate = parts[0].strip().rstrip(',').strip()
                            if city_candidate and not "eventos científico" in city_candidate.lower():
                                city = city_candidate
                                
                            start_date_str = parts[1].strip().rstrip('-').strip()
                    
                    if "hasta" in l.lower():
                        parts = re.split(r'\bhasta\b', l, flags=re.IGNORECASE)
                        if len(parts) > 1:
                            end_date_str = parts[1].strip()
                
                # Parse Dates using start_date_str and end_date_str
                if start_date_str:
                    try:
                         # Usually format YYYY-MM-DD HH:MM:SS.0
                         start_date_clean = start_date_str.split()[0] # Take YYYY-MM-DD
                         start_date = datetime.datetime.strptime(start_date_clean, "%Y-%m-%d")
                    except: pass
                
                if end_date_str:
                    try:
                         end_date_clean = end_date_str.split()[0]
                         end_date = datetime.datetime.strptime(end_date_clean, "%Y-%m-%d")
                    except: pass

                # Scope and Participation
                scope = ""
                participation = ""
                for l in lines:
                    if "Ámbito:" in l:
                         m_s = re.search(r'Ámbito:\s*([^,]+)', l, re.IGNORECASE)
                         if m_s: scope = m_s.group(1).strip()
                         
                         m_p = re.search(r'Tipos de participación:\s*(.+)', l, re.IGNORECASE)
                         if m_p: participation = m_p.group(1).strip()
                
                # Institutions
                # Inside <ul><li>...
                institutions = []
                ul_tags = content_td.find_all('ul')
                for ul in ul_tags:
                    lis = ul.find_all('li')
                    for li in lis:
                        # Parsing logic for: <i>Nombre...</i> Value <i>Tipo...</i> Value
                        # Or simply text content if tags are messed up
                        li_text = li.get_text(separator="|").strip()
                        # "Nombre de la institución:|Universidade ...|Tipo de vinculación|Gestionadora"
                        
                        inst_name = ""
                        rel_type = ""
                        
                        parts = li_text.split('|')
                        for i, p in enumerate(parts):
                            clean_p = p.strip().lower()
                            if "nombre de la institución" in clean_p and i + 1 < len(parts):
                                inst_name = parts[i+1].strip()
                            if "tipo de vinculación" in clean_p and i + 1 < len(parts):
                                rel_type = parts[i+1].strip()
                        
                        if inst_name:
                            institutions.append({
                                "name": self._to_title_case(inst_name),
                                "relationship": self._to_title_case(rel_type)
                            })

                events.append({
                    "event_type": self._to_title_case(event_type),
                    "name": self._to_title_case(event_name),
                    "city": self._to_title_case(city),
                    "start_date": start_date,
                    "end_date": end_date,
                    "scope": self._to_title_case(scope),
                    "participation_type": self._to_title_case(participation),
                    "institutions": institutions
                })
        return events


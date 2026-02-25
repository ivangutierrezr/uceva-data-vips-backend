from django.core.management.base import BaseCommand
from scienti.models import Researcher
import requests
import time

class Command(BaseCommand):
    help = 'Enriches researcher data by querying the MinCiencias open data portal'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting researcher enrichment process...'))
        
        # Get all researchers
        all_researchers = Researcher.objects.all()
        
        # Filter researchers with numeric IDs (code_rh), which are required for the external API
        valid_researchers = [r for r in all_researchers if r.code_rh and r.code_rh.isdigit()]
        
        # Map code_rh -> Researcher object for quick access
        researchers_map = {r.code_rh: r for r in valid_researchers}
        ids_to_process = list(researchers_map.keys())
        
        self.stdout.write(f"Found {len(ids_to_process)} valid researchers (with numeric ID) out of {len(all_researchers)} total.")

        # Batch IDs to avoid URL length limits
        batch_size = 50
        base_url = "https://www.datos.gov.co/resource/bqtm-4y2h.json"
        
        updated_count = 0
        errors_count = 0
        
        # Process in batches
        for i in range(0, len(ids_to_process), batch_size):
            batch_ids = ids_to_process[i:i + batch_size]
            
            # Format IDs for SoQL query (Socrata)
            # In Socrata id_persona_pr is text, so we need single quotes around values
            quoted_ids = [f"'{pid}'" for pid in batch_ids]
            id_list_str = ",".join(quoted_ids)
            
            # SoQL Query
            # Filter by IDs in the current batch
            # Order by convocation year descending to get the most recent data
            # Updated columns based on dataset bqtm-4y2h inspection (2025-02-19)
            # Use residence fields: nme_municipio_res_pr, nme_departamento_res_pr
            # University info (inst_cod_nombre_pr) not available in this dataset
            query_params = {
                "$select": "id_persona_pr, nme_clasificacion_pr, nme_niv_form_pr, ano_convo, nme_municipio_res_pr, nme_departamento_res_pr",
                "$where": f"id_persona_pr in ({id_list_str})",
                "$order": "ano_convo DESC",
                "$limit": 5000  # High limit in case of many historical records per person
            }

            try:
                # Perform the request
                response = requests.get(base_url, params=query_params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                # Process results
                # Since we ordered by date DESC, the first record found for an ID is the most recent
                processed_ids_in_batch = set()
                
                for record in data:
                    remote_id = record.get('id_persona_pr')
                    category_val = record.get('nme_clasificacion_pr')
                    education_val = record.get('nme_niv_form_pr')
                    city_val = record.get('nme_municipio_res_pr')
                    dept_val = record.get('nme_departamento_res_pr')
                    # University not available in this dataset

                    # Skip if we already processed this ID in this batch (due to DESC order, first is best)
                    if remote_id in researchers_map and remote_id not in processed_ids_in_batch:
                        researcher = researchers_map[remote_id]
                        
                        fields_to_update = []
                        
                        # Update Category
                        if category_val and researcher.category != category_val:
                            researcher.category = category_val
                            fields_to_update.append('category')
                        
                        # Update Education Level
                        if education_val and researcher.education_level != education_val:
                            researcher.education_level = education_val
                            fields_to_update.append('education_level')

                        # Update City
                        if city_val and researcher.city != city_val:
                            researcher.city = city_val
                            fields_to_update.append('city')

                        # Update Department
                        if dept_val and researcher.department != dept_val:
                            researcher.department = dept_val
                            fields_to_update.append('department')
                        
                        # Save if changes detected
                        if fields_to_update:
                            researcher.save(update_fields=fields_to_update)
                            updated_count += 1
                            if updated_count % 10 == 0:
                                self.stdout.write(f"Updated: {researcher.name} -> {category_val} | {education_val}")
                        
                        processed_ids_in_batch.add(remote_id)
                
                # Respect rate limits
                time.sleep(0.5)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error processing batch starting at index {i}: {str(e)}"))
                errors_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Process completed. Updated records: {updated_count}. Batch errors: {errors_count}'))

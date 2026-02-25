import uuid
from django.db import models

# --- ABSTRACT MODELS & CATALOGS ---

class AuditableModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Country(AuditableModel):
    name = models.CharField(max_length=150, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Countries"
        db_table = "scienti_country"

class Department(AuditableModel):
    name = models.CharField(max_length=150)
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='departments')

    def __str__(self):
        return f"{self.name}, {self.country}" if self.country else self.name

    class Meta:
        verbose_name_plural = "Departments"
        unique_together = ('name', 'country')
        db_table = "scienti_department"

class City(AuditableModel):
    name = models.CharField(max_length=150)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='cities')
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='cities')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Cities"
        unique_together = ('name', 'country')
        db_table = "scienti_city"

class Publisher(AuditableModel):
    name = models.CharField(max_length=255, unique=True)
    
    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Publishers"
        db_table = "scienti_publisher"

class Journal(AuditableModel):
    name = models.CharField(max_length=500)
    issn = models.CharField(max_length=50, blank=True, null=True)
    
    def __str__(self):
        return f"{self.name} ({self.issn})"

    class Meta:
        db_table = "scienti_journal"

# --- MAIN MODELS ---


class ResearchLine(AuditableModel):
    name = models.CharField(max_length=500, unique=True, verbose_name="Research Line Name")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Research Lines"
        db_table = "scienti_research_line"

class KnowledgeArea(AuditableModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="Knowledge Area Name")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Knowledge Areas"
        db_table = "scienti_knowledge_area"

class NationalProgram(AuditableModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="National Program Name")

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "National Programs"
        db_table = "scienti_national_program"


class ResearchGroup(AuditableModel):
    code = models.CharField(max_length=50, unique=True, verbose_name="MinCiencias Code")
    name = models.TextField()
    leader = models.CharField(max_length=255, blank=True, null=True) # Name of the leader
    gruplac_url = models.URLField(max_length=1000, blank=True, null=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    
    # Expanded Data
    formation_date_info = models.CharField(max_length=100, blank=True, null=True) # "2004 - 4"
    department = models.CharField(max_length=150, blank=True, null=True)
    city = models.CharField(max_length=150, blank=True, null=True)
    
    # Normalized Location
    department_obj = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='groups')
    city_obj = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='groups')

    certification_status = models.CharField(max_length=255, blank=True, null=True) # "Si el día ..."
    website = models.URLField(max_length=1000, blank=True, null=True)
    email = models.EmailField(max_length=255, blank=True, null=True)
    
    classification_validity = models.TextField(blank=True, null=True) # "con vigencia hasta..."

    # Relationships
    research_lines = models.ManyToManyField(ResearchLine, related_name='groups', blank=True)
    knowledge_areas = models.ManyToManyField(KnowledgeArea, related_name='groups', blank=True)
    national_programs = models.ManyToManyField(NationalProgram, related_name='groups', blank=True) # Primary
    secondary_national_programs = models.ManyToManyField(NationalProgram, related_name='groups_secondary', blank=True) # Secondary

    
    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        verbose_name = "Research Group"
        verbose_name_plural = "Research Groups"
        db_table = "scienti_research_group"

class Researcher(AuditableModel):
    # puede ser cod_rh (numérico) o un ID generado (NORH-...)
    code_rh = models.CharField(max_length=100, unique=True, verbose_name="RH Code or Internal ID") 
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=50, blank=True, null=True) # Junior, Senior, etc
    education_level = models.CharField(max_length=100, blank=True, null=True) # Undergraduate, Master, PhD
    cvlac_url = models.URLField(max_length=1000, blank=True, null=True)
    
    # Enrich fields
    city = models.CharField(max_length=150, blank=True, null=True)
    department = models.CharField(max_length=150, blank=True, null=True)
    university = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return self.name

    class Meta:
        db_table = "scienti_researcher"

class GroupMember(AuditableModel):
    group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE, related_name='members')
    researcher = models.ForeignKey(Researcher, on_delete=models.CASCADE, related_name='memberships')
    membership_type = models.CharField(max_length=255, blank=True) # Vinculacion
    dedication_hours = models.CharField(max_length=50, blank=True, null=True)
    period = models.CharField(max_length=100, blank=True) # Inicio - Fin
    status = models.CharField(max_length=20, default="ACTIVE") 

    class Meta:
        unique_together = ('group', 'researcher', 'membership_type') 
        db_table = "scienti_group_member"


class ProductType(AuditableModel):
    name = models.CharField(max_length=150, unique=True, verbose_name="Product Type Name")
    category = models.CharField(max_length=50, blank=True, null=True, verbose_name="Category (Book, Chapter, etc)")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Product Types"
        db_table = "scienti_product_type"

class Institution(AuditableModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="Institution Name")
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='institutions')
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='institutions')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Institutions"
        db_table = "scienti_institution"

# --- RESEARCH PRODUCTS ---

class Article(AuditableModel):
    hash_id = models.CharField(max_length=50, unique=True) # ART-HASH
    title = models.TextField()
    
    year = models.IntegerField(null=True, blank=True)
    doi = models.CharField(max_length=255, blank=True, null=True)
    doi_suffix = models.CharField(max_length=255, blank=True, null=True)
    issn = models.CharField(max_length=50, blank=True, null=True)

    volume = models.CharField(max_length=50, blank=True, null=True)
    issue = models.CharField(max_length=50, blank=True, null=True) # Fasciculo
    pages = models.CharField(max_length=50, blank=True, null=True)
    
    product_type_obj = models.ForeignKey(ProductType, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')
    product_type = models.CharField(max_length=255, blank=True, null=True) # Kept for migration ease, eventually remove
    

    # Normalized Relations
    group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE, related_name='articles')
    journal = models.ForeignKey(Journal, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')

    def __str__(self):
        return self.title[:50]

    class Meta:
        db_table = "scienti_article"

class Book(AuditableModel):
    hash_id = models.CharField(max_length=50, unique=True) # LIB-HASH
    title = models.TextField()
    isbn = models.CharField(max_length=50, blank=True, null=True)
    year = models.IntegerField(null=True, blank=True)
    
    product_type_obj = models.ForeignKey(ProductType, on_delete=models.SET_NULL, null=True, blank=True, related_name='books')
    product_type = models.CharField(max_length=255, blank=True, null=True) # Kept for migration ease
    
    # Normalized Relations
    group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE, related_name='books')
    publisher = models.ForeignKey(Publisher, on_delete=models.SET_NULL, null=True, blank=True, related_name='books')
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='books')
    country = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='books')

    class Meta:
        db_table = "scienti_book"
    
class BookChapter(AuditableModel):
    hash_id = models.CharField(max_length=50, unique=True) # CAP-HASH
    chapter_title = models.TextField()
    book_title = models.TextField()
    isbn = models.CharField(max_length=50, blank=True, null=True)
    year = models.IntegerField(null=True, blank=True)
    
    product_type_obj = models.ForeignKey(ProductType, on_delete=models.SET_NULL, null=True, blank=True, related_name='chapters')
    product_type = models.CharField(max_length=255, blank=True, null=True) # Kept for migration ease
    
    group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE, related_name='chapters')
    publisher = models.ForeignKey(Publisher, on_delete=models.SET_NULL, null=True, blank=True, related_name='chapters')

    class Meta:
        db_table = "scienti_book_chapter"

class AcademicProgram(AuditableModel):
    name = models.CharField(max_length=255, unique=True, verbose_name="Academic Program Name")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Academic Programs"
        db_table = "scienti_academic_program"

class Thesis(AuditableModel):
    hash_id = models.CharField(max_length=50, unique=True) # TES-HASH
    title = models.TextField()
    period = models.CharField(max_length=255, blank=True)
    guidance_type = models.CharField(max_length=100, blank=True) # Tipo orientacion
    
    academic_program_obj = models.ForeignKey(AcademicProgram, on_delete=models.SET_NULL, null=True, blank=True, related_name='theses')
    academic_program = models.CharField(max_length=255, blank=True) # Kept for migration ease
    
    number_of_pages = models.CharField(max_length=50, blank=True)
    grade = models.CharField(max_length=100, blank=True) # Valoracion
    
    institution_obj = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True, blank=True, related_name='theses')
    institution = models.CharField(max_length=255, blank=True) # Kept for migration ease
    
    start_date = models.CharField(max_length=50, null=True, blank=True) 
    end_date = models.CharField(max_length=50, null=True, blank=True)   
    year = models.IntegerField(null=True, blank=True)     
    
    thesis_type_obj = models.ForeignKey(ProductType, on_delete=models.SET_NULL, null=True, blank=True, related_name='theses')
    thesis_type = models.CharField(max_length=255, blank=True, null=True) # Kept for migration ease

    group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE, related_name='theses')
    
    def __str__(self):
        return self.title[:50]

    class Meta:
        db_table = "scienti_thesis"

class ScientificEvent(AuditableModel):
    hash_id = models.CharField(max_length=50, unique=True) # EVA-HASH
    title = models.TextField()
    event_type = models.CharField(max_length=255, blank=True, null=True)
    # Could normalize event_type too if many duplicates
    
    city = models.CharField(max_length=150, blank=True, null=True) # Kept for migration ease
    city_obj = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    department_obj = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    country_obj = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    scope = models.CharField(max_length=100, blank=True, null=True) # Ambito
    participation_type = models.CharField(max_length=255, blank=True, null=True)

    group = models.ForeignKey(ResearchGroup, on_delete=models.CASCADE, related_name='events')

    def __str__(self):
        return self.title[:50]

    class Meta:
        db_table = "scienti_scientific_event"

class EventInstitution(AuditableModel):
    event = models.ForeignKey(ScientificEvent, on_delete=models.CASCADE, related_name='institutions')
    
    institution_obj = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True, blank=True, related_name='event_participations')
    institution_name = models.CharField(max_length=255) # Kept for migration ease
    
    relationship_type = models.CharField(max_length=100, blank=True) # Gestionadora, Patrocinadora...
    
    class Meta:
        db_table = "scienti_event_institution"

# --- AUTHORSHIP RELATIONS ---

class ArticleAuthor(AuditableModel):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='authors')
    researcher = models.ForeignKey(Researcher, on_delete=models.CASCADE, null=True, blank=True)
    author_name = models.CharField(max_length=255)
    is_group_member = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "scienti_article_author"

class BookAuthor(AuditableModel):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='authors')
    researcher = models.ForeignKey(Researcher, on_delete=models.CASCADE, null=True, blank=True)
    author_name = models.CharField(max_length=255)
    is_group_member = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "scienti_book_author"

class ChapterAuthor(AuditableModel):
    chapter = models.ForeignKey(BookChapter, on_delete=models.CASCADE, related_name='authors')
    researcher = models.ForeignKey(Researcher, on_delete=models.CASCADE, null=True, blank=True)
    author_name = models.CharField(max_length=255)
    is_group_member = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "scienti_chapter_author"

class ThesisTutor(AuditableModel):
    thesis = models.ForeignKey(Thesis, on_delete=models.CASCADE, related_name='tutors')
    researcher = models.ForeignKey(Researcher, on_delete=models.CASCADE, null=True, blank=True) 
    tutor_name = models.CharField(max_length=255)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = "scienti_thesis_tutor"

class ThesisStudent(AuditableModel):
    thesis = models.ForeignKey(Thesis, on_delete=models.CASCADE, related_name='students')
    researcher = models.ForeignKey(Researcher, on_delete=models.CASCADE, null=True, blank=True) 
    student_name = models.CharField(max_length=255)
    order = models.IntegerField(default=0)
    
    class Meta:
        db_table = "scienti_thesis_student"

# --- ARTICLE CATEGORIZATION ---

class ArticleCategorySource(AuditableModel):
    name = models.CharField(max_length=150, unique=True, verbose_name="Source Name")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Article Category Sources"
        db_table = "scienti_article_category_source"

class ArticleCategory(AuditableModel):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='categories')
    source = models.ForeignKey(ArticleCategorySource, on_delete=models.CASCADE, related_name='categories')
    year = models.IntegerField()
    category = models.CharField(max_length=50)

    class Meta:
        unique_together = ('article', 'source', 'year')
        verbose_name_plural = "Article Categories"
        db_table = "scienti_article_category"



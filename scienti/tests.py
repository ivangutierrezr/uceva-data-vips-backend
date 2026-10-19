from django.test import TestCase
from rest_framework.test import APIClient

from scienti.models import (
	Article,
	Book,
	BookChapter,
	Journal,
	ResearchGroup,
	Researcher,
)


class GlobalSearchApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()

		self.group = ResearchGroup.objects.create(
			code='GRP-001',
			name='Grupo de Prueba UCEVA',
		)

		self.researcher = Researcher.objects.create(
			code_rh='RH-9001',
			name='Ana Maria Gomez',
			category='Senior',
		)

		self.journal = Journal.objects.create(
			name='Revista Test',
			issn='1234-5678',
		)

		self.article = Article.objects.create(
			hash_id='ART-001',
			title='Modelo de cooperacion academica',
			year=2025,
			doi='10.1000/xyz123',
			issn='1234-5678',
			group=self.group,
			journal=self.journal,
		)

		self.book = Book.objects.create(
			hash_id='LIB-001',
			title='Analitica institucional para UCEVA',
			isbn='978-958-1234-56-7',
			year=2024,
			group=self.group,
		)

		self.chapter = BookChapter.objects.create(
			hash_id='CAP-001',
			chapter_title='Capitulo de metodologia aplicada',
			book_title='Manual de investigacion',
			isbn='9789581234567',
			year=2023,
			group=self.group,
		)

	def test_search_requires_q_parameter(self):
		response = self.client.get('/api/search/')
		self.assertEqual(response.status_code, 400)

	def test_search_by_doi_issn_and_isbn(self):
		response_doi = self.client.get('/api/search/', {'q': '10.1000/xyz123'})
		self.assertEqual(response_doi.status_code, 200)
		self.assertEqual(response_doi.data['totals']['articles'], 1)

		response_issn = self.client.get('/api/search/', {'q': '12345678'})
		self.assertEqual(response_issn.status_code, 200)
		self.assertEqual(response_issn.data['totals']['articles'], 1)

		response_isbn = self.client.get('/api/search/', {'q': '9789581234567'})
		self.assertEqual(response_isbn.status_code, 200)
		self.assertEqual(response_isbn.data['totals']['books'], 1)
		self.assertEqual(response_isbn.data['totals']['bookChapters'], 1)

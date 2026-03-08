import re
import unicodedata
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand
from django.db import transaction

from scienti.models import Book, BookChapter


class Command(BaseCommand):
    help = "Clean duplicated books and chapters keeping most complete/latest records"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply deletion. Without this flag the command only reports duplicates.",
        )

    def normalize_key(self, text: str | None) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFD", text)
        no_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return re.sub(r"[^A-Z0-9]", "", no_accents.upper())

    def normalize_text(self, text: str | None) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize("NFD", text)
        no_accents = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        lowered = no_accents.lower()
        lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    def similarity(self, a: str | None, b: str | None) -> float:
        na = self.normalize_text(a)
        nb = self.normalize_text(b)
        if not na or not nb:
            return 0.0
        return SequenceMatcher(None, na, nb).ratio()

    def to_year(self, value) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def pick_better_book(self, current: Book, candidate: Book) -> Book:
        cy = self.to_year(current.year)
        ny = self.to_year(candidate.year)
        if ny > cy:
            return candidate
        if cy > ny:
            return current

        curr_len = len(self.normalize_text(current.title))
        cand_len = len(self.normalize_text(candidate.title))
        if cand_len > curr_len:
            return candidate
        if curr_len > cand_len:
            return current

        curr_score = sum(bool(getattr(current, field)) for field in ["isbn", "publisher_id", "country_id"]) 
        cand_score = sum(bool(getattr(candidate, field)) for field in ["isbn", "publisher_id", "country_id"]) 
        if cand_score > curr_score:
            return candidate
        return current

    def pick_better_chapter(self, current: BookChapter, candidate: BookChapter) -> BookChapter:
        cy = self.to_year(current.year)
        ny = self.to_year(candidate.year)
        if ny > cy:
            return candidate
        if cy > ny:
            return current

        curr_len = len(self.normalize_text(current.chapter_title)) + len(self.normalize_text(current.book_title))
        cand_len = len(self.normalize_text(candidate.chapter_title)) + len(self.normalize_text(candidate.book_title))
        if cand_len > curr_len:
            return candidate
        if curr_len > cand_len:
            return current

        curr_score = sum(bool(getattr(current, field)) for field in ["isbn", "publisher_id"]) 
        cand_score = sum(bool(getattr(candidate, field)) for field in ["isbn", "publisher_id"]) 
        if cand_score > curr_score:
            return candidate
        return current

    def process_books(self, apply_changes: bool):
        books = list(Book.objects.select_related("publisher", "country", "group").order_by("group_id", "created_at", "id"))

        to_delete = []
        survivors_by_group: dict[str, list[Book]] = {}

        for candidate in books:
            group_key = str(candidate.group_id)
            group_survivors = survivors_by_group.setdefault(group_key, [])

            duplicate_index = None
            for idx, current in enumerate(group_survivors):
                same_isbn = bool(candidate.isbn) and bool(current.isbn) and self.normalize_key(candidate.isbn) == self.normalize_key(current.isbn)
                title_similarity = self.similarity(candidate.title, current.title)
                same_country = str(candidate.country_id or "") == str(current.country_id or "")
                if same_isbn or (title_similarity >= 0.95 and same_country):
                    duplicate_index = idx
                    break

            if duplicate_index is None:
                group_survivors.append(candidate)
                continue

            current = group_survivors[duplicate_index]
            keeper = self.pick_better_book(current, candidate)
            removed = candidate if keeper is current else current
            group_survivors[duplicate_index] = keeper
            to_delete.append(removed)

        self.stdout.write(self.style.WARNING(f"book_rows_to_delete={len(to_delete)}"))
        for row in to_delete[:20]:
            self.stdout.write(f"BOOK DEL {row.id} | {row.title[:100]} | year={row.year} | isbn={row.isbn or ''}")

        if apply_changes and to_delete:
            deleted = 0
            with transaction.atomic():
                for row in to_delete:
                    row.delete()
                    deleted += 1
            self.stdout.write(self.style.SUCCESS(f"book_deleted={deleted}"))

    def process_chapters(self, apply_changes: bool):
        chapters = list(BookChapter.objects.select_related("publisher", "group").order_by("group_id", "created_at", "id"))

        to_delete = []
        survivors_by_group: dict[str, list[BookChapter]] = {}

        for candidate in chapters:
            group_key = str(candidate.group_id)
            group_survivors = survivors_by_group.setdefault(group_key, [])

            duplicate_index = None
            for idx, current in enumerate(group_survivors):
                same_isbn = bool(candidate.isbn) and bool(current.isbn) and self.normalize_key(candidate.isbn) == self.normalize_key(current.isbn)
                chapter_similarity = self.similarity(candidate.chapter_title, current.chapter_title)
                book_similarity = self.similarity(candidate.book_title, current.book_title)

                if same_isbn or (chapter_similarity >= 0.95 and book_similarity >= 0.90):
                    duplicate_index = idx
                    break

            if duplicate_index is None:
                group_survivors.append(candidate)
                continue

            current = group_survivors[duplicate_index]
            keeper = self.pick_better_chapter(current, candidate)
            removed = candidate if keeper is current else current
            group_survivors[duplicate_index] = keeper
            to_delete.append(removed)

        self.stdout.write(self.style.WARNING(f"chapter_rows_to_delete={len(to_delete)}"))
        for row in to_delete[:20]:
            self.stdout.write(
                f"CHAPTER DEL {row.id} | {row.chapter_title[:80]} | book={row.book_title[:40]} | year={row.year} | isbn={row.isbn or ''}"
            )

        if apply_changes and to_delete:
            deleted = 0
            with transaction.atomic():
                for row in to_delete:
                    row.delete()
                    deleted += 1
            self.stdout.write(self.style.SUCCESS(f"chapter_deleted={deleted}"))

    def handle(self, *args, **options):
        apply_changes = options.get("apply", False)

        self.process_books(apply_changes)
        self.process_chapters(apply_changes)

        if not apply_changes:
            self.stdout.write(self.style.NOTICE("Dry-run only. Use --apply to delete duplicates."))

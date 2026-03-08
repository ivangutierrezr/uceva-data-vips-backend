import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from scienti.models import Article


class Command(BaseCommand):
    help = "Remove duplicated articles per group keeping the earliest created row"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply deletion. Without this flag the command only reports duplicates.",
        )

    def normalize(self, value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"[^A-Z0-9]", "", value.upper())

    def build_key(self, article: Article) -> str:
        return "|".join(
            [
                str(article.group_id or ""),
                self.normalize(article.product_type),
                self.normalize(article.title),
                str(article.year or ""),
                self.normalize(article.journal.name if article.journal else ""),
                self.normalize(article.country.name if article.country else ""),
                self.normalize(article.volume),
                self.normalize(article.issue),
                self.normalize(article.pages),
            ]
        )

    def handle(self, *args, **options):
        apply_changes = options.get("apply", False)

        rows = list(
            Article.objects.select_related("journal", "country", "group").order_by(
                "created_at", "id"
            )
        )

        grouped = defaultdict(list)
        for row in rows:
            grouped[self.build_key(row)].append(row)

        duplicate_groups = [items for items in grouped.values() if len(items) > 1]
        duplicated_rows = sum(len(items) - 1 for items in duplicate_groups)

        self.stdout.write(self.style.WARNING(f"duplicate_groups={len(duplicate_groups)}"))
        self.stdout.write(self.style.WARNING(f"rows_to_delete={duplicated_rows}"))

        for items in duplicate_groups[:20]:
            keeper = items[0]
            self.stdout.write(
                f"KEEP {keeper.id} | {keeper.title[:90]} | year={keeper.year} | issn={keeper.issn or ''}"
            )
            for duplicate in items[1:]:
                self.stdout.write(
                    f"  DEL {duplicate.id} | {duplicate.title[:90]} | year={duplicate.year} | issn={duplicate.issn or ''}"
                )

        if not apply_changes:
            self.stdout.write(self.style.NOTICE("Dry-run only. Use --apply to delete duplicates."))
            return

        if duplicated_rows == 0:
            self.stdout.write(self.style.SUCCESS("No duplicated rows to delete."))
            return

        with transaction.atomic():
            deleted = 0
            for items in duplicate_groups:
                for duplicate in items[1:]:
                    duplicate.delete()
                    deleted += 1

        self.stdout.write(self.style.SUCCESS(f"Deleted rows={deleted}"))

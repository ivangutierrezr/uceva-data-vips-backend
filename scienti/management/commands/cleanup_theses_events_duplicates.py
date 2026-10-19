import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from scienti.models import Thesis, ScientificEvent


class Command(BaseCommand):
    help = "Remove duplicated theses and events per group keeping the earliest created row"

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

    def build_thesis_key(self, thesis: Thesis) -> str:
        return "|".join([
            str(thesis.group_id or ""),
            self.normalize(thesis.title),
            str(thesis.year or ""),
            self.normalize(thesis.thesis_type),
            self.normalize(thesis.institution),
        ])

    def build_event_key(self, event: ScientificEvent) -> str:
        return "|".join([
            str(event.group_id or ""),
            self.normalize(event.title),
            self.normalize(event.event_type),
            str(event.start_date or ""),
        ])

    def _cleanup_model(self, model_name, queryset, build_key, apply_changes):
        rows = list(queryset.order_by("created_at", "id"))
        grouped = defaultdict(list)
        for row in rows:
            grouped[build_key(row)].append(row)

        duplicate_groups = [items for items in grouped.values() if len(items) > 1]
        duplicated_rows = sum(len(items) - 1 for items in duplicate_groups)

        self.stdout.write(self.style.WARNING(f"[{model_name}] duplicate_groups={len(duplicate_groups)}"))
        self.stdout.write(self.style.WARNING(f"[{model_name}] rows_to_delete={duplicated_rows}"))

        for items in duplicate_groups[:10]:
            keeper = items[0]
            self.stdout.write(f"  KEEP {keeper.id} | {keeper.title[:90]}")
            for dup in items[1:]:
                self.stdout.write(f"    DEL {dup.id} | {dup.title[:90]}")

        if not apply_changes:
            return 0

        if duplicated_rows == 0:
            return 0

        with transaction.atomic():
            deleted = 0
            for items in duplicate_groups:
                for dup in items[1:]:
                    dup.delete()
                    deleted += 1
        return deleted

    def handle(self, *args, **options):
        apply_changes = options.get("apply", False)

        deleted_theses = self._cleanup_model(
            "Tesis",
            Thesis.objects.select_related("group"),
            self.build_thesis_key,
            apply_changes,
        )

        deleted_events = self._cleanup_model(
            "Eventos",
            ScientificEvent.objects.select_related("group"),
            self.build_event_key,
            apply_changes,
        )

        if not apply_changes:
            self.stdout.write(self.style.NOTICE("Dry-run only. Use --apply to delete duplicates."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Deleted theses={deleted_theses} events={deleted_events}"))

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
from django.db import connection


def main() -> None:
    django.setup()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename LIKE 'scienti_%'
            ORDER BY tablename
            """
        )
        tables = [row[0] for row in cursor.fetchall()]

        print(f"tables_to_truncate={len(tables)}")
        for table_name in tables:
            print(table_name)

        if not tables:
            print("No scienti tables found. Nothing to truncate.")
            return

        quoted_tables = ", ".join(f'"{name}"' for name in tables)
        cursor.execute(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE")
        print("truncate_done=OK")


if __name__ == "__main__":
    main()

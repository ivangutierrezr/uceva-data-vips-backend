from __future__ import annotations

import os


def setup_django(settings_module: str = "config.settings") -> None:
    """Initialize Django when running ad-hoc scripts.

    Safe to call multiple times.
    """

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

    import django

    if not django.apps.apps.ready:
        django.setup()

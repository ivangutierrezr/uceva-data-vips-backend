from __future__ import annotations

import unicodedata


def remove_accents(value: str) -> str:
    nfkd_form = unicodedata.normalize("NFKD", value)
    return "".join(c for c in nfkd_form if not unicodedata.category(c).startswith("Mn"))


def debug_search(search_term: str) -> None:
    from scienti.utils.exports.django_setup import setup_django

    setup_django()
    from scienti.models import Country

    raw_name = search_term.strip()
    name_spaced = raw_name.replace("-", " ")

    print(f"\n--- Searching for '{search_term}' ---")
    print(f"1) Exact match: '{raw_name}'")
    c = Country.objects.filter(name__iexact=raw_name).first()
    print(f"   -> {c.name if c else 'NOT FOUND'}")

    print(f"2) Spaced match: '{name_spaced}'")
    c = Country.objects.filter(name__iexact=name_spaced).first()
    print(f"   -> {c.name if c else 'NOT FOUND'}")

    print("3) Normalized match:")
    search_normalized = remove_accents(name_spaced).lower()
    all_countries = Country.objects.all()
    for country in all_countries:
        if remove_accents(country.name).lower() == search_normalized:
            print(f"   -> {country.name}")
            return

    for country in all_countries:
        c_norm = remove_accents(country.name).lower()
        if len(search_normalized) > 3 and (search_normalized in c_norm or c_norm in search_normalized):
            print(f"   -> {country.name} (partial)")
            return

    print("   -> NOT FOUND")


if __name__ == "__main__":
    debug_search("Estados Unidos")

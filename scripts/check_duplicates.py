from __future__ import annotations

import re
import unicodedata
from collections import defaultdict


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    from scienti.utils.exports.django_setup import setup_django

    setup_django()
    from scienti.models import Article

    articles = Article.objects.all()
    title_map: dict[str, list[Article]] = defaultdict(list)

    for article in articles.iterator():
        norm_title = normalize_text(article.title or "")
        if len(norm_title) < 5:
            continue
        title_map[norm_title].append(article)

    duplicates = [(title, grouped) for title, grouped in title_map.items() if len(grouped) > 1]
    if not duplicates:
        print("No duplicates found by normalized title.")
        return

    for title, grouped_articles in duplicates:
        print(f"\nPotential duplicate: '{title}'")
        for art in grouped_articles:
            country_name = art.country.name if art.country else "Unknown"
            print(f"  - ID: {art.id} | Year: {art.year} | ISSN: {art.issn} | Country: {country_name}")


if __name__ == "__main__":
    main()

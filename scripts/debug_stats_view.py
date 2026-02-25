from __future__ import annotations


def main() -> None:
    from scienti.utils.exports.django_setup import setup_django

    setup_django()
    from scienti.models import Researcher, Article, Thesis, Book, BookChapter, ScientificEvent

    print(f"Researchers: {Researcher.objects.count()}")
    print(f"Articles: {Article.objects.count()}")
    print(f"Theses: {Thesis.objects.count()}")
    print(f"Books: {Book.objects.count()}")
    print(f"Chapters: {BookChapter.objects.count()}")
    print(f"Events: {ScientificEvent.objects.count()}")


if __name__ == "__main__":
    main()

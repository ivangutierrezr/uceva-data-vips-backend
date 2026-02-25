from __future__ import annotations

import datetime
import re


def normalize_date(date_text: str) -> datetime.date | None:
    if not date_text:
        return None

    months = {
        "enero": 1,
        "febrero": 2,
        "febreo": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    text = date_text.strip().lower()
    year_match = re.search(r"(\d{4})", text)
    if not year_match:
        return None

    year = int(year_match.group(1))
    month = 1

    for m_name, m_num in months.items():
        if m_name in text:
            month = m_num
            break
    else:
        text_no_year = text.replace(str(year), "").strip()
        month_match = re.search(r"\b(1[0-2]|0?[1-9])\b", text_no_year)
        if month_match:
            month = int(month_match.group(1))

    try:
        return datetime.date(year, month, 1)
    except ValueError:
        return None


def main() -> None:
    samples = [
        "Desde 3 2023 hasta",
        "Desde 3 2023 hasta ",
        "Desde 3 2023 hasta 10 2024",
    ]
    for line in samples:
        match = re.search(r"Desde\s+(.*?)\s+hasta\s*(.*)", line, re.IGNORECASE)
        if not match:
            print(f"No match: {line}")
            continue
        start = normalize_date(match.group(1).strip())
        end = normalize_date(match.group(2).strip())
        print(f"{line} -> start={start} end={end}")


if __name__ == "__main__":
    main()

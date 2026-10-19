from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Sequence


def write_csv(path: str | Path, headers: Sequence[str], rows: Iterable[Sequence[object]]) -> Path:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(list(headers))
        for row in rows:
            writer.writerow(["" if v is None else str(v) for v in row])

    return out_path

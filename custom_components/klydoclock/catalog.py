"""Read the klydo catalog from a copy of the clock's Room database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile


@dataclass(frozen=True, slots=True)
class Klydo:
    """One animation known to the clock."""

    id: str
    name: str
    main_loop: str
    creator: str | None
    subtitle: str | None


def load_catalog(database: bytes, wal: bytes | None) -> dict[str, Klydo]:
    """Parse the database (plus its write-ahead log) into a catalog. Blocking."""
    with tempfile.TemporaryDirectory(prefix="klydoclock_") as tmp:
        path = Path(tmp) / "klydo_database"
        path.write_bytes(database)
        if wal:
            (Path(tmp) / "klydo_database-wal").write_bytes(wal)
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute(
                "SELECT id, name, mainLoop, creator, subtitle FROM klydos"
            ).fetchall()
        finally:
            conn.close()
    return {
        row[0]: Klydo(row[0], row[1], row[2], row[3] or None, row[4] or None)
        for row in rows
    }

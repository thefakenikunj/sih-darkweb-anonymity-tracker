"""
collectors/local_import.py — Phase 1

Imports observation records from a local file on disk. This is the collector
called out explicitly in the project's own risk assessment: nothing about
the architecture stops someone from later pointing it at real scraped data
instead of synthetic fixtures. The mitigations below are enforced here, in
code — not left as documentation:

  1. Inherits BaseCollector's DEMO_MODE / legal-basis gates (see base.py).
     While config.DEMO_MODE is True, this collector can only be constructed
     with is_demo_data=True.
  2. While config.DEMO_MODE is True, the file path must additionally resolve
     to somewhere inside the project's data/ directory. This stops "demo"
     imports from quietly reading arbitrary paths on disk (e.g. a real
     scrape dropped elsewhere) even if is_demo_data was set carelessly.
  3. Only a small allow-list of inert formats is supported: .json, .jsonl,
     .csv. Anything else (.py, .pkl, .exe, ...) is refused outright.
  4. Parsing uses only json.loads / csv.DictReader. No eval, no exec, no
     pickle, no importlib — imported content is never treated as code.
  5. Each record's raw_text is read as plain text and stored as plain text.
     Nothing here renders, interprets, or follows links/markup in it.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Iterator

from collectors.base import BaseCollector, CollectorError, RawRecord
from models import ObservationType, SourceType

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_ALLOWED_ROOT = (PROJECT_ROOT / "data").resolve()

ALLOWED_EXTENSIONS = {".json", ".jsonl", ".csv"}


class LocalImportCollector(BaseCollector):
    source_type = SourceType.LOCAL_IMPORT

    def __init__(
        self,
        file_path: str | Path,
        *,
        source_name: str | None = None,
        is_demo_data: bool = True,
        legal_basis_or_authorization_note: str | None = None,
    ) -> None:
        self.file_path = Path(file_path).resolve()
        super().__init__(
            source_name=source_name or f"local_import:{self.file_path.name}",
            is_demo_data=is_demo_data,
            legal_basis_or_authorization_note=legal_basis_or_authorization_note,
        )
        self._validate_file_path()

    # -- extra governance on top of BaseCollector's gates ------------------

    def _validate_file_path(self) -> None:
        if self.file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise CollectorError(
                f"LocalImportCollector refused: '{self.file_path.suffix}' is not "
                f"in the allowed format list {sorted(ALLOWED_EXTENSIONS)}. "
                f"Imported content is never executed or unpickled, so only "
                f"plain structured-text formats are supported."
            )

        if not self.file_path.exists():
            raise CollectorError(f"LocalImportCollector refused: file not found: {self.file_path}")

        if self.is_demo_data:
            # Confine demo imports to the project's data/ directory, even if
            # a caller flagged something as demo data by mistake.
            try:
                self.file_path.relative_to(DEMO_ALLOWED_ROOT)
            except ValueError as exc:
                raise CollectorError(
                    f"LocalImportCollector refused: is_demo_data=True but "
                    f"'{self.file_path}' is outside the demo data directory "
                    f"({DEMO_ALLOWED_ROOT}). Move the file there, or construct "
                    f"this collector with is_demo_data=False and a legal-basis "
                    f"note if this is genuinely non-demo data (only possible "
                    f"outside config.DEMO_MODE)."
                ) from exc

    # -- interface ----------------------------------------------------------

    def collect(self) -> Iterator[RawRecord]:
        suffix = self.file_path.suffix.lower()
        if suffix == ".json":
            yield from self._collect_json()
        elif suffix == ".jsonl":
            yield from self._collect_jsonl()
        elif suffix == ".csv":
            yield from self._collect_csv()
        else:  # pragma: no cover — guarded in _validate_file_path already
            raise CollectorError(f"Unsupported extension: {suffix}")

    def _collect_json(self) -> Iterator[RawRecord]:
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        records = data if isinstance(data, list) else [data]
        for rec in records:
            yield self._record_from_dict(rec)

    def _collect_jsonl(self) -> Iterator[RawRecord]:
        with self.file_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield self._record_from_dict(json.loads(line))

    def _collect_csv(self) -> Iterator[RawRecord]:
        with self.file_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield self._record_from_dict(row)

    @staticmethod
    def _record_from_dict(rec: dict) -> RawRecord:
        required = {"observation_type", "raw_text"}
        missing = required - rec.keys()
        if missing:
            raise CollectorError(f"Record missing required field(s): {sorted(missing)}")

        observed_at = None
        if rec.get("observed_at"):
            observed_at = datetime.fromisoformat(rec["observed_at"])

        known_keys = {"persona_handle", "observation_type", "raw_text", "observed_at"}
        return RawRecord(
            persona_handle=rec.get("persona_handle") or None,
            observation_type=ObservationType(rec["observation_type"]),
            raw_text=str(rec["raw_text"]),
            observed_at=observed_at,
            extra={k: v for k, v in rec.items() if k not in known_keys},
        )

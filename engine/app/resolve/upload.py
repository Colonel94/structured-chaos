"""Object-store upload adapter — a CSV/JSON/JSONL file → ``list[dict]`` for ``ingest_object_collection``.

The self-serve half of the object store (winning-condition §2: "connecting the object store is self-serve
and inside the 10 minutes, by file upload"). A stranger exports their orders/bookings/assets from whatever
system they use and drops the file; this turns those bytes into the schema-agnostic row dicts the ingest
profiler consumes. No schema is declared — the profiler discovers the identifier columns itself.

Format is detected from the extension, then the content: ``.json`` (an array of objects, or a wrapper like
``{"objects": [...]}``), ``.jsonl`` (one JSON object per line), else CSV (with a header row). Values are
kept as trimmed strings — the profiler and the exact-key index normalise them.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

_WRAPPER_KEYS = ("objects", "data", "records", "rows", "items")
MAX_OBJECT_ROWS = 5_000
MAX_OBJECT_FIELDS = 200
MAX_OBJECT_VALUE_CHARS = 32_000


class ObjectFileError(ValueError):
    """The uploaded file could not be parsed into a list of objects."""


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    if len(row) > MAX_OBJECT_FIELDS:
        raise ObjectFileError(
            f"an object has more than {MAX_OBJECT_FIELDS} fields; split or simplify the export"
        )
    out: dict[str, Any] = {}
    for k, v in row.items():
        if not k or not str(k).strip():
            continue
        key = str(k).strip()
        if len(key) > 200:
            raise ObjectFileError("a field name is longer than 200 characters")
        value = v.strip() if isinstance(v, str) else v
        # Values are stored in JSONB and may be embedded. Bound both plain strings and nested JSON so
        # a small upload cannot expand into pathological database/model work.
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if len(rendered) > MAX_OBJECT_VALUE_CHARS:
            raise ObjectFileError(
                f"field {key!r} is longer than {MAX_OBJECT_VALUE_CHARS} characters"
            )
        out[key] = value
    return out


def _parse_csv(text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ObjectFileError("CSV has no header row")
    rows = [_clean_row(dict(r)) for r in reader]
    return [r for r in rows if any(v not in (None, "") for v in r.values())]


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ObjectFileError(f"invalid JSON: {exc.msg}") from exc
    if isinstance(doc, dict):
        for key in _WRAPPER_KEYS:  # a wrapper object like {"objects": [...]}
            inner = doc.get(key)
            if isinstance(inner, list):
                doc = inner
                break
        else:
            doc = [doc]  # a single object
    if not isinstance(doc, list):
        raise ObjectFileError("JSON must be an array of objects (or {objects: [...]})")
    return [_clean_row(d) for d in doc if isinstance(d, dict)]


def _parse_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ObjectFileError(f"invalid JSON on line {i}: {exc.msg}") from exc
        if isinstance(obj, dict):
            rows.append(_clean_row(obj))
    return rows


def parse_object_file(filename: str, data: bytes) -> list[dict[str, Any]]:
    """Parse an uploaded object export into a list of row dicts. Raises :class:`ObjectFileError` on a
    file that isn't parseable, or that contains no objects."""
    text = data.decode("utf-8-sig", errors="replace")  # -sig strips a BOM if the export has one
    name = filename.lower().strip()
    if name.endswith((".jsonl", ".ndjson")):
        rows = _parse_jsonl(text)
    elif name.endswith(".json") or text.lstrip()[:1] in "[{":
        rows = _parse_json(text)
    else:
        rows = _parse_csv(text)
    if not rows:
        raise ObjectFileError("no objects found in the file")
    if len(rows) > MAX_OBJECT_ROWS:
        raise ObjectFileError(
            f"the file contains more than {MAX_OBJECT_ROWS} objects; split it into smaller uploads"
        )
    return rows

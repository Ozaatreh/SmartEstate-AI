"""Human-readable document codes from PostgreSQL sequences (never ``max() + 1``)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SEQUENCES = {
    "employee": ("employee_no_seq", "EMP-", 4),
    "operational_project": ("operational_project_code_seq", "OP-", 4),
    "supplier": ("supplier_code_seq", "SUP-", 5),
    "purchase_request": ("purchase_request_code_seq", "PR-", 5),
}


def next_code(session: Session, kind: str) -> str:
    seq, prefix, width = SEQUENCES[kind]
    value = session.execute(text(f"SELECT nextval('{seq}')")).scalar_one()  # noqa: S608 - fixed identifiers
    return f"{prefix}{int(value):0{width}d}"

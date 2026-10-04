"""Declarative base, naming convention and column helpers (ADR-001)."""

from enum import Enum as PyEnum
from typing import Any, ClassVar

from sqlalchemy import JSON, BigInteger, Enum, MetaData
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Deterministic constraint names: required for SQLite batch migrations and for a
# future second backend (TimescaleDB/PostgreSQL) to share one migration history.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[Any]: JSON}


def _enum_db_values(cls: type[PyEnum]) -> list[str]:
    return [m.value if isinstance(m.value, str) else m.name.lower() for m in cls]


def ts_column(*, nullable: bool = False, primary_key: bool = False, index: bool = False) -> Any:
    """A UTC timestamp as integer milliseconds since the Unix epoch (``*_ts`` columns)."""
    return mapped_column(BigInteger, nullable=nullable, primary_key=primary_key, index=index)


def enum_column[E: PyEnum](
    enum_cls: type[E],
    name: str,
    *,
    nullable: bool = False,
    default: E | None = None,
    primary_key: bool = False,
) -> Any:
    """A closed enum stored as TEXT with a named CHECK constraint.

    String enums are stored by ``value``; other enums (``ValueKind``) by lower-case name.
    """
    return mapped_column(
        Enum(
            enum_cls,
            name=name,
            native_enum=False,
            create_constraint=True,
            length=32,
            validate_strings=True,
            values_callable=_enum_db_values,
        ),
        nullable=nullable,
        default=default,
        primary_key=primary_key,
    )

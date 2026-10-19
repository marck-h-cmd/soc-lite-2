"""SOC-Lite · Tipos de columna personalizados.

`INET` de PostgreSQL es devuelto por asyncpg como objetos `ipaddress.IPv4Address`
/ `IPv6Address`, mientras que los esquemas Pydantic y la API JSON esperan una
cadena. Este `TypeDecorator` normaliza la frontera de la base de datos:

* al escribir: acepta `str`, `IPv4Address` o `IPv6Address` y los convierte a texto;
* al leer: devuelve siempre `str` (o `None`).
"""
from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy.dialects.postgresql import INET as PG_INET
from sqlalchemy.types import TypeDecorator


class INET(TypeDecorator):
    """INET de PostgreSQL que se comporta como cadena en Python."""

    impl = PG_INET
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (IPv4Address, IPv6Address)):
            return str(value)
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(value)

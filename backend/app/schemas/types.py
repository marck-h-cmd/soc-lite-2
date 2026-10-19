"""SOC-Lite · Tipos Pydantic reutilizables.

`EmailAddress` sustituye a `EmailStr` para admitir dominios internos
(p. ej. `analista@org.local`) en entornos de laboratorio: `email-validator`
rechaza por diseño los dominios de uso especial (`.local`, `.test`, `.invalid`),
lo que rompía el login de los usuarios semilla.

* En producción (`ENVIRONMENT=production`) la validación es estricta.
* Fuera de producción se acepta un dominio interno siempre que la dirección
  tenga forma válida (`usuario@dominio.tld`).
"""
from __future__ import annotations

import re
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator

from app.core.config import settings

# Validación sintáctica mínima: parte local + dominio con al menos un punto.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def _validate_email_address(value: str) -> str:
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    try:
        validate_email(
            candidate,
            check_deliverability=False,
            test_environment=settings.ENVIRONMENT != "production",
            globally_deliverable=False,
        )
    except EmailNotValidError as exc:
        # Dominio interno de laboratorio (p. ej. `@org.local`): se admite fuera
        # de producción, nunca en producción.
        if settings.ENVIRONMENT != "production" and _EMAIL_RE.match(candidate):
            return candidate.lower()
        raise ValueError(str(exc)) from exc
    return candidate.lower()


EmailAddress = Annotated[str, AfterValidator(_validate_email_address)]

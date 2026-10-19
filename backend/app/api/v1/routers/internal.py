"""SOC-Lite · Endpoints internos servicio-a-servicio.

El microservicio de triaje (LangChain) necesita consultar el contexto histórico
de una regla y la memoria de falsos positivos. Estas consultas no representan a
un usuario, por lo que se autentican con `X-Service-Token` (token compartido
`INTERNAL_SERVICE_TOKEN`) en lugar de un JWT.

Están separadas de la API de usuario a propósito: **no** se relajan los permisos
RBAC de `/alerts` ni de `/dashboard`, y el prefijo `/internal` queda fuera de la
bitácora de acceso para no generar ruido con llamadas máquina-máquina.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, require_service_token
from app.models import Alert
from app.models.enums import TriageVerdict

router = APIRouter(
    prefix="/internal",
    tags=["Interno"],
    dependencies=[Depends(require_service_token)],
)


@router.get("/false-positives", summary="Memoria de falsos positivos por regla")
async def false_positive_context(
    db: DbSession,
    rule_id: str = Query(..., min_length=1),
    agent_name: str | None = None,
    days: int = Query(90, ge=1, le=365),
) -> dict:
    """Alerta marcadas como falso positivo para una regla (memoria de incidentes)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    filters = [
        Alert.rule_id == rule_id,
        Alert.verdict == TriageVerdict.FALSE_POSITIVE,
        Alert.deleted_at.is_(None),
        Alert.occurred_at >= since,
    ]
    rows = (
        await db.execute(
            select(Alert).where(*filters).order_by(Alert.occurred_at.desc()).limit(50)
        )
    ).scalars().all()
    if agent_name:
        rows = sorted(rows, key=lambda a: 0 if a.agent_name == agent_name else 1)

    return {
        "rule_id": rule_id,
        "agent_name": agent_name,
        "days": days,
        "matches": len(rows),
        "recent_examples": [
            {
                "alert_id": a.id,
                "agent": a.agent_name,
                "date": a.occurred_at.isoformat(),
                "summary": (a.rule_description or "")[:160],
            }
            for a in rows[:5]
        ],
        "conclusion": (
            "Existen falsos positivos previos de esta regla: evalúa si el patrón se repite"
            if rows
            else "Sin falsos positivos previos registrados para esta regla"
        ),
    }


@router.get("/rule-context", summary="Contexto histórico de una regla del SIEM")
async def rule_context(
    db: DbSession,
    rule_id: str = Query(..., min_length=1),
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Volumen, tasa de FP e IPs origen más frecuentes de una regla del SIEM."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = [
        Alert.rule_id == rule_id,
        Alert.deleted_at.is_(None),
        Alert.occurred_at >= since,
    ]
    total = (await db.execute(select(func.count(Alert.id)).where(*base))).scalar_one()
    false_positives = (
        await db.execute(
            select(func.count(Alert.id)).where(*base, Alert.verdict == TriageVerdict.FALSE_POSITIVE)
        )
    ).scalar_one()
    ip_rows = (
        await db.execute(
            select(Alert.source_ip, func.count(Alert.id).label("n"))
            .where(*base, Alert.source_ip.is_not(None))
            .group_by(Alert.source_ip)
            .order_by(func.count(Alert.id).desc())
            .limit(5)
        )
    ).all()
    fp_rate = round(false_positives / total, 3) if total else 0.0
    interpretation = (
        "regla de ruido crónico"
        if total and fp_rate > 0.7
        else "regla con historial de verdaderos positivos"
        if total and fp_rate < 0.3
        else "regla con historial mixto"
        if total
        else "regla sin historial en el periodo"
    )

    return {
        "rule_id": rule_id,
        "days": days,
        "occurrences_period": total,
        "false_positives": false_positives,
        "fp_rate": fp_rate,
        "top_source_ips": [{"ip": str(ip), "count": count} for ip, count in ip_rows],
        "interpretation": interpretation,
    }

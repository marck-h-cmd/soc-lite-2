# SOC-Lite · Triaje automático de alertas SOC

> **Caso de uso 1 (Crítico):** solución accesible para PYME / empresa mediana / organismo
> público que combina orquestación *low-code* (n8n) con enriquecimiento contextual y
> razonamiento LLM (LangChain + Ollama) para reducir la fatiga de alertas.
> Sustituye el MTTT de horas por minutos y habilita operación 24/7 sin personal nocturno.

[![Norma](https://img.shields.io/badge/ISO%2FIEC%2027001-2022-0f172a)](docs/01-arquitectura.md)
[![Marco](https://img.shields.io/badge/NIST%20CSF-2.0-06b6d4)](docs/01-arquitectura.md)
[![Licencia](https://img.shields.io/badge/licencia-uso%20interno-64748b)](#licencia)

---

## El problema en una frase

Los SOAR comerciales cuestan decenas de miles de dólares; las PYMEs sólo tienen SIEMs
open source que **generan** alertas pero no las **priorizan ni enriquecen**. El 70–90 %
son falsos positivos, así que las alertas críticas se pierden entre el ruido.

## La solución

```
Wazuh/OPNsense ──webhook──▶ n8n ──▶ LangChain + Ollama ──▶ PostgreSQL ──▶ Dashboard React
                            │                │                                │
                            │                └─ AbuseIPDB · VirusTotal · GeoIP │
                            │                   MITRE · memoria de FP         │
                            └──▶ Slack / Telegram / osTicket ◀────────────────┘
```

| Antes | Después |
|---|---|
| MTTT de 2–8 horas | **30 s – 5 min** |
| 100 % de alertas revisadas por un humano | **~12 %** escalan a humano |
| Sin cobertura nocturna | **24×7** |
| Tasa de falsos positivos desconocida | **medida y trazable** |

---

## Requisitos del sistema — cumplimiento

| Requisito obligatorio | Estado | Dónde |
|---|---|---|
| Stack tecnológico justificado (backend + frontend) | ✅ | [`docs/07-stack-tecnologico.md`](docs/07-stack-tecnologico.md) |
| PostgreSQL como base de datos principal | ✅ | [`db/schema.sql`](db/schema.sql) · [`docs/02-modelo-datos.md`](docs/02-modelo-datos.md) |
| Dashboard con métricas e indicadores | ✅ | [`backend/app/services/metrics_service.py`](backend/app/services/metrics_service.py) · `frontend/src/pages/Dashboard.tsx` |
| Reportes exportables en **PDF, Word y Excel** | ✅ | [`backend/app/services/report_service.py`](backend/app/services/report_service.py) |
| Módulo de usuarios, roles y perfiles (**RBAC**) | ✅ | [`backend/app/api/v1/routers/roles.py`](backend/app/api/v1/routers/roles.py) · 22 permisos / 5 roles |
| Bitácora de auditoría con **entrada/salida por módulo** (usuario, fecha, hora, acción) | ✅ | [`backend/app/middleware/audit_middleware.py`](backend/app/middleware/audit_middleware.py) · [`backend/app/services/audit_service.py`](backend/app/services/audit_service.py) |

---

## Arranque rápido

### Opción A — Docker Compose (recomendado)

```bash
git clone <repositorio> && cd soc-lite
cp .env.example .env          # ajustar SECRET_KEY, contraseñas y API keys
docker compose up -d
docker compose exec ollama ollama pull llama3.1:8b

# Servicios:
#   Frontend   → https://localhost            (o http://localhost:5173 en dev)
#   API        → https://localhost/api/v1
#   OpenAPI    → http://localhost:8000/docs
#   n8n        → http://localhost:5678
```

### Opción B — Desarrollo local

```bash
# 1. Base de datos
createdb soclite
psql -U soclite -d soclite -f db/schema.sql
psql -U soclite -d soclite -f db/seed.sql
# Opcional: 5.000 alertas sintéticas para probar el dashboard
psql -U soclite -d soclite -c "SELECT soclite.generate_synthetic_alerts(5000, 30);"

# 2. Backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Microservicio de triaje
cd ../langchain-service && pip install -r requirements.txt
ollama pull llama3.1:8b
uvicorn app.main:app --reload --port 8001

# 4. Frontend
cd ../frontend && pnpm install && pnpm dev
```

> **Ejecución local verificada (Windows, sin Docker):** en
> [`docs/08-puesta-en-marcha-local.md`](docs/08-puesta-en-marcha-local.md) están los
> comandos exactos, las correcciones aplicadas para que la aplicación arranque y la
> configuración que queda pendiente (Ollama, claves de threat intelligence, n8n).

### Credenciales de demostración
| Usuario | Contraseña | Rol | Para demostrar |
|---|---|---|---|
| `admin` | `Admin123!` | Administrador | Usuarios, roles y configuración |
| `soc_manager` | `Manager123!` | Jefe de SOC | Reportes gerenciales e incidentes |
| `analista1` | `Analyst123!` | Analista SOC | Triaje, feedback y gestión de alertas |
| `auditor1` | `Audit123!` | Auditor | Bitácora y reportes de auditoría (sólo lectura) |
| `visor1` | `Viewer123!` | Consulta | Dashboard de sólo lectura (**RBAC visible**) |

> ⚠️ Cambiar todas las contraseñas y `SECRET_KEY` antes de cualquier uso real.

---

## Estructura del repositorio

```
soc-lite/
├── docker-compose.yml            Stack completo (8 servicios)
├── .env.example                  Plantilla de configuración (70+ variables)
├── deploy/nginx.conf             Proxy inverso, TLS y cabeceras de seguridad
│
├── db/
│   ├── schema.sql                Esquema PostgreSQL completo (12 tablas, 4 vistas, 8 enums)
│   ├── seed.sql                  Datos semilla realistas (usuarios, roles, alertas, bitácora)
│   └── synthetic_data.sql        Generador de 5.000+ alertas para pruebas de carga
│
├── backend/                      FastAPI + SQLAlchemy 2.0 async
│   ├── app/core/                 Config, seguridad JWT/bcrypt, contexto, errores, logging
│   ├── app/models/               ORM tipado
│   ├── app/schemas/              Contratos Pydantic v2
│   ├── app/api/v1/routers/       10 routers: auth, users, roles, alerts, triage,
│   │                             incidents, dashboard, reports, audit, health
│   ├── app/services/             Auditoría, triaje, métricas, reportes
│   ├── app/middleware/           Bitácora de acceso + cabeceras de seguridad
│   └── Dockerfile
│
├── langchain-service/            Agente LLM (FastAPI + LangChain + LangGraph)
│   ├── app/agents/triage_agent.py   Agente ReAct con salida estructurada
│   ├── app/tools/threat_intel.py    6 herramientas con caché Redis
│   ├── app/chains/prompts.py        Prompts versionados + few-shot
│   └── Dockerfile
│
├── frontend/                     React 18 + TypeScript + Vite + Tailwind
│   └── src/{api,components,pages,context,types}
│
├── n8n/                          Workflows importables (JSON)
│   ├── soc_lite_triage_workflow.json
│   ├── soc_lite_dedup_suppression_workflow.json
│   ├── soc_lite_sla_escalation_workflow.json
│   ├── soc_lite_metrics_aggregation_workflow.json
│   └── soc_lite_report_generation_workflow.json
│
└── docs/                         Documentación de arquitectura
    ├── 00-contrato-api.md        Contrato normativo de la API v1
    ├── 01-arquitectura.md        Componentes, capas, ADR, despliegue, riesgos
    ├── 02-modelo-datos.md        Diccionario de datos y datos semilla
    ├── 03-backend.md             Implementación del backend
    ├── 04-frontend.md            Implementación del frontend
    ├── 05-workflow-n8n.md        Flujo de nodos paso a paso
    ├── 06-datasets-publicos.md   Datasets abiertos reutilizables
    └── 07-stack-tecnologico.md   Justificación del stack
```

---

## Documentación

| Documento | Contenido |
|---|---|
| [Contrato de API](docs/00-contrato-api.md) | Endpoints, enums, envelopes y esquemas de error (normativo) |
| [Arquitectura](docs/01-arquitectura.md) | Problema, capas, componentes, ADR, topología, riesgos |
| [Modelo de datos](docs/02-modelo-datos.md) | 12 tablas, diccionario, inmutabilidad de la bitácora, semilla |
| [Backend](docs/03-backend.md) | RBAC, auditoría de doble capa, triaje, métricas, reportes |
| [Frontend](docs/04-frontend.md) | Estructura, estado, RBAC en UI, widgets y endpoints |
| [Workflows n8n](docs/05-workflow-n8n.md) | Los 10 nodos, entradas/salidas, reintentos, idempotencia |
| [Datasets públicos](docs/06-datasets-publicos.md) | Datasets de logs, TI, malware y evaluación de LLM |
| [Stack tecnológico](docs/07-stack-tecnologico.md) | Justificación de cada tecnología y su coste |
| [Puesta en marcha local](docs/08-puesta-en-marcha-local.md) | Ejecución verificada en Windows, correcciones aplicadas y configuración pendiente (LLM, APIs, n8n) |

---

## Prueba de humo

```bash
# 1. Autenticarse
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=analista1&password=Analyst123!" | jq -r .access_token)

# 2. Simular una alerta de Wazuh
curl -s -X POST http://localhost:8000/api/v1/alerts/ingest \
  -H "X-Ingest-Key: $INGEST_API_KEY" -H "Content-Type: application/json" \
  -d '{"rule":{"id":"5710","level":10,"description":"Attempt to login using a non-existent user"},
       "agent":{"name":"WKS-CONTAB01"},"data":{"srcip":"203.0.113.44","dstip":"10.0.4.21"},
       "full_log":"sshd: Failed password for invalid user admin from 203.0.113.44",
       "timestamp":"2025-01-31T14:22:05Z"}' | jq

# 3. Consultar KPIs
curl -s http://localhost:8000/api/v1/dashboard/summary -H "Authorization: Bearer $TOKEN" | jq

# 4. Exportar reporte gerencial en Word
curl -s "http://localhost:8000/api/v1/reports/management?format=docx" \
  -H "Authorization: Bearer $TOKEN" -o reporte_gerencial.docx

# 5. Verificar que TODO quedó auditado
curl -s "http://localhost:8000/api/v1/audit/logs?page_size=10" \
  -H "Authorization: Bearer $TOKEN" | jq '.items[] | {occurred_at, username, module, action, result}'

# 6. Verificar la integridad de la cadena de hashes
curl -s http://localhost:8000/api/v1/audit/verify-chain -H "Authorization: Bearer $TOKEN" | jq
```

---

## Seguridad y cumplimiento

- **Sin exfiltración de datos:** `ALLOW_EXTERNAL_LLM=false` por defecto; inferencia con
  Ollama local; GeoIP con base MaxMind local. Sólo se consultan *indicadores* (IPs, hashes),
  nunca el log completo.
- **Bitácora inmutable:** reglas PostgreSQL que anulan `UPDATE`/`DELETE` + encadenamiento
  sha256 verificable con `GET /api/v1/audit/verify-chain`.
- **RBAC de mínimo privilegio:** 22 permisos granulares, 5 roles de sistema, matriz de
  permisos editable desde la interfaz, y ocultación de acciones en la UI.
- **Defensa en profundidad:** único puerto expuesto (443), TLS 1.2/1.3, HSTS, CSP,
  cabeceras de seguridad, límite de tasa en la ingesta, segmentación de redes.
- **Trazabilidad extremo a extremo:** el mismo `trace_id` correlaciona log del backend,
  triaje, bitácora y `X-Trace-Id` de la respuesta HTTP.

---

## Limitaciones conocidas y trabajo futuro

| Limitación | Mitigación actual | Trabajo futuro |
|---|---|---|
| Un modelo de 8B puede errar en casos ambiguos | `AUTO_CLOSE_FP_CONFIDENCE=0.90` + feedback humano + métrica de concordancia | Fine-tuning con el corpus de feedback acumulado |
| `audit_log` crece indefinidamente | Retención de 12 meses | Particionado declarativo por mes |
| Sin broker de tareas | Reportes síncronos + `BackgroundTasks` | Celery + Redis para reportes muy grandes |
| Prompt injection desde el log | Bloque delimitado; el agente sólo propone | Clasificador de inyección previo al prompt |
| Alertas descartadas por umbral de severidad | Umbral configurable | Modelo de *novelty detection* para lo descartado |

---

## Licencia

Uso interno. **Atención:** n8n se distribuye bajo *Sustainable Use License* (uso interno
libre; revisar términos si se redistribuye comercialmente). Ollama (MIT), LangChain (MIT),
FastAPI (MIT), PostgreSQL (PostgreSQL License), React (MIT).

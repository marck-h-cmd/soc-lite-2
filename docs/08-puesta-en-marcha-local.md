# Puesta en marcha local (Windows) y configuración pendiente

> Estado de esta ejecución: **aplicación funcionando de punta a punta** sobre
> PostgreSQL 17 local, backend FastAPI, microservicio LangChain y frontend servido
> en `http://127.0.0.1:5173`. El triaje opera en **modo degradado heurístico**
> porque no hay un LLM local instalado (ver §4.1).

---

## 1. Servicios en ejecución

| Servicio | URL | Estado | Notas |
|---|---|---|---|
| Frontend (SPA) | http://127.0.0.1:5173 | ✅ | `frontend/dist` + proxy `/api` → backend |
| API REST | http://127.0.0.1:8000/api/v1 | ✅ | FastAPI + SQLAlchemy async |
| Swagger / OpenAPI | http://127.0.0.1:8000/docs | ✅ | 59 rutas documentadas |
| Microservicio de triaje | http://127.0.0.1:8001/health | ⚠️ `degraded` | Sin Ollama: fallback heurístico |
| PostgreSQL | 127.0.0.1:**55432** | ✅ | Clúster propio, base `soclite`, esquema `soclite` |
| n8n | — | ❌ no iniciado | Requiere Docker o instalación Node |
| Redis | — | ❌ no requerido | El backend no lo usa; el triaje cachea en memoria |

Credenciales de demostración (las del `seed.sql`):

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `Admin123!` | Administrador (22 permisos) |
| `soc_manager` | `Manager123!` | Jefe de SOC |
| `analista1` | `Analyst123!` | Analista SOC |
| `auditor1` | `Audit123!` | Auditor (sólo lectura + auditoría) |
| `visor1` | `Viewer123!` | Consulta (sólo lectura) |

> Las contraseñas semilla tienen 9 caracteres; la política `PASSWORD_MIN_LENGTH=12`
> sólo se aplica al **cambiar/crear** contraseñas (ISO 27001 A.5.17).

---

## 2. Cómo se levantó (reproducible)

### 2.1 Base de datos (sin Docker)

Se creó un clúster propio para no tocar el servicio PostgreSQL del sistema ni
depender de una contraseña desconocida:

```powershell
$PG = "C:\Program Files\PostgreSQL\17\bin"
& "$PG\initdb.exe" -D .pgdata -U soclite --auth=trust --encoding=UTF8 --locale=C
& "$PG\postgres.exe" -D .pgdata -p 55432 -c listen_addresses=127.0.0.1   # en otra terminal
& "$PG\createdb.exe" -h 127.0.0.1 -p 55432 -U soclite soclite
$env:PGCLIENTENCODING="UTF8"
& "$PG\psql.exe" -h 127.0.0.1 -p 55432 -U soclite -d soclite -v ON_ERROR_STOP=1 -f db\schema.sql
& "$PG\psql.exe" -h 127.0.0.1 -p 55432 -U soclite -d soclite -v ON_ERROR_STOP=1 -f db\seed.sql
& "$PG\psql.exe" -h 127.0.0.1 -p 55432 -U soclite -d soclite -c "SELECT soclite.generate_synthetic_alerts(3000, 30);"
```

> `pg_ctl start` falla dentro de la sesión confinada del agente (`could not create
> restricted token`); por eso se lanza `postgres.exe` directamente. En una consola
> normal `pg_ctl` funciona.

### 2.2 Dependencias y servicios

```powershell
# Backend
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000

# Microservicio de triaje
python -m venv langchain-service\.venv
langchain-service\.venv\Scripts\python.exe -m pip install -r langchain-service\requirements.txt
langchain-service\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001

# Frontend (build ya generado en frontend/dist)
cd frontend; pnpm install --ignore-scripts; cd ..
backend\.venv\Scripts\python.exe scripts\serve_frontend.py --port 5173
```

El `.env` local se creó a partir de `.env.example` con:

* `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=55432`, usuario/clave `soclite`.
* `BACKEND_URL=http://127.0.0.1:8000` (el valor por defecto es el nombre de
  servicio Docker `http://backend:8000`; sin esto, las tools de contexto del
  agente no resuelven el host).
* `SECRET_KEY`, `INTERNAL_SERVICE_TOKEN` e `INGEST_API_KEY` aleatorios.

---

## 3. Defectos encontrados y corregidos

La revisión estática previa no detectó estos fallos porque **ninguno rompe la
compilación**: todos aparecen al importar la app, al arrancar o al primer request.

| # | Archivo | Síntoma | Corrección |
|---|---|---|---|
| 1 | `backend/app/core/config.py` | `SettingsError` al arrancar: `CORS_ORIGINS` separado por comas no es JSON | `Annotated[list[str], NoDecode]` + validador que acepta comas o array |
| 2 | `backend/app/api/v1/routers/auth.py` | `ImportError: cannot import MessageResponse` | Importar desde `schemas.common` |
| 3 | `backend/app/models/user.py` | `AmbiguousForeignKeysError` en `User.roles` (`user_roles` tiene dos FK a `users`) | `foreign_keys=[user_roles.c.user_id, user_roles.c.role_id]` |
| 4 | `backend/app/core/security.py` | Login 500: `jti` de `token_urlsafe` no es UUID y `refresh_tokens.jti` es UUID | `jti = str(uuid.uuid4())` |
| 5 | `backend/app/schemas/types.py` (nuevo) + `schemas/user.py` | Login 500: `EmailStr` rechaza `admin@org.local` | Tipo `EmailAddress` con `email-validator`; dominios internos sólo fuera de producción |
| 6 | `backend/app/db/types.py` (nuevo) + `models/{alert,user,audit}.py` | Listados 500: `INET` devuelve `IPv4Address`, Pydantic espera `str` | `TypeDecorator INET` que normaliza a cadena |
| 7 | `backend/app/api/v1/routers/audit.py` | `GET /audit/logs/export` → 422: la ruta `{log_id}` la capturaba | Convertidor `{log_id:int}` |
| 8 | `backend/app/main.py` | `/openapi.json` 500: el email de contacto `soc@org.local` no pasa la validación OpenAPI | `soc@example.com` |
| 9 | `langchain-service/requirements.txt` | `ResolutionImpossible`: `ollama 0.4.5` exige `httpx<0.28`, el archivo fijaba `0.28.1` | `httpx==0.27.2` |
| 10 | `langchain-service/app/agents/triage_agent.py` | El agente ReAct **nunca** se construía: LangGraph 0.2.x usa `state_modifier`, no `prompt`; caía siempre a la cadena simple y las tools no se usaban | Intento `prompt=` y fallback a `state_modifier=` |
| 11 | `backend/app/api/v1/routers/internal.py` (nuevo), `tools/threat_intel.py` | Las tools `wazuh_context` y `search_known_false_positives` llamaban a endpoints de usuario con `X-Service-Token` → 401 | Endpoints internos `/api/v1/internal/*` autenticados con token de servicio |
| 12 | `db/synthetic_data.sql` | `generate_synthetic_alerts` abortaba: PostgreSQL no soporta arrays de arrays (`v_rules[i]` → NULL) | Reglas como texto `id\|desc\|sev\|mitre` + `string_to_array` |
| 13 | `scripts/serve_frontend.py` (nuevo) | — | Servidor estático de `frontend/dist` + proxy `/api` (sustituye a Vite cuando no se pueden lanzar procesos hijos) |

---

## 4. Qué falta configurar

### 4.1 LLM de triaje — **lo único importante para salir del modo degradado**

Sin LLM el sistema **no falla**: el microservicio devuelve un triaje heurístico
marcado como `degraded` y la alerta nunca se pierde. Para triaje real:

```powershell
winget install Ollama.Ollama          # o instalador de https://ollama.com
ollama pull llama3.1:8b               # ~4,7 GB · 8 GB de RAM recomendados
ollama serve                          # escucha en 127.0.0.1:11434
```

Luego reiniciar el microservicio y comprobar:

```powershell
curl http://127.0.0.1:8001/health
# "llm_reachable": true
```

Variables implicadas: `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`,
`OLLAMA_MODEL` (si el equipo tiene poca RAM: `llama3.2:3b` o `qwen2.5:3b`).

**Alternativa OpenAI** (sólo si la política de datos lo autoriza, porque las
alertas salen de la infraestructura):

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
ALLOW_EXTERNAL_LLM=true
```

### 4.2 APIs de inteligencia de amenazas (opcionales)

Las tools se registran sólo si hay clave; sin ellas el agente trabaja con las 4
herramientas locales (`geoip_lookup`, `wazuh_context`,
`search_known_false_positives`, `mitre_lookup`).

| Variable | Servicio | Plan gratuito | Efecto |
|---|---|---|---|
| `ABUSEIPDB_API_KEY` | https://www.abuseipdb.com/api | 1.000 consultas/día | reputación de IP, reportes, Tor |
| `VIRUSTOTAL_API_KEY` | https://www.virustotal.com/gui/my-apikey | 4 req/min, 500/día | detecciones de IP/hash/dominio |
| `GEOIP_DB_PATH` | https://www.maxmind.com (GeoLite2-City) | gratis con registro | geolocalización/ASN **100 % local** |

```env
ABUSEIPDB_API_KEY=...
VIRUSTOTAL_API_KEY=...
GEOIP_DB_PATH=./data/GeoLite2-City.mmdb
```

> `OTX_API_KEY` y `SHODAN_API_KEY` existen en la configuración pero **ninguna tool
> los consume** todavía: configurarlos no cambia el comportamiento.

### 4.3 Redis (opcional)

El backend declara `REDIS_URL` pero no lo usa. El microservicio intenta Redis para
cachear enriquecimiento y, si no está, usa memoria local. Sólo hace falta si se
quiere caché compartida entre réplicas:

```powershell
redis-server            # o el servicio redis de docker-compose
```

### 4.4 Notificaciones (Slack / Telegram / correo)

`TriageService.queue_notification()` **encola** la notificación en la tabla
`notifications` (canal `slack` por defecto) pero **no hay worker de envío**: el
envío real lo hace el workflow n8n (`soc_lite_triage_workflow.json`, nodo 8) o
queda pendiente de implementar. Configurar estas variables sólo cambia el canal
y el destino de la fila encolada:

```env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SLACK_CHANNEL=#soc-alertas
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
SMTP_HOST=smtp.org.local
```

### 4.5 Ticketing (osTicket / Redmine)

Igual que las notificaciones: el backend devuelve `ticket_id: null`; la creación
del ticket está en el nodo 9 del workflow n8n. Configurar
`OSTICKET_BASE_URL`/`OSTICKET_API_KEY` o `REDMINE_*` cuando se active ese nodo.

### 4.6 n8n (orquestación low-code)

No se pudo iniciar en esta sesión: Docker Desktop no es accesible desde el
entorno confinado. Opciones:

```bash
docker compose up -d n8n        # recomendado
# o instalación local:
npx n8n
```

Después: importar los 5 JSON de `n8n/`, crear las credenciales
(PostgreSQL, HTTP Header Auth con `INTERNAL_SERVICE_TOKEN`, Slack/Telegram) y
ajustar las URLs internas (`http://backend:8000`, `http://langchain:8001`).

### 4.7 Integración con Wazuh

En el manager (`/var/ossec/etc/ossec.conf`):

```xml
<integration>
  <name>custom-soc-lite</name>
  <hook_url>http://IP_SOCLITE:8000/api/v1/alerts/ingest</hook_url>
  <api_key>INGEST_API_KEY</api_key>   <!-- header X-Ingest-Key -->
  <level>7</level>
  <alert_format>json</alert_format>
</integration>
```

La clave debe coincidir con `INGEST_API_KEY`. El umbral `level` puede dejarse en 3
y filtrar en SOC-Lite con `MIN_SEVERITY_TO_PROCESS=7`.

### 4.8 Producción

1. `ENVIRONMENT=production`, `DEBUG=false`, `LOG_FORMAT=json`.
2. `SECRET_KEY`, contraseñas de PostgreSQL y tokens nuevos (los del repo son demo).
3. TLS en `deploy/nginx.conf` y un único puerto expuesto (443).
4. Cambiar las contraseñas de los 5 usuarios demo o desactivarlos.
5. `docker compose up -d --build` (los Dockerfile ya existen).

---

## 5. Verificación ejecutada

| Prueba | Resultado |
|---|---|
| Login de los 5 roles | ✅ 200 (JWT + refresh token persistido) |
| Ingesta Wazuh (`POST /alerts/ingest` con `X-Ingest-Key`) | ✅ 201, deduplicación por fingerprint |
| Triaje automático en segundo plano | ✅ alerta → `escalated`, riesgo 88, incidente creado |
| Fallback sin LLM | ✅ `degraded=true`, `model=heuristic-fallback`, alerta conservada |
| Dashboard (8 endpoints) | ✅ con 3.006 alertas, 2.907 triajes, 435 filas de métricas |
| Reportes 3 tipos × 3 formatos | ✅ 9 archivos válidos (PDF 4–8 páginas, DOCX con tablas, XLSX 9–11 hojas) |
| RBAC | ✅ `visor1` recibe 403 en escritura/usuarios y las denegaciones quedan auditadas |
| Bitácora | ✅ `verify-chain` intacta (80 eventos encadenados) |
| Export de bitácora CSV/XLSX | ✅ 200 (tras corregir el shadowing de rutas) |
| OpenAPI / Swagger | ✅ `/docs` y `/openapi.json` (98 KB) |
| TypeScript | ✅ `tsc --noEmit` sin errores |

Datos de demostración: `SELECT soclite.generate_synthetic_alerts(3000, 30);`
(3.000 alertas sintéticas en 30 días; el generador estaba roto, ver §3 #12).

---

## 6. Limitaciones de esta puesta en marcha

| Limitación | Motivo | Cómo resolverlo |
|---|---|---|
| Triaje heurístico, no LLM | Ollama no está instalado | §4.1 |
| `pnpm dev` / `pnpm build` no ejecutan | El sandbox no permite que Node lance procesos hijos (esbuild) → `spawn EPERM` | En una consola normal funciona; aquí se sirve `dist/` con `scripts/serve_frontend.py` |
| n8n no iniciado | Docker inaccesible desde el entorno confinado | §4.6 |
| Sin pruebas automatizadas | `backend/tests/` está vacío | Añadir `pytest` + `httpx.ASGITransport` (el contrato ya está documentado) |
| `OTX_API_KEY` / `SHODAN_API_KEY` inertes | No hay tools que los usen | Implementarlas o eliminarlas de la configuración |
| Notificaciones sólo encoladas | No hay worker de envío | n8n o un `BackgroundTasks` de envío |
| Documentación dice «11 hojas» en Excel | Los reportes operativo/gerencial tienen 9; el de auditoría 11 | Ajustar el README |

"""SOC-Lite · Prueba de humo de punta a punta.

Ejercita el flujo completo contra una instancia en ejecución:

  1. Salud de la API, OpenAPI y login de los cinco roles.
  2. Ingesta de una alerta Wazuh (webhook con X-Ingest-Key).
  3. Triaje automático en segundo plano (LLM o fallback heurístico).
  4. Dashboard, reportes PDF/DOCX/XLSX e integridad de la bitácora.
  5. RBAC: un usuario de sólo lectura no puede modificar alertas.

Uso (con el backend arrancado):

    backend\\.venv\\Scripts\\python.exe scripts\\smoke_test.py
    backend\\.venv\\Scripts\\python.exe scripts\\smoke_test.py --ingest-key <clave>

La clave de ingesta se lee de `--ingest-key`, de la variable `INGEST_API_KEY` o
del archivo `.env` de la raíz. Si no se encuentra, se omite la prueba de ingesta.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
USERS = [
    ("admin", "Admin123!"),
    ("soc_manager", "Manager123!"),
    ("analista1", "Analyst123!"),
    ("auditor1", "Audit123!"),
    ("visor1", "Viewer123!"),
]

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    results.append((ok, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name:<48} {detail}")
    return ok


def read_env_value(key: str) -> str | None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            if name.strip() == key:
                return value.strip() or None
    return None


def login(client: httpx.Client, base: str, username: str, password: str) -> str | None:
    response = client.post(f"{base}/auth/login", data={"username": username, "password": password})
    if response.status_code != 200:
        return None
    return response.json()["access_token"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueba de humo de SOC-Lite")
    parser.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--ingest-key", default=None)
    args = parser.parse_args()
    base = args.base.rstrip("/")
    ingest_key = args.ingest_key or read_env_value("INGEST_API_KEY")

    with httpx.Client(timeout=180) as client:
        # ------------------------------------------------------------------
        # 1. Salud y autenticación
        # ------------------------------------------------------------------
        name = "api/health"
        response = client.get(f"{base}/health")
        check(response.status_code == 200, name, str(response.status_code))

        # OpenAPI se publica en la raíz del backend, no bajo /api/v1
        root_url = base[: -len("/api/v1")] if base.endswith("/api/v1") else base
        response = client.get(f"{root_url}/openapi.json")
        check(response.status_code == 200, "api/openapi.json", f"{len(response.content)} bytes")

        tokens: dict[str, str] = {}
        for username, password in USERS:
            token = login(client, base, username, password)
            if token:
                tokens[username] = token
            check(token is not None, f"login {username}", "200" if token else "sin token")

        admin = tokens.get("admin")
        if not admin:
            print("\nNo se pudo autenticar como admin: se aborta la prueba.")
            return 1
        headers = {"Authorization": f"Bearer {admin}"}

        # ------------------------------------------------------------------
        # 2. Ingesta de alerta
        # ------------------------------------------------------------------
        alert_id = None
        if ingest_key:
            payload = {
                "rule": {"id": "5710", "level": 12,
                         "description": "Multiple failed SSH logins from external host",
                         "groups": ["authentication_failed", "sshd"]},
                "agent": {"name": "WKS-CONTAB01"},
                "data": {"srcip": f"203.0.113.{uuid.uuid4().int % 200 + 20}", "dstip": "10.0.4.21"},
                "full_log": "sshd: Failed password for invalid user admin from 203.0.113.99 port 54321 ssh2",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "mitre": {"technique": "T1110", "tactic": "Credential Access"},
            }
            response = client.post(f"{base}/alerts/ingest", json=payload,
                                   headers={**headers, "X-Ingest-Key": ingest_key})
            ok = response.status_code in (200, 201)
            if ok:
                alert_id = response.json()["alert_id"]
            check(ok, "alerta ingerida (webhook Wazuh)", response.text[:90])
        else:
            print("SKIP  ingesta: no hay INGEST_API_KEY (use --ingest-key)")

        # ------------------------------------------------------------------
        # 3. Triaje (automático o manual)
        # ------------------------------------------------------------------
        if alert_id:
            triage = None
            for _ in range(30):
                time.sleep(1)
                response = client.get(f"{base}/alerts/{alert_id}", headers=headers)
                if response.status_code == 200 and response.json().get("triage"):
                    triage = response.json()["triage"]
                    break
            check(triage is not None, "triaje registrado")
            if triage:
                detail = (f"verdict={triage.get('verdict')} risk={triage.get('risk_score')} "
                          f"model={triage.get('model_name')}")
                check(triage.get("verdict") is not None, "veredicto del triaje", detail)
                check(0 <= int(triage.get("risk_score") or 0) <= 100, "risk_score en rango",
                      str(triage.get("risk_score")))

        # ------------------------------------------------------------------
        # 4. Dashboard, reportes y bitácora
        # ------------------------------------------------------------------
        response = client.get(f"{base}/dashboard/summary", headers=headers)
        summary = response.json() if response.status_code == 200 else {}
        check(response.status_code == 200 and "alerts_total" in summary,
              "dashboard/summary", f"alerts_total={summary.get('alerts_total')}")

        magic = {
            "pdf": b"%PDF-",
            "docx": b"PK",
            "xlsx": b"PK",
        }
        for report_format in ("pdf", "docx", "xlsx"):
            response = client.get(f"{base}/reports/management",
                                  params={"format": report_format}, headers=headers)
            ok = response.status_code == 200 and response.content.startswith(magic[report_format])
            check(ok, f"reporte gerencial {report_format}", f"{len(response.content)} bytes")

        response = client.get(f"{base}/audit/verify-chain", headers=headers)
        chain = response.json() if response.status_code == 200 else {}
        check(response.status_code == 200 and chain.get("intact") is True,
              "cadena de hashes de la bitácora",
              f"eventos={chain.get('checked')}")

        # ------------------------------------------------------------------
        # 5. RBAC
        # ------------------------------------------------------------------
        viewer = tokens.get("visor1")
        if viewer:
            viewer_headers = {"Authorization": f"Bearer {viewer}"}
            response = client.get(f"{base}/dashboard/summary", headers=viewer_headers)
            check(response.status_code == 200, "visor puede leer dashboard")
            response = client.get(f"{base}/users", headers=viewer_headers)
            check(response.status_code == 403, "visor no puede listar usuarios",
                  str(response.status_code))
            if alert_id:
                response = client.patch(f"{base}/alerts/{alert_id}",
                                        json={"status": "closed"}, headers=viewer_headers)
                check(response.status_code == 403, "visor no puede modificar alertas",
                      str(response.status_code))

    failed = [name for ok, name, _ in results if not ok]
    print("\n" + "=" * 70)
    print(f"{len(results) - len(failed)}/{len(results)} pruebas correctas")
    if failed:
        print("Fallos: " + ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

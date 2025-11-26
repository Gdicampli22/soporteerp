import os, requests, pandas as pd

API_URL = os.environ.get("ERP_API_URL","http://localhost:8000")
API_KEY = os.environ.get("ERP_API_KEY","dev-key")
HEAD = {"x-api-key": API_KEY}

def _get(path, params=None):
    r = requests.get(f"{API_URL}{path}", params=params or {}, headers=HEAD, timeout=15)
    r.raise_for_status(); return r.json()

def _post(path, data=None, params=None):
    if isinstance(data, dict):
        r = requests.post(f"{API_URL}{path}", json=data, params=params or {}, headers=HEAD, timeout=20)
    else:
        r = requests.post(f"{API_URL}{path}", params=params or {}, headers=HEAD, timeout=20)
    r.raise_for_status(); return r.json()

def load_usuarios_df():
    return pd.DataFrame(_get("/usuarios"))

def load_tickets_df():
    data = _get("/tickets")
    df = pd.DataFrame(data)
    if not df.empty:
        df["Fecha_Creación"] = pd.to_datetime(df["Fecha_Creación"], errors="coerce")
    return df

def upsert_ticket(rec: dict):
    rc = rec.copy()
    v = rc.get("Fecha_Creación")
    if hasattr(v, "isoformat"): rc["Fecha_Creación"] = v.isoformat()
    return _post("/tickets", data=rc)

def registrar_auditoria(usuario, rol, ticket, campo, antes, despues, motivo):
    return _post("/auditoria", data={
        "usuario":usuario,"rol":rol,"ticket":ticket,"campo":campo,
        "antes":str(antes),"despues":str(despues),"motivo":str(motivo)
    })

def list_clientes():
    return _get("/clientes")

def list_reportantes(cliente: str):
    return _get("/reportantes", params={"cliente": cliente})

def create_cliente(nombre: str):
    return _post("/clientes", params={"nombre": nombre})

def create_reportante(cliente: str, nombre: str):
    return _post("/reportantes", params={"cliente": cliente, "nombre": nombre})

def bulk_update_tickets(ids, set_estado=None, set_prioridad=None, set_agente=None):
    payload = {"ids": ids}
    if set_estado: payload["set_estado"] = set_estado
    if set_prioridad: payload["set_prioridad"] = set_prioridad
    if set_agente: payload["set_agente"] = set_agente
    return _post("/tickets/bulk_update", data=payload)

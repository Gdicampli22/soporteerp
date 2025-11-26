import os
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import storage_sqlite as store
import pandas as pd

API_KEY = os.environ.get("ERP_API_KEY","dev-key")

app = FastAPI(title="ERP Support API (Portfolio)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

def _check_key(x_api_key: str | None):
    if x_api_key!=API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

class Ticket(BaseModel):
    ID_Ticket: str
    Empresa: str
    Usuario_Reportante: str
    Agente_Soporte: str
    Módulo_ERP: str
    Prioridad: str
    Categoría: str
    Estado: str
    SLA: str
    Fecha_Creación: str
    Tiempo_Resolución_hs: float | None = None
    Comentarios: str | None = None
    Satisfacción: float | None = None

class BulkUpdate(BaseModel):
    ids: List[str]
    set_estado: Optional[str] = None
    set_prioridad: Optional[str] = None
    set_agente: Optional[str] = None

@app.get("/usuarios")
def usuarios(x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    return store.load_usuarios_df().to_dict(orient="records")

@app.get("/tickets")
def tickets(x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    return store.load_tickets_df().assign(
        Fecha_Creación=lambda d: d["Fecha_Creación"].astype(str)
    ).to_dict(orient="records")

@app.post("/tickets")
def upsert(ticket: Ticket, x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    store.upsert_ticket(ticket.dict())
    return {"ok": True}

@app.post("/tickets/bulk_update")
def bulk_update(payload: BulkUpdate, x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    df = store.load_tickets_df()
    updated = 0
    for tid in payload.ids:
        m = df[df["ID_Ticket"]==tid]
        if m.empty: continue
        rec = m.iloc[0].to_dict()
        if payload.set_estado:    rec["Estado"] = payload.set_estado
        if payload.set_prioridad: rec["Prioridad"] = payload.set_prioridad
        if payload.set_agente:    rec["Agente_Soporte"] = payload.set_agente
        store.upsert_ticket(rec); updated += 1
    return {"updated": updated}

@app.get("/clientes")
def clientes(x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    return store.list_clientes()

@app.post("/clientes")
def add_cliente(nombre: str, x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    store.add_cliente_si_no_existe(nombre)
    return {"ok": True}

@app.get("/reportantes")
def reportantes(cliente: str = Query(...), x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    return store.list_reportantes(cliente)

@app.post("/reportantes")
def add_reportante(cliente: str, nombre: str, x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    store.add_reportante_si_no_existe(cliente, nombre)
    return {"ok": True}

class Audit(BaseModel):
    usuario: str; rol: str; ticket: str; campo: str; antes: str; despues: str; motivo: str

@app.post("/auditoria")
def auditoria(reg: Audit, x_api_key: Optional[str]=Header(default=None)):
    _check_key(x_api_key)
    store.registrar_auditoria(**reg.dict())
    return {"ok": True}


# Soporte ERP v8 (Portfolio)

Incluye:
- App Streamlit v8 con **Kanban interactivo**, **SLA dinámico por prioridad**, **exportar CSV**, **Backlog Aging**, filtros por agente, alta cliente→reportante in-line y auditoría.
- Compatible con **SQLite** o **API FastAPI** (toggle `USE_API` en el sidebar).

## Instalación
```bash
pip install -r requirements.txt
```

## Ejecutar App (SQLite local)
```bash
streamlit run app_streamlit_soporte_erp_portfolio_v8.py
```

## Ejecutar API (opcional)
```bash
# variables (opcional)
# Windows (PowerShell): $env:ERP_API_KEY='dev-key'
# Linux/Mac:
export ERP_API_KEY=dev-key

uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
# En la app, activar "Usar API (FastAPI)".
```

## Credenciales demo
- Coordinación: `admin / admin123`
- Agentes: `slopez / agente123`, `cperes / agente123`

## Notas
- **Crear ticket**: al elegir *Cliente*, el **Reportante** se filtra; si no existe, se **crea in-line** y queda asociado.
- **Tickets**: críticos/vencidos resaltan en **rojo**, CSV export, **Kanban** con acciones de estado por tarjeta.
- **Dashboard**: KPIs, **Backlog Aging**, top módulos, clientes con CSAT bajo, filtros por agente.

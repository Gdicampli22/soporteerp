import streamlit as st, pandas as pd, altair as alt, time


# === VALIDACIONES PROFESIONALES ===
def validar_ticket(data):
    obligatorios = ["Empresa","Usuario_Reportante","Modulo","Prioridad","Categoria","Descripcion"]
    for campo in obligatorios:
        if not data.get(campo):
            st.error(f"El campo {campo} es obligatorio.")
            return False
    return True

# === SISTEMA DE NOTAS INTERNAS (PLACEHOLDER) ===
def mostrar_notas(id_ticket, conn):
    st.subheader("📝 Notas internas")
    notas = conn.execute("SELECT fecha, usuario, nota FROM Notas WHERE id_ticket=? ORDER BY fecha DESC",(id_ticket,)).fetchall()
    for n in notas:
        st.info(f"**{n[1]}** – {n[0]}  
{n[2]}")
{n[2]}")
    nueva = st.text_area("Agregar nueva nota")
    if st.button("Guardar nota"):
        conn.execute("INSERT INTO Notas (id_ticket, fecha, usuario, nota) VALUES (?,?,?,?)",
                     (id_ticket, str(datetime.date.today()), st.session_state.get("user",""), nueva))
        conn.commit()
        st.rerun()

st.image('static/logo.png', width=180)
st.markdown('# 🧰 Soporte de Aplicaciones ERP')
st.image('static/banner.jpg', use_container_width=True)

from datetime import datetime, timedelta, date

# ====== CONFIG ======
st.set_page_config(page_title="Soporte ERP - v8 (Portfolio)", layout="wide")
SESSION_TIMEOUT = 15 * 60

MODULOS = ["Ventas", "Facturación", "Inventario", "Producción", "Logística", "Compras", "Tesorería", "Contabilidad"]
PRIORIDADES = ["Alta", "Media", "Baja"]
CATEGORIAS = ["Error crítico", "Consulta funcional", "Mejora", "Reporte caído", "Integración"]
ESTADOS = ["Abierto", "Priorizado", "En Progreso", "En Espera", "Resuelto", "Cerrado"]
SLA_VALUES = ["Dentro de SLA", "Fuera de SLA"]

EXPECTED_TICKET_COLS = [
    "ID_Ticket","Empresa","Usuario_Reportante","Agente_Soporte","Módulo_ERP","Prioridad",
    "Categoría","Estado","SLA","Fecha_Creación","Tiempo_Resolución_hs","Comentarios","Satisfacción"
]
EXPECTED_USER_COLS = ["usuario","contraseña","rol","nombre_agente"]

# SLA objetivo (dinámico) por prioridad
SLA_OBJ_HORAS = {"Alta": 24, "Media": 48, "Baja": 72}
UMBRAL_CSAT_BAJO = 3.0
CRITICOS_POR_PRIORIDAD = {"Alta": True, "Media": False, "Baja": False}

# ====== DATASOURCE ======
USE_API = st.sidebar.checkbox("Usar API (FastAPI) en lugar de SQLite local", value=False, help="Para demo de arquitectura desacoplada")
if USE_API:
    from api_client import (
        load_usuarios_df, load_tickets_df, upsert_ticket,
        registrar_auditoria as registrar_auditoria_db,
        list_clientes, list_reportantes, create_cliente, create_reportante,
        bulk_update_tickets
    )
else:
    from storage_sqlite import (
        load_usuarios_df, load_tickets_df, upsert_ticket,
        registrar_auditoria as registrar_auditoria_db,
        list_clientes, list_reportantes, add_cliente_si_no_existe, add_reportante_si_no_existe, _conn
    )

# ====== UI THEME ======
def aplicar_tema():
    if st.session_state.get("tema","Claro")=="Oscuro":
        st.markdown("""
        <style>
        :root,.stApp{background-color:#0f1117;color:#e5e7eb}
        .stButton>button{background:#2d2f36;color:#e5e7eb;border-radius:10px}
        .stSelectbox>div>div,.stTextInput>div>div>input,.stTextArea textarea,.stDateInput input{
            background:#1a1d24!important;color:#e5e7eb!important;border:1px solid #2d2f36!important}
        </style>""", unsafe_allow_html=True)

def set_activity(): st.session_state["last_activity"] = time.time()
def check_session_timeout():
    if "last_activity" in st.session_state and time.time()-st.session_state["last_activity"]>SESSION_TIMEOUT:
        st.warning("Sesión cerrada por inactividad.")
        for k in ["logged","usuario","rol","nombre_agente","last_activity"]: st.session_state.pop(k,None)
        st.rerun()

# ====== LOGIN ======
def do_login(df_users: pd.DataFrame):
    st.subheader("🔑 Inicio de sesión")
    rol = st.radio("Selecciona tu rol", ["Agente","Coordinación"], horizontal=True)
    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")
    if st.button("Iniciar sesión", use_container_width=True):
        match = df_users[(df_users["usuario"]==usuario)&(df_users["contraseña"]==password)&(df_users["rol"]==rol)]
        if not match.empty:
            st.session_state.update({"logged":True,"usuario":usuario,"rol":rol,"nombre_agente":match.iloc[0]["nombre_agente"]})
            set_activity(); st.success(f"Bienvenido/a {st.session_state['nombre_agente']} ({rol})"); st.rerun()
        else:
            st.error("Credenciales inválidas o rol incorrecto.")

# ====== SCHEMA HELPERS ======
def ensure_ticket_schema(df: pd.DataFrame)->pd.DataFrame:
    if df.empty: df = pd.DataFrame(columns=EXPECTED_TICKET_COLS)
    for c in EXPECTED_TICKET_COLS:
        if c not in df.columns: df[c] = pd.Series(dtype="object")
    df["Fecha_Creación"] = pd.to_datetime(df["Fecha_Creación"], errors="coerce")
    df["Tiempo_Resolución_hs"] = pd.to_numeric(df["Tiempo_Resolución_hs"], errors="coerce")
    df["Satisfacción"] = pd.to_numeric(df["Satisfacción"], errors="coerce")
    return df[EXPECTED_TICKET_COLS]

def ensure_user_schema(df: pd.DataFrame)->pd.DataFrame:
    if df.empty: df = pd.DataFrame(columns=EXPECTED_USER_COLS)
    for c in EXPECTED_USER_COLS:
        if c not in df.columns: df[c] = pd.Series(dtype="object")
    return df[EXPECTED_USER_COLS]

# ====== SLA / CRÍTICOS ======
def horas_desde_creacion(r)->float:
    f = r.get("Fecha_Creación")
    if pd.isna(f): return 0.0
    return (pd.Timestamp.now() - pd.to_datetime(f)).total_seconds()/3600.0

def sla_breached(r)->bool:
    if str(r.get("Estado","")) in ["Resuelto","Cerrado"]: return False
    pri = str(r.get("Prioridad",""))
    obj = SLA_OBJ_HORAS.get(pri, 999999)
    return horas_desde_creacion(r) > obj

def es_critico(r)->bool:
    return CRITICOS_POR_PRIORIDAD.get(str(r.get("Prioridad","")),False) or str(r.get("SLA",""))=="Fuera de SLA" or sla_breached(r)

def es_vencido(r)->bool:
    if str(r.get("SLA",""))=="Fuera de SLA": return True
    f = r.get("Fecha_Creación")
    if pd.isna(f): return False
    return (str(r.get("Estado","")) not in ["Resuelto","Cerrado"]) and ((pd.Timestamp.now()-f)>pd.Timedelta(days=10))

def low_csat_clientes(df: pd.DataFrame)->pd.DataFrame:
    c = df.groupby("Empresa")["Satisfacción"].mean().reset_index().rename(columns={"Satisfacción":"CSAT"})
    return c[c["CSAT"]<UMBRAL_CSAT_BAJO].sort_values("CSAT")

# ====== FILTROS ======
def filtros_tickets(df: pd.DataFrame, enable_agente_filter=False)->pd.DataFrame:
    with st.expander("🔎 Filtros", expanded=True):
        c1,c2,c3,c4,c5 = st.columns(5)
        codigo = c1.text_input("Código", placeholder="TCK-...")
        cliente = c2.text_input("Cliente")
        filtro_mod = c3.selectbox("Módulo", ["Todos"]+sorted(list(set(MODULOS+df["Módulo_ERP"].dropna().astype(str).tolist()))))
        filtro_est = c4.selectbox("Estado", ["Todos"]+[e for e in ESTADOS if e in df["Estado"].unique()])
        filtro_pri = c5.selectbox("Prioridad", ["Todos"]+[p for p in PRIORIDADES if p in df["Prioridad"].unique()])
        if enable_agente_filter:
            c6,_ = st.columns([1,4])
            agente_sel = c6.selectbox("Agente", ["Todos"]+sorted(df["Agente_Soporte"].dropna().astype(str).unique().tolist()))
        else:
            agente_sel = "Todos"
    q = df.copy()
    if codigo: q = q[q["ID_Ticket"].astype(str).str.contains(codigo, case=False, na=False)]
    if cliente: q = q[q["Empresa"].astype(str).str.contains(cliente, case=False, na=False)]
    if filtro_mod!="Todos": q = q[q["Módulo_ERP"]==filtro_mod]
    if filtro_est!="Todos": q = q[q["Estado"]==filtro_est]
    if filtro_pri!="Todos": q = q[q["Prioridad"]==filtro_pri]
    if agente_sel!="Todos": q = q[q["Agente_Soporte"]==agente_sel]
    return q

def tabla_estilada_criticos(df: pd.DataFrame):
    if df.empty: return st.dataframe(df, use_container_width=True)
    def _rowstyle(r):
        if es_critico(r) or es_vencido(r): return ['background-color: rgba(255,0,0,0.15)']*len(r)
        return ['']*len(r)
    st.dataframe(df.style.apply(_rowstyle, axis=1), use_container_width=True, hide_index=True)

def seleccionar_ticket(df: pd.DataFrame):
    ids = df["ID_Ticket"].astype(str).tolist()
    if not ids:
        st.info("No hay tickets con los filtros actuales.")
        return None
    return st.selectbox("Seleccioná un ticket para gestionar", ids)

# ====== EDITAR TICKET ======
def form_editar_ticket(ticket_id: str, df_tickets: pd.DataFrame, df_users: pd.DataFrame):
    st.markdown(f"### ✏️ Editando **{ticket_id}**")
    idxs = df_tickets.index[df_tickets["ID_Ticket"]==ticket_id]
    if len(idxs)==0:
        st.error("No se encontró el ticket."); return
    idx = idxs[0]; row = df_tickets.loc[idx].copy()
    empresas = list_clientes()

    col1,col2,col3 = st.columns(3)
    with col1:
        empresa = st.selectbox("Cliente", empresas, index=empresas.index(row["Empresa"]) if row["Empresa"] in empresas else 0)
        reps = list_reportantes(empresa)
        usuario_rep = st.selectbox("Usuario reportante", (reps+["Otro…"]) if reps else ["Otro…"],
                                   index=(reps+["Otro…"]).index(row["Usuario_Reportante"]) if row["Usuario_Reportante"] in reps else len((reps or [])))
        if usuario_rep=="Otro…":
            if USE_API:
                nuevo_rep = st.text_input("Nuevo reportante")
                if st.button("➕ Guardar reportante en API"):
                    if nuevo_rep.strip():
                        create_reportante(empresa, nuevo_rep.strip()); st.success("Reportante creado."); st.rerun()
            else:
                usuario_rep = st.text_input("Nuevo reportante", value=row.get("Usuario_Reportante",""))
                if st.button("➕ Guardar reportante"):
                    if empresa.strip() and usuario_rep.strip():
                        add_reportante_si_no_existe(empresa.strip(), usuario_rep.strip()); st.success("Reportante agregado."); st.rerun()
    with col2:
        modulo = st.selectbox("Módulo ERP", sorted(list(set(MODULOS+[str(row["Módulo_ERP"])]))),
                              index=sorted(list(set(MODULOS+[str(row["Módulo_ERP"])]))).index(str(row["Módulo_ERP"])))
        prioridad = st.selectbox("Prioridad", PRIORIDADES, index=PRIORIDADES.index(row["Prioridad"]) if row["Prioridad"] in PRIORIDADES else 1)
        categoria = st.selectbox("Categoría", CATEGORIAS, index=CATEGORIAS.index(row["Categoría"]) if row["Categoría"] in CATEGORIAS else 1)
    with col3:
        estado = st.selectbox("Estado", ESTADOS, index=ESTADOS.index(row["Estado"]) if row["Estado"] in ESTADOS else 0)
        sla = st.selectbox("SLA", SLA_VALUES, index=SLA_VALUES.index(row["SLA"]) if row["SLA"] in SLA_VALUES else 0)
        tiempo_hs = st.number_input("Tiempo de resolución (hs)", value=float(row["Tiempo_Resolución_hs"]) if pd.notna(row["Tiempo_Resolución_hs"]) else 0.0, min_value=0.0, step=0.5)

    fecha_cre = st.date_input("Fecha de creación", value=row["Fecha_Creación"].date() if pd.notna(row["Fecha_Creación"]) else date.today())
    comentarios = st.text_area("Comentarios", value=str(row.get("Comentarios","") or ""))
    csat = st.slider("Satisfacción (1 a 5)", 1.0, 5.0, float(row.get("Satisfacción",3.0) or 3.0), step=0.5)

    agentes = df_users[df_users["rol"]=="Agente"]["nombre_agente"].dropna().unique().tolist()
    if st.session_state["rol"]=="Coordinación":
        agente_soporte = st.selectbox("Reasignar a", sorted(list(set(agentes+[str(row["Agente_Soporte"])]))),
                                      index=sorted(list(set(agentes+[str(row["Agente_Soporte"])]))).index(str(row["Agente_Soporte"])))
    else:
        agente_soporte = row["Agente_Soporte"]

    if st.button("💾 Guardar cambios", use_container_width=True):
        cambios = []
        def _cmp(campo, nuevo):
            nonlocal cambios; antes = row[campo]
            if (str(antes) if not pd.isna(antes) else "") != (str(nuevo) if not pd.isna(nuevo) else ""):
                df_tickets.at[idx, campo] = nuevo; cambios.append((campo, antes, nuevo))
        _cmp("Empresa", empresa)
        _cmp("Usuario_Reportante", usuario_rep if usuario_rep!="Otro…" else row["Usuario_Reportante"])
        _cmp("Módulo_ERP", modulo); _cmp("Prioridad", prioridad); _cmp("Categoría", categoria)
        _cmp("Estado", estado); _cmp("SLA", sla); _cmp("Tiempo_Resolución_hs", None if tiempo_hs==0 else tiempo_hs)
        _cmp("Comentarios", comentarios); _cmp("Satisfacción", csat)
        _cmp("Agente_Soporte", agente_soporte); _cmp("Fecha_Creación", pd.to_datetime(fecha_cre))
        if cambios:
            upsert_ticket(df_tickets.loc[idx].to_dict())
            for campo, antes, despues in cambios:
                registrar_auditoria_db(st.session_state["usuario"], st.session_state["rol"], ticket_id, campo, antes, despues, "Edición completa")
            st.success("Cambios guardados."); st.rerun()
        else:
            st.info("No hubo cambios para guardar.")

# ====== ALTA TICKET (filtra reportantes por cliente + alta in-line) ======
def form_alta_ticket(df_tickets: pd.DataFrame, df_users: pd.DataFrame):
    st.subheader("➕ Crear nuevo ticket")

    def _on_change_cliente():
        st.session_state.pop("alta_reportante_sel", None)
        st.session_state.pop("alta_nuevo_rep", None)

    empresas = list_clientes()
    empresa = st.selectbox("Cliente*", empresas + ["Otro…"], key="alta_cliente_sel", on_change=_on_change_cliente)

    if empresa == "Otro…":
        nuevo_cli = st.text_input("Nuevo cliente*", key="alta_nuevo_cliente")
        if nuevo_cli and st.button("➕ Guardar cliente", use_container_width=True):
            if USE_API: create_cliente(nuevo_cli.strip())
            else:       add_cliente_si_no_existe(nuevo_cli.strip())
            st.success("Cliente creado. Ahora seleccioná el nuevo cliente en la lista.")
            st.rerun()
        return

    reportantes = list_reportantes(empresa)
    opciones_rep = (reportantes if reportantes else []) + ["Otro…"]
    usuario_reportante = st.selectbox("Usuario reportante*", opciones_rep, key="alta_reportante_sel",
                                      help="Solo se muestran reportantes del cliente seleccionado.")
    nuevo_rep = None
    if usuario_reportante == "Otro…":
        nuevo_rep = st.text_input("Nuevo reportante*", key="alta_nuevo_rep")
        st.caption("El nuevo reportante quedará asociado al cliente seleccionado.")

    c1,c2,c3 = st.columns(3)
    with c1:
        modulo = st.selectbox("Módulo ERP*", sorted(list(set(MODULOS + df_tickets["Módulo_ERP"].dropna().astype(str).unique().tolist()))))
    with c2:
        prioridad = st.selectbox("Prioridad*", PRIORIDADES)
    with c3:
        sla = st.selectbox("SLA*", SLA_VALUES)
    categoria = st.selectbox("Categoría*", CATEGORIAS)

    if st.session_state["rol"]=="Coordinación":
        agentes = df_users[df_users["rol"]=="Agente"]["nombre_agente"].dropna().unique().tolist()
        agente_soporte = st.selectbox("Asignar a agente*", sorted(agentes))
    else:
        agente_soporte = st.session_state["nombre_agente"]
        st.info(f"**{n[1]}** – {n[0]}  
{n[2]}")

    comentarios = st.text_area("Comentarios iniciales", placeholder="Detalle el incidente, pasos para replicar, capturas, etc.")

    if st.button("Crear ticket", type="primary", use_container_width=True):
        if not empresa or not modulo or not prioridad or not categoria or not sla or not agente_soporte:
            st.error("Completá todos los campos obligatorios (*)"); return
        reportante_final = usuario_reportante
        if usuario_reportante=="Otro…":
            if not (nuevo_rep and nuevo_rep.strip()):
                st.error("Ingresá el nombre del nuevo reportante."); return
            reportante_final = nuevo_rep.strip()
            if USE_API: create_reportante(empresa.strip(), reportante_final)
            else:       add_reportante_si_no_existe(empresa.strip(), reportante_final)

        existente = df_tickets["ID_Ticket"].dropna().astype(str).tolist(); pref, nums = "TCK-", []
        for t in existente:
            if t.startswith(pref):
                try: nums.append(int(t.replace(pref,"")))
                except: pass
        nuevo_id = f"{pref}{((max(nums)+1) if nums else 1):05d}"
        nuevo = {
            "ID_Ticket": nuevo_id, "Empresa": empresa.strip(), "Usuario_Reportante": reportante_final,
            "Agente_Soporte": agente_soporte, "Módulo_ERP": modulo, "Prioridad": prioridad,
            "Categoría": categoria, "Estado": "Abierto", "SLA": sla,
            "Fecha_Creación": datetime.now(), "Tiempo_Resolución_hs": None,
            "Comentarios": (comentarios or "").strip(), "Satisfacción": 3.0
        }
        upsert_ticket(nuevo)
        registrar_auditoria_db(st.session_state["usuario"], st.session_state["rol"], nuevo_id, "CREACION","-","-","Alta de ticket")
        st.success(f"Ticket **{nuevo_id}** creado correctamente."); st.rerun()

# ====== CHART HELPERS ======
def _date_range(df: pd.DataFrame):
    fmin = pd.to_datetime(df["Fecha_Creación"]).min()
    fmax = pd.to_datetime(df["Fecha_Creación"]).max()
    if pd.isna(fmin) or pd.isna(fmax):
        hoy = date.today(); return hoy - timedelta(days=30), hoy
    return fmin.date(), fmax.date()

def _filter_by_date(df: pd.DataFrame, dfrom: date, dto: date)->pd.DataFrame:
    if df.empty: return df
    return df[(df["Fecha_Creación"]>=pd.to_datetime(dfrom)) & (df["Fecha_Creación"]<=pd.to_datetime(dto)+pd.Timedelta(days=1))]

def _kpis(df: pd.DataFrame):
    total = len(df); crit = df.apply(es_critico,axis=1).sum(); venc = df.apply(es_vencido,axis=1).sum()
    sla_ok = (df.apply(lambda r: not sla_breached(r), axis=1) & (df["Estado"].isin(["Resuelto","Cerrado"])==False)).sum()
    sla_rate = (sla_ok/total*100) if total else 0
    avg_res = df["Tiempo_Resolución_hs"].dropna().mean(); csat = df["Satisfacción"].dropna().mean()
    return total,crit,venc,sla_rate,avg_res,csat

def chart_bar(data,x,y,title): return alt.Chart(data).mark_bar().encode(x=alt.X(x, sort='-y', title=None), y=alt.Y(y, title=None), tooltip=[x,y]).properties(height=300, title=title)
def chart_line(data,x,y,title): return alt.Chart(data).mark_line(point=True).encode(x=alt.X(x,title=None), y=alt.Y(y,title=None), tooltip=[x,y]).properties(height=300, title=title)
def _timeseries(df: pd.DataFrame, title="Tickets por día"):
    tmp = df.copy(); tmp["Fecha"] = pd.to_datetime(tmp["Fecha_Creación"],errors="coerce").dt.date
    ts = tmp.groupby("Fecha")["ID_Ticket"].count().reset_index().rename(columns={"ID_Ticket":"Tickets"})
    return chart_line(ts,"Fecha:T","Tickets:Q",title)

def backlog_aging_chart(df: pd.DataFrame, title="Backlog Aging (días)"):
    if df.empty: st.caption("Sin datos para backlog."); return
    tmp = df.copy(); tmp = tmp[~tmp["Estado"].isin(["Resuelto","Cerrado"])].copy()
    if tmp.empty: st.caption("No hay tickets abiertos para backlog."); return
    tmp["Edad_dias"] = (pd.Timestamp.now() - pd.to_datetime(tmp["Fecha_Creación"], errors="coerce")).dt.days
    bins = pd.cut(tmp["Edad_dias"], bins=[-1,2,7,14,30,9999], labels=["0-2","3-7","8-14","15-30",">30"])
    dfb = bins.value_counts().sort_index().reset_index(); dfb.columns = ["Rango", "Tickets"]
    st.altair_chart(chart_bar(dfb, "Rango:N", "Tickets:Q", title), use_container_width=True)

# ====== KANBAN (interactivo con acciones en tarjeta) ======
def render_kanban(df: pd.DataFrame, df_users: pd.DataFrame):
    st.markdown("#### 🗂️ Vista Kanban por estado (acciones rápidas)")
    estados = ["Abierto","Priorizado","En Progreso","En Espera","Resuelto","Cerrado"]
    cols = st.columns(len(estados))
    for i, est in enumerate(estados):
        col = cols[i]
        subset = df[df["Estado"]==est].sort_values("Fecha_Creación", ascending=False).head(50)
        with col:
            st.markdown(f"**{est}** ({len(subset)})")
            for _, r in subset.iterrows():
                tid = r["ID_Ticket"]
                badge = "🔴" if (es_critico(r) or es_vencido(r)) else ("⏱️" if sla_breached(r) else "🟢")
                st.caption(f"{badge} {tid} • {r['Empresa']} • {r['Módulo_ERP']} • {r['Prioridad']}")
                with st.expander("Acciones", expanded=False):
                    nuevo_estado = st.selectbox(f"Estado {tid}", ESTADOS, index=ESTADOS.index(est), key=f"kb_est_{tid}")
                    if st.button("Actualizar estado", key=f"kb_upd_{tid}"):
                        row = r.to_dict(); row["Estado"] = nuevo_estado
                        upsert_ticket(row)
                        registrar_auditoria_db(st.session_state["usuario"], st.session_state["rol"], tid, "Estado", est, nuevo_estado, "Kanban")
                        st.success("Estado actualizado."); st.rerun()

# ====== PAGES ======
def page_dashboard_agent(df_t: pd.DataFrame, df_u: pd.DataFrame):
    ag = st.session_state["nombre_agente"]
    st.subheader("📊 Dashboard – Mi desempeño")
    fmin,fmax = _date_range(df_t); dfrom,dto = st.date_input("Rango de fechas",(fmin,fmax))
    mine = _filter_by_date(df_t[df_t["Agente_Soporte"]==ag], dfrom, dto)
    total,crit,venc,sla_rate,avg_res,csat = _kpis(mine)
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Mis tickets", total); m2.metric("Críticos 🔴", int(crit)); m3.metric("Vencidos ⏱️", int(venc))
    m4.metric("SLA %", f"{sla_rate:,.1f}%"); m5.metric("CSAT", f"{csat:,.2f}" if pd.notna(csat) else "—")
    pri = mine["Prioridad"].fillna("Desconocido").value_counts().reset_index(); pri.columns=["Prioridad","Cantidad"]
    mod = mine["Módulo_ERP"].fillna("Desconocido").value_counts().reset_index(); mod.columns=["Módulo_ERP","Cantidad"]
    low = low_csat_clientes(mine[mine["Estado"].isin(["Resuelto","Cerrado"])])
    cA,cB = st.columns(2)
    with cA: st.altair_chart(chart_bar(pri,"Prioridad:N","Cantidad:Q","Prioridades de mis casos"), use_container_width=True)
    with cB: st.altair_chart(chart_bar(mod,"Módulo_ERP:N","Cantidad:Q","Módulos más atendidos (yo)"), use_container_width=True)
    if not low.empty: st.altair_chart(chart_bar(low,"Empresa:N","CSAT:Q","Clientes con calificación baja (mis resoluciones)"), use_container_width=True)
    st.altair_chart(_timeseries(mine, "Tickets por día (yo)"), use_container_width=True)
    backlog_aging_chart(mine, "Backlog Aging (yo)")

def page_dashboard_coord(df_t: pd.DataFrame):
    st.subheader("📊 Dashboard – Coordinación")
    fmin,fmax = _date_range(df_t)
    c1,c2 = st.columns(2)
    with c1: dfrom,dto = st.date_input("Rango de fechas",(fmin,fmax), key="fechas_coord_dash")
    with c2: ag_sel = st.selectbox("Filtrar por agente", ["Todos"]+sorted(df_t["Agente_Soporte"].dropna().astype(str).unique().tolist()))
    q = _filter_by_date(df_t, dfrom, dto); 
    if ag_sel!="Todos": q = q[q["Agente_Soporte"]==ag_sel]
    total,crit,venc,sla_rate,avg_res,csat = _kpis(q)
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Tickets", total); m2.metric("Críticos 🔴", int(crit)); m3.metric("Vencidos ⏱️", int(venc))
    m4.metric("SLA %", f"{sla_rate:,.1f}%"); m5.metric("CSAT", f"{csat:,.2f}" if pd.notna(csat) else "—")
    agent = q.groupby("Agente_Soporte")["ID_Ticket"].count().reset_index().rename(columns={"ID_Ticket":"Tickets"}).sort_values("Tickets", ascending=False).head(12)
    mod = q["Módulo_ERP"].fillna("Desconocido").value_counts().reset_index(); mod.columns=["Módulo_ERP","Cantidad"]
    cli = q["Empresa"].fillna("Desconocido").value_counts().reset_index(); cli.columns=["Empresa","Cantidad"]
    sla_mod = q.groupby(["Módulo_ERP","SLA"])["ID_Ticket"].count().reset_index().rename(columns={"ID_Ticket":"Cantidad"})
    c1,c2 = st.columns(2)
    with c1:
        if not agent.empty: st.altair_chart(chart_bar(agent,"Agente_Soporte:N","Tickets:Q","Tickets por agente"), use_container_width=True)
        st.altair_chart(chart_bar(cli,"Empresa:N","Cantidad:Q","Clientes con más casos"), use_container_width=True)
    with c2:
        st.altair_chart(chart_bar(mod,"Módulo_ERP:N","Cantidad:Q","Módulos más atendidos"), use_container_width=True)
        st.altair_chart(alt.Chart(sla_mod).mark_bar().encode(
            x=alt.X("Módulo_ERP:N", sort='-y', title=None),
            y=alt.Y("Cantidad:Q", title=None),
            color=alt.Color("SLA:N"),
            tooltip=["Módulo_ERP","SLA","Cantidad"]).properties(height=300, title="SLA por módulo"),
            use_container_width=True)
    low = low_csat_clientes(q[q["Estado"].isin(["Resuelto","Cerrado"])])
    if not low.empty: st.altair_chart(chart_bar(low,"Empresa:N","CSAT:Q","Clientes con calificación baja"), use_container_width=True)
    st.altair_chart(_timeseries(q, "Tickets por día (global / filtrado)"), use_container_width=True)
    backlog_aging_chart(q, "Backlog Aging (global / filtrado)")

def acciones_masivas(df_filtrado: pd.DataFrame, df_users: pd.DataFrame):
    st.markdown("#### ⚡ Acciones masivas (Coordinación)")
    ids = df_filtrado["ID_Ticket"].astype(str).tolist()
    seleccion = st.multiselect("Seleccioná tickets", ids, max_selections=100)
    col1, col2, col3 = st.columns(3)
    with col1: nuevo_estado = st.selectbox("Cambiar estado a…", ["Sin cambio"] + ESTADOS)
    with col2: nueva_prioridad = st.selectbox("Cambiar prioridad a…", ["Sin cambio"] + PRIORIDADES)
    with col3:
        agentes = df_users[df_users["rol"]=="Agente"]["nombre_agente"].dropna().unique().tolist()
        nuevo_agente = st.selectbox("Reasignar a…", ["Sin cambio"] + sorted(agentes))
    if st.button("Aplicar a seleccionados", use_container_width=True, type="primary", disabled=(not seleccion)):
        if USE_API:
            payload = {}
            if nuevo_estado!="Sin cambio": payload["set_estado"]=nuevo_estado
            if nueva_prioridad!="Sin cambio": payload["set_prioridad"]=nueva_prioridad
            if nuevo_agente!="Sin cambio": payload["set_agente"]=nuevo_agente
            if not payload: st.info("No hay cambios para aplicar."); return
            payload["ids"]=seleccion
            from api_client import bulk_update_tickets as _bulk; res = _bulk(**payload); st.success(f"Actualizados: {res.get('updated',0)}"); st.rerun()
        else:
            df_local = st.session_state.get("_df_tickets_full", df_filtrado); changed=0
            for tid in seleccion:
                idxs = df_local.index[df_local["ID_Ticket"]==tid]
                if len(idxs)==0: continue
                idx = idxs[0]
                if nuevo_estado!="Sin cambio": df_local.at[idx,"Estado"] = nuevo_estado
                if nueva_prioridad!="Sin cambio": df_local.at[idx,"Prioridad"] = nueva_prioridad
                if nuevo_agente!="Sin cambio": df_local.at[idx,"Agente_Soporte"] = nuevo_agente
                upsert_ticket(df_local.loc[idx].to_dict()); changed += 1
            st.success(f"Actualizados: {changed}"); st.rerun()

def page_tickets(df_t: pd.DataFrame, df_u: pd.DataFrame, enable_agente_filter=False):
    st.subheader("📋 Gestión de Tickets")
    df_f = filtros_tickets(df_t, enable_agente_filter=enable_agente_filter)
    cols = ["ID_Ticket","Empresa","Usuario_Reportante","Agente_Soporte","Módulo_ERP","Prioridad","Categoría","Estado","SLA","Fecha_Creación","Tiempo_Resolución_hs","Satisfacción","Comentarios"]
    tabla_estilada_criticos(df_f[cols].sort_values("Fecha_Creación", ascending=False))
    # Exportar CSV
    csv = df_f[cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ Exportar CSV", data=csv, file_name="tickets_filtrados.csv", mime="text/csv", use_container_width=True)
    # Kanban
    with st.expander("🗂️ Vista Kanban", expanded=False):
        render_kanban(df_f, df_u)
    if st.session_state["rol"]=="Coordinación": acciones_masivas(df_f, df_u)
    sel = seleccionar_ticket(df_f)
    if sel: form_editar_ticket(sel, df_t, df_u)

# ====== MAIN ======
def main():
    st.sidebar.selectbox("Tema", ["Claro","Oscuro"], key="tema", on_change=aplicar_tema); aplicar_tema(); check_session_timeout()
    df_users = ensure_user_schema(load_usuarios_df()); df_tickets = ensure_ticket_schema(load_tickets_df())
    if not st.session_state.get("logged", False): do_login(df_users); return
    cA,cB,cC = st.columns([2,2,1])
    with cA: st.markdown(f"**👤 {st.session_state['nombre_agente']}**  |  **Rol:** {st.session_state['rol']}")
    with cB: st.caption(f"Usuario: {st.session_state['usuario']}")
    with cC:
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            for k in ["logged","usuario","rol","nombre_agente","last_activity"]: st.session_state.pop(k,None); st.rerun()
    if not USE_API:
        st.session_state["_df_tickets_full"] = df_tickets.copy()
    set_activity()
    if st.session_state["rol"]=="Coordinación":
        pagina = st.sidebar.radio("Navegación", ["Dashboard","Tickets","Crear ticket","Estadísticas & Análisis"])
        if pagina=="Dashboard": page_dashboard_coord(df_tickets)
        elif pagina=="Tickets": page_tickets(df_tickets, df_users, enable_agente_filter=True)
        elif pagina=="Crear ticket": form_alta_ticket(df_tickets, df_users)
        elif pagina=="Estadísticas & Análisis": page_dashboard_agent(df_tickets, df_users)  # reutiliza KPIs
    else:
        pagina = st.sidebar.radio("Navegación", ["Dashboard","Tickets","Crear ticket"])
        if pagina=="Dashboard": page_dashboard_agent(df_tickets, df_users)
        elif pagina=="Tickets": page_tickets(df_tickets[df_tickets["Agente_Soporte"]==st.session_state["nombre_agente"]].copy(), df_users)
        elif pagina=="Crear ticket": form_alta_ticket(df_tickets, df_users)

    st.markdown("<hr/>", unsafe_allow_html=True)
    st.caption("Versión 8 – Soporte ERP Portfolio")

    with st.expander("📝 Ver auditoría de cambios"):
        if USE_API:
            st.caption("La auditoría se registra vía API (ver servidor).")
        else:
            with _conn() as cn:
                import pandas as _pd
                aud = _pd.read_sql("SELECT timestamp, usuario, rol, ticket, campo, antes, despues, motivo FROM Auditoria ORDER BY id DESC", cn)
            if aud.empty: st.caption("Aún no hay registros de auditoría.")
            else: st.dataframe(aud, use_container_width=True, hide_index=True)

if __name__=="__main__": main()

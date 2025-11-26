import sqlite3, os, pandas as pd
from contextlib import contextmanager
from datetime import datetime, timedelta
DB_PATH = os.environ.get("ERP_SQLITE_PATH", "erp_mock.db")

@contextmanager
def _conn():
    cn = sqlite3.connect(DB_PATH)
    try:
        yield cn
    finally:
        cn.close()

def _init_db():
    with _conn() as cn:
        c = cn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS Usuarios(
            usuario TEXT PRIMARY KEY, contraseña TEXT, rol TEXT, nombre_agente TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS Clientes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS Reportantes(
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente TEXT, nombre TEXT,
            UNIQUE(cliente, nombre))""")
        c.execute("""CREATE TABLE IF NOT EXISTS Tickets(
            ID_Ticket TEXT PRIMARY KEY, Empresa TEXT, Usuario_Reportante TEXT,
            Agente_Soporte TEXT, Módulo_ERP TEXT, Prioridad TEXT, Categoría TEXT,
            Estado TEXT, SLA TEXT, Fecha_Creación TEXT, Tiempo_Resolución_hs REAL,
            Comentarios TEXT, Satisfacción REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS Auditoria(
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, usuario TEXT, rol TEXT,
            ticket TEXT, campo TEXT, antes TEXT, despues TEXT, motivo TEXT)""")
        cn.commit()
        # seed
        ucount = c.execute("SELECT COUNT(*) FROM Usuarios").fetchone()[0]
        if ucount == 0:
            c.executemany("INSERT INTO Usuarios(usuario,contraseña,rol,nombre_agente) VALUES (?,?,?,?)", [
                ("admin","admin123","Coordinación","Coordinador"),
                ("slopez","agente123","Agente","Sofía López"),
                ("cperes","agente123","Agente","Carlos Pérez"),
            ])
        clis = ["MetalPlus SRL","AgroAndes SA","LogiWare","TextilNova","SolarTech"]
        for cli in clis:
            c.execute("INSERT OR IGNORE INTO Clientes(nombre) VALUES (?)", (cli,))
        reps = [("MetalPlus SRL","Pablo Silva"),("MetalPlus SRL","Ana Ruiz"),
                ("AgroAndes SA","Marcos Peña"),("LogiWare","Lucía Medina"),
                ("TextilNova","Valeria Ortiz"),("SolarTech","Diego Gómez")]
        for (cli, rep) in reps:
            c.execute("INSERT OR IGNORE INTO Reportantes(cliente,nombre) VALUES (?,?)", (cli, rep))
        # tickets demo
        tcount = c.execute("SELECT COUNT(*) FROM Tickets").fetchone()[0]
        if tcount == 0:
            import random
            mods = ["Ventas","Inventario","Facturación","Producción","Logística","Compras","Tesorería","Contabilidad"]
            pris = ["Alta","Media","Baja"]
            cats = ["Error crítico","Consulta funcional","Mejora","Reporte caído","Integración"]
            estados = ["Abierto","Priorizado","En Progreso","En Espera","Resuelto","Cerrado"]
            agentes = ["Sofía López","Carlos Pérez"]
            for i in range(1, 61):
                emp = random.choice(clis)
                rep = c.execute("SELECT nombre FROM Reportantes WHERE cliente=? ORDER BY RANDOM() LIMIT 1",(emp,)).fetchone()[0]
                ag = random.choice(agentes)
                mod = random.choice(mods)
                pri = random.choice(pris)
                cat = random.choice(cats)
                est = random.choice(estados)
                sla = "Dentro de SLA"
                ts = (datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 20))).isoformat()
                trh = None if est not in ("Resuelto","Cerrado") else round(random.uniform(1, 24),1)
                com = "Comentario demo"
                csat = round(random.uniform(2.5, 5.0),1) if est in ("Resuelto","Cerrado") else None
                tid = f"TCK-{i:05d}"
                c.execute("""INSERT OR REPLACE INTO Tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (tid, emp, rep, ag, mod, pri, cat, est, sla, ts, trh, com, csat))
        cn.commit()

_init_db()

def load_usuarios_df():
    with _conn() as cn:
        return pd.read_sql("SELECT * FROM Usuarios", cn)

def load_tickets_df():
    with _conn() as cn:
        df = pd.read_sql("SELECT * FROM Tickets", cn, parse_dates=["Fecha_Creación"])
    return df

def list_clientes():
    with _conn() as cn:
        return [r[0] for r in cn.execute("SELECT nombre FROM Clientes ORDER BY nombre").fetchall()]

def list_reportantes(cliente: str):
    with _conn() as cn:
        return [r[0] for r in cn.execute("SELECT nombre FROM Reportantes WHERE cliente=? ORDER BY nombre",(cliente,)).fetchall()]

def add_cliente_si_no_existe(nombre: str):
    with _conn() as cn:
        cn.execute("INSERT OR IGNORE INTO Clientes(nombre) VALUES (?)",(nombre,)); cn.commit()

def add_reportante_si_no_existe(cliente: str, nombre: str):
    with _conn() as cn:
        cn.execute("INSERT OR IGNORE INTO Reportantes(cliente,nombre) VALUES (?,?)",(cliente,nombre)); cn.commit()

def upsert_ticket(rec: dict):
    vals = [rec.get(k) for k in ["ID_Ticket","Empresa","Usuario_Reportante","Agente_Soporte","Módulo_ERP",
                                 "Prioridad","Categoría","Estado","SLA","Fecha_Creación",
                                 "Tiempo_Resolución_hs","Comentarios","Satisfacción"]]
    if hasattr(vals[9], "isoformat"):
        vals[9] = vals[9].isoformat()
    with _conn() as cn:
        cn.execute("""INSERT INTO Tickets(ID_Ticket,Empresa,Usuario_Reportante,Agente_Soporte,Módulo_ERP,Prioridad,Categoría,Estado,SLA,Fecha_Creación,Tiempo_Resolución_hs,Comentarios,Satisfacción)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                      ON CONFLICT(ID_Ticket) DO UPDATE SET
                        Empresa=excluded.Empresa, Usuario_Reportante=excluded.Usuario_Reportante, Agente_Soporte=excluded.Agente_Soporte,
                        Módulo_ERP=excluded.Módulo_ERP, Prioridad=excluded.Prioridad, Categoría=excluded.Categoría, Estado=excluded.Estado,
                        SLA=excluded.SLA, Fecha_Creación=excluded.Fecha_Creación, Tiempo_Resolución_hs=excluded.Tiempo_Resolución_hs,
                        Comentarios=excluded.Comentarios, Satisfacción=excluded.Satisfacción
                   """, vals)
        cn.commit()

def registrar_auditoria(usuario, rol, ticket, campo, antes, despues, motivo):
    with _conn() as cn:
        cn.execute("""INSERT INTO Auditoria(timestamp, usuario, rol, ticket, campo, antes, despues, motivo)
                      VALUES (?,?,?,?,?,?,?,?)""",
                   (datetime.now().isoformat(), usuario, rol, ticket, str(campo), str(antes), str(despues), str(motivo)))
        cn.commit()


def get_connection():
    cn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cn.row_factory = sqlite3.Row
    return cn

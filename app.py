import sqlite3
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st

DB_FILE = "eventos_fazenda_v9.db"

def conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def q(sql, params=()):
    c = conn()
    df = pd.read_sql_query(sql, c, params=params)
    c.close()
    return df

def x(sql, params=()):
    c = conn()
    cur = c.cursor()
    cur.execute(sql, params)
    c.commit()
    lid = cur.lastrowid
    c.close()
    return lid

def add_col(table, col, definition):
    c = conn()
    cur = c.cursor()
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    c.commit()
    c.close()

def init_db():
    c = conn()
    cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS clientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, telefone TEXT, email TEXT,
        documento TEXT, tipo_cliente TEXT, empresa TEXT, origem_lead TEXT, observacoes TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS espacos(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, capacidade INTEGER DEFAULT 0,
        descricao TEXT, ativo INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS tipos_evento(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, capacidade_sugerida INTEGER DEFAULT 0,
        regras TEXT, ativo INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS eventos(
        id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT, titulo TEXT NOT NULL, cliente_id INTEGER,
        tipo_evento_id INTEGER, espaco_id INTEGER, data_evento TEXT NOT NULL, hora_inicio TEXT, hora_fim TEXT,
        adultos INTEGER DEFAULT 0, criancas INTEGER DEFAULT 0, status_pipeline TEXT, status_operacional TEXT,
        valor_locacao REAL DEFAULT 0, valor_adultos REAL DEFAULT 0, valor_criancas REAL DEFAULT 0,
        valor_servicos REAL DEFAULT 0, desconto REAL DEFAULT 0, valor_total REAL DEFAULT 0,
        forma_pagamento TEXT, responsavel_comercial TEXT, responsavel_interno TEXT, observacoes TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS pagamentos(
        id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER, descricao TEXT, valor REAL NOT NULL,
        vencimento TEXT, data_pagamento TEXT, status TEXT DEFAULT 'Em aberto', forma_pagamento TEXT, observacoes TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS despesas(
        id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER, tipo_despesa TEXT DEFAULT 'Fixa',
        fornecedor TEXT, descricao TEXT, categoria TEXT, valor REAL NOT NULL, vencimento TEXT,
        data_pagamento TEXT, status TEXT DEFAULT 'Pendente', recorrente TEXT DEFAULT 'Não', observacoes TEXT)""")
    c.commit()
    c.close()

    for table, cols in {
        "eventos": [("adultos","INTEGER DEFAULT 0"), ("criancas","INTEGER DEFAULT 0"), ("valor_adultos","REAL DEFAULT 0"), ("valor_criancas","REAL DEFAULT 0")],
        "despesas": [("tipo_despesa","TEXT DEFAULT 'Fixa'"), ("categoria","TEXT"), ("recorrente","TEXT DEFAULT 'Não'")],
        "pagamentos": [("evento_id","INTEGER")]
    }.items():
        for col, definition in cols:
            try: add_col(table, col, definition)
            except Exception: pass

    # Base limpa: nenhum cadastro é carregado automaticamente.

def moeda(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def data_safe(v):
    try:
        if pd.isna(v) or not v:
            return date.today()
        return pd.to_datetime(v).date()
    except Exception:
        return date.today()

def clientes_df(): return q("SELECT id,nome FROM clientes ORDER BY nome")
def espacos_df(): return q("SELECT id,nome,capacidade FROM espacos WHERE ativo=1 ORDER BY nome")
def tipos_df(): return q("SELECT id,nome FROM tipos_evento WHERE ativo=1 ORDER BY nome")

def carregar_cadastros_sugeridos():
    """Carrega sugestões de espaços e tipos somente quando o usuário clicar no botão."""
    espacos = [
        ("Salão Principal",250,"Eventos sociais e corporativos"),
        ("Área Externa",400,"Jardins e área aberta"),
        ("Piscinas e Toboáguas",180,"Day use e lazer"),
        ("Espaço Corporativo",150,"Treinamentos e workshops"),
        ("Churrasco e Confraternizações",120,"Eventos menores")
    ]
    tipos = [
        ("Casamento",200,"Evento social premium"),
        ("Aniversário",100,"Evento social"),
        ("Corporativo",120,"Evento empresarial"),
        ("Formatura",250,"Evento social ampliado"),
        ("Ensaio Fotográfico",15,"Pacote enxuto"),
        ("15 Anos",150,"Evento social premium"),
        ("Workshop",80,"Formato diurno"),
        ("Day Use",80,"Lazer e alimentação opcional")
    ]

    existentes_espacos_df = q("SELECT nome FROM espacos")
    existentes_espacos = set(existentes_espacos_df["nome"].tolist()) if not existentes_espacos_df.empty else set()
    for item in espacos:
        if item[0] not in existentes_espacos:
            x("INSERT INTO espacos(nome,capacidade,descricao,ativo) VALUES(?,?,?,1)", item)

    existentes_tipos_df = q("SELECT nome FROM tipos_evento")
    existentes_tipos = set(existentes_tipos_df["nome"].tolist()) if not existentes_tipos_df.empty else set()
    for item in tipos:
        if item[0] not in existentes_tipos:
            x("INSERT INTO tipos_evento(nome,capacidade_sugerida,regras,ativo) VALUES(?,?,?,1)", item)


def eventos_df():
    return q("""
        SELECT e.id, COALESCE(e.codigo,'EVT-'||e.id) codigo, e.titulo, c.nome cliente, t.nome tipo_evento,
               es.nome espaco, e.data_evento, e.hora_inicio, e.hora_fim, e.adultos, e.criancas,
               e.status_pipeline, e.status_operacional, e.valor_total,
               COALESCE((SELECT SUM(valor) FROM pagamentos p WHERE p.evento_id=e.id AND p.status='Pago'),0) total_pago,
               e.valor_total - COALESCE((SELECT SUM(valor) FROM pagamentos p WHERE p.evento_id=e.id AND p.status='Pago'),0) saldo_evento
        FROM eventos e
        LEFT JOIN clientes c ON c.id=e.cliente_id
        LEFT JOIN tipos_evento t ON t.id=e.tipo_evento_id
        LEFT JOIN espacos es ON es.id=e.espaco_id
        ORDER BY e.data_evento, e.hora_inicio
    """)

def evento_row(eid):
    df = q("SELECT * FROM eventos WHERE id=?", (eid,))
    return df.iloc[0] if not df.empty else None

def conflito(data_evento, espaco_id, evento_id=None):
    sql = "SELECT id FROM eventos WHERE data_evento=? AND espaco_id=? AND status_operacional<>'Cancelado'"
    params = [data_evento, espaco_id]
    if evento_id:
        sql += " AND id<>?"
        params.append(evento_id)
    return not q(sql, tuple(params)).empty

def backup_excel():
    """
    Gera backup Excel de forma segura.
    Corrige o erro 'At least one sheet must be visible' garantindo que:
    1) a aba INSTRUCOES sempre exista;
    2) falhas em alguma tabela não impedem a geração do arquivo;
    3) nomes de abas ficam dentro do limite do Excel.
    """
    out = BytesIO()

    tabelas = [
        ("clientes", "CLIENTES"),
        ("eventos", "EVENTOS"),
        ("pagamentos", "PAGAMENTOS"),
        ("despesas", "DESPESAS"),
        ("espacos", "ESPACOS"),
        ("tipos_evento", "TIPOS_EVENTO"),
    ]

    instrucoes = pd.DataFrame({
        "ORIENTACAO": [
            "Backup padrão do sistema Quinta do Conde.",
            "Financeiro funciona mesmo sem eventos.",
            "Despesas fixas/gerais ficam na aba DESPESAS.",
            "Este arquivo foi gerado automaticamente pelo sistema."
        ]
    })

    erros = []

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        # Primeira aba sempre criada
        instrucoes.to_excel(writer, sheet_name="INSTRUCOES", index=False)

        for tabela, aba in tabelas:
            try:
                df = q(f"SELECT * FROM {tabela}")
                # Excel limita nomes de abas a 31 caracteres
                aba_segura = aba[:31]
                df.to_excel(writer, sheet_name=aba_segura, index=False)
            except Exception as e:
                erros.append({"TABELA": tabela, "ERRO": str(e)})

        if erros:
            pd.DataFrame(erros).to_excel(writer, sheet_name="LOG_ERROS", index=False)

    out.seek(0)
    return out.getvalue()

def fluxo_df(inicio, fim, saldo_inicial):
    receb = q("""SELECT data_pagamento AS data, SUM(valor) entradas FROM pagamentos
                 WHERE status='Pago' AND data_pagamento BETWEEN ? AND ? GROUP BY data_pagamento""", (str(inicio), str(fim)))
    saidas = q("""SELECT COALESCE(data_pagamento,vencimento) AS data, SUM(valor) saidas FROM despesas
                  WHERE status='Paga' AND COALESCE(data_pagamento,vencimento) BETWEEN ? AND ?
                  GROUP BY COALESCE(data_pagamento,vencimento)""", (str(inicio), str(fim)))
    base = pd.DataFrame({"data":[str(d.date()) for d in pd.date_range(inicio, fim)]})
    base = base.merge(receb, on="data", how="left").merge(saidas, on="data", how="left")
    base["entradas"] = base["entradas"].fillna(0)
    base["saidas"] = base["saidas"].fillna(0)
    base["saldo_dia"] = base["entradas"] - base["saidas"]
    base["saldo_acumulado"] = saldo_inicial + base["saldo_dia"].cumsum()
    return base

st.set_page_config(page_title="Quinta do Conde | Premium", page_icon="🏡", layout="wide")
init_db()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp {
    background: radial-gradient(circle at top left, rgba(186,155,119,.20), transparent 30%),
                radial-gradient(circle at top right, rgba(98,120,82,.13), transparent 28%),
                linear-gradient(180deg, #FBF8F2 0%, #EFE4D5 100%);
}
.block-container { padding-top: 1rem; max-width: 1380px; }
h1, h2, h3 { color:#38271C; letter-spacing:-.02em; }
[data-testid="stMetric"] {
    background: rgba(255,255,255,.94);
    border:1px solid #D9C8B2;
    border-radius:24px;
    padding:17px;
    box-shadow:0 12px 30px rgba(67,45,29,.08);
}
.hero {
    background: linear-gradient(135deg,#4A3324 0%,#7A5A43 46%,#B99A6D 100%);
    color:white;
    padding:30px 34px;
    border-radius:34px;
    margin-bottom:20px;
    box-shadow:0 18px 42px rgba(72,50,33,.24);
}
.card {
    background: rgba(255,255,255,.84);
    border:1px solid #D9C8B2;
    border-radius:22px;
    padding:18px 20px;
    box-shadow:0 10px 26px rgba(67,45,29,.07);
    color:#4F3D2F;
}
.alert { background:#FFF4E5; border:1px solid #E8B76B; border-radius:18px; padding:14px 16px; color:#6B451F; }
.ok { background:#F0F8F0; border:1px solid #A8C79E; border-radius:18px; padding:14px 16px; color:#385E34; }
.stButton>button, .stDownloadButton>button {
    border-radius:14px!important; border:1px solid #7A5A43!important;
    background:linear-gradient(135deg,#5A402C,#7A5A43)!important; color:white!important; font-weight:700!important;
}
div[data-testid="stSidebar"] { background:#F4EBDD; }
</style>
<div class="hero">
    <h1 style="margin:0;">🏡 Quinta do Conde</h1>
    <div style="opacity:.94;font-size:1.10rem;margin-top:6px;">Sistema Premium de Eventos e Financeiro</div>
    <div style="opacity:.90;margin-top:5px;">Dashboard executivo, previsão de caixa, alertas, despesas fixas, backup em Excel e base inicial limpa.</div>
</div>
""", unsafe_allow_html=True)

menu = st.sidebar.radio("Menu", ["Dashboard Premium","Clientes","Eventos","Financeiro","Fluxo de Caixa","Agenda","Backup Excel","Cadastros"])

if menu == "Dashboard Premium":
    ev = eventos_df()
    receb = q("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE status='Pago'")["total"].iloc[0]
    receber = q("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE status<>'Pago'")["total"].iloc[0]
    desp_paga = q("SELECT COALESCE(SUM(valor),0) total FROM despesas WHERE status='Paga'")["total"].iloc[0]
    desp_aberta = q("SELECT COALESCE(SUM(valor),0) total FROM despesas WHERE status<>'Paga'")["total"].iloc[0]
    resultado = float(receb or 0) - float(desp_paga or 0)

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Eventos", len(ev))
    c2.metric("Recebido", moeda(receb))
    c3.metric("A receber", moeda(receber))
    c4.metric("Despesas abertas", moeda(desp_aberta))
    c5.metric("Resultado realizado", moeda(resultado))

    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.subheader("Carteira de eventos")
        if ev.empty:
            st.info("Nenhum evento cadastrado.")
        else:
            view = ev.copy()
            for col in ["valor_total","total_pago","saldo_evento"]:
                view[col] = view[col].apply(moeda)
            st.dataframe(view, use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Alertas")
        vencidas = q("SELECT COUNT(*) qtd, COALESCE(SUM(valor),0) total FROM despesas WHERE status <> 'Paga' AND vencimento < ?", (str(date.today()),))
        proximas = q("SELECT COUNT(*) qtd, COALESCE(SUM(valor),0) total FROM despesas WHERE status <> 'Paga' AND vencimento BETWEEN ? AND ?", (str(date.today()), str(date.today()+timedelta(days=7))))
        if vencidas["qtd"].iloc[0] > 0:
            st.markdown(f"<div class='alert'>⚠️ Despesas vencidas: <b>{int(vencidas['qtd'].iloc[0])}</b><br>Total: <b>{moeda(vencidas['total'].iloc[0])}</b></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='ok'>✅ Nenhuma despesa vencida.</div>", unsafe_allow_html=True)
        st.write("")
        st.markdown(f"<div class='alert'>📌 Próximos 7 dias: <b>{int(proximas['qtd'].iloc[0])}</b><br>Total: <b>{moeda(proximas['total'].iloc[0])}</b></div>", unsafe_allow_html=True)

    mov = q("""
        SELECT substr(data_pagamento,1,7) mes, SUM(valor) recebido, 0 saidas
        FROM pagamentos WHERE status='Pago' AND data_pagamento IS NOT NULL GROUP BY substr(data_pagamento,1,7)
        UNION ALL
        SELECT substr(COALESCE(data_pagamento,vencimento),1,7) mes, 0 recebido, SUM(valor) saidas
        FROM despesas WHERE status='Paga' GROUP BY substr(COALESCE(data_pagamento,vencimento),1,7)
    """)
    st.subheader("Visão financeira mensal")
    if not mov.empty:
        pivot = mov.groupby("mes", as_index=False).sum()
        pivot["resultado"] = pivot["recebido"] - pivot["saidas"]
        st.bar_chart(pivot.set_index("mes")[["recebido","saidas","resultado"]])
    else:
        st.info("Ainda não há movimentos financeiros para o gráfico.")

elif menu == "Clientes":
    tab1,tab2 = st.tabs(["Cadastrar","Editar / Excluir"])
    with tab1:
        with st.form("cliente_new", clear_on_submit=True):
            c1,c2,c3=st.columns(3)
            nome=c1.text_input("Nome / razão social*")
            telefone=c2.text_input("Telefone / WhatsApp")
            email=c3.text_input("E-mail")
            c4,c5,c6=st.columns(3)
            doc=c4.text_input("CPF/CNPJ")
            tipo=c5.selectbox("Tipo",["Pessoa Física","Pessoa Jurídica"])
            empresa=c6.text_input("Empresa")
            origem=st.selectbox("Origem do lead",["Site","Instagram","Indicação","Google","WhatsApp","Outro"])
            obs=st.text_area("Observações")
            if st.form_submit_button("Salvar cliente"):
                if not nome.strip():
                    st.error("Informe o nome.")
                else:
                    x("INSERT INTO clientes(nome,telefone,email,documento,tipo_cliente,empresa,origem_lead,observacoes) VALUES(?,?,?,?,?,?,?,?)",(nome,telefone,email,doc,tipo,empresa,origem,obs))
                    st.success("Cliente cadastrado.")
    with tab2:
        df=q("SELECT * FROM clientes ORDER BY nome")
        if df.empty:
            st.info("Nenhum cliente.")
        else:
            op={f"{r['id']} - {r['nome']}":int(r["id"]) for _,r in df.iterrows()}
            cid=op[st.selectbox("Cliente",list(op.keys()))]
            r=q("SELECT * FROM clientes WHERE id=?",(cid,)).iloc[0]
            with st.form("cliente_edit"):
                nome=st.text_input("Nome",r["nome"])
                telefone=st.text_input("Telefone",r["telefone"] or "")
                email=st.text_input("E-mail",r["email"] or "")
                doc=st.text_input("CPF/CNPJ",r["documento"] or "")
                tipo=st.selectbox("Tipo",["Pessoa Física","Pessoa Jurídica"], index=1 if r["tipo_cliente"]=="Pessoa Jurídica" else 0)
                empresa=st.text_input("Empresa",r["empresa"] or "")
                origem=st.text_input("Origem",r["origem_lead"] or "")
                obs=st.text_area("Observações",r["observacoes"] or "")
                a,b=st.columns(2)
                if a.form_submit_button("Salvar alterações"):
                    x("UPDATE clientes SET nome=?,telefone=?,email=?,documento=?,tipo_cliente=?,empresa=?,origem_lead=?,observacoes=? WHERE id=?",(nome,telefone,email,doc,tipo,empresa,origem,obs,cid))
                    st.success("Cliente atualizado.")
                if b.form_submit_button("Excluir"):
                    if q("SELECT COUNT(*) qtd FROM eventos WHERE cliente_id=?",(cid,))["qtd"].iloc[0]:
                        st.error("Cliente com evento vinculado.")
                    else:
                        x("DELETE FROM clientes WHERE id=?",(cid,))
                        st.success("Cliente excluído.")
            st.dataframe(df,use_container_width=True,hide_index=True)

elif menu == "Eventos":
    tab1,tab2 = st.tabs(["Cadastrar evento","Editar / Excluir evento"])

    def evento_form(r=None):
        cli=clientes_df(); esp=espacos_df(); tip=tipos_df()
        if cli.empty:
            st.warning("Cadastre um cliente primeiro.")
            return None
        if esp.empty:
            st.warning("Cadastre pelo menos um espaço antes de criar eventos.")
            return None
        if tip.empty:
            st.warning("Cadastre pelo menos um tipo de evento antes de criar eventos.")
            return None
        mcli=dict(zip(cli["nome"],cli["id"]))
        mesp={f"{a.nome} | cap. {int(a.capacidade)}":int(a.id) for a in esp.itertuples()}
        mtip=dict(zip(tip["nome"],tip["id"]))
        titulo=st.text_input("Nome da proposta / evento*", r["titulo"] if r is not None else "")
        c1,c2,c3=st.columns(3)
        cliente=c1.selectbox("Cliente",list(mcli.keys()))
        tipo=c2.selectbox("Tipo de evento",list(mtip.keys()))
        espaco=c3.selectbox("Espaço",list(mesp.keys()))
        c4,c5,c6=st.columns(3)
        data=c4.date_input("Data", value=data_safe(r["data_evento"]) if r is not None else date.today()+timedelta(days=30))
        hi=c5.time_input("Início", value=datetime.strptime((r["hora_inicio"] if r is not None and r["hora_inicio"] else "10:00"),"%H:%M").time())
        hf=c6.time_input("Fim", value=datetime.strptime((r["hora_fim"] if r is not None and r["hora_fim"] else "22:00"),"%H:%M").time())
        c7,c8=st.columns(2)
        adultos=c7.number_input("Adultos",min_value=0,step=1,value=int(r["adultos"] or 0) if r is not None else 0)
        criancas=c8.number_input("Crianças",min_value=0,step=1,value=int(r["criancas"] or 0) if r is not None else 0)
        c9,c10=st.columns(2)
        pipeline=c9.selectbox("Pipeline",["Lead","Visita agendada","Proposta enviada","Negociação","Fechado","Perdido"])
        status=c10.selectbox("Status operacional",["Orçamento","Pré-reserva","Confirmado","Realizado","Cancelado"])
        st.markdown("#### Formação da proposta")
        c11,c12,c13,c14,c15=st.columns(5)
        loc=c11.number_input("Locação/pacote",min_value=0.0,step=100.0,value=float(r["valor_locacao"] or 0) if r is not None else 0.0)
        vad=c12.number_input("Valor adultos",min_value=0.0,step=100.0,value=float(r["valor_adultos"] or 0) if r is not None else 0.0)
        vcr=c13.number_input("Valor crianças",min_value=0.0,step=100.0,value=float(r["valor_criancas"] or 0) if r is not None else 0.0)
        serv=c14.number_input("Serviços",min_value=0.0,step=100.0,value=float(r["valor_servicos"] or 0) if r is not None else 0.0)
        desc=c15.number_input("Desconto",min_value=0.0,step=100.0,value=float(r["desconto"] or 0) if r is not None else 0.0)
        total=max(loc+vad+vcr+serv-desc,0)
        st.info(f"Valor total: {moeda(total)}")
        c16,c17,c18=st.columns(3)
        forma=c16.selectbox("Forma principal",["Pix","Boleto","Cartão","Transferência","Dinheiro","Outro"])
        resp_com=c17.text_input("Responsável comercial", r["responsavel_comercial"] if r is not None and r["responsavel_comercial"] else "")
        resp_int=c18.text_input("Responsável interno", r["responsavel_interno"] if r is not None and r["responsavel_interno"] else "")
        obs=st.text_area("Observações", r["observacoes"] if r is not None and r["observacoes"] else "")
        return dict(titulo=titulo,cliente_id=int(mcli[cliente]),tipo_evento_id=int(mtip[tipo]),espaco_id=int(mesp[espaco]),
                    data_evento=str(data),hora_inicio=hi.strftime("%H:%M"),hora_fim=hf.strftime("%H:%M"),
                    adultos=int(adultos),criancas=int(criancas),status_pipeline=pipeline,status_operacional=status,
                    valor_locacao=float(loc),valor_adultos=float(vad),valor_criancas=float(vcr),valor_servicos=float(serv),
                    desconto=float(desc),valor_total=float(total),forma_pagamento=forma,responsavel_comercial=resp_com,
                    responsavel_interno=resp_int,observacoes=obs)
    with tab1:
        with st.form("new_event"):
            d=evento_form()
            if st.form_submit_button("Salvar evento"):
                if not d or not d["titulo"].strip():
                    st.error("Informe o nome.")
                elif conflito(d["data_evento"],d["espaco_id"]):
                    st.error("Já existe reserva ativa para data/espaço.")
                else:
                    x("""INSERT INTO eventos(codigo,titulo,cliente_id,tipo_evento_id,espaco_id,data_evento,hora_inicio,hora_fim,adultos,criancas,status_pipeline,status_operacional,valor_locacao,valor_adultos,valor_criancas,valor_servicos,desconto,valor_total,forma_pagamento,responsavel_comercial,responsavel_interno,observacoes)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (f"EVT-{int(datetime.now().timestamp())}",d["titulo"],d["cliente_id"],d["tipo_evento_id"],d["espaco_id"],d["data_evento"],d["hora_inicio"],d["hora_fim"],d["adultos"],d["criancas"],d["status_pipeline"],d["status_operacional"],d["valor_locacao"],d["valor_adultos"],d["valor_criancas"],d["valor_servicos"],d["desconto"],d["valor_total"],d["forma_pagamento"],d["responsavel_comercial"],d["responsavel_interno"],d["observacoes"]))
                    st.success("Evento salvo.")
    with tab2:
        df=eventos_df()
        if df.empty:
            st.info("Nenhum evento.")
        else:
            op={f"{r['codigo']} | {r['titulo']} | {r['cliente']}":int(r["id"]) for _,r in df.iterrows()}
            eid=op[st.selectbox("Evento",list(op.keys()))]
            r=evento_row(eid)
            with st.form("edit_event"):
                d=evento_form(r)
                a,b=st.columns(2)
                if a.form_submit_button("Salvar alterações"):
                    if conflito(d["data_evento"],d["espaco_id"],eid):
                        st.error("Conflito de data/espaço.")
                    else:
                        x("""UPDATE eventos SET titulo=?,cliente_id=?,tipo_evento_id=?,espaco_id=?,data_evento=?,hora_inicio=?,hora_fim=?,adultos=?,criancas=?,status_pipeline=?,status_operacional=?,valor_locacao=?,valor_adultos=?,valor_criancas=?,valor_servicos=?,desconto=?,valor_total=?,forma_pagamento=?,responsavel_comercial=?,responsavel_interno=?,observacoes=? WHERE id=?""",
                          (d["titulo"],d["cliente_id"],d["tipo_evento_id"],d["espaco_id"],d["data_evento"],d["hora_inicio"],d["hora_fim"],d["adultos"],d["criancas"],d["status_pipeline"],d["status_operacional"],d["valor_locacao"],d["valor_adultos"],d["valor_criancas"],d["valor_servicos"],d["desconto"],d["valor_total"],d["forma_pagamento"],d["responsavel_comercial"],d["responsavel_interno"],d["observacoes"],eid))
                        st.success("Evento atualizado.")
                if b.form_submit_button("Excluir evento"):
                    x("DELETE FROM pagamentos WHERE evento_id=?",(eid,))
                    x("DELETE FROM despesas WHERE evento_id=?",(eid,))
                    x("DELETE FROM eventos WHERE id=?",(eid,))
                    st.success("Evento excluído.")
            view=df.copy()
            for col in ["valor_total","total_pago","saldo_evento"]:
                view[col]=view[col].apply(moeda)
            st.dataframe(view,use_container_width=True,hide_index=True)

elif menu == "Financeiro":
    tab1,tab2,tab3=st.tabs(["Resumo financeiro","Pagamentos de eventos","Despesas fixas e gerais"])
    with tab1:
        receb=q("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE status='Pago'")["total"].iloc[0]
        desp_p=q("SELECT COALESCE(SUM(valor),0) total FROM despesas WHERE status='Paga'")["total"].iloc[0]
        desp_a=q("SELECT COALESCE(SUM(valor),0) total FROM despesas WHERE status<>'Paga'")["total"].iloc[0]
        fixa_a=q("SELECT COALESCE(SUM(valor),0) total FROM despesas WHERE tipo_despesa='Fixa' AND status<>'Paga'")["total"].iloc[0]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Recebido",moeda(receb)); c2.metric("Despesas pagas",moeda(desp_p)); c3.metric("Despesas abertas",moeda(desp_a)); c4.metric("Fixas abertas",moeda(fixa_a))
        df=q("SELECT id,tipo_despesa,fornecedor,descricao,categoria,valor,vencimento,status,recorrente FROM despesas ORDER BY vencimento,id")
        if df.empty:
            st.info("Nenhuma despesa lançada.")
        else:
            df["valor"]=df["valor"].apply(moeda)
            st.dataframe(df,use_container_width=True,hide_index=True)
    with tab2:
        ev=eventos_df()
        if ev.empty:
            st.info("Nenhum evento cadastrado. As despesas fixas podem ser lançadas na próxima aba mesmo assim.")
        else:
            op={f"{r['codigo']} | {r['titulo']} | {r['cliente']}":int(r["id"]) for _,r in ev.iterrows()}
            eid=op[st.selectbox("Evento",list(op.keys()))]
            total=float(evento_row(eid)["valor_total"] or 0)
            pago=q("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE evento_id=? AND status='Pago'",(eid,))["total"].iloc[0]
            c1,c2,c3=st.columns(3); c1.metric("Contrato",moeda(total)); c2.metric("Pago",moeda(pago)); c3.metric("Saldo",moeda(total-float(pago or 0)))
            with st.form("new_pay",clear_on_submit=True):
                p1,p2,p3=st.columns(3)
                desc=p1.text_input("Descrição",value="Pix / Sinal")
                valor=p2.number_input("Valor",min_value=0.0,step=50.0)
                venc=p3.date_input("Vencimento",value=date.today())
                p4,p5,p6=st.columns(3)
                data_pag=p4.date_input("Data do pagamento",value=date.today())
                status=p5.selectbox("Status",["Pago","Em aberto"])
                forma=p6.selectbox("Forma",["Pix","Boleto","Cartão","Transferência","Dinheiro","Outro"])
                obs=st.text_input("Observações")
                if st.form_submit_button("Salvar pagamento"):
                    x("INSERT INTO pagamentos(evento_id,descricao,valor,vencimento,data_pagamento,status,forma_pagamento,observacoes) VALUES(?,?,?,?,?,?,?,?)",(eid,desc,float(valor),str(venc),str(data_pag) if status=="Pago" else None,status,forma,obs))
                    st.success("Pagamento salvo.")
            pags=q("SELECT * FROM pagamentos WHERE evento_id=? ORDER BY vencimento,id",(eid,))
            if not pags.empty:
                opg={f"{r['id']} | {r['descricao']} | {moeda(r['valor'])} | {r['status']}":int(r["id"]) for _,r in pags.iterrows()}
                pid=opg[st.selectbox("Editar / excluir pagamento",list(opg.keys()))]
                r=q("SELECT * FROM pagamentos WHERE id=?",(pid,)).iloc[0]
                with st.form("edit_pay"):
                    p1,p2,p3=st.columns(3)
                    desc=p1.text_input("Descrição",r["descricao"] or "")
                    valor=p2.number_input("Valor",min_value=0.0,step=50.0,value=float(r["valor"] or 0))
                    venc=p3.date_input("Vencimento",value=data_safe(r["vencimento"]))
                    p4,p5,p6=st.columns(3)
                    data_pag=p4.date_input("Data do pagamento",value=data_safe(r["data_pagamento"]))
                    status=p5.selectbox("Status",["Pago","Em aberto"],index=0 if r["status"]=="Pago" else 1)
                    forma=p6.selectbox("Forma",["Pix","Boleto","Cartão","Transferência","Dinheiro","Outro"])
                    obs=st.text_input("Observações",r["observacoes"] or "")
                    a,b=st.columns(2)
                    if a.form_submit_button("Salvar alteração"):
                        x("UPDATE pagamentos SET descricao=?,valor=?,vencimento=?,data_pagamento=?,status=?,forma_pagamento=?,observacoes=? WHERE id=?",(desc,float(valor),str(venc),str(data_pag) if status=="Pago" else None,status,forma,obs,pid))
                        st.success("Pagamento atualizado.")
                    if b.form_submit_button("Excluir pagamento"):
                        x("DELETE FROM pagamentos WHERE id=?",(pid,))
                        st.success("Pagamento excluído.")
                view=pags.copy(); view["valor"]=view["valor"].apply(moeda); st.dataframe(view,use_container_width=True,hide_index=True)
    with tab3:
        st.markdown('<div class="card">Lance aqui despesas fixas mesmo sem eventos: aluguel, energia, água, folha, internet, manutenção, marketing, contador etc.</div>',unsafe_allow_html=True)
        with st.form("new_exp",clear_on_submit=True):
            d1,d2,d3=st.columns(3)
            tipo=d1.selectbox("Tipo",["Fixa","Geral","Evento"])
            fornecedor=d2.text_input("Fornecedor")
            categoria=d3.selectbox("Categoria",["Aluguel","Energia","Água","Internet","Folha","Manutenção","Marketing","Impostos","Fornecedor","Outros"])
            d4,d5,d6=st.columns(3)
            descricao=d4.text_input("Descrição")
            valor=d5.number_input("Valor",min_value=0.0,step=100.0)
            venc=d6.date_input("Vencimento",value=date.today())
            d7,d8,d9=st.columns(3)
            data_pag=d7.date_input("Data pagamento",value=date.today())
            status=d8.selectbox("Status",["Pendente","Paga"])
            recorrente=d9.selectbox("Recorrente?",["Não","Sim"])
            obs=st.text_area("Observações")
            if st.form_submit_button("Salvar despesa"):
                x("INSERT INTO despesas(evento_id,tipo_despesa,fornecedor,descricao,categoria,valor,vencimento,data_pagamento,status,recorrente,observacoes) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(None,tipo,fornecedor,descricao,categoria,float(valor),str(venc),str(data_pag) if status=="Paga" else None,status,recorrente,obs))
                st.success("Despesa salva.")
        desp=q("SELECT * FROM despesas WHERE evento_id IS NULL OR tipo_despesa IN ('Fixa','Geral') ORDER BY vencimento,id")
        if not desp.empty:
            opd={f"{r['id']} | {r['tipo_despesa']} | {r['descricao']} | {moeda(r['valor'])} | {r['status']}":int(r["id"]) for _,r in desp.iterrows()}
            did=opd[st.selectbox("Editar / excluir despesa",list(opd.keys()))]
            r=q("SELECT * FROM despesas WHERE id=?",(did,)).iloc[0]
            with st.form("edit_exp"):
                d1,d2,d3=st.columns(3)
                tipo=d1.selectbox("Tipo",["Fixa","Geral","Evento"], index=["Fixa","Geral","Evento"].index(r["tipo_despesa"]) if r["tipo_despesa"] in ["Fixa","Geral","Evento"] else 0)
                fornecedor=d2.text_input("Fornecedor",r["fornecedor"] or "")
                categoria=d3.text_input("Categoria",r["categoria"] or "")
                d4,d5,d6=st.columns(3)
                descricao=d4.text_input("Descrição",r["descricao"] or "")
                valor=d5.number_input("Valor",min_value=0.0,step=100.0,value=float(r["valor"] or 0))
                venc=d6.date_input("Vencimento",value=data_safe(r["vencimento"]))
                d7,d8,d9=st.columns(3)
                data_pag=d7.date_input("Data pagamento",value=data_safe(r["data_pagamento"]))
                status=d8.selectbox("Status",["Pendente","Paga"],index=1 if r["status"]=="Paga" else 0)
                recorrente=d9.selectbox("Recorrente?",["Não","Sim"],index=1 if r["recorrente"]=="Sim" else 0)
                obs=st.text_area("Observações",r["observacoes"] or "")
                a,b=st.columns(2)
                if a.form_submit_button("Salvar alteração"):
                    x("UPDATE despesas SET tipo_despesa=?,fornecedor=?,descricao=?,categoria=?,valor=?,vencimento=?,data_pagamento=?,status=?,recorrente=?,observacoes=? WHERE id=?",(tipo,fornecedor,descricao,categoria,float(valor),str(venc),str(data_pag) if status=="Paga" else None,status,recorrente,obs,did))
                    st.success("Despesa atualizada.")
                if b.form_submit_button("Excluir despesa"):
                    x("DELETE FROM despesas WHERE id=?",(did,))
                    st.success("Despesa excluída.")
            view=desp.copy(); view["valor"]=view["valor"].apply(moeda); st.dataframe(view,use_container_width=True,hide_index=True)

elif menu == "Fluxo de Caixa":
    st.subheader("Fluxo de Caixa")
    c1,c2,c3=st.columns(3)
    ini=c1.date_input("Data inicial", value=date.today().replace(day=1))
    fim=c2.date_input("Data final", value=date.today()+timedelta(days=30))
    saldo_inicial=c3.number_input("Saldo inicial", value=0.0, step=100.0)
    fluxo=fluxo_df(ini,fim,saldo_inicial)
    menor=fluxo["saldo_acumulado"].min() if not fluxo.empty else 0
    a,b,c=st.columns(3)
    a.metric("Entradas", moeda(fluxo["entradas"].sum()))
    b.metric("Saídas", moeda(fluxo["saidas"].sum()))
    c.metric("Menor saldo projetado", moeda(menor))
    if menor < 0:
        st.markdown(f"<div class='alert'>⚠️ Alerta: caixa negativo no período. Menor saldo: <b>{moeda(menor)}</b></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='ok'>✅ Caixa projetado positivo no período.</div>", unsafe_allow_html=True)
    graf=fluxo.copy()
    graf["data"]=pd.to_datetime(graf["data"])
    st.line_chart(graf.set_index("data")[["entradas","saidas","saldo_acumulado"]])
    view=fluxo.copy()
    for col in ["entradas","saidas","saldo_dia","saldo_acumulado"]:
        view[col]=view[col].apply(moeda)
    st.dataframe(view,use_container_width=True,hide_index=True)

elif menu == "Agenda":
    ev=eventos_df()
    if ev.empty:
        st.info("Nenhum evento.")
    else:
        c1,c2,c3=st.columns(3)
        ini=c1.date_input("Data inicial",value=date.today().replace(day=1))
        fim=c2.date_input("Data final",value=date.today()+timedelta(days=90))
        filtro=c3.selectbox("Espaço",["Todos"]+espacos_df()["nome"].tolist())
        ev["data_dt"]=pd.to_datetime(ev["data_evento"],errors="coerce").dt.date
        ev=ev[(ev["data_dt"]>=ini)&(ev["data_dt"]<=fim)]
        if filtro!="Todos":
            ev=ev[ev["espaco"]==filtro]
        if ev.empty:
            st.info("Nenhum evento no período.")
        else:
            for dt,grp in ev.groupby("data_evento"):
                st.markdown(f"### {pd.to_datetime(dt).strftime('%d/%m/%Y')}")
                st.dataframe(grp,use_container_width=True,hide_index=True)

elif menu == "Backup Excel":
    st.subheader("Backup em Excel")
    st.markdown('<div class="card">Exporta eventos, pagamentos e despesas fixas/gerais.</div>',unsafe_allow_html=True)
    st.download_button("Baixar backup em Excel", data=backup_excel(), file_name=f"backup_quinta_do_conde_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif menu == "Cadastros":
    st.markdown("<div class='card'>A base começa limpa. Cadastre manualmente os espaços e tipos de evento, ou carregue uma sugestão inicial se fizer sentido.</div>", unsafe_allow_html=True)
    if st.button("Carregar cadastros sugeridos da Quinta do Conde"):
        carregar_cadastros_sugeridos()
        st.success("Cadastros sugeridos carregados com sucesso.")
    tab1,tab2=st.tabs(["Espaços","Tipos de evento"])
    with tab1:
        with st.form("espaco_form",clear_on_submit=True):
            nome=st.text_input("Nome do espaço")
            cap=st.number_input("Capacidade",min_value=0,step=10)
            desc=st.text_area("Descrição")
            if st.form_submit_button("Salvar") and nome.strip():
                try:
                    x("INSERT INTO espacos(nome,capacidade,descricao,ativo) VALUES(?,?,?,1)",(nome,int(cap),desc))
                    st.success("Espaço cadastrado.")
                except Exception:
                    st.error("Já existe esse espaço.")
        st.dataframe(q("SELECT * FROM espacos ORDER BY nome"),use_container_width=True,hide_index=True)
    with tab2:
        with st.form("tipo_form",clear_on_submit=True):
            nome=st.text_input("Tipo de evento")
            cap=st.number_input("Capacidade sugerida",min_value=0,step=10)
            regras=st.text_area("Regras")
            if st.form_submit_button("Salvar") and nome.strip():
                try:
                    x("INSERT INTO tipos_evento(nome,capacidade_sugerida,regras,ativo) VALUES(?,?,?,1)",(nome,int(cap),regras))
                    st.success("Tipo cadastrado.")
                except Exception:
                    st.error("Já existe esse tipo.")
        st.dataframe(q("SELECT * FROM tipos_evento ORDER BY nome"),use_container_width=True,hide_index=True)

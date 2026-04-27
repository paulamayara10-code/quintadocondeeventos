import sqlite3
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

DB_FILE = "eventos_fazenda_v7.db"


def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def run_query(query, params=None):
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params or ())
    conn.close()
    return df


def execute(query, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def add_col(table, col, definition):
    conn = get_conn()
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
    conn.commit()
    conn.close()


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, telefone TEXT, email TEXT,
            documento TEXT, tipo_cliente TEXT, empresa TEXT, origem_lead TEXT, observacoes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS espacos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, capacidade INTEGER DEFAULT 0,
            descricao TEXT, ativo INTEGER DEFAULT 1)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_evento (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE, capacidade_sugerida INTEGER DEFAULT 0,
            regras TEXT, ativo INTEGER DEFAULT 1)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT, titulo TEXT NOT NULL, cliente_id INTEGER,
            tipo_evento_id INTEGER, espaco_id INTEGER, data_evento TEXT NOT NULL, hora_inicio TEXT, hora_fim TEXT,
            quantidade_convidados INTEGER DEFAULT 0, adultos INTEGER DEFAULT 0, criancas INTEGER DEFAULT 0,
            status_pipeline TEXT, status_operacional TEXT, valor_locacao REAL DEFAULT 0, valor_adultos REAL DEFAULT 0,
            valor_criancas REAL DEFAULT 0, valor_servicos REAL DEFAULT 0, desconto REAL DEFAULT 0,
            valor_total REAL DEFAULT 0, forma_pagamento TEXT, responsavel_comercial TEXT, responsavel_interno TEXT,
            observacoes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER NOT NULL, descricao TEXT, valor REAL NOT NULL,
            vencimento TEXT, data_pagamento TEXT, status TEXT DEFAULT 'Em aberto', forma_pagamento TEXT, observacoes TEXT)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS servicos_adicionais (
            id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER NOT NULL, servico TEXT NOT NULL,
            fornecedor TEXT, valor REAL DEFAULT 0, observacoes TEXT)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id INTEGER NOT NULL, fornecedor TEXT, descricao TEXT,
            valor REAL NOT NULL, vencimento TEXT, data_pagamento TEXT, status TEXT DEFAULT 'Pendente', observacoes TEXT)
    """)
    conn.commit(); conn.close()

    for col, definition in [("adultos","INTEGER DEFAULT 0"),("criancas","INTEGER DEFAULT 0"),("valor_adultos","REAL DEFAULT 0"),("valor_criancas","REAL DEFAULT 0")]:
        add_col("eventos", col, definition)

    if run_query("SELECT COUNT(*) qtd FROM espacos")["qtd"].iloc[0] == 0:
        for nome, cap, desc in [
            ("Salão Principal",250,"Espaço para eventos sociais e corporativos"),
            ("Área Externa",400,"Jardins e área aberta"),
            ("Piscinas e Toboáguas",180,"Day use e eventos com lazer"),
            ("Espaço Corporativo",150,"Treinamentos e workshops"),
            ("Churrasco e Confraternizações",120,"Eventos menores")]:
            execute("INSERT INTO espacos (nome, capacidade, descricao, ativo) VALUES (?,?,?,1)", (nome,cap,desc))
    if run_query("SELECT COUNT(*) qtd FROM tipos_evento")["qtd"].iloc[0] == 0:
        for nome, cap, regras in [
            ("Casamento",200,"Evento social premium"),("Aniversário",100,"Pacote social"),
            ("Corporativo",120,"Operação corporativa"),("Formatura",250,"Evento social ampliado"),
            ("Ensaio Fotográfico",15,"Pacote enxuto"),("15 Anos",150,"Social premium"),
            ("Workshop",80,"Formato diurno"),("Lançamento de Produto",120,"Evento corporativo"),("Day Use",80,"Lazer")]:
            execute("INSERT INTO tipos_evento (nome, capacidade_sugerida, regras, ativo) VALUES (?,?,?,1)", (nome,cap,regras))


def fmt(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except Exception:
        return "R$ 0,00"


def get_clientes(): return run_query("SELECT id,nome FROM clientes ORDER BY nome")
def get_espacos(): return run_query("SELECT id,nome,capacidade FROM espacos WHERE ativo=1 ORDER BY nome")
def get_tipos(): return run_query("SELECT id,nome,capacidade_sugerida FROM tipos_evento WHERE ativo=1 ORDER BY nome")


def eventos_full():
    return run_query("""
        SELECT e.id, COALESCE(e.codigo,'EVT-'||e.id) codigo, e.titulo, c.nome cliente, te.nome tipo_evento,
               es.nome espaco, e.data_evento, e.hora_inicio, e.hora_fim, e.adultos, e.criancas,
               COALESCE(e.adultos,0)+COALESCE(e.criancas,0) convidados_total,
               e.status_pipeline, e.status_operacional, e.valor_total,
               COALESCE((SELECT SUM(p.valor) FROM pagamentos p WHERE p.evento_id=e.id AND p.status='Pago'),0) total_pago,
               e.forma_pagamento, e.responsavel_comercial, e.responsavel_interno
        FROM eventos e
        LEFT JOIN clientes c ON c.id=e.cliente_id
        LEFT JOIN tipos_evento te ON te.id=e.tipo_evento_id
        LEFT JOIN espacos es ON es.id=e.espaco_id
        ORDER BY e.data_evento, e.hora_inicio
    """)


def evento_detalhe(eid):
    df = run_query("""
        SELECT e.*, c.nome cliente_nome, c.telefone cliente_telefone, c.email cliente_email,
               te.nome tipo_evento_nome, es.nome espaco_nome
        FROM eventos e
        LEFT JOIN clientes c ON c.id=e.cliente_id
        LEFT JOIN tipos_evento te ON te.id=e.tipo_evento_id
        LEFT JOIN espacos es ON es.id=e.espaco_id
        WHERE e.id=?
    """, (eid,))
    return df.iloc[0].to_dict() if not df.empty else None


def conflito(data_evento, espaco_id, eid=None):
    sql = "SELECT id FROM eventos WHERE data_evento=? AND espaco_id=? AND status_operacional <> 'Cancelado'"
    params = [data_evento, espaco_id]
    if eid:
        sql += " AND id<>?"; params.append(eid)
    return not run_query(sql, tuple(params)).empty


def resumo_financeiro(eid):
    ev = evento_detalhe(eid); total = float(ev.get("valor_total") or 0) if ev else 0
    pago = float(run_query("SELECT COALESCE(SUM(valor),0) total FROM pagamentos WHERE evento_id=? AND status='Pago'", (eid,))["total"].iloc[0] or 0)
    desp = float(run_query("SELECT COALESCE(SUM(valor),0) total FROM despesas WHERE evento_id=? AND status='Paga'", (eid,))["total"].iloc[0] or 0)
    lucro = pago - desp
    return total, pago, total-pago, desp, lucro, (lucro/pago*100 if pago else 0)


def delete_evento(eid):
    for t in ["pagamentos","servicos_adicionais","despesas"]:
        execute(f"DELETE FROM {t} WHERE evento_id=?", (eid,))
    execute("DELETE FROM eventos WHERE id=?", (eid,))


def exportar_excel():
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        pd.DataFrame({"ORIENTACAO":["Backup padrão do sistema Quinta do Conde.","Não altere nomes de abas e colunas."]}).to_excel(w, "INSTRUCOES", index=False)
        run_query("SELECT * FROM clientes ORDER BY id").to_excel(w, "CLIENTES", index=False)
        run_query("SELECT * FROM eventos ORDER BY id").to_excel(w, "EVENTOS", index=False)
        run_query("SELECT * FROM pagamentos ORDER BY id").to_excel(w, "PAGAMENTOS", index=False)
        run_query("SELECT * FROM servicos_adicionais ORDER BY id").to_excel(w, "SERVICOS", index=False)
        run_query("SELECT * FROM despesas ORDER BY id").to_excel(w, "DESPESAS", index=False)
        run_query("SELECT * FROM espacos ORDER BY id").to_excel(w, "ESPACOS", index=False)
        run_query("SELECT * FROM tipos_evento ORDER BY id").to_excel(w, "TIPOS_EVENTO", index=False)
    out.seek(0); return out.getvalue()


def gerar_pdf(eid):
    ev = evento_detalhe(eid)
    if not ev: return None
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4); w,h=A4; m=1.6*cm; uw=w-2*m
    c.setFillColor(colors.HexColor("#F8F4EE")); c.rect(0,0,w,h,fill=1,stroke=0)
    c.setFillColor(colors.HexColor("#5A402C")); c.roundRect(m,h-4.1*cm,uw,2.5*cm,16,fill=1,stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold",22); c.drawString(m+16,h-2.2*cm,"Quinta do Conde")
    c.setFont("Helvetica",11); c.drawString(m+16,h-2.9*cm,"Proposta comercial de evento")
    c.setFillColor(colors.HexColor("#3F2F20")); c.setFont("Helvetica-Bold",16); c.drawString(m,h-5*cm,str(ev.get("titulo","")))
    c.setFont("Helvetica",10); c.drawString(m,h-5.6*cm,f"Código {ev.get('codigo','')} | Data {pd.to_datetime(ev.get('data_evento')).strftime('%d/%m/%Y')}")
    y=h-7*cm
    linhas=[
        f"Cliente: {ev.get('cliente_nome') or '-'}", f"Telefone: {ev.get('cliente_telefone') or '-'}", f"Tipo: {ev.get('tipo_evento_nome') or '-'}",
        f"Espaço: {ev.get('espaco_nome') or '-'}", f"Adultos: {int(ev.get('adultos') or 0)} | Crianças: {int(ev.get('criancas') or 0)}",
        f"Locação: {fmt(ev.get('valor_locacao') or 0)}", f"Adultos: {fmt(ev.get('valor_adultos') or 0)}", f"Crianças: {fmt(ev.get('valor_criancas') or 0)}",
        f"Serviços: {fmt(ev.get('valor_servicos') or 0)}", f"Desconto: {fmt(ev.get('desconto') or 0)}", f"TOTAL: {fmt(ev.get('valor_total') or 0)}"
    ]
    for line in linhas:
        c.setFillColor(colors.black); c.setFont("Helvetica",11); c.drawString(m,y,line); y-=0.65*cm
    c.setFillColor(colors.HexColor("#7A5A43")); c.setFont("Helvetica",9); c.drawString(m,1.4*cm,"Quinta do Conde - Proposta gerada pelo sistema")
    c.save(); buf.seek(0); return buf.getvalue()


st.set_page_config(page_title="Quinta do Conde | Eventos", page_icon="🏡", layout="wide")
init_db()
st.markdown('''<style>.stApp{background:linear-gradient(180deg,#FAF7F2 0%,#F3ECE3 70%,#EDE4D8 100%)}h1,h2,h3{color:#3F2F20}.qc-banner{background:linear-gradient(120deg,#5A402C,#7A5A43,#A38666);color:white;padding:20px 24px;border-radius:24px;margin-bottom:18px;box-shadow:0 8px 24px rgba(63,47,32,.15)}[data-testid="stMetric"]{background:#fff;border:1px solid #DCCFBE;border-radius:18px;padding:10px}</style>''', unsafe_allow_html=True)
st.markdown('<div class="qc-banner"><h1 style="margin:0">🏡 Quinta do Conde</h1><div>Sistema Comercial + Gestão de Eventos</div><div style="opacity:.9">Versão com edição, exclusão, pagamentos múltiplos e adultos/crianças.</div></div>', unsafe_allow_html=True)

menu = st.sidebar.radio("Menu", ["Dashboard", "Clientes", "Espaços e Tipos", "Eventos", "Financeiro", "Agenda", "Backup Excel", "Relatórios"])

if menu == "Dashboard":
    df = eventos_full(); hoje=date.today(); ini=hoje.replace(day=1); fim=(ini.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    mes = pd.DataFrame()
    if not df.empty:
        df["data_dt"] = pd.to_datetime(df["data_evento"], errors="coerce").dt.date
        mes = df[(df["data_dt"]>=ini)&(df["data_dt"]<=fim)]
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Eventos no mês", len(mes)); c2.metric("Faturamento previsto", fmt(mes["valor_total"].sum() if not mes.empty else 0)); c3.metric("Recebido", fmt(mes["total_pago"].sum() if not mes.empty else 0)); c4.metric("Convidados", int(mes["convidados_total"].sum() if not mes.empty else 0))
    st.dataframe(df, use_container_width=True, hide_index=True)

elif menu == "Clientes":
    tab1,tab2=st.tabs(["Cadastrar", "Editar / Excluir"])
    with tab1:
        with st.form("cliente_novo", clear_on_submit=True):
            c1,c2,c3=st.columns(3); nome=c1.text_input("Nome*"); tel=c2.text_input("Telefone/WhatsApp"); email=c3.text_input("E-mail")
            c4,c5,c6=st.columns(3); doc=c4.text_input("CPF/CNPJ"); tipo=c5.selectbox("Tipo",["Pessoa Física","Pessoa Jurídica"]); emp=c6.text_input("Empresa")
            origem=st.selectbox("Origem",["Site","Instagram","Indicação","Google","WhatsApp","Outro"]); obs=st.text_area("Observações")
            if st.form_submit_button("Salvar"):
                if nome.strip(): execute("INSERT INTO clientes (nome,telefone,email,documento,tipo_cliente,empresa,origem_lead,observacoes) VALUES (?,?,?,?,?,?,?,?)",(nome,tel,email,doc,tipo,emp,origem,obs)); st.success("Cliente salvo.")
                else: st.error("Informe o nome.")
    with tab2:
        cli=run_query("SELECT * FROM clientes ORDER BY nome")
        if cli.empty: st.info("Nenhum cliente.")
        else:
            op={f"{r['id']} - {r['nome']}":int(r['id']) for _,r in cli.iterrows()}; cid=op[st.selectbox("Cliente",list(op.keys()))]; a=run_query("SELECT * FROM clientes WHERE id=?",(cid,)).iloc[0]
            with st.form("cliente_edit"):
                nome=st.text_input("Nome",a["nome"]); tel=st.text_input("Telefone",a["telefone"] or ""); email=st.text_input("E-mail",a["email"] or ""); obs=st.text_area("Observações",a["observacoes"] or "")
                c1,c2=st.columns(2)
                if c1.form_submit_button("Salvar alterações"):
                    execute("UPDATE clientes SET nome=?, telefone=?, email=?, observacoes=? WHERE id=?",(nome,tel,email,obs,cid)); st.success("Atualizado.")
                if c2.form_submit_button("Excluir"):
                    vinc=run_query("SELECT COUNT(*) qtd FROM eventos WHERE cliente_id=?",(cid,))["qtd"].iloc[0]
                    if vinc: st.error("Cliente tem eventos vinculados.")
                    else: execute("DELETE FROM clientes WHERE id=?",(cid,)); st.success("Excluído.")
        st.dataframe(cli, use_container_width=True, hide_index=True)

elif menu == "Espaços e Tipos":
    tab1,tab2=st.tabs(["Espaços","Tipos de evento"])
    with tab1:
        with st.form("esp"):
            nome=st.text_input("Espaço"); cap=st.number_input("Capacidade",0,step=10); desc=st.text_area("Descrição")
            if st.form_submit_button("Salvar") and nome.strip():
                try: execute("INSERT INTO espacos (nome,capacidade,descricao,ativo) VALUES (?,?,?,1)",(nome,int(cap),desc)); st.success("Salvo.")
                except Exception: st.error("Já existe.")
        st.dataframe(run_query("SELECT id,nome,capacidade,descricao FROM espacos WHERE ativo=1 ORDER BY nome"),use_container_width=True,hide_index=True)
    with tab2:
        with st.form("tipo"):
            nome=st.text_input("Tipo de evento"); cap=st.number_input("Capacidade sugerida",0,step=10); regras=st.text_area("Regras")
            if st.form_submit_button("Salvar") and nome.strip():
                try: execute("INSERT INTO tipos_evento (nome,capacidade_sugerida,regras,ativo) VALUES (?,?,?,1)",(nome,int(cap),regras)); st.success("Salvo.")
                except Exception: st.error("Já existe.")
        st.dataframe(run_query("SELECT id,nome,capacidade_sugerida,regras FROM tipos_evento WHERE ativo=1 ORDER BY nome"),use_container_width=True,hide_index=True)

elif menu == "Eventos":
    def form_evento(a=None):
        clientes=get_clientes(); espacos=get_espacos(); tipos=get_tipos()
        if clientes.empty: st.warning("Cadastre cliente primeiro."); return None
        mc=dict(zip(clientes["nome"],clientes["id"])); me={f"{r['nome']} | cap. {int(r['capacidade'])}":int(r['id']) for _,r in espacos.iterrows()}; mt={r['nome']:int(r['id']) for _,r in tipos.iterrows()}
        titulo=st.text_input("Nome do evento*", a["titulo"] if a is not None else "")
        c1,c2,c3=st.columns(3); cliente=c1.selectbox("Cliente",list(mc.keys())); tipo=c2.selectbox("Tipo",list(mt.keys())); espaco=c3.selectbox("Espaço",list(me.keys()))
        c4,c5,c6=st.columns(3); data=c4.date_input("Data", pd.to_datetime(a["data_evento"]).date() if a is not None else date.today()+timedelta(days=30)); hi=c5.time_input("Início", datetime.strptime(a["hora_inicio"] if a is not None and a["hora_inicio"] else "10:00","%H:%M").time()); hf=c6.time_input("Fim", datetime.strptime(a["hora_fim"] if a is not None and a["hora_fim"] else "22:00","%H:%M").time())
        c7,c8=st.columns(2); adultos=c7.number_input("Adultos",0,step=1,value=int(a["adultos"] or 0) if a is not None else 0); criancas=c8.number_input("Crianças",0,step=1,value=int(a["criancas"] or 0) if a is not None else 0)
        c9,c10=st.columns(2); pipeline=c9.selectbox("Pipeline",["Lead","Visita agendada","Proposta enviada","Negociação","Fechado","Perdido"]); status=c10.selectbox("Status operacional",["Orçamento","Pré-reserva","Confirmado","Realizado","Cancelado"])
        st.markdown("#### Valores")
        c11,c12,c13,c14,c15=st.columns(5); vl=c11.number_input("Locação",0.0,step=100.0,value=float(a["valor_locacao"] or 0) if a is not None else 0.0); va=c12.number_input("Valor adultos",0.0,step=100.0,value=float(a["valor_adultos"] or 0) if a is not None else 0.0); vc=c13.number_input("Valor crianças",0.0,step=100.0,value=float(a["valor_criancas"] or 0) if a is not None else 0.0); vs=c14.number_input("Serviços",0.0,step=100.0,value=float(a["valor_servicos"] or 0) if a is not None else 0.0); desc=c15.number_input("Desconto",0.0,step=100.0,value=float(a["desconto"] or 0) if a is not None else 0.0)
        total=max(vl+va+vc+vs-desc,0); st.info(f"Total: {fmt(total)}")
        c16,c17,c18=st.columns(3); forma=c16.selectbox("Forma principal",["Pix","Boleto","Cartão","Transferência","Dinheiro","Outro"]); rc=c17.text_input("Resp. comercial", a["responsavel_comercial"] if a is not None and a["responsavel_comercial"] else ""); ri=c18.text_input("Resp. interno", a["responsavel_interno"] if a is not None and a["responsavel_interno"] else "")
        obs=st.text_area("Observações", a["observacoes"] if a is not None and a["observacoes"] else "")
        return dict(titulo=titulo,cliente_id=int(mc[cliente]),tipo_evento_id=int(mt[tipo]),espaco_id=int(me[espaco]),data_evento=str(data),hora_inicio=hi.strftime("%H:%M"),hora_fim=hf.strftime("%H:%M"),adultos=int(adultos),criancas=int(criancas),quantidade_convidados=int(adultos+criancas),status_pipeline=pipeline,status_operacional=status,valor_locacao=float(vl),valor_adultos=float(va),valor_criancas=float(vc),valor_servicos=float(vs),desconto=float(desc),valor_total=float(total),forma_pagamento=forma,responsavel_comercial=rc,responsavel_interno=ri,observacoes=obs)
    tab1,tab2=st.tabs(["Cadastrar", "Editar / Excluir"])
    with tab1:
        with st.form("novo_evento"):
            d=form_evento()
            if st.form_submit_button("Salvar evento"):
                if not d or not d["titulo"].strip(): st.error("Informe o nome.")
                elif conflito(d["data_evento"],d["espaco_id"]): st.error("Já existe reserva ativa nesta data/espaço.")
                else:
                    execute("""INSERT INTO eventos (codigo,titulo,cliente_id,tipo_evento_id,espaco_id,data_evento,hora_inicio,hora_fim,quantidade_convidados,adultos,criancas,status_pipeline,status_operacional,valor_locacao,valor_adultos,valor_criancas,valor_servicos,desconto,valor_total,forma_pagamento,responsavel_comercial,responsavel_interno,observacoes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (f"EVT-{int(datetime.now().timestamp())}",d["titulo"],d["cliente_id"],d["tipo_evento_id"],d["espaco_id"],d["data_evento"],d["hora_inicio"],d["hora_fim"],d["quantidade_convidados"],d["adultos"],d["criancas"],d["status_pipeline"],d["status_operacional"],d["valor_locacao"],d["valor_adultos"],d["valor_criancas"],d["valor_servicos"],d["desconto"],d["valor_total"],d["forma_pagamento"],d["responsavel_comercial"],d["responsavel_interno"],d["observacoes"])); st.success("Evento salvo.")
    with tab2:
        df=eventos_full()
        if df.empty: st.info("Nenhum evento.")
        else:
            op={f"{r['codigo']} | {r['titulo']} | {r['cliente']}":int(r['id']) for _,r in df.iterrows()}; eid=op[st.selectbox("Evento",list(op.keys()))]; a=evento_detalhe(eid)
            with st.form("edit_evento"):
                d=form_evento(a); c1,c2=st.columns(2)
                if c1.form_submit_button("Salvar alterações"):
                    if conflito(d["data_evento"],d["espaco_id"],eid): st.error("Conflito com outra reserva.")
                    else:
                        execute("""UPDATE eventos SET titulo=?,cliente_id=?,tipo_evento_id=?,espaco_id=?,data_evento=?,hora_inicio=?,hora_fim=?,quantidade_convidados=?,adultos=?,criancas=?,status_pipeline=?,status_operacional=?,valor_locacao=?,valor_adultos=?,valor_criancas=?,valor_servicos=?,desconto=?,valor_total=?,forma_pagamento=?,responsavel_comercial=?,responsavel_interno=?,observacoes=? WHERE id=?""", (d["titulo"],d["cliente_id"],d["tipo_evento_id"],d["espaco_id"],d["data_evento"],d["hora_inicio"],d["hora_fim"],d["quantidade_convidados"],d["adultos"],d["criancas"],d["status_pipeline"],d["status_operacional"],d["valor_locacao"],d["valor_adultos"],d["valor_criancas"],d["valor_servicos"],d["desconto"],d["valor_total"],d["forma_pagamento"],d["responsavel_comercial"],d["responsavel_interno"],d["observacoes"],eid)); st.success("Atualizado.")
                if c2.form_submit_button("Excluir evento"):
                    delete_evento(eid); st.success("Evento excluído.")
            pdf=gerar_pdf(eid); st.download_button("Baixar proposta PDF",pdf,file_name=f"proposta_{eid}.pdf",mime="application/pdf")
        st.dataframe(eventos_full(),use_container_width=True,hide_index=True)

elif menu == "Financeiro":
    df=eventos_full()
    if df.empty: st.warning("Cadastre eventos.")
    else:
        op={f"{r['codigo']} | {r['titulo']} | {r['cliente']}":int(r['id']) for _,r in df.iterrows()}; eid=op[st.selectbox("Evento",list(op.keys()))]
        total,pago,aberto,desp,lucro,margem=resumo_financeiro(eid); c1,c2,c3,c4,c5,c6=st.columns(6); c1.metric("Contrato",fmt(total)); c2.metric("Pago",fmt(pago)); c3.metric("Em aberto",fmt(aberto)); c4.metric("Despesas",fmt(desp)); c5.metric("Lucro",fmt(lucro)); c6.metric("Margem",f"{margem:.1f}%")
        tab1,tab2,tab3=st.tabs(["Pagamentos", "Serviços", "Despesas"])
        with tab1:
            with st.form("pag_novo", clear_on_submit=True):
                p1,p2,p3=st.columns(3); desc=p1.text_input("Descrição",value="Pix / Sinal"); valor=p2.number_input("Valor",0.0,step=50.0); venc=p3.date_input("Vencimento",date.today())
                p4,p5,p6=st.columns(3); data_pag=p4.date_input("Data do pagamento",date.today()); status=p5.selectbox("Status",["Pago","Em aberto"]); forma=p6.selectbox("Forma",["Pix","Boleto","Cartão","Transferência","Dinheiro","Outro"]); obs=st.text_input("Obs")
                if st.form_submit_button("Salvar pagamento"):
                    execute("INSERT INTO pagamentos (evento_id,descricao,valor,vencimento,data_pagamento,status,forma_pagamento,observacoes) VALUES (?,?,?,?,?,?,?,?)",(eid,desc,float(valor),str(venc),str(data_pag) if status=="Pago" else None,status,forma,obs)); st.success("Pagamento salvo.")
            pags=run_query("SELECT * FROM pagamentos WHERE evento_id=? ORDER BY vencimento,id",(eid,))
            if not pags.empty:
                opp={f"{r['id']} | {r['descricao']} | {fmt(r['valor'])} | {r['status']}":int(r['id']) for _,r in pags.iterrows()}; pid=opp[st.selectbox("Editar/excluir pagamento",list(opp.keys()))]; a=run_query("SELECT * FROM pagamentos WHERE id=?",(pid,)).iloc[0]
                with st.form("pag_edit"):
                    p1,p2,p3=st.columns(3); desc=p1.text_input("Descrição",a["descricao"] or ""); valor=p2.number_input("Valor",0.0,step=50.0,value=float(a["valor"] or 0)); venc=p3.date_input("Vencimento",pd.to_datetime(a["vencimento"]).date() if a["vencimento"] else date.today())
                    p4,p5,p6=st.columns(3); data_pag=p4.date_input("Data pagamento",pd.to_datetime(a["data_pagamento"]).date() if a["data_pagamento"] else date.today()); status=p5.selectbox("Status",["Pago","Em aberto"],index=0 if a["status"]=="Pago" else 1); forma=p6.selectbox("Forma",["Pix","Boleto","Cartão","Transferência","Dinheiro","Outro"]); obs=st.text_input("Obs",a["observacoes"] or "")
                    c1,c2=st.columns(2)
                    if c1.form_submit_button("Salvar alteração"):
                        execute("UPDATE pagamentos SET descricao=?,valor=?,vencimento=?,data_pagamento=?,status=?,forma_pagamento=?,observacoes=? WHERE id=?",(desc,float(valor),str(venc),str(data_pag) if status=="Pago" else None,status,forma,obs,pid)); st.success("Atualizado.")
                    if c2.form_submit_button("Excluir pagamento"):
                        execute("DELETE FROM pagamentos WHERE id=?",(pid,)); st.success("Excluído.")
                st.dataframe(pags,use_container_width=True,hide_index=True)
        with tab2:
            with st.form("serv"):
                s1,s2,s3=st.columns(3); serv=s1.text_input("Serviço"); forn=s2.text_input("Fornecedor"); valor=s3.number_input("Valor",0.0,step=100.0); obs=st.text_input("Obs")
                if st.form_submit_button("Salvar serviço") and serv.strip():
                    execute("INSERT INTO servicos_adicionais (evento_id,servico,fornecedor,valor,observacoes) VALUES (?,?,?,?,?)",(eid,serv,forn,float(valor),obs)); total_serv=run_query("SELECT COALESCE(SUM(valor),0) total FROM servicos_adicionais WHERE evento_id=?",(eid,))["total"].iloc[0]; execute("UPDATE eventos SET valor_servicos=?, valor_total=MAX(valor_locacao+valor_adultos+valor_criancas+?-desconto,0) WHERE id=?",(float(total_serv),float(total_serv),eid)); st.success("Serviço salvo.")
            st.dataframe(run_query("SELECT * FROM servicos_adicionais WHERE evento_id=?",(eid,)),use_container_width=True,hide_index=True)
        with tab3:
            with st.form("desp"):
                d1,d2,d3=st.columns(3); forn=d1.text_input("Fornecedor"); desc=d2.text_input("Descrição"); valor=d3.number_input("Valor",0.0,step=100.0); d4,d5,d6=st.columns(3); venc=d4.date_input("Vencimento",date.today()); data_pg=d5.date_input("Data pagamento",date.today()); status=d6.selectbox("Status",["Pendente","Paga"]); obs=st.text_input("Obs")
                if st.form_submit_button("Salvar despesa"):
                    execute("INSERT INTO despesas (evento_id,fornecedor,descricao,valor,vencimento,data_pagamento,status,observacoes) VALUES (?,?,?,?,?,?,?,?)",(eid,forn,desc,float(valor),str(venc),str(data_pg) if status=="Paga" else None,status,obs)); st.success("Despesa salva.")
            st.dataframe(run_query("SELECT * FROM despesas WHERE evento_id=?",(eid,)),use_container_width=True,hide_index=True)

elif menu == "Agenda":
    c1,c2,c3=st.columns(3); ini=c1.date_input("Data inicial",date.today().replace(day=1)); fim=c2.date_input("Data final",date.today()+timedelta(days=90)); filtro=c3.selectbox("Espaço",["Todos"]+get_espacos()["nome"].tolist())
    df=eventos_full()
    if not df.empty:
        df["data_dt"]=pd.to_datetime(df["data_evento"],errors="coerce").dt.date; df=df[(df["data_dt"]>=ini)&(df["data_dt"]<=fim)]
        if filtro!="Todos": df=df[df["espaco"]==filtro]
    st.dataframe(df,use_container_width=True,hide_index=True)

elif menu == "Backup Excel":
    st.download_button("Baixar backup em Excel", exportar_excel(), file_name=f"backup_quinta_do_conde_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

elif menu == "Relatórios":
    df=eventos_full();
    if not df.empty:
        v=df.copy(); v["valor_total"]=v["valor_total"].apply(fmt); v["total_pago"]=v["total_pago"].apply(fmt); st.dataframe(v,use_container_width=True,hide_index=True)
    else: st.info("Nenhum evento cadastrado.")

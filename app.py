import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

DB_FILE = "eventos_fazenda_v2.db"


def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            documento TEXT,
            tipo_cliente TEXT,
            empresa TEXT,
            origem_lead TEXT,
            observacoes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS espacos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            capacidade INTEGER DEFAULT 0,
            valor_base REAL DEFAULT 0,
            descricao TEXT,
            ativo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_evento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
            preco_base REAL DEFAULT 0,
            capacidade_sugerida INTEGER DEFAULT 0,
            regras TEXT,
            ativo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            titulo TEXT NOT NULL,
            cliente_id INTEGER,
            tipo_evento_id INTEGER,
            espaco_id INTEGER,
            data_evento TEXT NOT NULL,
            hora_inicio TEXT,
            hora_fim TEXT,
            quantidade_convidados INTEGER DEFAULT 0,
            status_pipeline TEXT,
            status_operacional TEXT,
            valor_locacao REAL DEFAULT 0,
            valor_convidados REAL DEFAULT 0,
            valor_servicos REAL DEFAULT 0,
            desconto REAL DEFAULT 0,
            valor_total REAL DEFAULT 0,
            sinal_pago REAL DEFAULT 0,
            forma_pagamento TEXT,
            responsavel_comercial TEXT,
            responsavel_interno TEXT,
            observacoes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (tipo_evento_id) REFERENCES tipos_evento(id),
            FOREIGN KEY (espaco_id) REFERENCES espacos(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS servicos_adicionais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id INTEGER NOT NULL,
            servico TEXT NOT NULL,
            fornecedor TEXT,
            valor REAL DEFAULT 0,
            observacoes TEXT,
            FOREIGN KEY (evento_id) REFERENCES eventos(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id INTEGER NOT NULL,
            descricao TEXT,
            valor REAL NOT NULL,
            vencimento TEXT,
            data_pagamento TEXT,
            status TEXT DEFAULT 'Em aberto',
            forma_pagamento TEXT,
            observacoes TEXT,
            FOREIGN KEY (evento_id) REFERENCES eventos(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id INTEGER NOT NULL,
            fornecedor TEXT,
            descricao TEXT,
            valor REAL NOT NULL,
            vencimento TEXT,
            data_pagamento TEXT,
            status TEXT DEFAULT 'Pendente',
            observacoes TEXT,
            FOREIGN KEY (evento_id) REFERENCES eventos(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            servico TEXT,
            telefone TEXT,
            email TEXT,
            valor_padrao REAL DEFAULT 0,
            observacoes TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_evento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            concluido INTEGER DEFAULT 0,
            observacoes TEXT,
            FOREIGN KEY (evento_id) REFERENCES eventos(id)
        )
    """)

    conn.commit()

    # seeds
    cur.execute("SELECT COUNT(*) FROM espacos")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO espacos (nome, capacidade, valor_base, descricao, ativo)
            VALUES (?, ?, ?, ?, 1)
        """, [
            ("Salão Principal", 250, 12000, "Espaço para eventos sociais e corporativos"),
            ("Área Externa", 400, 15000, "Jardins e área aberta para cerimônias e confraternizações"),
            ("Piscinas e Toboáguas", 180, 9000, "Operação para day use e eventos com lazer"),
            ("Espaço Corporativo", 150, 10000, "Treinamentos, convenções e workshops"),
            ("Churrasco e Confraternizações", 120, 7000, "Eventos menores e confraternizações")
        ])

    cur.execute("SELECT COUNT(*) FROM tipos_evento")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO tipos_evento (nome, preco_base, capacidade_sugerida, regras, ativo)
            VALUES (?, ?, ?, ?, 1)
        """, [
            ("Casamento", 18000, 200, "Priorizar proposta premium e checklist ampliado"),
            ("Aniversário", 9000, 100, "Pacote social com opcionais"),
            ("Corporativo", 12000, 120, "Foco em estrutura, almoço e apoio operacional"),
            ("15 Anos", 15000, 150, "Pacote social premium"),
            ("Workshop", 8000, 80, "Formato diurno"),
            ("Lançamento de Produto", 14000, 120, "Foco em branding e recepção"),
            ("Ensaio Fotográfico", 2500, 15, "Pacote enxuto"),
            ("Day Use", 6000, 80, "Operação com lazer e alimentação opcional")
        ])

    conn.commit()
    conn.close()


def run_query(query, params=None):
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params or ())
    conn.close()
    return df


def execute_query(query, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def update_query(query, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query, params or ())
    conn.commit()
    qtd = cur.rowcount
    conn.close()
    return qtd


def format_currency(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def get_clientes():
    return run_query("SELECT id, nome FROM clientes ORDER BY nome")


def get_espacos():
    return run_query("SELECT id, nome, capacidade, valor_base FROM espacos WHERE ativo = 1 ORDER BY nome")


def get_tipos():
    return run_query("SELECT id, nome, preco_base, capacidade_sugerida FROM tipos_evento WHERE ativo = 1 ORDER BY nome")


def get_eventos_full():
    return run_query("""
        SELECT
            e.id,
            COALESCE(e.codigo, 'EVT-' || e.id) AS codigo,
            e.titulo,
            c.nome AS cliente,
            te.nome AS tipo_evento,
            es.nome AS espaco,
            e.data_evento,
            e.hora_inicio,
            e.hora_fim,
            e.quantidade_convidados,
            e.status_pipeline,
            e.status_operacional,
            e.valor_total,
            e.sinal_pago,
            e.responsavel_comercial,
            e.responsavel_interno,
            e.forma_pagamento
        FROM eventos e
        LEFT JOIN clientes c ON c.id = e.cliente_id
        LEFT JOIN tipos_evento te ON te.id = e.tipo_evento_id
        LEFT JOIN espacos es ON es.id = e.espaco_id
        ORDER BY e.data_evento, e.hora_inicio
    """)


def existe_conflito(data_evento, espaco_id, evento_id=None):
    sql = """
        SELECT id, titulo
        FROM eventos
        WHERE data_evento = ?
          AND espaco_id = ?
          AND status_operacional <> 'Cancelado'
    """
    params = [data_evento, espaco_id]
    if evento_id:
        sql += " AND id <> ?"
        params.append(evento_id)
    df = run_query(sql, tuple(params))
    return not df.empty


def carregar_checklist_padrao(evento_id):
    itens = [
        "Visita realizada",
        "Proposta enviada",
        "Contrato assinado",
        "Sinal recebido",
        "Cardápio definido",
        "Decoração alinhada",
        "DJ/Banda confirmado",
        "Fotografia alinhada",
        "Equipe de apoio escalada",
        "Montagem programada",
        "Desmontagem programada",
    ]
    existentes = run_query("SELECT item FROM checklist_evento WHERE evento_id = ?", (evento_id,))
    existentes = set(existentes["item"].tolist()) if not existentes.empty else set()
    for item in itens:
        if item not in existentes:
            execute_query("""
                INSERT INTO checklist_evento (evento_id, item, concluido, observacoes)
                VALUES (?, ?, 0, '')
            """, (evento_id, item))


def total_servicos_evento(evento_id):
    df = run_query("SELECT COALESCE(SUM(valor), 0) AS total FROM servicos_adicionais WHERE evento_id = ?", (evento_id,))
    return float(df["total"].iloc[0]) if not df.empty else 0.0


def resumo_financeiro_evento(evento_id):
    evento = run_query("SELECT valor_total FROM eventos WHERE id = ?", (evento_id,))
    valor_total = float(evento["valor_total"].iloc[0]) if not evento.empty else 0.0

    receb = run_query("""
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM pagamentos
        WHERE evento_id = ? AND status = 'Pago'
    """, (evento_id,))
    receb_total = float(receb["total"].iloc[0]) if not receb.empty else 0.0

    desp = run_query("""
        SELECT COALESCE(SUM(valor), 0) AS total
        FROM despesas
        WHERE evento_id = ? AND status = 'Paga'
    """, (evento_id,))
    desp_total = float(desp["total"].iloc[0]) if not desp.empty else 0.0

    aberto = valor_total - receb_total
    lucro = receb_total - desp_total
    margem = (lucro / receb_total * 100) if receb_total else 0.0
    return valor_total, receb_total, aberto, desp_total, lucro, margem


def df_to_csv_download(df, file_name, label):
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, csv, file_name=file_name, mime="text/csv")


st.set_page_config(
    page_title="Quinta do Conde | Gestão Comercial de Eventos",
    page_icon="🏡",
    layout="wide"
)

init_db()

st.markdown("""
<style>
:root {
    --qc-bg: #fbfaf7;
    --qc-card: #ffffff;
    --qc-line: #e7dfd4;
}
.stApp {
    background: linear-gradient(180deg, #fbfaf7 0%, #f4efe8 100%);
}
.block-container {
    padding-top: 1rem;
}
h1, h2, h3 {
    color: #3f2f20;
}
[data-testid="stMetric"] {
    background: var(--qc-card);
    border: 1px solid var(--qc-line);
    border-radius: 18px;
    padding: 10px;
}
.qc-banner {
    background: linear-gradient(120deg, rgba(85,62,43,.95), rgba(141,110,82,.92));
    color: #fff;
    padding: 18px 22px;
    border-radius: 22px;
    margin-bottom: 18px;
}
.small-muted {
    color: #7b6a58;
    font-size: 0.92rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="qc-banner">
    <h1 style="margin:0;">🏡 Quinta do Conde</h1>
    <div style="font-size:1.05rem; margin-top:6px;">Sistema Comercial + Gestão de Eventos</div>
    <div style="margin-top:6px; opacity:.92;">Foco em captação, proposta, fechamento, operação e resultado financeiro.</div>
</div>
""", unsafe_allow_html=True)

menu = st.sidebar.radio(
    "Menu",
    [
        "Dashboard Executivo",
        "CRM / Clientes",
        "Espaços e Tipos",
        "Propostas e Eventos",
        "Agenda Comercial",
        "Financeiro",
        "Operação / Checklist",
        "Relatórios"
    ]
)

if menu == "Dashboard Executivo":
    eventos = get_eventos_full()
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    fim_mes = (inicio_mes.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    mes_df = eventos[(pd.to_datetime(eventos["data_evento"], errors="coerce").dt.date >= inicio_mes) &
                     (pd.to_datetime(eventos["data_evento"], errors="coerce").dt.date <= fim_mes)] if not eventos.empty else pd.DataFrame()

    faturamento_mes = mes_df["valor_total"].sum() if not mes_df.empty else 0
    ticket_medio = mes_df["valor_total"].mean() if not mes_df.empty else 0
    eventos_mes = len(mes_df)

    pipeline_df = run_query("""
        SELECT status_pipeline, COUNT(*) AS quantidade, COALESCE(SUM(valor_total), 0) AS valor
        FROM eventos
        GROUP BY status_pipeline
        ORDER BY quantidade DESC
    """)

    leads = int(pipeline_df[pipeline_df["status_pipeline"].isin(["Lead", "Visita agendada", "Proposta enviada", "Negociação"])]["quantidade"].sum()) if not pipeline_df.empty else 0
    fechados = int(pipeline_df[pipeline_df["status_pipeline"] == "Fechado"]["quantidade"].sum()) if not pipeline_df.empty else 0
    conversao = (fechados / (leads + fechados) * 100) if (leads + fechados) else 0

    agenda_futura = run_query("""
        SELECT
            e.data_evento,
            e.titulo,
            c.nome AS cliente,
            te.nome AS tipo_evento,
            es.nome AS espaco,
            e.status_pipeline,
            e.valor_total
        FROM eventos e
        LEFT JOIN clientes c ON c.id = e.cliente_id
        LEFT JOIN tipos_evento te ON te.id = e.tipo_evento_id
        LEFT JOIN espacos es ON es.id = e.espaco_id
        WHERE e.data_evento >= date('now')
        ORDER BY e.data_evento
        LIMIT 12
    """)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eventos no mês", eventos_mes)
    c2.metric("Faturamento previsto", format_currency(faturamento_mes))
    c3.metric("Ticket médio", format_currency(ticket_medio))
    c4.metric("Conversão comercial", f"{conversao:.1f}%")

    c5, c6, c7 = st.columns(3)
    abertos = run_query("SELECT COALESCE(SUM(valor), 0) AS total FROM pagamentos WHERE status = 'Em aberto'")
    receb_aberto = float(abertos["total"].iloc[0]) if not abertos.empty else 0
    c5.metric("Recebimentos em aberto", format_currency(receb_aberto))

    ocupacao = run_query("""
        SELECT es.nome AS espaco, COUNT(*) AS quantidade
        FROM eventos e
        LEFT JOIN espacos es ON es.id = e.espaco_id
        WHERE e.status_operacional <> 'Cancelado'
        GROUP BY es.nome
        ORDER BY quantidade DESC
    """)
    espaco_top = ocupacao["espaco"].iloc[0] if not ocupacao.empty else "-"
    qtd_top = int(ocupacao["quantidade"].iloc[0]) if not ocupacao.empty else 0
    c6.metric("Espaço mais demandado", espaco_top, delta=f"{qtd_top} eventos")
    c7.metric("Pipeline fechado", fechados)

    st.subheader("Pipeline comercial")
    if not pipeline_df.empty:
        pipe_view = pipeline_df.copy()
        pipe_view["valor"] = pipe_view["valor"].apply(format_currency)
        st.dataframe(pipe_view, use_container_width=True, hide_index=True)
        st.bar_chart(pipeline_df.set_index("status_pipeline")[["quantidade"]])

    st.subheader("Próximos eventos / propostas")
    if agenda_futura.empty:
        st.info("Nenhum evento futuro cadastrado.")
    else:
        agenda_view = agenda_futura.copy()
        agenda_view["valor_total"] = agenda_view["valor_total"].apply(format_currency)
        st.dataframe(agenda_view, use_container_width=True, hide_index=True)

    st.subheader("Receita potencial por mês")
    receita_mes = run_query("""
        SELECT substr(data_evento, 1, 7) AS mes, COALESCE(SUM(valor_total), 0) AS total
        FROM eventos
        GROUP BY substr(data_evento, 1, 7)
        ORDER BY mes
    """)
    if not receita_mes.empty:
        st.line_chart(receita_mes.set_index("mes"))


elif menu == "CRM / Clientes":
    st.subheader("Cadastro comercial de clientes")

    with st.form("cliente_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome / razão social*")
        telefone = c2.text_input("Telefone / WhatsApp")
        email = c3.text_input("E-mail")

        c4, c5, c6 = st.columns(3)
        documento = c4.text_input("CPF/CNPJ")
        tipo_cliente = c5.selectbox("Tipo do cliente", ["Pessoa Física", "Pessoa Jurídica"])
        empresa = c6.text_input("Empresa")

        c7, c8 = st.columns(2)
        origem = c7.selectbox("Origem do lead", ["Site", "Instagram", "Indicação", "Google", "WhatsApp", "Outro"])
        obs = c8.text_area("Observações")

        salvar = st.form_submit_button("Salvar cliente")
        if salvar:
            if not nome.strip():
                st.error("Informe o nome do cliente.")
            else:
                execute_query("""
                    INSERT INTO clientes (nome, telefone, email, documento, tipo_cliente, empresa, origem_lead, observacoes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (nome, telefone, email, documento, tipo_cliente, empresa, origem, obs))
                st.success("Cliente cadastrado com sucesso.")

    clientes_df = run_query("""
        SELECT id, nome, telefone, email, documento, tipo_cliente, empresa, origem_lead, observacoes
        FROM clientes
        ORDER BY nome
    """)
    st.divider()
    st.subheader("Base de clientes")
    if not clientes_df.empty:
        st.dataframe(clientes_df, use_container_width=True, hide_index=True)
        df_to_csv_download(clientes_df, "clientes_quinta_do_conde.csv", "Baixar clientes em CSV")
    else:
        st.info("Nenhum cliente cadastrado.")


elif menu == "Espaços e Tipos":
    st.subheader("Estrutura comercial")
    tab1, tab2 = st.tabs(["Espaços", "Tipos de evento"])

    with tab1:
        with st.form("espaco_form", clear_on_submit=True):
            e1, e2, e3 = st.columns(3)
            nome = e1.text_input("Nome do espaço")
            capacidade = e2.number_input("Capacidade", min_value=0, step=10)
            valor_base = e3.number_input("Valor base", min_value=0.0, step=500.0)

            descricao = st.text_area("Descrição")
            salvar = st.form_submit_button("Salvar espaço")
            if salvar and nome.strip():
                try:
                    execute_query("""
                        INSERT INTO espacos (nome, capacidade, valor_base, descricao, ativo)
                        VALUES (?, ?, ?, ?, 1)
                    """, (nome.strip(), int(capacidade), float(valor_base), descricao))
                    st.success("Espaço cadastrado.")
                except Exception:
                    st.error("Já existe um espaço com esse nome.")

        df = run_query("SELECT id, nome, capacidade, valor_base, descricao FROM espacos WHERE ativo = 1 ORDER BY nome")
        if not df.empty:
            view = df.copy()
            view["valor_base"] = view["valor_base"].apply(format_currency)
            st.dataframe(view, use_container_width=True, hide_index=True)

    with tab2:
        with st.form("tipo_form", clear_on_submit=True):
            t1, t2, t3 = st.columns(3)
            nome = t1.text_input("Tipo de evento")
            preco_base = t2.number_input("Preço base", min_value=0.0, step=500.0)
            capacidade_sugerida = t3.number_input("Capacidade sugerida", min_value=0, step=10)
            regras = st.text_area("Regras / observações")
            salvar = st.form_submit_button("Salvar tipo")
            if salvar and nome.strip():
                try:
                    execute_query("""
                        INSERT INTO tipos_evento (nome, preco_base, capacidade_sugerida, regras, ativo)
                        VALUES (?, ?, ?, ?, 1)
                    """, (nome.strip(), float(preco_base), int(capacidade_sugerida), regras))
                    st.success("Tipo de evento cadastrado.")
                except Exception:
                    st.error("Já existe um tipo com esse nome.")

        df = run_query("SELECT id, nome, preco_base, capacidade_sugerida, regras FROM tipos_evento WHERE ativo = 1 ORDER BY nome")
        if not df.empty:
            view = df.copy()
            view["preco_base"] = view["preco_base"].apply(format_currency)
            st.dataframe(view, use_container_width=True, hide_index=True)


elif menu == "Propostas e Eventos":
    st.subheader("Cadastro de proposta / evento")
    clientes = get_clientes()
    espacos = get_espacos()
    tipos = get_tipos()

    if clientes.empty:
        st.warning("Cadastre pelo menos um cliente antes de criar propostas.")
    else:
        mapa_clientes = dict(zip(clientes["nome"], clientes["id"]))
        mapa_espacos = {f"{r['nome']} | cap. {int(r['capacidade'])} | base {format_currency(r['valor_base'])}": (r["id"], float(r["valor_base"])) for _, r in espacos.iterrows()}
        mapa_tipos = {f"{r['nome']} | base {format_currency(r['preco_base'])}": (r["id"], float(r["preco_base"])) for _, r in tipos.iterrows()}

        with st.form("evento_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            titulo = c1.text_input("Nome da proposta / evento*")
            cliente_sel = c2.selectbox("Cliente", list(mapa_clientes.keys()))
            data_evento = c3.date_input("Data do evento", value=date.today() + timedelta(days=30))

            c4, c5, c6 = st.columns(3)
            tipo_sel = c4.selectbox("Tipo de evento", list(mapa_tipos.keys()))
            espaco_sel = c5.selectbox("Espaço", list(mapa_espacos.keys()))
            convidados = c6.number_input("Quantidade de convidados", min_value=0, step=5)

            c7, c8, c9 = st.columns(3)
            hora_inicio = c7.time_input("Hora início", value=datetime.strptime("10:00", "%H:%M").time())
            hora_fim = c8.time_input("Hora fim", value=datetime.strptime("22:00", "%H:%M").time())
            pipeline = c9.selectbox("Etapa do pipeline", ["Lead", "Visita agendada", "Proposta enviada", "Negociação", "Fechado", "Perdido"])

            c10, c11, c12 = st.columns(3)
            status_operacional = c10.selectbox("Status operacional", ["Orçamento", "Pré-reserva", "Confirmado", "Realizado", "Cancelado"])
            responsavel_comercial = c11.text_input("Responsável comercial")
            responsavel_interno = c12.text_input("Responsável interno")

            tipo_id, valor_tipo = mapa_tipos[tipo_sel]
            espaco_id, valor_espaco = mapa_espacos[espaco_sel]

            st.markdown("#### Formação da proposta")
            c13, c14, c15, c16 = st.columns(4)
            valor_locacao = c13.number_input("Valor locação", min_value=0.0, step=500.0, value=float(valor_espaco))
            valor_convidados = c14.number_input("Valor por convidados", min_value=0.0, step=500.0, value=float(valor_tipo))
            valor_servicos = c15.number_input("Serviços adicionais", min_value=0.0, step=500.0)
            desconto = c16.number_input("Desconto", min_value=0.0, step=100.0)

            c17, c18 = st.columns(2)
            sinal_pago = c17.number_input("Sinal pago", min_value=0.0, step=100.0)
            forma_pagamento = c18.selectbox("Forma de pagamento", ["Pix", "Boleto", "Cartão", "Transferência", "Dinheiro", "Outro"])

            observacoes = st.text_area("Observações da proposta")

            valor_total = max((valor_locacao + valor_convidados + valor_servicos - desconto), 0.0)
            st.info(f"Valor total da proposta: {format_currency(valor_total)}")

            salvar = st.form_submit_button("Salvar proposta / evento")
            if salvar:
                if not titulo.strip():
                    st.error("Informe o nome da proposta.")
                elif existe_conflito(str(data_evento), espaco_id):
                    st.error("Já existe uma reserva ativa para essa data e espaço.")
                else:
                    rid = execute_query("""
                        INSERT INTO eventos (
                            codigo, titulo, cliente_id, tipo_evento_id, espaco_id, data_evento, hora_inicio, hora_fim,
                            quantidade_convidados, status_pipeline, status_operacional, valor_locacao, valor_convidados,
                            valor_servicos, desconto, valor_total, sinal_pago, forma_pagamento,
                            responsavel_comercial, responsavel_interno, observacoes
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        f"EVT-{int(datetime.now().timestamp())}",
                        titulo.strip(),
                        int(mapa_clientes[cliente_sel]),
                        int(tipo_id),
                        int(espaco_id),
                        str(data_evento),
                        hora_inicio.strftime("%H:%M"),
                        hora_fim.strftime("%H:%M"),
                        int(convidados),
                        pipeline,
                        status_operacional,
                        float(valor_locacao),
                        float(valor_convidados),
                        float(valor_servicos),
                        float(desconto),
                        float(valor_total),
                        float(sinal_pago),
                        forma_pagamento,
                        responsavel_comercial,
                        responsavel_interno,
                        observacoes
                    ))
                    carregar_checklist_padrao(rid)
                    if sinal_pago > 0:
                        execute_query("""
                            INSERT INTO pagamentos (evento_id, descricao, valor, vencimento, data_pagamento, status, forma_pagamento, observacoes)
                            VALUES (?, ?, ?, ?, ?, 'Pago', ?, ?)
                        """, (rid, "Sinal da proposta", float(sinal_pago), str(data_evento), str(date.today()), forma_pagamento, "Registrado na abertura da proposta"))
                    st.success("Proposta/evento salvo com sucesso.")

    st.divider()
    st.subheader("Carteira comercial")
    df = get_eventos_full()
    if not df.empty:
        view = df.copy()
        view["valor_total"] = view["valor_total"].apply(format_currency)
        view["sinal_pago"] = view["sinal_pago"].apply(format_currency)
        st.dataframe(view, use_container_width=True, hide_index=True)
        df_to_csv_download(df, "carteira_eventos_quinta_do_conde.csv", "Baixar carteira comercial")
    else:
        st.info("Nenhuma proposta cadastrada.")


elif menu == "Agenda Comercial":
    st.subheader("Agenda de propostas e eventos")
    c1, c2, c3 = st.columns(3)
    data_ini = c1.date_input("Data inicial", value=date.today().replace(day=1))
    data_fim = c2.date_input("Data final", value=date.today() + timedelta(days=90))
    filtro_espaco = c3.selectbox("Espaço", ["Todos"] + get_espacos()["nome"].tolist())

    df = get_eventos_full()
    if not df.empty:
        df["data_evento_dt"] = pd.to_datetime(df["data_evento"], errors="coerce").dt.date
        df = df[(df["data_evento_dt"] >= data_ini) & (df["data_evento_dt"] <= data_fim)]
        if filtro_espaco != "Todos":
            df = df[df["espaco"] == filtro_espaco]

    if df.empty:
        st.info("Nenhum evento no período selecionado.")
    else:
        for data_evt, grupo in df.sort_values(["data_evento", "hora_inicio"]).groupby("data_evento"):
            st.markdown(f"### {pd.to_datetime(data_evt).strftime('%d/%m/%Y')}")
            grupo_v = grupo[["titulo", "cliente", "tipo_evento", "espaco", "hora_inicio", "hora_fim", "status_pipeline", "status_operacional", "valor_total"]].copy()
            grupo_v["valor_total"] = grupo_v["valor_total"].apply(format_currency)
            st.dataframe(grupo_v, use_container_width=True, hide_index=True)


elif menu == "Financeiro":
    st.subheader("Financeiro por evento")
    eventos = get_eventos_full()

    if eventos.empty:
        st.warning("Cadastre propostas antes de usar o financeiro.")
    else:
        mapa = {f"{r['codigo']} | {r['titulo']} | {r['data_evento']}": int(r["id"]) for _, r in eventos.iterrows()}
        evento_sel = st.selectbox("Selecione o evento", list(mapa.keys()))
        evento_id = mapa[evento_sel]

        valor_total, recebido, aberto, despesas_pagas, lucro, margem = resumo_financeiro_evento(evento_id)

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Contrato", format_currency(valor_total))
        m2.metric("Recebido", format_currency(recebido))
        m3.metric("Aberto", format_currency(aberto))
        m4.metric("Despesas pagas", format_currency(despesas_pagas))
        m5.metric("Lucro realizado", format_currency(lucro))
        m6.metric("Margem", f"{margem:.1f}%")

        tab1, tab2, tab3 = st.tabs(["Serviços da proposta", "Recebimentos", "Despesas"])

        with tab1:
            with st.form("servico_adicional", clear_on_submit=True):
                s1, s2, s3 = st.columns(3)
                servico = s1.text_input("Serviço")
                fornecedor = s2.text_input("Fornecedor")
                valor = s3.number_input("Valor", min_value=0.0, step=100.0)
                obs = st.text_input("Observações")
                salvar = st.form_submit_button("Adicionar serviço")
                if salvar and servico.strip():
                    execute_query("""
                        INSERT INTO servicos_adicionais (evento_id, servico, fornecedor, valor, observacoes)
                        VALUES (?, ?, ?, ?, ?)
                    """, (evento_id, servico.strip(), fornecedor, float(valor), obs))
                    total_serv = total_servicos_evento(evento_id)
                    update_query("""
                        UPDATE eventos
                        SET valor_servicos = ?, valor_total = MAX((valor_locacao + valor_convidados + ? - desconto), 0)
                        WHERE id = ?
                    """, (total_serv, total_serv, evento_id))
                    st.success("Serviço adicionado e proposta atualizada.")

            serv_df = run_query("""
                SELECT servico, fornecedor, valor, observacoes
                FROM servicos_adicionais
                WHERE evento_id = ?
                ORDER BY id
            """, (evento_id,))
            if not serv_df.empty:
                view = serv_df.copy()
                view["valor"] = view["valor"].apply(format_currency)
                st.dataframe(view, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum serviço adicional lançado.")

        with tab2:
            with st.form("pag_form", clear_on_submit=True):
                p1, p2, p3 = st.columns(3)
                descricao = p1.text_input("Descrição", value="Parcela")
                valor = p2.number_input("Valor do recebimento", min_value=0.0, step=100.0)
                venc = p3.date_input("Vencimento", value=date.today())
                p4, p5, p6 = st.columns(3)
                data_pg = p4.date_input("Data pagamento", value=date.today())
                status = p5.selectbox("Status", ["Em aberto", "Pago"])
                forma = p6.selectbox("Forma", ["Pix", "Boleto", "Cartão", "Transferência", "Dinheiro", "Outro"])
                obs = st.text_input("Observações")
                salvar = st.form_submit_button("Salvar recebimento")
                if salvar:
                    execute_query("""
                        INSERT INTO pagamentos (evento_id, descricao, valor, vencimento, data_pagamento, status, forma_pagamento, observacoes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        evento_id, descricao, float(valor), str(venc),
                        str(data_pg) if status == "Pago" else None, status, forma, obs
                    ))
                    st.success("Recebimento salvo.")

            df_pag = run_query("""
                SELECT descricao, valor, vencimento, data_pagamento, status, forma_pagamento, observacoes
                FROM pagamentos
                WHERE evento_id = ?
                ORDER BY vencimento
            """, (evento_id,))
            if not df_pag.empty:
                view = df_pag.copy()
                view["valor"] = view["valor"].apply(format_currency)
                st.dataframe(view, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum recebimento lançado.")

        with tab3:
            with st.form("desp_form", clear_on_submit=True):
                d1, d2, d3 = st.columns(3)
                fornecedor = d1.text_input("Fornecedor")
                descricao = d2.text_input("Descrição")
                valor = d3.number_input("Valor da despesa", min_value=0.0, step=100.0)
                d4, d5, d6 = st.columns(3)
                venc = d4.date_input("Vencimento", value=date.today())
                data_pg = d5.date_input("Data pagamento", value=date.today())
                status = d6.selectbox("Status", ["Pendente", "Paga"])
                obs = st.text_input("Observações")
                salvar = st.form_submit_button("Salvar despesa")
                if salvar:
                    execute_query("""
                        INSERT INTO despesas (evento_id, fornecedor, descricao, valor, vencimento, data_pagamento, status, observacoes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        evento_id, fornecedor, descricao, float(valor), str(venc),
                        str(data_pg) if status == "Paga" else None, status, obs
                    ))
                    st.success("Despesa salva.")

            df_d = run_query("""
                SELECT fornecedor, descricao, valor, vencimento, data_pagamento, status, observacoes
                FROM despesas
                WHERE evento_id = ?
                ORDER BY vencimento
            """, (evento_id,))
            if not df_d.empty:
                view = df_d.copy()
                view["valor"] = view["valor"].apply(format_currency)
                st.dataframe(view, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma despesa lançada.")


elif menu == "Operação / Checklist":
    st.subheader("Checklist operacional por evento")
    eventos = get_eventos_full()
    if eventos.empty:
        st.warning("Cadastre eventos antes de usar o checklist.")
    else:
        mapa = {f"{r['codigo']} | {r['titulo']} | {r['data_evento']}": int(r["id"]) for _, r in eventos.iterrows()}
        evento_sel = st.selectbox("Selecione o evento", list(mapa.keys()))
        evento_id = mapa[evento_sel]

        check_df = run_query("""
            SELECT id, item, concluido, observacoes
            FROM checklist_evento
            WHERE evento_id = ?
            ORDER BY id
        """, (evento_id,))

        if check_df.empty:
            st.info("Checklist vazio.")
        else:
            total = len(check_df)
            concl = int(check_df["concluido"].sum())
            progresso = (concl / total) if total else 0
            st.progress(progresso, text=f"Progresso do evento: {concl}/{total} itens concluídos")

            for _, row in check_df.iterrows():
                c1, c2, c3 = st.columns([4, 2, 1.5])
                novo_status = c1.checkbox(row["item"], value=bool(row["concluido"]), key=f"item_{row['id']}")
                nova_obs = c2.text_input("Obs.", value=row["observacoes"] or "", key=f"obs_{row['id']}")
                if c3.button("Salvar", key=f"btn_{row['id']}"):
                    update_query("""
                        UPDATE checklist_evento
                        SET concluido = ?, observacoes = ?
                        WHERE id = ?
                    """, (1 if novo_status else 0, nova_obs, int(row["id"])))
                    st.success("Item atualizado.")

        st.divider()
        with st.form("novo_check", clear_on_submit=True):
            item = st.text_input("Novo item de checklist")
            obs = st.text_input("Observações")
            salvar = st.form_submit_button("Adicionar item")
            if salvar and item.strip():
                execute_query("""
                    INSERT INTO checklist_evento (evento_id, item, concluido, observacoes)
                    VALUES (?, ?, 0, ?)
                """, (evento_id, item.strip(), obs))
                st.success("Novo item adicionado.")


elif menu == "Relatórios":
    st.subheader("Relatórios gerenciais")
    c1, c2 = st.columns(2)
    data_ini = c1.date_input("Data inicial", value=date.today().replace(day=1))
    data_fim = c2.date_input("Data final", value=date.today() + timedelta(days=90))

    df = get_eventos_full()
    if not df.empty:
        df["data_evento_dt"] = pd.to_datetime(df["data_evento"], errors="coerce").dt.date
        df = df[(df["data_evento_dt"] >= data_ini) & (df["data_evento_dt"] <= data_fim)]

    if df.empty:
        st.info("Nenhum dado no período.")
    else:
        st.markdown("#### Eventos por tipo")
        tipo_df = df.groupby("tipo_evento", as_index=False).agg(
            quantidade=("id", "count"),
            valor_total=("valor_total", "sum")
        ).sort_values("valor_total", ascending=False)
        tipo_view = tipo_df.copy()
        tipo_view["valor_total"] = tipo_view["valor_total"].apply(format_currency)
        st.dataframe(tipo_view, use_container_width=True, hide_index=True)

        st.markdown("#### Eventos por espaço")
        esp_df = df.groupby("espaco", as_index=False).agg(
            quantidade=("id", "count"),
            valor_total=("valor_total", "sum")
        ).sort_values("quantidade", ascending=False)
        esp_view = esp_df.copy()
        esp_view["valor_total"] = esp_view["valor_total"].apply(format_currency)
        st.dataframe(esp_view, use_container_width=True, hide_index=True)

        st.markdown("#### Carteira detalhada")
        det = df[[
            "codigo", "titulo", "cliente", "tipo_evento", "espaco", "data_evento",
            "status_pipeline", "status_operacional", "valor_total", "responsavel_comercial", "responsavel_interno"
        ]].copy()
        det["valor_total_fmt"] = det["valor_total"].apply(format_currency)
        st.dataframe(det.drop(columns=["valor_total"]), use_container_width=True, hide_index=True)

        df_to_csv_download(det, "relatorio_gerencial_quinta_do_conde.csv", "Baixar relatório gerencial")

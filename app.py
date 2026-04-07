import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

DB_FILE = "eventos_fazenda_v4.db"


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
            descricao TEXT,
            ativo INTEGER DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tipos_evento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE,
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

    cur.execute("SELECT COUNT(*) FROM espacos")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO espacos (nome, capacidade, descricao, ativo)
            VALUES (?, ?, ?, 1)
        """, [
            ("Salão Principal", 250, "Espaço para eventos sociais e corporativos"),
            ("Área Externa", 400, "Jardins e área aberta para cerimônias e confraternizações"),
            ("Piscinas e Toboáguas", 180, "Operação para day use e eventos com lazer"),
            ("Espaço Corporativo", 150, "Treinamentos, convenções e workshops"),
            ("Churrasco e Confraternizações", 120, "Eventos menores e confraternizações")
        ])

    cur.execute("SELECT COUNT(*) FROM tipos_evento")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO tipos_evento (nome, capacidade_sugerida, regras, ativo)
            VALUES (?, ?, ?, 1)
        """, [
            ("Casamento", 200, "Priorizar proposta premium e checklist ampliado"),
            ("Aniversário", 100, "Pacote social com opcionais"),
            ("Corporativo", 120, "Foco em estrutura, almoço e apoio operacional"),
            ("15 Anos", 150, "Pacote social premium"),
            ("Workshop", 80, "Formato diurno"),
            ("Lançamento de Produto", 120, "Foco em branding e recepção"),
            ("Ensaio Fotográfico", 15, "Pacote enxuto"),
            ("Day Use", 80, "Operação com lazer e alimentação opcional")
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
    return run_query("SELECT id, nome, capacidade FROM espacos WHERE ativo = 1 ORDER BY nome")


def get_tipos():
    return run_query("SELECT id, nome, capacidade_sugerida FROM tipos_evento WHERE ativo = 1 ORDER BY nome")


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
            e.forma_pagamento,
            e.responsavel_comercial,
            e.responsavel_interno
        FROM eventos e
        LEFT JOIN clientes c ON c.id = e.cliente_id
        LEFT JOIN tipos_evento te ON te.id = e.tipo_evento_id
        LEFT JOIN espacos es ON es.id = e.espaco_id
        ORDER BY e.data_evento, e.hora_inicio
    """)


def get_evento_detalhe(evento_id):
    df = run_query("""
        SELECT
            e.*,
            c.nome AS cliente_nome,
            c.telefone AS cliente_telefone,
            c.email AS cliente_email,
            c.documento AS cliente_documento,
            c.empresa AS cliente_empresa,
            te.nome AS tipo_evento_nome,
            es.nome AS espaco_nome
        FROM eventos e
        LEFT JOIN clientes c ON c.id = e.cliente_id
        LEFT JOIN tipos_evento te ON te.id = e.tipo_evento_id
        LEFT JOIN espacos es ON es.id = e.espaco_id
        WHERE e.id = ?
    """, (evento_id,))
    return df.iloc[0].to_dict() if not df.empty else None


def get_servicos_evento(evento_id):
    return run_query("""
        SELECT servico, fornecedor, valor, observacoes
        FROM servicos_adicionais
        WHERE evento_id = ?
        ORDER BY id
    """, (evento_id,))


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


def wrap_text(c, text, max_width, font_name="Helvetica", font_size=10):
    if not text:
        return []
    words = str(text).split()
    lines = []
    current = ""
    for word in words:
        test = word if not current else current + " " + word
        if stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_box(c, x, y, w, h, title, body_lines):
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#D9CDBE"))
    c.roundRect(x, y, w, h, 8, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#7A5A43"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 12, y + h - 16, title)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    current_y = y + h - 32
    for line in body_lines:
        c.drawString(x + 12, current_y, line)
        current_y -= 13


def gerar_pdf_proposta(evento_id):
    evento = get_evento_detalhe(evento_id)
    servicos = get_servicos_evento(evento_id)
    if not evento:
        return None

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margem = 1.6 * cm
    usable_w = width - 2 * margem

    # fundo / cabeçalho
    c.setFillColor(colors.HexColor("#FAF7F2"))
    c.rect(0, 0, width, height, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#5A402C"))
    c.roundRect(margem, height - 4.0*cm, usable_w, 2.5*cm, 14, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(margem + 16, height - 2.2*cm, "Quinta do Conde")
    c.setFont("Helvetica", 11)
    c.drawString(margem + 16, height - 2.9*cm, "Proposta comercial de evento")

    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margem, height - 4.9*cm, evento.get("titulo", ""))

    c.setFont("Helvetica", 10)
    subtitulo = f"Código {evento.get('codigo', '')}  |  Data do evento {pd.to_datetime(evento.get('data_evento')).strftime('%d/%m/%Y') if evento.get('data_evento') else ''}"
    c.drawString(margem, height - 5.5*cm, subtitulo)

    # cards
    box_y = height - 9.4 * cm
    box_h = 3.1 * cm
    box_gap = 0.35 * cm
    box_w = (usable_w - box_gap) / 2

    cliente_linhas = [
        f"Cliente: {evento.get('cliente_nome') or '-'}",
        f"Telefone: {evento.get('cliente_telefone') or '-'}",
        f"E-mail: {evento.get('cliente_email') or '-'}",
    ]
    evento_linhas = [
        f"Tipo: {evento.get('tipo_evento_nome') or '-'}",
        f"Espaço: {evento.get('espaco_nome') or '-'}",
        f"Horário: {evento.get('hora_inicio') or '-'} às {evento.get('hora_fim') or '-'}",
    ]

    draw_box(c, margem, box_y, box_w, box_h, "Dados do cliente", cliente_linhas)
    draw_box(c, margem + box_w + box_gap, box_y, box_w, box_h, "Dados do evento", evento_linhas)

    box_y2 = box_y - box_h - 0.35*cm
    proposta_linhas = [
        f"Convidados: {int(evento.get('quantidade_convidados') or 0)}",
        f"Forma de pagamento: {evento.get('forma_pagamento') or '-'}",
        f"Status: {evento.get('status_operacional') or '-'}",
    ]
    valores_linhas = [
        f"Locação: {format_currency(evento.get('valor_locacao') or 0)}",
        f"Convidados/alimentação: {format_currency(evento.get('valor_convidados') or 0)}",
        f"Serviços adicionais: {format_currency(evento.get('valor_servicos') or 0)}",
    ]
    draw_box(c, margem, box_y2, box_w, box_h, "Resumo comercial", proposta_linhas)
    draw_box(c, margem + box_w + box_gap, box_y2, box_w, box_h, "Composição da proposta", valores_linhas)

    # quadro total
    total_y = box_y2 - 2.2*cm
    c.setFillColor(colors.HexColor("#EFE5D8"))
    c.roundRect(margem, total_y, usable_w, 1.6*cm, 10, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#5A402C"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margem + 16, total_y + 0.95*cm, "Valor total da proposta")
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(margem + usable_w - 16, total_y + 0.9*cm, format_currency(evento.get("valor_total") or 0))

    # tabela simples de itens
    top = total_y - 0.8*cm
    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margem, top, "Itens da proposta")

    table_y = top - 0.7*cm
    row_h = 0.8*cm
    col1 = margem
    col2 = margem + usable_w * 0.68
    col3 = margem + usable_w * 0.84

    def row(y, descricao, valor):
        c.setStrokeColor(colors.HexColor("#D9CDBE"))
        c.line(margem, y, margem + usable_w, y)
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        c.drawString(col1 + 4, y - 14, descricao)
        c.drawRightString(margem + usable_w - 8, y - 14, format_currency(valor))

    c.setFillColor(colors.HexColor("#7A5A43"))
    c.rect(margem, table_y - row_h + 4, usable_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(col1 + 4, table_y - 14, "Descrição")
    c.drawRightString(margem + usable_w - 8, table_y - 14, "Valor")

    y = table_y - row_h
    row(y, "Locação / pacote principal", evento.get("valor_locacao") or 0); y -= row_h
    row(y, "Convidados / alimentação", evento.get("valor_convidados") or 0); y -= row_h
    row(y, "Serviços adicionais", evento.get("valor_servicos") or 0); y -= row_h
    row(y, "Desconto", -(evento.get("desconto") or 0)); y -= row_h
    c.line(margem, y, margem + usable_w, y)

    # serviços detalhados
    y -= 0.9*cm
    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margem, y, "Detalhamento de serviços")
    y -= 0.55*cm

    if servicos.empty:
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        c.drawString(margem, y, "Nenhum serviço adicional detalhado.")
        y -= 0.8*cm
    else:
        for _, s in servicos.iterrows():
            if y < 4.0*cm:
                c.showPage()
                c.setFillColor(colors.HexColor("#FAF7F2"))
                c.rect(0, 0, width, height, fill=1, stroke=0)
                y = height - 2.5*cm
            descricao = f"- {s['servico']} | Fornecedor: {s['fornecedor'] or '-'} | Valor: {format_currency(s['valor'])}"
            lines = wrap_text(c, descricao, usable_w, "Helvetica", 10)
            for line in lines:
                c.setFont("Helvetica", 10)
                c.setFillColor(colors.black)
                c.drawString(margem, y, line)
                y -= 12
            if s["observacoes"]:
                obs_lines = wrap_text(c, f"Obs.: {s['observacoes']}", usable_w - 20, "Helvetica", 9)
                for line in obs_lines:
                    c.setFont("Helvetica-Oblique", 9)
                    c.setFillColor(colors.HexColor("#5E5E5E"))
                    c.drawString(margem + 12, y, line)
                    y -= 11
            y -= 6

    # observações
    obs = evento.get("observacoes") or "Proposta sujeita a alinhamento final de escopo, disponibilidade e condições comerciais."
    if y < 5.2*cm:
        c.showPage()
        c.setFillColor(colors.HexColor("#FAF7F2"))
        c.rect(0, 0, width, height, fill=1, stroke=0)
        y = height - 2.5*cm

    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margem, y, "Observações")
    y -= 0.45*cm

    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#D9CDBE"))
    box_h_obs = 3.2*cm
    c.roundRect(margem, y - box_h_obs + 6, usable_w, box_h_obs, 10, fill=1, stroke=1)

    obs_lines = wrap_text(c, obs, usable_w - 24, "Helvetica", 10)
    text_y = y - 16
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    for line in obs_lines[:8]:
        c.drawString(margem + 12, text_y, line)
        text_y -= 12

    # rodapé
    c.setFillColor(colors.HexColor("#7A5A43"))
    c.setFont("Helvetica", 9)
    c.drawString(margem, 1.4*cm, "Quinta do Conde - Proposta comercial gerada pelo sistema")
    c.drawRightString(width - margem, 1.4*cm, datetime.now().strftime("Gerado em %d/%m/%Y %H:%M"))

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


st.set_page_config(
    page_title="Quinta do Conde | Gestão Comercial de Eventos",
    page_icon="🏡",
    layout="wide"
)

init_db()

st.markdown("""
<style>
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
    background: #ffffff;
    border: 1px solid #e7dfd4;
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
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="qc-banner">
    <h1 style="margin:0;">🏡 Quinta do Conde</h1>
    <div style="font-size:1.05rem; margin-top:6px;">Sistema Comercial + Gestão de Eventos</div>
    <div style="margin-top:6px; opacity:.92;">Versão com proposta em PDF e formação manual.</div>
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

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eventos no mês", eventos_mes)
    c2.metric("Faturamento previsto", format_currency(faturamento_mes))
    c3.metric("Ticket médio", format_currency(ticket_medio))
    c4.metric("Conversão comercial", f"{conversao:.1f}%")

    st.subheader("Pipeline comercial")
    if not pipeline_df.empty:
        pipe_view = pipeline_df.copy()
        pipe_view["valor"] = pipe_view["valor"].apply(format_currency)
        st.dataframe(pipe_view, use_container_width=True, hide_index=True)
        st.bar_chart(pipeline_df.set_index("status_pipeline")[["quantidade"]])

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
    if not clientes_df.empty:
        st.dataframe(clientes_df, use_container_width=True, hide_index=True)
        df_to_csv_download(clientes_df, "clientes_quinta_do_conde.csv", "Baixar clientes em CSV")
    else:
        st.info("Nenhum cliente cadastrado.")

elif menu == "Espaços e Tipos":
    tab1, tab2 = st.tabs(["Espaços", "Tipos de evento"])

    with tab1:
        with st.form("espaco_form", clear_on_submit=True):
            e1, e2 = st.columns(2)
            nome = e1.text_input("Nome do espaço")
            capacidade = e2.number_input("Capacidade", min_value=0, step=10)
            descricao = st.text_area("Descrição")
            salvar = st.form_submit_button("Salvar espaço")
            if salvar and nome.strip():
                try:
                    execute_query("""
                        INSERT INTO espacos (nome, capacidade, descricao, ativo)
                        VALUES (?, ?, ?, 1)
                    """, (nome.strip(), int(capacidade), descricao))
                    st.success("Espaço cadastrado.")
                except Exception:
                    st.error("Já existe um espaço com esse nome.")

        df = run_query("SELECT id, nome, capacidade, descricao FROM espacos WHERE ativo = 1 ORDER BY nome")
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab2:
        with st.form("tipo_form", clear_on_submit=True):
            t1, t2 = st.columns(2)
            nome = t1.text_input("Tipo de evento")
            capacidade_sugerida = t2.number_input("Capacidade sugerida", min_value=0, step=10)
            regras = st.text_area("Regras / observações")
            salvar = st.form_submit_button("Salvar tipo")
            if salvar and nome.strip():
                try:
                    execute_query("""
                        INSERT INTO tipos_evento (nome, capacidade_sugerida, regras, ativo)
                        VALUES (?, ?, ?, 1)
                    """, (nome.strip(), int(capacidade_sugerida), regras))
                    st.success("Tipo de evento cadastrado.")
                except Exception:
                    st.error("Já existe um tipo com esse nome.")

        df = run_query("SELECT id, nome, capacidade_sugerida, regras FROM tipos_evento WHERE ativo = 1 ORDER BY nome")
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)

elif menu == "Propostas e Eventos":
    st.subheader("Cadastro de proposta / evento")
    clientes = get_clientes()
    espacos = get_espacos()
    tipos = get_tipos()

    if clientes.empty:
        st.warning("Cadastre pelo menos um cliente antes de criar propostas.")
    else:
        mapa_clientes = dict(zip(clientes["nome"], clientes["id"]))
        mapa_espacos = {f"{r['nome']} | cap. {int(r['capacidade'])}": int(r["id"]) for _, r in espacos.iterrows()}
        mapa_tipos = {f"{r['nome']} | cap. sug. {int(r['capacidade_sugerida'])}": int(r["id"]) for _, r in tipos.iterrows()}

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

            st.markdown("#### Formação manual da proposta")
            c13, c14, c15, c16 = st.columns(4)
            valor_locacao = c13.number_input("Locação / pacote principal", min_value=0.0, step=500.0)
            valor_convidados = c14.number_input("Convidados / alimentação", min_value=0.0, step=500.0)
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
                elif existe_conflito(str(data_evento), mapa_espacos[espaco_sel]):
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
                        int(mapa_tipos[tipo_sel]),
                        int(mapa_espacos[espaco_sel]),
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
    df = get_eventos_full()
    if not df.empty:
        view = df.copy()
        view["valor_total"] = view["valor_total"].apply(format_currency)
        view["sinal_pago"] = view["sinal_pago"].apply(format_currency)
        st.dataframe(view, use_container_width=True, hide_index=True)

        opcoes_pdf = {f"{r['codigo']} | {r['titulo']} | {r['cliente']}": int(r["id"]) for _, r in df.iterrows()}
        evento_pdf_sel = st.selectbox("Gerar PDF da proposta", list(opcoes_pdf.keys()))
        pdf_bytes = gerar_pdf_proposta(opcoes_pdf[evento_pdf_sel])
        if pdf_bytes:
            nome_arquivo = f"proposta_{opcoes_pdf[evento_pdf_sel]}.pdf"
            st.download_button("Baixar proposta em PDF", data=pdf_bytes, file_name=nome_arquivo, mime="application/pdf")
    else:
        st.info("Nenhuma proposta cadastrada.")

elif menu == "Agenda Comercial":
    c1, c2, c3 = st.columns(3)
    data_ini = c1.date_input("Data inicial", value=date.today().replace(day=1))
    data_fim = c2.date_input("Data final", value=date.today() + timedelta(days=90))
    espacos_lista = get_espacos()["nome"].tolist()
    filtro_espaco = c3.selectbox("Espaço", ["Todos"] + espacos_lista)

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

            serv_df = get_servicos_evento(evento_id)
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
        det = df[[
            "codigo", "titulo", "cliente", "tipo_evento", "espaco", "data_evento",
            "status_pipeline", "status_operacional", "valor_total", "responsavel_comercial", "responsavel_interno"
        ]].copy()
        det["valor_total_fmt"] = det["valor_total"].apply(format_currency)
        st.dataframe(det.drop(columns=["valor_total"]), use_container_width=True, hide_index=True)
        df_to_csv_download(det, "relatorio_gerencial_quinta_do_conde.csv", "Baixar relatório gerencial")

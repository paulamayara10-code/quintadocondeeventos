import sqlite3
from datetime import date, datetime, timedelta
from io import BytesIO

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

DB_FILE = "eventos_fazenda_v5.db"


# ---------------------------
# Banco
# ---------------------------
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
        SELECT id
        FROM eventos
        WHERE data_evento = ?
          AND espaco_id = ?
          AND status_operacional <> 'Cancelado'
    """
    params = [data_evento, espaco_id]
    if evento_id:
        sql += " AND id <> ?"
        params.append(evento_id)
    return not run_query(sql, tuple(params)).empty


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
    return valor_total, recebido_total if False else receb_total, aberto, desp_total, lucro, margem


# ---------------------------
# Excel backup
# ---------------------------
def exportar_backup_excel():
    clientes_df = run_query("""
        SELECT id AS ID_CLIENTE, nome AS NOME, telefone AS TELEFONE, email AS EMAIL,
               documento AS DOCUMENTO, tipo_cliente AS TIPO, empresa AS EMPRESA,
               origem_lead AS ORIGEM_LEAD, observacoes AS OBSERVACOES
        FROM clientes ORDER BY id
    """)

    eventos_df = run_query("""
        SELECT
            e.id AS ID_EVENTO,
            COALESCE(e.codigo, 'EVT-' || e.id) AS CODIGO,
            e.titulo AS TITULO,
            e.cliente_id AS ID_CLIENTE,
            c.nome AS CLIENTE,
            e.data_evento AS DATA_EVENTO,
            te.nome AS TIPO_EVENTO,
            es.nome AS ESPACO,
            e.quantidade_convidados AS CONVIDADOS,
            e.status_pipeline AS STATUS_PIPELINE,
            e.status_operacional AS STATUS_OPERACIONAL,
            e.valor_locacao AS VALOR_LOCACAO,
            e.valor_convidados AS VALOR_CONVIDADOS,
            e.valor_servicos AS VALOR_SERVICOS,
            e.desconto AS DESCONTO,
            e.valor_total AS VALOR_TOTAL,
            e.sinal_pago AS SINAL_PAGO,
            e.forma_pagamento AS FORMA_PAGAMENTO,
            e.responsavel_comercial AS RESPONSAVEL_COMERCIAL,
            e.responsavel_interno AS RESPONSAVEL_INTERNO,
            e.observacoes AS OBSERVACOES
        FROM eventos e
        LEFT JOIN clientes c ON c.id = e.cliente_id
        LEFT JOIN tipos_evento te ON te.id = e.tipo_evento_id
        LEFT JOIN espacos es ON es.id = e.espaco_id
        ORDER BY e.id
    """)

    servicos_df = run_query("""
        SELECT id AS ID_SERVICO, evento_id AS ID_EVENTO, servico AS SERVICO,
               fornecedor AS FORNECEDOR, valor AS VALOR, observacoes AS OBSERVACOES
        FROM servicos_adicionais ORDER BY id
    """)

    pagamentos_df = run_query("""
        SELECT id AS ID_PAGAMENTO, evento_id AS ID_EVENTO, descricao AS DESCRICAO,
               valor AS VALOR, vencimento AS VENCIMENTO, data_pagamento AS DATA_PAGAMENTO,
               status AS STATUS, forma_pagamento AS FORMA, observacoes AS OBSERVACOES
        FROM pagamentos ORDER BY id
    """)

    despesas_df = run_query("""
        SELECT id AS ID_DESPESA, evento_id AS ID_EVENTO, fornecedor AS FORNECEDOR,
               descricao AS DESCRICAO, valor AS VALOR, vencimento AS VENCIMENTO,
               data_pagamento AS DATA_PAGAMENTO, status AS STATUS, observacoes AS OBSERVACOES
        FROM despesas ORDER BY id
    """)

    estrutura_df = run_query("""
        SELECT id AS ID_ESPACO, nome AS ESPACO, capacidade AS CAPACIDADE, descricao AS DESCRICAO
        FROM espacos WHERE ativo = 1 ORDER BY id
    """)
    tipos_df = run_query("""
        SELECT id AS ID_TIPO, nome AS TIPO_EVENTO, capacidade_sugerida AS CAPACIDADE_SUGERIDA, regras AS REGRAS
        FROM tipos_evento WHERE ativo = 1 ORDER BY id
    """)

    instrucoes_df = pd.DataFrame({
        "ORIENTACAO": [
            "Use este arquivo como backup e padrão de intercâmbio.",
            "A importação do backup substitui a base atual do sistema.",
            "Mantenha os nomes das abas e das colunas exatamente como estão.",
            "A inclusão via sistema permanece ativa normalmente.",
            "Antes de importar, salve uma cópia do backup anterior."
        ]
    })

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        instrucoes_df.to_excel(writer, sheet_name="INSTRUCOES", index=False)
        clientes_df.to_excel(writer, sheet_name="CLIENTES", index=False)
        eventos_df.to_excel(writer, sheet_name="EVENTOS", index=False)
        servicos_df.to_excel(writer, sheet_name="SERVICOS", index=False)
        pagamentos_df.to_excel(writer, sheet_name="PAGAMENTOS", index=False)
        despesas_df.to_excel(writer, sheet_name="DESPESAS", index=False)
        estrutura_df.to_excel(writer, sheet_name="ESPACOS", index=False)
        tipos_df.to_excel(writer, sheet_name="TIPOS_EVENTO", index=False)
    output.seek(0)
    return output.getvalue()


def importar_backup_excel(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)

    obrigatorias = ["CLIENTES", "EVENTOS", "SERVICOS", "PAGAMENTOS", "DESPESAS"]
    faltantes = [aba for aba in obrigatorias if aba not in xls.sheet_names]
    if faltantes:
        raise ValueError(f"Abas obrigatórias ausentes: {', '.join(faltantes)}")

    clientes = pd.read_excel(xls, "CLIENTES").fillna("")
    eventos = pd.read_excel(xls, "EVENTOS").fillna("")
    servicos = pd.read_excel(xls, "SERVICOS").fillna("")
    pagamentos = pd.read_excel(xls, "PAGAMENTOS").fillna("")
    despesas = pd.read_excel(xls, "DESPESAS").fillna("")

    espacos = pd.read_excel(xls, "ESPACOS").fillna("") if "ESPACOS" in xls.sheet_names else pd.DataFrame()
    tipos = pd.read_excel(xls, "TIPOS_EVENTO").fillna("") if "TIPOS_EVENTO" in xls.sheet_names else pd.DataFrame()

    conn = get_conn()
    cur = conn.cursor()

    for tabela in ["servicos_adicionais", "pagamentos", "despesas", "checklist_evento", "eventos", "clientes"]:
        cur.execute(f"DELETE FROM {tabela}")

    if not espacos.empty:
        cur.execute("DELETE FROM espacos")
        for _, r in espacos.iterrows():
            cur.execute("""
                INSERT INTO espacos (id, nome, capacidade, descricao, ativo)
                VALUES (?, ?, ?, ?, 1)
            """, (
                int(r.get("ID_ESPACO")) if str(r.get("ID_ESPACO")).strip() else None,
                str(r.get("ESPACO", "")),
                int(r.get("CAPACIDADE") or 0),
                str(r.get("DESCRICAO", ""))
            ))

    if not tipos.empty:
        cur.execute("DELETE FROM tipos_evento")
        for _, r in tipos.iterrows():
            cur.execute("""
                INSERT INTO tipos_evento (id, nome, capacidade_sugerida, regras, ativo)
                VALUES (?, ?, ?, ?, 1)
            """, (
                int(r.get("ID_TIPO")) if str(r.get("ID_TIPO")).strip() else None,
                str(r.get("TIPO_EVENTO", "")),
                int(r.get("CAPACIDADE_SUGERIDA") or 0),
                str(r.get("REGRAS", ""))
            ))

    mapa_clientes = {}
    for _, r in clientes.iterrows():
        cur.execute("""
            INSERT INTO clientes (id, nome, telefone, email, documento, tipo_cliente, empresa, origem_lead, observacoes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r["ID_CLIENTE"]) if str(r["ID_CLIENTE"]).strip() else None,
            str(r.get("NOME", "")),
            str(r.get("TELEFONE", "")),
            str(r.get("EMAIL", "")),
            str(r.get("DOCUMENTO", "")),
            str(r.get("TIPO", "")),
            str(r.get("EMPRESA", "")),
            str(r.get("ORIGEM_LEAD", "")),
            str(r.get("OBSERVACOES", ""))
        ))
        if str(r["ID_CLIENTE"]).strip():
            mapa_clientes[int(r["ID_CLIENTE"])] = int(r["ID_CLIENTE"])

    mapa_espacos = {row["nome"]: row["id"] for _, row in pd.read_sql_query("SELECT id, nome FROM espacos", conn).iterrows()}
    mapa_tipos = {row["nome"]: row["id"] for _, row in pd.read_sql_query("SELECT id, nome FROM tipos_evento", conn).iterrows()}

    for _, r in eventos.iterrows():
        cliente_id = int(r["ID_CLIENTE"]) if str(r.get("ID_CLIENTE", "")).strip() else None
        espaco_id = mapa_espacos.get(str(r.get("ESPACO", "")).strip())
        tipo_id = mapa_tipos.get(str(r.get("TIPO_EVENTO", "")).strip())

        cur.execute("""
            INSERT INTO eventos (
                id, codigo, titulo, cliente_id, tipo_evento_id, espaco_id, data_evento, hora_inicio, hora_fim,
                quantidade_convidados, status_pipeline, status_operacional, valor_locacao, valor_convidados,
                valor_servicos, desconto, valor_total, sinal_pago, forma_pagamento, responsavel_comercial,
                responsavel_interno, observacoes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r["ID_EVENTO"]) if str(r["ID_EVENTO"]).strip() else None,
            str(r.get("CODIGO", "")),
            str(r.get("TITULO", "")),
            cliente_id,
            tipo_id,
            espaco_id,
            str(r.get("DATA_EVENTO", ""))[:10],
            "",
            "",
            int(r.get("CONVIDADOS") or 0),
            str(r.get("STATUS_PIPELINE", "")),
            str(r.get("STATUS_OPERACIONAL", "")),
            float(r.get("VALOR_LOCACAO") or 0),
            float(r.get("VALOR_CONVIDADOS") or 0),
            float(r.get("VALOR_SERVICOS") or 0),
            float(r.get("DESCONTO") or 0),
            float(r.get("VALOR_TOTAL") or 0),
            float(r.get("SINAL_PAGO") or 0),
            str(r.get("FORMA_PAGAMENTO", "")),
            str(r.get("RESPONSAVEL_COMERCIAL", "")),
            str(r.get("RESPONSAVEL_INTERNO", "")),
            str(r.get("OBSERVACOES", ""))
        ))

    for _, r in servicos.iterrows():
        cur.execute("""
            INSERT INTO servicos_adicionais (evento_id, servico, fornecedor, valor, observacoes)
            VALUES (?, ?, ?, ?, ?)
        """, (
            int(r.get("ID_EVENTO")),
            str(r.get("SERVICO", "")),
            str(r.get("FORNECEDOR", "")),
            float(r.get("VALOR") or 0),
            str(r.get("OBSERVACOES", ""))
        ))

    for _, r in pagamentos.iterrows():
        cur.execute("""
            INSERT INTO pagamentos (evento_id, descricao, valor, vencimento, data_pagamento, status, forma_pagamento, observacoes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r.get("ID_EVENTO")),
            str(r.get("DESCRICAO", "")),
            float(r.get("VALOR") or 0),
            str(r.get("VENCIMENTO", ""))[:10],
            str(r.get("DATA_PAGAMENTO", ""))[:10] if str(r.get("DATA_PAGAMENTO", "")).strip() else None,
            str(r.get("STATUS", "")),
            str(r.get("FORMA", "")),
            str(r.get("OBSERVACOES", ""))
        ))

    for _, r in despesas.iterrows():
        cur.execute("""
            INSERT INTO despesas (evento_id, fornecedor, descricao, valor, vencimento, data_pagamento, status, observacoes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(r.get("ID_EVENTO")),
            str(r.get("FORNECEDOR", "")),
            str(r.get("DESCRICAO", "")),
            float(r.get("VALOR") or 0),
            str(r.get("VENCIMENTO", ""))[:10],
            str(r.get("DATA_PAGAMENTO", ""))[:10] if str(r.get("DATA_PAGAMENTO", "")).strip() else None,
            str(r.get("STATUS", "")),
            str(r.get("OBSERVACOES", ""))
        ))

    evento_ids = [r[0] for r in cur.execute("SELECT id FROM eventos").fetchall()]
    for evento_id in evento_ids:
        existentes = [r[0] for r in cur.execute("SELECT item FROM checklist_evento WHERE evento_id = ?", (evento_id,)).fetchall()]
        for item in [
            "Visita realizada", "Proposta enviada", "Contrato assinado", "Sinal recebido",
            "Cardápio definido", "Decoração alinhada", "DJ/Banda confirmado",
            "Fotografia alinhada", "Equipe de apoio escalada", "Montagem programada",
            "Desmontagem programada"
        ]:
            if item not in existentes:
                cur.execute("""
                    INSERT INTO checklist_evento (evento_id, item, concluido, observacoes)
                    VALUES (?, ?, 0, '')
                """, (evento_id, item))

    conn.commit()
    conn.close()


# ---------------------------
# PDF
# ---------------------------
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
    c.setStrokeColor(colors.HexColor("#DCCFBE"))
    c.roundRect(x, y, w, h, 10, stroke=1, fill=1)
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

    c.setFillColor(colors.HexColor("#F8F4EE"))
    c.rect(0, 0, width, height, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#5A402C"))
    c.roundRect(margem, height - 4.1*cm, usable_w, 2.5*cm, 16, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(margem + 16, height - 2.2*cm, "Quinta do Conde")
    c.setFont("Helvetica", 11)
    c.drawString(margem + 16, height - 2.9*cm, "Proposta comercial de evento")

    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margem, height - 5.0*cm, str(evento.get("titulo", "")))
    c.setFont("Helvetica", 10)
    data_txt = pd.to_datetime(evento.get("data_evento")).strftime("%d/%m/%Y") if evento.get("data_evento") else ""
    c.drawString(margem, height - 5.6*cm, f"Código {evento.get('codigo', '')} | Data do evento {data_txt}")

    box_y = height - 9.4 * cm
    box_h = 3.1 * cm
    gap = 0.35 * cm
    box_w = (usable_w - gap) / 2

    draw_box(c, margem, box_y, box_w, box_h, "Dados do cliente", [
        f"Cliente: {evento.get('cliente_nome') or '-'}",
        f"Telefone: {evento.get('cliente_telefone') or '-'}",
        f"E-mail: {evento.get('cliente_email') or '-'}",
    ])
    draw_box(c, margem + box_w + gap, box_y, box_w, box_h, "Dados do evento", [
        f"Tipo: {evento.get('tipo_evento_nome') or '-'}",
        f"Espaço: {evento.get('espaco_nome') or '-'}",
        f"Horário: {evento.get('hora_inicio') or '-'} às {evento.get('hora_fim') or '-'}",
    ])

    box_y2 = box_y - box_h - 0.35*cm
    draw_box(c, margem, box_y2, box_w, box_h, "Resumo comercial", [
        f"Convidados: {int(evento.get('quantidade_convidados') or 0)}",
        f"Forma de pagamento: {evento.get('forma_pagamento') or '-'}",
        f"Status: {evento.get('status_operacional') or '-'}",
    ])
    draw_box(c, margem + box_w + gap, box_y2, box_w, box_h, "Composição da proposta", [
        f"Locação: {format_currency(evento.get('valor_locacao') or 0)}",
        f"Convidados/alimentação: {format_currency(evento.get('valor_convidados') or 0)}",
        f"Serviços adicionais: {format_currency(evento.get('valor_servicos') or 0)}",
    ])

    total_y = box_y2 - 2.15*cm
    c.setFillColor(colors.HexColor("#E9DED0"))
    c.roundRect(margem, total_y, usable_w, 1.6*cm, 10, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#5A402C"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margem + 16, total_y + 0.95*cm, "Valor total da proposta")
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(margem + usable_w - 16, total_y + 0.9*cm, format_currency(evento.get("valor_total") or 0))

    top = total_y - 0.8*cm
    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margem, top, "Itens da proposta")

    table_y = top - 0.7*cm
    row_h = 0.8*cm

    def row(y, descricao, valor):
        c.setStrokeColor(colors.HexColor("#DCCFBE"))
        c.line(margem, y, margem + usable_w, y)
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.black)
        c.drawString(margem + 4, y - 14, descricao)
        c.drawRightString(margem + usable_w - 8, y - 14, format_currency(valor))

    c.setFillColor(colors.HexColor("#7A5A43"))
    c.rect(margem, table_y - row_h + 4, usable_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margem + 4, table_y - 14, "Descrição")
    c.drawRightString(margem + usable_w - 8, table_y - 14, "Valor")

    y = table_y - row_h
    row(y, "Locação / pacote principal", evento.get("valor_locacao") or 0); y -= row_h
    row(y, "Convidados / alimentação", evento.get("valor_convidados") or 0); y -= row_h
    row(y, "Serviços adicionais", evento.get("valor_servicos") or 0); y -= row_h
    row(y, "Desconto", -(evento.get("desconto") or 0)); y -= row_h
    c.line(margem, y, margem + usable_w, y)
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
            descricao = f"- {s['servico']} | Fornecedor: {s['fornecedor'] or '-'} | Valor: {format_currency(s['valor'])}"
            lines = wrap_text(c, descricao, usable_w, "Helvetica", 10)
            for line in lines:
                c.setFont("Helvetica", 10)
                c.drawString(margem, y, line)
                y -= 12
            y -= 4

    obs = evento.get("observacoes") or "Proposta sujeita a alinhamento final de escopo, disponibilidade e condições comerciais."
    c.setFillColor(colors.HexColor("#3F2F20"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margem, max(y, 5.3*cm), "Observações")
    y = max(y, 5.3*cm) - 0.45*cm

    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#DCCFBE"))
    c.roundRect(margem, y - 3.2*cm + 6, usable_w, 3.2*cm, 10, fill=1, stroke=1)
    obs_lines = wrap_text(c, obs, usable_w - 24, "Helvetica", 10)
    text_y = y - 16
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    for line in obs_lines[:8]:
        c.drawString(margem + 12, text_y, line)
        text_y -= 12

    c.setFillColor(colors.HexColor("#7A5A43"))
    c.setFont("Helvetica", 9)
    c.drawString(margem, 1.4*cm, "Quinta do Conde - Proposta comercial gerada pelo sistema")
    c.drawRightString(width - margem, 1.4*cm, datetime.now().strftime("Gerado em %d/%m/%Y %H:%M"))

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="Quinta do Conde | Gestão Comercial de Eventos", page_icon="🏡", layout="wide")
init_db()

st.markdown("""
<style>
.stApp {
    background:
        linear-gradient(180deg, rgba(250,247,242,1) 0%, rgba(243,236,227,1) 70%, rgba(237,228,216,1) 100%);
}
.block-container { padding-top: 1rem; }
h1, h2, h3 { color: #3F2F20; }
[data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #DCCFBE;
    border-radius: 18px;
    padding: 10px;
    box-shadow: 0 2px 10px rgba(90, 64, 44, .05);
}
.qc-banner {
    background: linear-gradient(120deg, #5A402C 0%, #7A5A43 45%, #A38666 100%);
    color: #fff;
    padding: 20px 24px;
    border-radius: 24px;
    margin-bottom: 18px;
    box-shadow: 0 8px 24px rgba(63,47,32,.15);
}
.qc-note {
    background: rgba(255,255,255,.75);
    border: 1px solid #DCCFBE;
    border-radius: 16px;
    padding: 12px 14px;
    color: #5C4837;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="qc-banner">
    <h1 style="margin:0;">🏡 Quinta do Conde</h1>
    <div style="font-size:1.05rem; margin-top:6px;">Sistema Comercial + Gestão de Eventos</div>
    <div style="margin-top:6px; opacity:.92;">Cadastro pelo sistema, backup padronizado em Excel e proposta em PDF.</div>
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
        "Backup Excel",
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

    if not pipeline_df.empty:
        st.subheader("Pipeline comercial")
        view = pipeline_df.copy()
        view["valor"] = view["valor"].apply(format_currency)
        st.dataframe(view, use_container_width=True, hide_index=True)
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

        if st.form_submit_button("Salvar cliente"):
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
        FROM clientes ORDER BY nome
    """)
    if not clientes_df.empty:
        st.dataframe(clientes_df, use_container_width=True, hide_index=True)
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
            if st.form_submit_button("Salvar espaço") and nome.strip():
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
            if st.form_submit_button("Salvar tipo") and nome.strip():
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

            if st.form_submit_button("Salvar proposta / evento"):
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
            st.download_button("Baixar proposta em PDF", data=pdf_bytes, file_name=f"proposta_{opcoes_pdf[evento_pdf_sel]}.pdf", mime="application/pdf")
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

elif menu == "Backup Excel":
    st.subheader("Backup e restauração em Excel")
    st.markdown("""
    <div class="qc-note">
        A inclusão e manutenção dos dados continua sendo feita pelo sistema.  
        O Excel funciona como backup padronizado: você exporta a base e, se precisar, importa depois no mesmo formato.
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Exportar backup")
        st.write("Gera um arquivo Excel único com as abas padronizadas do sistema.")
        excel_bytes = exportar_backup_excel()
        nome = f"backup_quinta_do_conde_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        st.download_button("Baixar backup em Excel", data=excel_bytes, file_name=nome, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with col2:
        st.markdown("### Importar backup")
        st.write("Restaura a base a partir do mesmo layout exportado pelo sistema.")
        arquivo = st.file_uploader("Selecione o backup .xlsx", type=["xlsx"])
        confirmar = st.checkbox("Entendo que a importação substituirá a base atual do sistema.")
        if arquivo and confirmar and st.button("Importar backup agora"):
            try:
                importar_backup_excel(arquivo)
                st.success("Backup importado com sucesso.")
            except Exception as e:
                st.error(f"Não foi possível importar o arquivo: {e}")

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

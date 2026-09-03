import io
import os
import sqlite3
import datetime
import pandas as pd
import streamlit as st
from PIL import Image
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage, Table, TableStyle

# ---------------------------------------------------------
# Banco de Dados Local (SQLite) com Migração Automática
# ---------------------------------------------------------
DB_FILE = "sst_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario TEXT PRIMARY KEY,
            senha TEXT NOT NULL,
            perfil TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS relatorios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            empresa TEXT NOT NULL,
            inspetor TEXT NOT NULL,
            total_itens INTEGER NOT NULL,
            multa_min REAL NOT NULL,
            multa_max REAL NOT NULL,
            economia_min REAL NOT NULL DEFAULT 0,
            economia_max REAL NOT NULL DEFAULT 0,
            pdf_bytes BLOB NOT NULL
        )
    """)
    
    # Migração segura para bases existentes sem quebrar dados
    c.execute("PRAGMA table_info(relatorios)")
    colunas_existentes = [col[1] for col in c.fetchall()]
    
    if "economia_min" not in colunas_existentes:
        c.execute("ALTER TABLE relatorios ADD COLUMN economia_min REAL NOT NULL DEFAULT 0")
    if "economia_max" not in colunas_existentes:
        c.execute("ALTER TABLE relatorios ADD COLUMN economia_max REAL NOT NULL DEFAULT 0")

    c.execute("SELECT usuario FROM usuarios WHERE usuario = 'admin'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios (usuario, senha, perfil) VALUES (?, ?, ?)", ("admin", "1234", "Admin"))
        
    conn.commit()
    conn.close()

init_db()

def autenticar_usuario(usuario, senha):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT usuario, perfil FROM usuarios WHERE usuario = ? AND senha = ?", (usuario, senha))
    row = c.fetchone()
    conn.close()
    return row

def listar_usuarios():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT usuario, perfil FROM usuarios ORDER BY usuario ASC")
    rows = c.fetchall()
    conn.close()
    return rows

def criar_usuario_db(usuario, senha, perfil):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO usuarios (usuario, senha, perfil) VALUES (?, ?, ?)", (usuario, senha, perfil))
        conn.commit()
        conn.close()
        return True, "Usuário cadastrado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Nome de usuário já existe!"

def excluir_usuario_db(usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE usuario = ?", (usuario,))
    conn.commit()
    conn.close()

def salvar_relatorio_db(data_str, empresa, inspetor, total_itens, multa_min, multa_max, econ_min, econ_max, pdf_bytes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO relatorios (data, empresa, inspetor, total_itens, multa_min, multa_max, economia_min, economia_max, pdf_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (data_str, empresa, inspetor, total_itens, multa_min, multa_max, econ_min, econ_max, pdf_bytes))
    conn.commit()
    conn.close()

def listar_relatorios():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, data, empresa, inspetor, total_itens, multa_min, multa_max, economia_min, economia_max FROM relatorios ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def obter_pdf_relatorio(relatorio_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT pdf_bytes, empresa, data FROM relatorios WHERE id = ?", (relatorio_id,))
    row = c.fetchone()
    conn.close()
    return row

def verificar_login():
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
        st.session_state.usuario_logado = ""
        st.session_state.perfil_logado = ""

    if st.session_state.autenticado:
        return True

    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔒 Acesso Restrito - Vistoria SST")
        st.caption("Entre com suas credenciais de fiscalização")
        with st.form("form_login"):
            usuario_in = st.text_input("Usuário:").strip()
            senha_in = st.text_input("Senha:", type="password").strip()
            entrar = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)
            if entrar:
                user_data = autenticar_usuario(usuario_in, senha_in)
                if user_data:
                    st.session_state.autenticado = True
                    st.session_state.usuario_logado = user_data[0]
                    st.session_state.perfil_logado = user_data[1]
                    st.success("Autenticado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha inválidos.")
    return False

# ---------------------------------------------------------
# Tabelas Oficiais NR 28 (Segurança e Medicina)
# ---------------------------------------------------------
TABELA_MULTAS_SEGURANCA = {
    "1 a 10":   {"I1": (630, 1120),   "I2": (1121, 1680),  "I3": (1681, 2240),  "I4": (2241, 2792)},
    "11 a 25":  {"I1": (1121, 1400),  "I2": (1401, 1960),  "I3": (1961, 2520),  "I4": (2521, 3360)},
    "26 a 50":  {"I1": (1401, 1680),  "I2": (1681, 2240),  "I3": (2241, 3080),  "I4": (3081, 3920)},
    "51 a 100": {"I1": (1681, 1960),  "I2": (1961, 2520),  "I3": (2521, 3360),  "I4": (3361, 4480)},
    "101 a 250":{"I1": (1961, 2240),  "I2": (2241, 3080),  "I3": (3081, 3920),  "I4": (3921, 5040)},
    "251 a 500":{"I1": (2241, 2520),  "I2": (2521, 3360),  "I3": (3361, 4480),  "I4": (4481, 5600)},
    "501 a 1000":{"I1": (2521, 2800), "I2": (2801, 3920), "I3": (3921, 5040),  "I4": (5041, 6304)},
    "Mais de 1000":{"I1": (2801, 3360),"I2": (3921, 4480), "I3": (5041, 5600), "I4": (6305, 6708)}
}

TABELA_MULTAS_MEDICINA = {
    "1 a 10":   {"I1": (378, 630),    "I2": (631, 1120),   "I3": (1121, 1680),  "I4": (1681, 2240)},
    "11 a 25":  {"I1": (631, 840),    "I2": (841, 1400),   "I3": (1401, 1960),  "I4": (1961, 2520)},
    "26 a 50":  {"I1": (841, 1120),   "I2": (1121, 1680),  "I3": (1681, 2240),  "I4": (2241, 3080)},
    "51 a 100": {"I1": (1121, 1400),  "I2": (1401, 1960),  "I3": (1961, 2520),  "I4": (2521, 3360)},
    "101 a 250":{"I1": (1401, 1680),  "I2": (1681, 2240),  "I3": (2241, 3080),  "I4": (3081, 3920)},
    "251 a 500":{"I1": (1681, 1960),  "I2": (1961, 2520),  "I3": (2521, 3360),  "I4": (3361, 4480)},
    "501 a 1000":{"I1": (1961, 2240), "I2": (2241, 3080), "I3": (3081, 3920),  "I4": (3921, 5040)},
    "Mais de 1000":{"I1": (2241, 2520),"I2": (3081, 3360), "I3": (3921, 4480), "I4": (5041, 5493)}
}

def carregar_dados_nr():
    caminho = "itens_nr28.csv"
    if os.path.exists(caminho):
        return pd.read_csv(caminho, dtype=str)
    else:
        return pd.DataFrame([
            {"nr": "NR 01", "item": "1.5.3.1", "descricao": "Deixar de elaborar ou de implementar o PGR", "infracao": "I4", "tipo": "S", "categoria": "PGR"},
            {"nr": "NR 06", "item": "6.3.1", "descricao": "Não fornecer aos empregados gratuitamente EPI adequado ao risco", "infracao": "I4", "tipo": "S", "categoria": "EPI"},
            {"nr": "NR 10", "item": "10.2.8.1", "descricao": "Não priorizar medidas de proteção coletiva em instalações elétricas", "infracao": "I4", "tipo": "S", "categoria": "Elétrica"},
            {"nr": "NR 12", "item": "12.5.1", "descricao": "Zonas de perigo de máquinas desprovidas de proteções físicas", "infracao": "I4", "tipo": "S", "categoria": "Máquinas"},
            {"nr": "NR 18", "item": "18.10.1", "descricao": "Falta de proteção contra quedas em aberturas no piso e periferias", "infracao": "I4", "tipo": "S", "categoria": "Construção"},
            {"nr": "NR 35", "item": "35.2.1", "descricao": "Trabalho em altura sem planejamento, Análise de Risco ou PT", "infracao": "I4", "tipo": "S", "categoria": "Altura"}
        ])

df_nr_base = carregar_dados_nr()

def calcular_multa(grau, faixa_func, tipo):
    tabela = TABELA_MULTAS_MEDICINA if tipo == "M" else TABELA_MULTAS_SEGURANCA
    return tabela.get(faixa_func, {}).get(grau, (0, 0))

def formata_brl(valor):
    return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# ---------------------------------------------------------
# Gráficos com Matplotlib
# ---------------------------------------------------------
def gerar_grafico_multas(lista_evidencias):
    multa_total_min = sum(e['valor_min'] for e in lista_evidencias if e['status'] == "Não Conformidade")
    multa_total_max = sum(e['valor_max'] for e in lista_evidencias if e['status'] == "Não Conformidade")
    econ_total_min = sum(e['valor_min'] for e in lista_evidencias if e['status'] == "Conformidade")
    econ_total_max = sum(e['valor_max'] for e in lista_evidencias if e['status'] == "Conformidade")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.4), gridspec_kw={'width_ratios': [1.2, 1]})

    rotulos = [f"#{i} ({e['nr']})" for i, e in enumerate(lista_evidencias, 1)]
    cores = ['#EF4444' if e['status'] == "Não Conformidade" else '#10B981' for e in lista_evidencias]
    valores_max = [e['valor_max'] for e in lista_evidencias]

    ax1.bar(range(len(rotulos)), valores_max, color=cores, width=0.55)
    ax1.set_ylabel('Impacto Máximo (R$)', fontsize=8)
    ax1.set_title('Valores por Apontamento', fontsize=9.5, fontweight='bold', pad=8)
    ax1.set_xticks(range(len(rotulos)))
    ax1.set_xticklabels(rotulos, fontsize=7.5, rotation=25, ha='right')
    ax1.grid(axis='y', linestyle='--', alpha=0.3)

    cats = ['Multas\n(Risco)', 'Economia\n(Evitado)']
    mins = [multa_total_min, econ_total_min]
    maxs = [multa_total_max, econ_total_max]
    x_pos = [0, 1]
    w = 0.35

    ax2.bar([p - w/2 for p in x_pos], mins, width=w, label='Mínimo', color=['#F87171', '#34D399'])
    ax2.bar([p + w/2 for p in x_pos], maxs, width=w, label='Máximo', color=['#DC2626', '#059669'])
    ax2.set_title('Balanço Financeiro Geral', fontsize=9.5, fontweight='bold', pad=8)
    ax2.set_xticks(x_pos)
    ax2.set_xticklabels(cats, fontsize=8.5, fontweight='bold')
    ax2.legend(frameon=True, fontsize=7.5)
    ax2.grid(axis='y', linestyle='--', alpha=0.3)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='PNG', dpi=180)
    plt.close(fig)
    buf.seek(0)
    return buf

# ---------------------------------------------------------
# Gerador de Relatório PDF Completo
# ---------------------------------------------------------
def gerar_pdf_completo(dados_gerais, lista_evidencias, logo_pil=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    elementos = []

    titulo_style = ParagraphStyle('T1', parent=styles['Heading1'], fontSize=15, textColor=colors.HexColor('#0F172A'), leading=18)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor('#475569'), leading=11)

    cell_label = ParagraphStyle('CellLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1E293B'), leading=12)
    cell_value = ParagraphStyle('CellValue', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'), leading=12)
    
    cell_th = ParagraphStyle('CellTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=1, leading=10)
    cell_td = ParagraphStyle('CellTD', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#0F172A'), leading=10)
    cell_td_center = ParagraphStyle('CellTDCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#0F172A'), alignment=1, leading=10)
    cell_td_total = ParagraphStyle('CellTDTotal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#0F172A'), alignment=1, leading=10)

    # 1. Cabeçalho com Logomarca
    texto_cabecalho = [
        Paragraph("Relatório Técnico de Vistoria, Riscos e Conformidades SST (NR 28)", titulo_style),
        Spacer(1, 4),
        Paragraph(f"<b>Data da Inspeção:</b> {dados_gerais['data']} | <b>Responsável Técnico:</b> {dados_gerais['inspetor']}", sub_style)
    ]

    if logo_pil is not None:
        logo_buf = io.BytesIO()
        logo_pil.save(logo_buf, format='PNG')
        logo_buf.seek(0)
        img_logo = ReportLabImage(logo_buf, width=110, height=48)
        cabecalho_tabela = [[img_logo, texto_cabecalho]]
        t_header = Table(cabecalho_tabela, colWidths=[120, 403])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (1, 0), (1, 0), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        elementos.append(t_header)
    else:
        elementos.extend(texto_cabecalho)
        elementos.append(Spacer(1, 10))

    total_multa_min = sum(e['valor_min'] for e in lista_evidencias if e['status'] == "Não Conformidade")
    total_multa_max = sum(e['valor_max'] for e in lista_evidencias if e['status'] == "Não Conformidade")
    total_econ_min = sum(e['valor_min'] for e in lista_evidencias if e['status'] == "Conformidade")
    total_econ_max = sum(e['valor_max'] for e in lista_evidencias if e['status'] == "Conformidade")

    qtd_nc = sum(1 for e in lista_evidencias if e['status'] == "Não Conformidade")
    qtd_conf = sum(1 for e in lista_evidencias if e['status'] == "Conformidade")

    # 2. Resumo Executivo
    info_cabecalho = [
        [Paragraph("Empresa Atendida (Cliente):", cell_label), Paragraph(dados_gerais['empresa_cliente'], cell_value)],
        [Paragraph("Faixa de Funcionários:", cell_label), Paragraph(dados_gerais['faixa_func'], cell_value)],
        [Paragraph("Quadro de Apontamentos:", cell_label), Paragraph(f"<b>{qtd_nc}</b> Não Conformidade(s)  |  <b>{qtd_conf}</b> Boa(s) Prática(s) / Conformidade(s)", cell_value)],
        [Paragraph("Passivo Fiscal em Risco (Multas):", cell_label), Paragraph(f"<font color='#B91C1C'><b>{formata_brl(total_multa_min)} a {formata_brl(total_multa_max)}</b></font>", cell_value)],
        [Paragraph("Economia Gerada (Risco Evitado):", cell_label), Paragraph(f"<font color='#047857'><b>{formata_brl(total_econ_min)} a {formata_brl(total_econ_max)}</b></font>", cell_value)]
    ]
    t_info = Table(info_cabecalho, colWidths=[180, 343])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1F5F9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos.append(t_info)
    elementos.append(Spacer(1, 14))

    # 3. Detalhamento dos Apontamentos com Campos Separados
    for idx, ev in enumerate(lista_evidencias, start=1):
        eh_conforme = (ev['status'] == "Conformidade")
        cor_status = "#059669" if eh_conforme else "#DC2626"
        tag_status = "CONFORMIDADE (BOA PRÁTICA)" if eh_conforme else f"NÃO CONFORMIDADE (PRIORIDADE {ev.get('prioridade', 'Média').upper()})"
        rotulo_valor = "Economia Gerada (Multa Evitada):" if eh_conforme else "Risco de Multa Aplicável (NR 28):"
        rotulo_acao = "Conduta / Padrão Adotado:" if eh_conforme else "Ação Corretiva Recomendada:"

        titulo_ev = ParagraphStyle(
            f'Ev_{idx}',
            parent=styles['Heading2'],
            fontSize=10.5,
            textColor=colors.HexColor(cor_status),
            spaceBefore=6,
            spaceAfter=4
        )
        elementos.append(Paragraph(f"#{idx} - [{tag_status}] - {ev['nr']} (Item {ev['item_nr']})", titulo_ev))

        detalhes_ev = [
            [Paragraph("Norma & Categoria:", cell_label), Paragraph(f"{ev['nr']} — {ev['categoria']}", cell_value)],
            [Paragraph("Item de Referência:", cell_label), Paragraph(ev['item_nr'], cell_value)],
            [Paragraph("Enquadramento NR 28:", cell_label), Paragraph(f"{ev['descricao']} (Grau {ev['infracao']} - {'Medicina' if ev['tipo']=='M' else 'Segurança'})", cell_value)],
            [Paragraph(rotulo_valor, cell_label), Paragraph(f"<b>{formata_brl(ev['valor_min'])} a {formata_brl(ev['valor_max'])}</b>", cell_value)],
            [Paragraph("Descrição do Cenário:", cell_label), Paragraph(ev['descricao_cenario'], cell_value)],
            [Paragraph(rotulo_acao, cell_label), Paragraph(ev['acao_corretiva'], cell_value)]
        ]
        if not eh_conforme:
            cor_pri = "#DC2626" if ev.get('prioridade') == "Alta" else ("#D97706" if ev.get('prioridade') == "Média" else "#059669")
            detalhes_ev.append([
                Paragraph("Grau de Prioridade:", cell_label),
                Paragraph(f"<font color='{cor_pri}'><b>{ev.get('prioridade', 'Média')}</b></font>", cell_value)
            ])

        t_ev = Table(detalhes_ev, colWidths=[160, 363])
        bg_card = '#F0FDF4' if eh_conforme else '#FEF2F2'
        borda_card = '#BBF7D0' if eh_conforme else '#FECACA'

        t_ev.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_card)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor(borda_card)),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        elementos.append(t_ev)
        elementos.append(Spacer(1, 6))

        if ev['imagens']:
            fotos_formatadas = []
            linha_atual = []
            for img in ev['imagens']:
                img_buf = io.BytesIO()
                img.save(img_buf, format='JPEG')
                img_buf.seek(0)
                rl_img = ReportLabImage(img_buf, width=250, height=170)
                linha_atual.append(rl_img)
                if len(linha_atual) == 2:
                    fotos_formatadas.append(linha_atual)
                    linha_atual = []
            if linha_atual:
                linha_atual.append("")
                fotos_formatadas.append(linha_atual)

            t_fotos = Table(fotos_formatadas, colWidths=[261, 262])
            t_fotos.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
            ]))
            elementos.append(t_fotos)

        elementos.append(Spacer(1, 10))

    # 4. Análise Gráfica
    elementos.append(Paragraph("<b>4. Análise Gráfica: Riscos de Multas vs Economia Gerada</b>", styles['Heading3']))
    elementos.append(Spacer(1, 6))
    grafico_buf = gerar_grafico_multas(lista_evidencias)
    elementos.append(ReportLabImage(grafico_buf, width=490, height=220))
    elementos.append(Spacer(1, 14))

    # 5. Apuração Financeira Consolidada
    elementos.append(Paragraph("<b>5. Balanço Financeiro das Multas e Economia (NR 28)</b>", styles['Heading3']))
    elementos.append(Spacer(1, 6))

    dados_conclusao = [
        [
            Paragraph("Item", cell_th),
            Paragraph("Situação", cell_th),
            Paragraph("Norma / Infração", cell_th),
            Paragraph("Grau", cell_th),
            Paragraph("Valor Mínimo", cell_th),
            Paragraph("Valor Máximo", cell_th)
        ]
    ]

    for idx, ev in enumerate(lista_evidencias, 1):
        eh_nc = (ev['status'] == "Não Conformidade")
        tag_t = "<font color='#DC2626'><b>Não Conf.</b></font>" if eh_nc else "<font color='#059669'><b>Conforme</b></font>"
        desc_curta = f"{ev['nr']} ({ev['item_nr']})"
        dados_conclusao.append([
            Paragraph(f"#{idx}", cell_td_center),
            Paragraph(tag_t, cell_td_center),
            Paragraph(desc_curta, cell_td),
            Paragraph(f"{ev['infracao']} ({ev['tipo']})", cell_td_center),
            Paragraph(formata_brl(ev['valor_min']), cell_td_center),
            Paragraph(formata_brl(ev['valor_max']), cell_td_center)
        ])

    dados_conclusao.append([
        Paragraph("TOTAL", cell_td_total),
        Paragraph("MULTAS EM RISCO", cell_td_total),
        Paragraph(f"{qtd_nc} apontamento(s)", cell_td_center),
        Paragraph("-", cell_td_total),
        Paragraph(formata_brl(total_multa_min), cell_td_total),
        Paragraph(formata_brl(total_multa_max), cell_td_total)
    ])
    dados_conclusao.append([
        Paragraph("TOTAL", cell_td_total),
        Paragraph("ECONOMIA GERADA", cell_td_total),
        Paragraph(f"{qtd_conf} boa(s) prática(s)", cell_td_center),
        Paragraph("-", cell_td_total),
        Paragraph(formata_brl(total_econ_min), cell_td_total),
        Paragraph(formata_brl(total_econ_max), cell_td_total)
    ])

    t_final = Table(dados_conclusao, colWidths=[35, 75, 153, 60, 100, 100])
    t_final.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -2), (-1, -2), colors.HexColor('#FEE2E2')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DCFCE7')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_final)
    elementos.append(Spacer(1, 14))

    # 6. Plano de Ação
    elementos.append(Paragraph("<b>6. Plano de Ação e Cronograma de Regularização (Pós-Vistoria)</b>", styles['Heading3']))
    elementos.append(Paragraph("<i>Quadro de intervenção técnica para saneamento das não conformidades identificadas:</i>", sub_style))
    elementos.append(Spacer(1, 4))

    dados_plano = [
        [
            Paragraph("Item", cell_th),
            Paragraph("Norma / Item", cell_th),
            Paragraph("Cenário Observado", cell_th),
            Paragraph("Ação Corretiva", cell_th),
            Paragraph("Prioridade", cell_th),
            Paragraph("Prazo Limite", cell_th)
        ]
    ]

    itens_nc = [e for e in lista_evidencias if e['status'] == "Não Conformidade"]
    if itens_nc:
        for idx, ev in enumerate(itens_nc, 1):
            cor_p = "#DC2626" if ev.get('prioridade') == "Alta" else ("#D97706" if ev.get('prioridade') == "Média" else "#059669")
            tag_pri = f"<font color='{cor_p}'><b>{ev.get('prioridade', 'Média')}</b></font>"
            
            dados_plano.append([
                Paragraph(f"#{idx}", cell_td_center),
                Paragraph(f"<b>{ev['nr']}</b><br/>{ev['item_nr']}", cell_td),
                Paragraph(ev['descricao_cenario'], cell_td),
                Paragraph(ev['acao_corretiva'], cell_td),
                Paragraph(tag_pri, cell_td_center),
                Paragraph("___/___/______", cell_td_center)
            ])

        t_plano = Table(dados_plano, colWidths=[30, 95, 148, 110, 70, 70])
        t_plano.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        elementos.append(t_plano)
    else:
        elementos.append(Paragraph("<font color='#059669'><b>Parabéns! Não foram identificadas não conformidades nesta vistoria. Nenhum plano de ação corretivo necessário.</b></font>", cell_value))

    doc.build(elementos)
    buffer.seek(0)
    return buffer

# ---------------------------------------------------------
# Interface Streamlit
# ---------------------------------------------------------
st.set_page_config(page_title="Vistoria SST - NR 28", layout="centered")

if not verificar_login():
    st.stop()

# Navegação Lateral
with st.sidebar:
    st.markdown(f"👤 Usuário: **{st.session_state.usuario_logado}** (`{st.session_state.perfil_logado}`)")
    if st.button("🚪 Sair (Logout)", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.usuario_logado = ""
        st.session_state.perfil_logado = ""
        st.rerun()

    st.markdown("---")
    opcoes_menu = ["📋 Nova Vistoria"]
    if st.session_state.perfil_logado == "Admin":
        opcoes_menu.append("⚙️ Painel de Administração")
    
    aba_selecionada = st.radio("Menu de Navegação:", opcoes_menu)

    st.markdown("---")
    st.subheader("🏢 Logomarca do Laudo")
    logo_upload = st.file_uploader("Subir Logo (PNG/JPG):", type=["png", "jpg", "jpeg"])
    logo_para_relatorio = None
    if logo_upload:
        logo_para_relatorio = Image.open(logo_upload)
        st.image(logo_para_relatorio, caption="Pré-visualização", width=140)
    elif os.path.exists("logo.png"):
        logo_para_relatorio = Image.open("logo.png")
        st.image(logo_para_relatorio, caption="Logo padrão (logo.png)", width=140)

# =========================================================
# ABA 1: PAINEL DE ADMINISTRAÇÃO
# =========================================================
if aba_selecionada == "⚙️ Painel de Administração":
    st.title("⚙️ Painel de Administração do Sistema")
    st.write("Gerencie os usuários e acesse o histórico completo de vistorias.")

    tab_usuarios, tab_relatorios = st.tabs(["👥 Gerenciar Usuários", "📂 Histórico de Relatórios Realizados"])

    with tab_usuarios:
        st.subheader("Usuários Cadastrados")
        usuarios_atuais = listar_usuarios()
        df_users = pd.DataFrame(usuarios_atuais, columns=["Nome de Usuário", "Perfil de Acesso"])
        st.dataframe(df_users, use_container_width=True)

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            st.markdown("#### ➕ Criar Novo Usuário")
            with st.form("form_novo_user"):
                novo_nome = st.text_input("Nome de Usuário:").strip()
                nova_senha = st.text_input("Senha:", type="password").strip()
                novo_perfil = st.selectbox("Perfil:", ["Inspetor", "Admin"])
                cadastrar = st.form_submit_button("Cadastrar Usuário", type="primary")
                if cadastrar:
                    if novo_nome and nova_senha:
                        sucesso, msg = criar_usuario_db(novo_nome, nova_senha, novo_perfil)
                        if sucesso:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.warning("Preencha o usuário e a senha.")

        with col_u2:
            st.markdown("#### ❌ Excluir Usuário")
            users_para_deletar = [u[0] for u in usuarios_atuais if u[0] != st.session_state.usuario_logado]
            if users_para_deletar:
                user_del = st.selectbox("Selecione o usuário para remover:", users_para_deletar)
                if st.button("🗑️ Excluir Definitivamente", type="secondary"):
                    excluir_usuario_db(user_del)
                    st.success(f"Usuário '{user_del}' excluído com sucesso!")
                    st.rerun()
            else:
                st.info("Não há outros usuários para exclusão.")

    with tab_relatorios:
        st.subheader("Histórico Completo de Vistorias Salvas")
        relatorios_salvos = listar_relatorios()
        if relatorios_salvos:
            df_rel = pd.DataFrame(
                relatorios_salvos,
                columns=["ID", "Data", "Empresa Cliente", "Inspetor", "Total Itens", "Multa Mín", "Multa Máx", "Economia Mín", "Economia Máx"]
            )
            df_rel["Multa Mín"] = df_rel["Multa Mín"].apply(formata_brl)
            df_rel["Multa Máx"] = df_rel["Multa Máx"].apply(formata_brl)
            df_rel["Economia Mín"] = df_rel["Economia Mín"].apply(formata_brl)
            df_rel["Economia Máx"] = df_rel["Economia Máx"].apply(formata_brl)
            st.dataframe(df_rel, use_container_width=True)

            st.markdown("---")
            st.markdown("#### 📥 Baixar Laudo Salvo")
            opcoes_rel = {r[0]: f"ID #{r[0]} | {r[1]} - {r[2]} (Inspetor: {r[3]})" for r in relatorios_salvos}
            id_sel = st.selectbox("Selecione a vistoria:", list(opcoes_rel.keys()), format_func=lambda x: opcoes_rel[x])
            
            dados_pdf = obter_pdf_relatorio(id_sel)
            if dados_pdf:
                pdf_bytes, emp_nome, data_vist = dados_pdf
                st.download_button(
                    label="⬇️ Baixar Este Relatório em PDF",
                    data=pdf_bytes,
                    file_name=f"Relatorio_{id_sel}_{emp_nome.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    key=f"btn_rel_{id_sel}",
                    use_container_width=True
                )
        else:
            st.info("Nenhum relatório foi salvo até o momento.")

# =========================================================
# ABA 2: NOVA VISTORIA (Fluxo Operacional de Campo)
# =========================================================
elif aba_selecionada == "📋 Nova Vistoria":
    if "evidencias" not in st.session_state:
        st.session_state.evidencias = []
    if "modo_adicionar" not in st.session_state:
        st.session_state.modo_adicionar = True
    if "contador_fluxo" not in st.session_state:
        st.session_state.contador_fluxo = 0
    if "fotos_atuais" not in st.session_state:
        st.session_state.fotos_atuais = []

    st.title("📸 Vistoria SST & Gestão de Riscos NR 28")

    # 1. Dados da Empresa e Auditoria
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            empresa_cliente = st.text_input("🏢 Empresa Atendida (Cliente):", value="Construtora Exemplo Ltda")
            inspetor_padrao = f"{st.session_state.usuario_logado.capitalize()} (SST)"
            inspetor = st.text_input("👷 Inspetor Responsável:", value=inspetor_padrao)
        with col2:
            faixa_func = st.selectbox("👥 Faixa de Funcionários:", list(TABELA_MULTAS_SEGURANCA.keys()), index=2)

    # 2. Placar Financeiro em Tempo Real
    st.markdown("---")
    tot_multa_min = sum(e['valor_min'] for e in st.session_state.evidencias if e['status'] == "Não Conformidade")
    tot_multa_max = sum(e['valor_max'] for e in st.session_state.evidencias if e['status'] == "Não Conformidade")
    tot_econ_min = sum(e['valor_min'] for e in st.session_state.evidencias if e['status'] == "Conformidade")
    tot_econ_max = sum(e['valor_max'] for e in st.session_state.evidencias if e['status'] == "Conformidade")

    c1, c2, c3 = st.columns(3)
    c1.metric("Cliente", empresa_cliente.split()[0] if empresa_cliente else "Cliente")
    c2.metric("⚠️ Multas em Risco (Máx)", formata_brl(tot_multa_max), delta=f"-{formata_brl(tot_multa_min)} (mín)", delta_color="inverse")
    c3.metric("✅ Economia Gerada (Máx)", formata_brl(tot_econ_max), delta=f"+{formata_brl(tot_econ_min)} (mín)")

    # 3. Formulário de Apontamentos
    if st.session_state.modo_adicionar:
        st.markdown("---")
        st.subheader(f"➕ Registrar Apontamento #{len(st.session_state.evidencias) + 1}")

        # Classificação da Situação (Correção do startswith)
        st.markdown("**1. Situação Identificada:**")
        status_selecionado = st.radio(
            "Esta evidência representa:",
            ["⚠️ Não Conformidade (Irregularidade / Risco de Multa)", "✅ Conformidade (Boa Prática / Economia Gerada)"],
            horizontal=True,
            key=f"status_{st.session_state.contador_fluxo}"
        )
        
        eh_conforme = status_selecionado.startswith("✅")
        status_str = "Conformidade" if eh_conforme else "Não Conformidade"

        # Prioridade (Apenas para Não Conformidades)
        prioridade_selecionada = "Média"
        if not eh_conforme:
            prioridade_selecionada = st.selectbox(
                "🚨 Prioridade de Correção / Intervenção:",
                ["Alta", "Média", "Baixa"],
                index=1,
                help="Define a urgência no cronograma de regularização do plano de ação.",
                key=f"prio_{st.session_state.contador_fluxo}"
            )

        # Fotos (Câmera + Galeria)
        st.markdown("**2. Registros Fotográficos:**")
        col_cam, col_up = st.columns(2)
        with col_cam:
            foto_cam = st.camera_input("Tirar foto com câmera", key=f"cam_{st.session_state.contador_fluxo}")
            if foto_cam and st.button("➕ Adicionar foto da câmera", use_container_width=True):
                st.session_state.fotos_atuais.append(Image.open(foto_cam))
                st.success("Foto da câmera adicionada!")

        with col_up:
            arquivos_up = st.file_uploader(
                "Ou selecione imagens da galeria:",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"up_{st.session_state.contador_fluxo}"
            )
            if arquivos_up and st.button("➕ Confirmar fotos da galeria", use_container_width=True):
                for arq in arquivos_up:
                    st.session_state.fotos_atuais.append(Image.open(arq))
                st.success(f"{len(arquivos_up)} foto(s) adicionada(s)!")

        if st.session_state.fotos_atuais:
            st.write(f"🖼️ Fotos anexadas ({len(st.session_state.fotos_atuais)}):")
            cols_p = st.columns(min(len(st.session_state.fotos_atuais), 4))
            for idx_f, img in enumerate(st.session_state.fotos_atuais):
                cols_p[idx_f % 4].image(img, use_container_width=True)
            if st.button("❌ Limpar fotos deste apontamento"):
                st.session_state.fotos_atuais = []
                st.rerun()

        # Seleção da Norma
        st.markdown("**3. Enquadramento Legal da Norma:**")
        lista_nrs_disponiveis = sorted(df_nr_base["nr"].unique())
        nr_selecionada = st.selectbox("Selecione a NR:", lista_nrs_disponiveis, key=f"nr_sel_{st.session_state.contador_fluxo}")

        df_filtrado = df_nr_base[df_nr_base["nr"] == nr_selecionada].reset_index(drop=True)
        opcoes_itens = [f"{row['item']} - {row['descricao']}" for _, row in df_filtrado.iterrows()]

        item_idx = st.selectbox("Selecione o item correspondente:", range(len(opcoes_itens)), format_func=lambda x: opcoes_itens[x], key=f"item_sel_{st.session_state.contador_fluxo}")
        item_escolhido = df_filtrado.iloc[item_idx]

        multa_calc_min, multa_calc_max = calcular_multa(item_escolhido['infracao'], faixa_func, item_escolhido['tipo'])

        if eh_conforme:
            st.success(
                f"**Item Conforme:** {item_escolhido['nr']} | Item: `{item_escolhido['item']}` | Grau: {item_escolhido['infracao']}\n\n"
                f"💰 **Economia Gerada estimada:** A empresa evitou um passivo fiscal entre **{formata_brl(multa_calc_min)} e {formata_brl(multa_calc_max)}**!"
            )
        else:
            st.error(
                f"**Não Conformidade:** {item_escolhido['nr']} | Item: `{item_escolhido['item']}` | Grau: {item_escolhido['infracao']} | Prioridade: {prioridade_selecionada}\n\n"
                f"⚠️ **Risco de Multa Aplicável (NR 28):** {formata_brl(multa_calc_min)} a {formata_brl(multa_calc_max)}"
            )

        # 4. Campos Separados
        st.markdown("**4. Detalhamento e Plano de Ação:**")
        desc_cenario = st.text_area(
            "📝 Descrição Detalhada do Cenário Constatado:",
            placeholder="Descreva exatamente o que foi visto em campo (local, máquinas, ferramentas, trabalhadores envolvidos)...",
            key=f"cenario_{st.session_state.contador_fluxo}"
        )

        label_acao = "🛡️ Conduta / Boas Práticas Mantidas:" if eh_conforme else "🛠️ Ação Corretiva Recomendada (O que fazer para regularizar):"
        placeholder_acao = "Descreva como a empresa mantém o padrão conforme..." if eh_conforme else "Ex: Instalar linha de vida com cabo de aço de 8mm e ancoragem inspecionada..."
        
        acao_corretiva = st.text_area(
            label_acao,
            placeholder=placeholder_acao,
            key=f"acao_{st.session_state.contador_fluxo}"
        )

        if st.button("💾 Salvar Apontamento e Atualizar Totais", type="primary", use_container_width=True):
            st.session_state.evidencias.append({
                "status": status_str,
                "prioridade": prioridade_selecionada,
                "nr": item_escolhido['nr'],
                "item_nr": item_escolhido['item'],
                "descricao": item_escolhido['descricao'],
                "categoria": item_escolhido['categoria'],
                "tipo": item_escolhido['tipo'],
                "infracao": item_escolhido['infracao'],
                "valor_min": multa_calc_min,
                "valor_max": multa_calc_max,
                "descricao_cenario": desc_cenario if desc_cenario else ("Conformidade atendida com sucesso." if eh_conforme else "Não conformidade constatada em campo."),
                "acao_corretiva": acao_corretiva if acao_corretiva else ("Manter o procedimento operacional padrão." if eh_conforme else "Regularizar conforme requisitos da norma."),
                "imagens": list(st.session_state.fotos_atuais)
            })
            st.session_state.fotos_atuais = []
            st.session_state.modo_adicionar = False
            st.session_state.contador_fluxo += 1
            st.rerun()

    else:
        st.success("✅ Apontamento salvo com sucesso!")
        st.write("### O que deseja fazer agora?")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("➕ Adicionar Outro Apontamento", use_container_width=True):
                st.session_state.modo_adicionar = True
                st.rerun()
        with col_b:
            if st.button("🏁 Finalizar e Ver Plano de Ação", type="primary", use_container_width=True):
                st.session_state.modo_adicionar = False

    # 4. Exibição da Tabela de Plano de Ação e Emissão do Laudo
    if st.session_state.evidencias:
        st.markdown("---")
        
        ncs_atuais = [e for e in st.session_state.evidencias if e['status'] == "Não Conformidade"]
        if ncs_atuais:
            st.subheader("📋 Plano de Ação para Regularização (Pré-visualização)")
            st.caption("No relatório em PDF, as colunas estarão formatadas e com o campo 'Prazo Limite' pronto para anotação:")
            
            df_plano_tela = pd.DataFrame([
                {
                    "Item": f"#{i}",
                    "Norma": e["nr"],
                    "Item da Norma": e["item_nr"],
                    "Cenário Observado": e["descricao_cenario"],
                    "Ação Corretiva": e["acao_corretiva"],
                    "Prioridade": e.get("prioridade", "Média"),
                    "Prazo Limite": "___/___/______"
                }
                for i, e in enumerate(ncs_atuais, 1)
            ])
            st.dataframe(df_plano_tela, use_container_width=True)

        st.subheader("📄 Emissão do Relatório Técnico")
        data_hoje = datetime.date.today().strftime("%d/%m/%Y")
        dados_relatorio = {
            "empresa_cliente": empresa_cliente,
            "inspetor": inspetor,
            "faixa_func": faixa_func,
            "data": data_hoje
        }

        pdf_buffer = gerar_pdf_completo(dados_relatorio, st.session_state.evidencias, logo_pil=logo_para_relatorio)
        pdf_bytes_final = pdf_buffer.getvalue()

        c_salvar, c_baixar, c_limpar = st.columns([1.2, 1.2, 1])
        with c_salvar:
            if st.button("💾 Salvar no Histórico", type="secondary", use_container_width=True):
                salvar_relatorio_db(
                    data_hoje,
                    empresa_cliente,
                    inspetor,
                    len(st.session_state.evidencias),
                    tot_multa_min,
                    tot_multa_max,
                    tot_econ_min,
                    tot_econ_max,
                    pdf_bytes_final
                )
                st.toast("✅ Relatório salvo no histórico com sucesso!")

        with c_baixar:
            st.download_button(
                label="⬇️ Baixar Laudo com Plano de Ação em PDF",
                data=pdf_bytes_final,
                file_name=f"Laudo_SST_{empresa_cliente.replace(' ', '_')}_{datetime.date.today().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )

        with c_limpar:
            if st.button("🗑️ Nova Vistoria", use_container_width=True):
                st.session_state.evidencias = []
                st.session_state.fotos_atuais = []
                st.session_state.modo_adicionar = True
                st.rerun()
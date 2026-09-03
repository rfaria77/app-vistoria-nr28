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
# Banco de Dados Local (SQLite) - Usuários e Relatórios
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
            pdf_bytes BLOB NOT NULL
        )
    """)
    # Usuário admin inicial
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

def salvar_relatorio_db(data_str, empresa, inspetor, total_itens, multa_min, multa_max, pdf_bytes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO relatorios (data, empresa, inspetor, total_itens, multa_min, multa_max, pdf_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data_str, empresa, inspetor, total_itens, multa_min, multa_max, pdf_bytes))
    conn.commit()
    conn.close()

def listar_relatorios():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, data, empresa, inspetor, total_itens, multa_min, multa_max FROM relatorios ORDER BY id DESC")
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

# ---------------------------------------------------------
# Login
# ---------------------------------------------------------
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
# Gráfico com Matplotlib
# ---------------------------------------------------------
def gerar_grafico_multas(lista_evidencias):
    rotulos = [f"#{i} ({e['nr']})" for i, e in enumerate(lista_evidencias, 1)]
    minimos = [e['multa_min'] for e in lista_evidencias]
    maximos = [e['multa_max'] for e in lista_evidencias]

    fig, ax = plt.subplots(figsize=(6.8, 3.2))
    x = range(len(rotulos))
    largura = 0.35

    ax.bar([p - largura/2 for p in x], minimos, width=largura, label='Multa Mínima (R$)', color='#2563EB')
    ax.bar([p + largura/2 for p in x], maximos, width=largura, label='Multa Máxima (R$)', color='#DC2626')

    ax.set_ylabel('Valor Estimado (R$)', fontsize=9)
    ax.set_title('Exposição Financeira por Não Conformidade (NR 28)', fontsize=11, fontweight='bold', pad=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels(rotulos, fontsize=9)
    ax.legend(frameon=True, fontsize=8)
    ax.grid(axis='y', linestyle='--', alpha=0.4)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='PNG', dpi=180)
    plt.close(fig)
    buf.seek(0)
    return buf

# ---------------------------------------------------------
# Gerador de Relatório PDF
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
    
    cell_th = ParagraphStyle('CellTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.white, alignment=1, leading=11)
    cell_td = ParagraphStyle('CellTD', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor('#0F172A'), leading=11)
    cell_td_center = ParagraphStyle('CellTDCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor('#0F172A'), alignment=1, leading=11)
    cell_td_total = ParagraphStyle('CellTDTotal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#0F172A'), alignment=1, leading=11)

    # 1. Cabeçalho com Logomarca
    texto_cabecalho = [
        Paragraph("Relatório Técnico de Inspeção e Notificação (NR 28)", titulo_style),
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

    # 2. Informações Gerais
    info_cabecalho = [
        [Paragraph("Empresa Atendida (Cliente):", cell_label), Paragraph(dados_gerais['empresa_cliente'], cell_value)],
        [Paragraph("Faixa de Funcionários:", cell_label), Paragraph(dados_gerais['faixa_func'], cell_value)],
        [Paragraph("Quantidade de Apontamentos:", cell_label), Paragraph(f"{len(lista_evidencias)} infração(ões) registrada(s)", cell_value)]
    ]
    t_info = Table(info_cabecalho, colWidths=[150, 373])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1F5F9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementos.append(t_info)
    elementos.append(Spacer(1, 14))

    # 3. Detalhamento de cada Evidência
    for idx, ev in enumerate(lista_evidencias, start=1):
        titulo_ev = ParagraphStyle(f'Ev_{idx}', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#1E3A8A'), spaceBefore=6, spaceAfter=4)
        elementos.append(Paragraph(f"Apontamento #{idx} - {ev['nr']} (Item {ev['item_nr']})", titulo_ev))

        detalhes_ev = [
            [Paragraph("Norma & Categoria:", cell_label), Paragraph(f"{ev['nr']} — {ev['categoria']}", cell_value)],
            [Paragraph("Item Infringido:", cell_label), Paragraph(ev['item_nr'], cell_value)],
            [Paragraph("Infração / Enquadramento:", cell_label), Paragraph(f"{ev['descricao']} (Grau {ev['infracao']} - {'Medicina' if ev['tipo']=='M' else 'Segurança'})", cell_value)],
            [Paragraph("Descrição / Medidas:", cell_label), Paragraph(ev['observacao'], cell_value)]
        ]

        t_ev = Table(detalhes_ev, colWidths=[140, 383])
        t_ev.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
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
    elementos.append(Paragraph("<b>4. Análise Gráfica da Exposição a Riscos</b>", styles['Heading3']))
    elementos.append(Spacer(1, 6))
    grafico_buf = gerar_grafico_multas(lista_evidencias)
    elementos.append(ReportLabImage(grafico_buf, width=490, height=220))
    elementos.append(Spacer(1, 14))

    # 5. Apuração Final
    total_min = sum(e['multa_min'] for e in lista_evidencias)
    total_max = sum(e['multa_max'] for e in lista_evidencias)

    elementos.append(Paragraph("<b>5. Apuração Final e Conclusão das Penalidades (NR 28)</b>", styles['Heading3']))
    elementos.append(Spacer(1, 6))

    dados_conclusao = [
        [
            Paragraph("Item", cell_th),
            Paragraph("Norma / Infração", cell_th),
            Paragraph("Grau", cell_th),
            Paragraph("Multa Mínima", cell_th),
            Paragraph("Multa Máxima", cell_th)
        ]
    ]

    for idx, ev in enumerate(lista_evidencias, 1):
        desc_curta = f"{ev['nr']} ({ev['item_nr']}) - {ev['descricao'][:45]}..." if len(ev['descricao']) > 45 else f"{ev['nr']} ({ev['item_nr']})"
        dados_conclusao.append([
            Paragraph(f"#{idx}", cell_td_center),
            Paragraph(desc_curta, cell_td),
            Paragraph(f"{ev['infracao']} ({ev['tipo']})", cell_td_center),
            Paragraph(formata_brl(ev['multa_min']), cell_td_center),
            Paragraph(formata_brl(ev['multa_max']), cell_td_center)
        ])

    dados_conclusao.append([
        Paragraph("TOTAL", cell_td_total),
        Paragraph("VALOR CONSOLIDADO ACUMULADO", cell_td_total),
        Paragraph("-", cell_td_total),
        Paragraph(formata_brl(total_min), cell_td_total),
        Paragraph(formata_brl(total_max), cell_td_total)
    ])

    t_final = Table(dados_conclusao, colWidths=[40, 203, 80, 100, 100])
    t_final.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEF08A')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t_final)

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
# ABA 1: PAINEL DE ADMINISTRAÇÃO (Admin Only)
# =========================================================
if aba_selecionada == "⚙️ Painel de Administração":
    st.title("⚙️ Painel de Administração do Sistema")
    st.write("Gerencie os usuários do app e consulte todos os relatórios emitidos pela equipe.")

    tab_usuarios, tab_relatorios = st.tabs(["👥 Gerenciar Usuários", "📂 Histórico de Relatórios Realizados"])

    # Sub-aba Usuários
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
                st.info("Não há outros usuários disponíveis para exclusão.")

    # Sub-aba Histórico de Relatórios
    with tab_relatorios:
        st.subheader("Histórico Completo de Vistorias Salvas")
        relatorios_salvos = listar_relatorios()
        if relatorios_salvos:
            df_rel = pd.DataFrame(relatorios_salvos, columns=["ID", "Data", "Empresa Cliente", "Inspetor", "Itens", "Multa Mín (R$)", "Multa Máx (R$)"])
            df_rel["Multa Mín (R$)"] = df_rel["Multa Mín (R$)"].apply(formata_brl)
            df_rel["Multa Máx (R$)"] = df_rel["Multa Máx (R$)"].apply(formata_brl)
            st.dataframe(df_rel, use_container_width=True)

            st.markdown("---")
            st.markdown("#### 📥 Visualizar / Baixar Relatório Anterior")
            col_d1, col_d2 = st.columns([2, 1])
            with col_d1:
                opcoes_rel = {r[0]: f"ID #{r[0]} | {r[1]} - {r[2]} (Inspetor: {r[3]})" for r in relatorios_salvos}
                id_sel = st.selectbox("Selecione a vistoria realizada:", list(opcoes_rel.keys()), format_func=lambda x: opcoes_rel[x])
            
            with col_d2:
                st.write("") # espaçamento vertical
                st.write("")
                dados_pdf = obter_pdf_relatorio(id_sel)
                if dados_pdf:
                    pdf_bytes, emp_nome, data_vist = dados_pdf
                    st.download_button(
                        label="⬇️ Baixar Este PDF",
                        data=pdf_bytes,
                        file_name=f"Relatorio_{id_sel}_{emp_nome.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        key=f"btn_rel_{id_sel}",
                        use_container_width=True
                    )
        else:
            st.info("Nenhum relatório foi salvo no banco de dados até o momento.")

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

    st.title("📸 Vistoria SST & Multas NR 28")

    # 1. Dados da Empresa e Auditoria
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            empresa_cliente = st.text_input("🏢 Empresa Atendida (Cliente):", value="Construtora Exemplo Ltda")
            inspetor_padrao = f"{st.session_state.usuario_logado.capitalize()} (SST)"
            inspetor = st.text_input("👷 Nome do Inspetor Técnico:", value=inspetor_padrao)
        with col2:
            faixa_func = st.selectbox("👥 Faixa de Funcionários:", list(TABELA_MULTAS_SEGURANCA.keys()), index=2)

    # 2. Placar Financeiro em Tempo Real
    st.markdown("---")
    total_min = sum(e['multa_min'] for e in st.session_state.evidencias)
    total_max = sum(e['multa_max'] for e in st.session_state.evidencias)

    c1, c2, c3 = st.columns(3)
    c1.metric("Cliente", empresa_cliente.split()[0] if empresa_cliente else "Cliente")
    c2.metric("Total Mínimo Acumulado", formata_brl(total_min))
    c3.metric("Total Máximo Acumulado", formata_brl(total_max))

    # 3. Formulário de Apontamentos
    if st.session_state.modo_adicionar:
        st.markdown("---")
        st.subheader(f"➕ Registrar Apontamento #{len(st.session_state.evidencias) + 1}")

        st.markdown("**1. Registros Fotográficos:**")
        col_cam, col_up = st.columns(2)
        with col_cam:
            foto_cam = st.camera_input("Tirar foto com a câmera", key=f"cam_{st.session_state.contador_fluxo}")
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
            st.write(f"🖼️ Fotos prontas ({len(st.session_state.fotos_atuais)}):")
            cols_p = st.columns(min(len(st.session_state.fotos_atuais), 4))
            for idx_f, img in enumerate(st.session_state.fotos_atuais):
                cols_p[idx_f % 4].image(img, use_container_width=True)
            if st.button("❌ Limpar fotos deste apontamento"):
                st.session_state.fotos_atuais = []
                st.rerun()

        st.markdown("**2. Enquadramento Legal da Infração:**")
        lista_nrs_disponiveis = sorted(df_nr_base["nr"].unique())
        nr_selecionada = st.selectbox("Selecione a Norma Regulamentadora (NR):", lista_nrs_disponiveis, key=f"nr_sel_{st.session_state.contador_fluxo}")

        df_filtrado = df_nr_base[df_nr_base["nr"] == nr_selecionada].reset_index(drop=True)
        opcoes_itens = [f"{row['item']} - {row['descricao']}" for _, row in df_filtrado.iterrows()]

        item_idx = st.selectbox("Selecione a irregularidade / infração:", range(len(opcoes_itens)), format_func=lambda x: opcoes_itens[x], key=f"item_sel_{st.session_state.contador_fluxo}")
        item_escolhido = df_filtrado.iloc[item_idx]

        multa_item_min, multa_item_max = calcular_multa(item_escolhido['infracao'], faixa_func, item_escolhido['tipo'])

        st.info(
            f"**Enquadramento:** {item_escolhido['nr']} | Item: `{item_escolhido['item']}` | "
            f"**Grau:** {item_escolhido['infracao']} ({'Medicina' if item_escolhido['tipo'] == 'M' else 'Segurança'}) | "
            f"**Multa Calculada:** {formata_brl(multa_item_min)} a {formata_brl(multa_item_max)}"
        )

        obs_atual = st.text_area(
            "Descrição detalhada / Medida corretiva recomendada:",
            placeholder="Descreva a irregularidade constatada em campo...",
            key=f"obs_{st.session_state.contador_fluxo}"
        )

        if st.button("💾 Salvar Evidência e Atualizar Valor", type="primary", use_container_width=True):
            st.session_state.evidencias.append({
                "nr": item_escolhido['nr'],
                "item_nr": item_escolhido['item'],
                "descricao": item_escolhido['descricao'],
                "categoria": item_escolhido['categoria'],
                "tipo": item_escolhido['tipo'],
                "infracao": item_escolhido['infracao'],
                "multa_min": multa_item_min,
                "multa_max": multa_item_max,
                "observacao": obs_atual if obs_atual else "Não conformidade constatada em vistoria de campo.",
                "imagens": list(st.session_state.fotos_atuais)
            })
            st.session_state.fotos_atuais = []
            st.session_state.modo_adicionar = False
            st.session_state.contador_fluxo += 1
            st.rerun()

    else:
        st.success("✅ Evidência registrada com sucesso!")
        st.write("### O que deseja fazer agora?")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("➕ Adicionar Outra Evidência", use_container_width=True):
                st.session_state.modo_adicionar = True
                st.rerun()
        with col_b:
            if st.button("🏁 Finalizar Vistoria e Ver Relatório", type="primary", use_container_width=True):
                st.session_state.modo_adicionar = False

    # 4. Geração e Salvamento Automático no Banco
    if st.session_state.evidencias:
        st.markdown("---")
        st.subheader("📄 Relatório Conclusivo em PDF")

        data_hoje = datetime.date.today().strftime("%d/%m/%Y")
        dados_relatorio = {
            "empresa_cliente": empresa_cliente,
            "inspetor": inspetor,
            "faixa_func": faixa_func,
            "data": data_hoje
        }

        pdf_buffer = gerar_pdf_completo(dados_relatorio, st.session_state.evidencias, logo_pil=logo_para_relatorio)
        pdf_bytes_final = pdf_buffer.getvalue()

        # Botão para salvar a vistoria no banco de dados e baixar
        c_salvar, c_baixar, c_limpar = st.columns([1.2, 1.2, 1])
        with c_salvar:
            if st.button("💾 Salvar no Histórico do Sistema", type="secondary", use_container_width=True):
                salvar_relatorio_db(
                    data_hoje,
                    empresa_cliente,
                    inspetor,
                    len(st.session_state.evidencias),
                    total_min,
                    total_max,
                    pdf_bytes_final
                )
                st.toast("✅ Relatório salvo com sucesso no banco de dados!")

        with c_baixar:
            st.download_button(
                label="⬇️ Baixar Relatório em PDF",
                data=pdf_bytes_final,
                file_name=f"Relatorio_{empresa_cliente.replace(' ', '_')}_{datetime.date.today().strftime('%Y%m%d')}.pdf",
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
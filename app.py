import io
import os
import json
import uuid
import sqlite3
import datetime
import urllib.parse
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt

from streamlit_js_eval import get_geolocation
from google import genai
from google.genai import types

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage, Table, TableStyle

# ---------------------------------------------------------
# Configuração da Página e CSS (Sem Pull-to-Refresh)
# ---------------------------------------------------------
st.set_page_config(page_title="Vistoria SST - NR 28", page_icon="🛡️", layout="centered")

st.markdown("""
<style>
    /* DESATIVA O PULL-TO-REFRESH (DESLIZAR PARA BAIXO E ZERAR) */
    html, body {
        overscroll-behavior-y: none !important;
        overscroll-behavior: none !important;
    }
    .stApp, div[data-testid="stAppViewContainer"] {
        overscroll-behavior-y: contain !important;
        overscroll-behavior: contain !important;
    }

    /* Força quebra de linha nas caixas de seleção em telas móveis */
    div[data-baseweb="select"] div {
        white-space: normal !important;
        word-break: break-word !important;
        height: auto !important;
        line-height: 1.35 !important;
    }
    div[data-baseweb="popover"] ul,
    div[data-baseweb="popover"] li,
    div[data-baseweb="popover"] div {
        white-space: normal !important;
        word-break: break-word !important;
        height: auto !important;
        min-height: 44px !important;
        padding-top: 6px !important;
        padding-bottom: 6px !important;
        line-height: 1.4 !important;
    }
    .norma-card {
        background-color: #f8fafc;
        border-left: 5px solid #2563eb;
        padding: 12px 16px;
        border-radius: 6px;
        margin-top: 8px;
        margin-bottom: 12px;
        word-wrap: break-word;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Banco de Dados Local (SQLite)
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
        CREATE TABLE IF NOT EXISTS sessoes (
            token TEXT PRIMARY KEY,
            usuario TEXT NOT NULL,
            perfil TEXT NOT NULL,
            expira TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS rascunhos (
            usuario TEXT PRIMARY KEY,
            empresa TEXT,
            inspetor TEXT,
            faixa_func TEXT,
            dados_json TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
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

# ---------------------------------------------------------
# Gestão de Rascunho Automático
# ---------------------------------------------------------
def salvar_rascunho_db(usuario, empresa, inspetor, faixa_func, lista_evidencias):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    evidencias_serializaveis = []
    for ev in lista_evidencias:
        item_copia = dict(ev)
        img_buffers = []
        for img in item_copia.get("imagens", []):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            img_buffers.append(buf.getvalue().hex())
        item_copia["imagens_hex"] = img_buffers
        if "imagens" in item_copia:
            del item_copia["imagens"]
        evidencias_serializaveis.append(item_copia)

    dados_json = json.dumps(evidencias_serializaveis)
    agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    c.execute("""
        INSERT INTO rascunhos (usuario, empresa, inspetor, faixa_func, dados_json, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(usuario) DO UPDATE SET
            empresa=excluded.empresa,
            inspetor=excluded.inspetor,
            faixa_func=excluded.faixa_func,
            dados_json=excluded.dados_json,
            atualizado_em=excluded.atualizado_em
    """, (usuario, empresa, inspetor, faixa_func, dados_json, agora))
    conn.commit()
    conn.close()

def carregar_rascunho_db(usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT empresa, inspetor, faixa_func, dados_json, atualizado_em FROM rascunhos WHERE usuario = ?", (usuario,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    empresa, inspetor, faixa_func, dados_json, atualizado_em = row
    itens = json.loads(dados_json)
    for it in itens:
        imgs_pil = []
        for hex_str in it.get("imagens_hex", []):
            raw_bytes = bytes.fromhex(hex_str)
            imgs_pil.append(Image.open(io.BytesIO(raw_bytes)))
        it["imagens"] = imgs_pil
        if "imagens_hex" in it:
            del it["imagens_hex"]
    return {
        "empresa": empresa,
        "inspetor": inspetor,
        "faixa_func": faixa_func,
        "evidencias": itens,
        "atualizado_em": atualizado_em
    }

def limpar_rascunho_db(usuario):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM rascunhos WHERE usuario = ?", (usuario,))
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# Gestão de Sessão (Token de 7 Dias)
# ---------------------------------------------------------
def criar_sessao(usuario, perfil):
    token = uuid.uuid4().hex
    expira = (datetime.datetime.now() + datetime.timedelta(days=7)).isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO sessoes (token, usuario, perfil, expira) VALUES (?, ?, ?, ?)", (token, usuario, perfil, expira))
    conn.commit()
    conn.close()
    return token

def validar_token_sessao(token):
    if not token:
        return None
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT usuario, perfil, expira FROM sessoes WHERE token = ?", (token,))
    row = c.fetchone()
    conn.close()

    if row:
        usuario, perfil, expira_str = row
        if datetime.datetime.now().isoformat() < expira_str:
            return usuario, perfil
        else:
            revogar_token_sessao(token)
    return None

def revogar_token_sessao(token):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM sessoes WHERE token = ?", (token,))
    conn.commit()
    conn.close()

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

    token_url = st.query_params.get("session")
    if not st.session_state.autenticado and token_url:
        sessao_valida = validar_token_sessao(token_url)
        if sessao_valida:
            st.session_state.autenticado = True
            st.session_state.usuario_logado = sessao_valida[0]
            st.session_state.perfil_logado = sessao_valida[1]
            return True

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
            lembrar = st.checkbox("Manter conectado neste dispositivo (7 dias)", value=True)
            entrar = st.form_submit_button("Entrar no Sistema", type="primary", use_container_width=True)
            if entrar:
                user_data = autenticar_usuario(usuario_in, senha_in)
                if user_data:
                    st.session_state.autenticado = True
                    st.session_state.usuario_logado = user_data[0]
                    st.session_state.perfil_logado = user_data[1]
                    if lembrar:
                        token_novo = criar_sessao(user_data[0], user_data[1])
                        st.query_params["session"] = token_novo
                    st.success("Autenticado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha inválidos.")
    return False

# ---------------------------------------------------------
# Otimização de Imagens e Carimbo Técnico
# ---------------------------------------------------------
def otimizar_e_carimbar(imagem_original, lat=None, lon=None):
    img = imagem_original.convert("RGB")
    img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    
    draw = ImageDraw.Draw(img)
    largura, altura = img.size

    altura_barra = max(34, int(altura * 0.065))
    agora_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    draw.rectangle([0, altura - altura_barra, largura, altura], fill=(15, 23, 42))

    texto_gps = f" | GPS: {lat:.5f}, {lon:.5f}" if (lat and lon) else " | GPS: Localização Não Obtida"
    texto_completo = f"REGISTRO FORENSE SST: {agora_str}{texto_gps}"

    try:
        fonte = ImageFont.load_default()
    except Exception:
        fonte = None

    pos_y = altura - int(altura_barra * 0.65)
    draw.text((15, pos_y), texto_completo, fill=(255, 255, 255), font=fonte)
    return img

# ---------------------------------------------------------
# Assistente de Enquadramento por Texto / Voz (Gemini IA)
# ---------------------------------------------------------
def sugerir_enquadramento_por_texto(descricao_problema, df_base_nrs):
    api_key = None
    if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    elif "GEMINI_API_KEY" in os.environ:
        api_key = os.environ["GEMINI_API_KEY"]

    if not api_key:
        return None, "Chave GEMINI_API_KEY não configurada nos Secrets do Streamlit."

    try:
        client = genai.Client(api_key=api_key)
        nrs_disponiveis = sorted(df_base_nrs["nr"].unique())

        prompt = f"""
        Você é um Engenheiro de Segurança do Trabalho especialista nas Normas Regulamentadoras (NRs) do Brasil.
        
        O inspetor em campo relatou a seguinte ocorrência:
        "{descricao_problema}"

        Com base exclusivamente na legislação brasileira de SST e preferencialmente nas normas cadastradas ({', '.join(nrs_disponiveis)}):
        1. Identifique se representa "Não Conformidade" ou "Conformidade".
        2. Indique a NR mais adequada (ex: "NR 35", "NR 10", "NR 12", "NR 06", etc.).
        3. Indique o item provável da norma.
        4. Descreva de forma técnica e formal o cenário.
        5. Formule a ação corretiva imediata.
        6. Determine a prioridade (Alta, Média ou Baixa).

        Responda ESTRITAMENTE em formato JSON:
        {{
            "status": "Não Conformidade" ou "Conformidade",
            "nr_sugerida": "Ex: NR 35",
            "item_provavel": "Ex: 35.2.1",
            "descricao_cenario": "Resumo técnico objetivo do fato",
            "acao_corretiva": "Medida técnica recomendada",
            "prioridade": "Alta", "Média" ou "Baixa"
        }}
        """

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text), None
    except Exception as e:
        return None, f"Erro na análise de texto: {str(e)}"

# ---------------------------------------------------------
# Link Direto para WhatsApp
# ---------------------------------------------------------
def gerar_link_whatsapp(telefone, empresa, tot_multa, tot_econ, qtd_nc):
    msg = (
        f"📋 *RELATÓRIO PRELIMINAR DE VISTORIA SST (NR 28)*\n\n"
        f"🏢 *Empresa:* {empresa}\n"
        f"📅 *Data:* {datetime.date.today().strftime('%d/%m/%Y')}\n"
        f"⚠️ *Não Conformidades:* {qtd_nc} apontamento(s)\n"
        f"💰 *Passivo em Risco:* {formata_brl(tot_multa)}\n"
        f"🛡️ *Economia Gerada (Risco Evitado):* {formata_brl(tot_econ)}\n\n"
        f"_O laudo técnico com o Plano de Ação detalhado já está disponível._"
    )
    telefone_limpo = "".join([c for c in telefone if c.isdigit()])
    return f"https://api.whatsapp.com/send?phone={telefone_limpo}&text={urllib.parse.quote(msg)}"

# ---------------------------------------------------------
# Tabelas Oficiais NR 28
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

@st.cache_data
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
                img.save(img_buf, format='JPEG', quality=85)
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

    # 5. Balanço Financeiro Consolidado
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

    # 6. Plano de Ação com Descrição Legal
    elementos.append(Paragraph("<b>6. Plano de Ação e Cronograma de Regularização (Pós-Vistoria)</b>", styles['Heading3']))
    elementos.append(Paragraph("<i>Quadro de intervenção técnica para saneamento das não conformidades identificadas:</i>", sub_style))
    elementos.append(Spacer(1, 4))

    dados_plano = [
        [
            Paragraph("Item", cell_th),
            Paragraph("Norma & Descrição Legal", cell_th),
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
            texto_norma_completo = f"<b>{ev['nr']} — Item {ev['item_nr']}</b><br/><font color='#334155'><i>{ev['descricao']}</i></font>"

            dados_plano.append([
                Paragraph(f"#{idx}", cell_td_center),
                Paragraph(texto_norma_completo, cell_td),
                Paragraph(ev['descricao_cenario'], cell_td),
                Paragraph(ev['acao_corretiva'], cell_td),
                Paragraph(tag_pri, cell_td_center),
                Paragraph("___/___/______", cell_td_center)
            ])

        t_plano = Table(dados_plano, colWidths=[28, 130, 135, 110, 60, 60])
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
if not verificar_login():
    st.stop()

loc_atual = get_geolocation()
lat_capturada = loc_atual['coords']['latitude'] if (loc_atual and 'coords' in loc_atual) else None
lon_capturada = loc_atual['coords']['longitude'] if (loc_atual and 'coords' in loc_atual) else None

with st.sidebar:
    st.markdown(f"👤 Usuário: **{st.session_state.usuario_logado}** (`{st.session_state.perfil_logado}`)")
    if lat_capturada and lon_capturada:
        st.caption(f"📍 GPS Ativo: `{lat_capturada:.4f}, {lon_capturada:.4f}`")
    else:
        st.caption("📍 GPS: Aguardando permissão...")

    if st.button("🚪 Sair (Logout)", use_container_width=True):
        token_atual = st.query_params.get("session")
        if token_atual:
            revogar_token_sessao(token_atual)
            st.query_params.clear()
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
# ABA 2: NOVA VISTORIA
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
    if "ia_sugestao" not in st.session_state:
        st.session_state.ia_sugestao = None
    if "editando_indice" not in st.session_state:
        st.session_state.editando_indice = None
    if "abrir_camera" not in st.session_state:
        st.session_state.abrir_camera = False

    rascunho_existente = carregar_rascunho_db(st.session_state.usuario_logado)
    if rascunho_existente and not st.session_state.evidencias:
        st.info(f"💾 **Rascunho detectado!** Foi encontrada uma vistoria em andamento de `{rascunho_existente['empresa']}` salva em {rascunho_existente['atualizado_em']}.")
        col_rec1, col_rec2 = st.columns(2)
        with col_rec1:
            if st.button("🔄 Retomar Esta Vistoria em Andamento", type="primary", use_container_width=True):
                st.session_state.evidencias = rascunho_existente["evidencias"]
                st.session_state.modo_adicionar = False
                st.rerun()
        with col_rec2:
            if st.button("🗑️ Descartar Rascunho Antigo", use_container_width=True):
                limpar_rascunho_db(st.session_state.usuario_logado)
                st.rerun()

    st.title("📸 Vistoria SST & Gestão de Riscos NR 28")

    # 1. Dados Gerais da Empresa
    with st.container():
        col1, col2 = st.columns(2)
        with col1:
            emp_padrao = rascunho_existente["empresa"] if (rascunho_existente and not st.session_state.evidencias) else "Construtora Exemplo Ltda"
            empresa_cliente = st.text_input("🏢 Empresa Atendida (Cliente):", value=emp_padrao)
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
    if st.session_state.modo_adicionar or st.session_state.editando_indice is not None:
        st.markdown("---")
        idx_edicao = st.session_state.editando_indice
        
        if idx_edicao is not None:
            st.subheader(f"✏️ Editando Apontamento #{idx_edicao + 1}")
            item_edicao = st.session_state.evidencias[idx_edicao]
            if not st.session_state.fotos_atuais and item_edicao.get("imagens"):
                st.session_state.fotos_atuais = list(item_edicao["imagens"])
        else:
            st.subheader(f"➕ Registrar Apontamento #{len(st.session_state.evidencias) + 1}")
            item_edicao = None

        # Assistente de Enquadramento por Texto ou Ditado de Voz
        st.markdown("""
        <div style="background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <b style="color: #1E40AF;">💡 Assistente Rápido por Descrição / Voz</b><br/>
            <span style="font-size: 0.85rem; color: #1E3A8A;">Descreva em poucas palavras o que está vendo (ou dite pelo microfone do teclado) para a IA localizar a NR:</span>
        </div>
        """, unsafe_allow_html=True)

        col_t1, col_t2 = st.columns([2.5, 1])
        with col_t1:
            texto_relato = st.text_input(
                "Descreva a situação encontrada:",
                placeholder="Ex: Operários em andaime a 4m sem cinto e sem proteção de periferia",
                key=f"texto_ia_{st.session_state.contador_fluxo}",
                label_visibility="collapsed"
            )
        with col_t2:
            if st.button("🔍 Enquadrar com IA", use_container_width=True, type="secondary"):
                if texto_relato.strip():
                    with st.spinner("Localizando NR correspondente..."):
                        res_ia, err_ia = sugerir_enquadramento_por_texto(texto_relato, df_nr_base)
                        if res_ia:
                            st.session_state.ia_sugestao = res_ia
                            st.toast(f"✅ Enquadrado na {res_ia.get('nr_sugerida', 'NR')}!")
                            st.rerun()
                        else:
                            st.error(err_ia)
                else:
                    st.warning("Descreva a situação primeiro.")

        st.markdown("**1. Registros Fotográficos (Carimbo Forense e Otimização):**")
        col_cam, col_up = st.columns(2)
        
        with col_cam:
            if not st.session_state.abrir_camera:
                if st.button("📷 Abrir Câmera", use_container_width=True):
                    st.session_state.abrir_camera = True
                    st.rerun()
            else:
                foto_cam = st.camera_input("Enquadre e tire a foto:", key=f"cam_{st.session_state.contador_fluxo}")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if foto_cam and st.button("➕ Confirmar Foto", use_container_width=True, type="primary"):
                        img_proc = otimizar_e_carimbar(Image.open(foto_cam), lat_capturada, lon_capturada)
                        st.session_state.fotos_atuais.append(img_proc)
                        st.session_state.abrir_camera = False
                        st.success("Foto salva com carimbo!")
                        st.rerun()
                with col_c2:
                    if st.button("❌ Fechar Câmera", use_container_width=True):
                        st.session_state.abrir_camera = False
                        st.rerun()

        with col_up:
            arquivos_up = st.file_uploader(
                "Ou selecione da galeria / câmera nativa:",
                type=["jpg", "jpeg", "png"],
                accept_multiple_files=True,
                key=f"up_{st.session_state.contador_fluxo}"
            )
            if arquivos_up and st.button("➕ Confirmar fotos da galeria", use_container_width=True):
                for arq in arquivos_up:
                    img_proc = otimizar_e_carimbar(Image.open(arq), lat_capturada, lon_capturada)
                    st.session_state.fotos_atuais.append(img_proc)
                st.success(f"{len(arquivos_up)} foto(s) adicionada(s)!")

        if st.session_state.fotos_atuais:
            st.write(f"🖼️ Fotos anexadas ({len(st.session_state.fotos_atuais)}):")
            cols_p = st.columns(min(len(st.session_state.fotos_atuais), 4))
            for idx_f, img in enumerate(st.session_state.fotos_atuais):
                cols_p[idx_f % 4].image(img, use_container_width=True)

            if st.button("❌ Limpar fotos deste apontamento", use_container_width=True):
                st.session_state.fotos_atuais = []
                st.session_state.ia_sugestao = None
                st.rerun()

        st.markdown("**2. Situação Identificada:**")
        index_status = 0
        if item_edicao:
            index_status = 1 if item_edicao["status"] == "Conformidade" else 0
        elif st.session_state.ia_sugestao and st.session_state.ia_sugestao.get("status") == "Conformidade":
            index_status = 1

        status_selecionado = st.radio(
            "Esta evidência representa:",
            ["⚠️ Não Conformidade (Irregularidade / Risco de Multa)", "✅ Conformidade (Boa Prática / Economia Gerada)"],
            index=index_status,
            horizontal=True,
            key=f"status_{st.session_state.contador_fluxo}"
        )
        
        eh_conforme = status_selecionado.startswith("✅")
        status_str = "Conformidade" if eh_conforme else "Não Conformidade"

        prioridade_selecionada = "Média"
        if not eh_conforme:
            idx_prio = 1
            if item_edicao:
                prio_val = item_edicao.get("prioridade", "Média")
                idx_prio = 0 if prio_val == "Alta" else (2 if prio_val == "Baixa" else 1)
            elif st.session_state.ia_sugestao:
                sug_p = st.session_state.ia_sugestao.get("prioridade", "Média")
                idx_prio = 0 if sug_p == "Alta" else (2 if sug_p == "Baixa" else 1)

            prioridade_selecionada = st.selectbox(
                "🚨 Prioridade de Correção / Intervenção:",
                ["Alta", "Média", "Baixa"],
                index=idx_prio,
                key=f"prio_{st.session_state.contador_fluxo}"
            )

        st.markdown("**3. Enquadramento Legal da Norma:**")
        lista_nrs_disponiveis = sorted(df_nr_base["nr"].unique())
        
        idx_nr_padrao = 0
        if item_edicao and item_edicao["nr"] in lista_nrs_disponiveis:
            idx_nr_padrao = lista_nrs_disponiveis.index(item_edicao["nr"])
        elif st.session_state.ia_sugestao:
            nr_sug = st.session_state.ia_sugestao.get("nr_sugerida", "")
            for idx_n, n_item in enumerate(lista_nrs_disponiveis):
                if nr_sug.replace(" ", "").upper() in n_item.replace(" ", "").upper():
                    idx_nr_padrao = idx_n
                    break

        nr_selecionada = st.selectbox("Selecione a NR:", lista_nrs_disponiveis, index=idx_nr_padrao, key=f"nr_sel_{st.session_state.contador_fluxo}")

        df_filtrado = df_nr_base[df_nr_base["nr"] == nr_selecionada].reset_index(drop=True)
        opcoes_itens = [f"Item {row['item']} — {row['descricao']}" for _, row in df_filtrado.iterrows()]

        idx_item_padrao = 0
        if item_edicao and item_edicao["nr"] == nr_selecionada:
            for i_idx, r in df_filtrado.iterrows():
                if r["item"] == item_edicao["item_nr"]:
                    idx_item_padrao = i_idx
                    break
        elif st.session_state.ia_sugestao:
            item_sug = st.session_state.ia_sugestao.get("item_provavel", "")
            for i_idx, r in df_filtrado.iterrows():
                if item_sug and item_sug in r["item"]:
                    idx_item_padrao = i_idx
                    break

        item_idx = st.selectbox(
            "Selecione o item correspondente da norma:",
            range(len(opcoes_itens)),
            index=idx_item_padrao,
            format_func=lambda x: opcoes_itens[x],
            key=f"item_sel_{st.session_state.contador_fluxo}"
        )
        item_escolhido = df_filtrado.iloc[item_idx]
        multa_calc_min, multa_calc_max = calcular_multa(item_escolhido['infracao'], faixa_func, item_escolhido['tipo'])

        if eh_conforme:
            st.markdown(f"""
            <div class="norma-card" style="border-left-color: #10B981; background-color: #F0FDF4;">
                <b style="color: #065F46; font-size: 1.05rem;">✅ Item Conforme: {item_escolhido['nr']} (Item {item_escolhido['item']})</b><br/>
                <p style="margin: 6px 0; color: #1F2937; line-height: 1.4;"><b>Requisito:</b> {item_escolhido['descricao']}</p>
                <span style="font-size: 0.9rem; color: #047857;">
                    <b>Categoria:</b> {item_escolhido['categoria']} | <b>Grau:</b> {item_escolhido['infracao']}<br/>
                    <b>Economia Estimada:</b> {formata_brl(multa_calc_min)} a {formata_brl(multa_calc_max)}
                </span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="norma-card" style="border-left-color: #EF4444; background-color: #FEF2F2;">
                <b style="color: #991B1B; font-size: 1.05rem;">⚠️ Não Conformidade: {item_escolhido['nr']} (Item {item_escolhido['item']})</b><br/>
                <p style="margin: 6px 0; color: #1F2937; line-height: 1.4;"><b>Infração:</b> {item_escolhido['descricao']}</p>
                <span style="font-size: 0.9rem; color: #B91C1C;">
                    <b>Categoria:</b> {item_escolhido['categoria']} | <b>Grau:</b> {item_escolhido['infracao']} | <b>Prioridade:</b> {prioridade_selecionada}<br/>
                    <b>Multa Prevista (NR 28):</b> {formata_brl(multa_calc_min)} a {formata_brl(multa_calc_max)}
                </span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("**4. Detalhamento e Plano de Ação:**")
        if item_edicao:
            valor_padrao_cenario = item_edicao.get("descricao_cenario", "")
            valor_padrao_acao = item_edicao.get("acao_corretiva", "")
        elif st.session_state.ia_sugestao:
            valor_padrao_cenario = st.session_state.ia_sugestao.get("descricao_cenario", "")
            valor_padrao_acao = st.session_state.ia_sugestao.get("acao_corretiva", "")
        else:
            valor_padrao_cenario = ""
            valor_padrao_acao = ""

        desc_cenario = st.text_area(
            "📝 Descrição Detalhada do Cenário Constatado:",
            value=valor_padrao_cenario,
            placeholder="Descreva o que foi visto em campo...",
            key=f"cenario_{st.session_state.contador_fluxo}"
        )

        label_acao = "🛡️ Conduta / Boas Práticas Mantidas:" if eh_conforme else "🛠️ Ação Corretiva Recomendada:"
        acao_corretiva = st.text_area(
            label_acao,
            value=valor_padrao_acao,
            placeholder="Medidas necessárias para regularização...",
            key=f"acao_{st.session_state.contador_fluxo}"
        )

        texto_botao = "💾 Atualizar Apontamento" if idx_edicao is not None else "💾 Salvar Apontamento no Laudo"
        if st.button(texto_botao, type="primary", use_container_width=True):
            novo_dado = {
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
            }
            if idx_edicao is not None:
                st.session_state.evidencias[idx_edicao] = novo_dado
                st.session_state.editando_indice = None
                st.toast("✅ Apontamento atualizado com sucesso!")
            else:
                st.session_state.evidencias.append(novo_dado)
                st.toast("✅ Apontamento salvo no laudo!")

            salvar_rascunho_db(st.session_state.usuario_logado, empresa_cliente, inspetor, faixa_func, st.session_state.evidencias)

            st.session_state.fotos_atuais = []
            st.session_state.ia_sugestao = None
            st.session_state.modo_adicionar = False
            st.session_state.abrir_camera = False
            st.session_state.contador_fluxo += 1
            st.rerun()

    else:
        st.write("### O que deseja fazer agora?")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("➕ Adicionar Outro Apontamento", use_container_width=True):
                st.session_state.modo_adicionar = True
                st.session_state.editando_indice = None
                st.session_state.fotos_atuais = []
                st.session_state.abrir_camera = False
                st.rerun()
        with col_b:
            if st.button("🏁 Finalizar Vistoria e Visualizar Laudo", type="primary", use_container_width=True):
                st.session_state.modo_adicionar = False
                st.session_state.editando_indice = None
                st.session_state.abrir_camera = False

    # 4. Gerenciador de Apontamentos (Editar / Excluir)
    if st.session_state.evidencias:
        st.markdown("---")
        st.subheader(f"📑 Apontamentos Registrados ({len(st.session_state.evidencias)})")
        
        for idx, ev in enumerate(st.session_state.evidencias):
            eh_c = (ev["status"] == "Conformidade")
            cor_tag = "🟢" if eh_c else "🔴"
            rot_tipo = "Boa Prática" if eh_c else f"Não Conformidade ({ev.get('prioridade', 'Média')})"

            with st.expander(f"{cor_tag} #{idx + 1}: {ev['nr']} (Item {ev['item_nr']}) — {rot_tipo}"):
                st.write(f"**Norma / Descrição:** {ev['descricao']}")
                st.write(f"**Cenário:** {ev['descricao_cenario']}")
                st.write(f"**Ação:** {ev['acao_corretiva']}")
                st.write(f"**Fotos anexadas:** {len(ev.get('imagens', []))}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button(f"✏️ Editar Apontamento #{idx + 1}", key=f"btn_edit_{idx}", use_container_width=True):
                        st.session_state.editando_indice = idx
                        st.session_state.modo_adicionar = True
                        st.session_state.fotos_atuais = list(ev.get("imagens", []))
                        st.session_state.abrir_camera = False
                        st.rerun()
                with col_btn2:
                    if st.button(f"🗑️ Excluir Apontamento #{idx + 1}", key=f"btn_del_{idx}", use_container_width=True):
                        st.session_state.evidencias.pop(idx)
                        salvar_rascunho_db(st.session_state.usuario_logado, empresa_cliente, inspetor, faixa_func, st.session_state.evidencias)
                        st.toast(f"Apontamento #{idx + 1} removido.")
                        st.rerun()

        # 5. Plano de Ação e Compartilhamento
        ncs_atuais = [e for e in st.session_state.evidencias if e['status'] == "Não Conformidade"]
        if ncs_atuais:
            st.markdown("---")
            st.subheader("📋 Plano de Ação para Regularização (Pré-visualização)")
            df_plano_tela = pd.DataFrame([
                {
                    "Item": f"#{i}",
                    "Norma / Item": f"{e['nr']} ({e['item_nr']})",
                    "Infração / Requisito Legal (NR)": e["descricao"],
                    "Cenário Observado": e["descricao_cenario"],
                    "Ação Corretiva": e["acao_corretiva"],
                    "Prioridade": e.get("prioridade", "Média"),
                    "Prazo Limite": "___/___/______"
                }
                for i, e in enumerate(ncs_atuais, 1)
            ])
            st.dataframe(df_plano_tela, use_container_width=True)

        st.subheader("📲 Compartilhar Resumo via WhatsApp")
        col_w1, col_w2 = st.columns([1.5, 1])
        with col_w1:
            tel_wpp = st.text_input("WhatsApp do Cliente/Engenheiro (DDD + Número):", placeholder="Ex: 11999998888")
        with col_w2:
            st.write("")
            st.write("")
            if tel_wpp:
                link_wpp = gerar_link_whatsapp(tel_wpp, empresa_cliente, tot_multa_max, tot_econ_max, len(ncs_atuais))
                st.markdown(f'<a href="{link_wpp}" target="_blank"><button style="background-color:#25D366;color:white;border:none;padding:10px 16px;border-radius:6px;font-weight:bold;width:100%;">💬 Enviar Resumo no WhatsApp</button></a>', unsafe_allow_html=True)

        # 6. Emissão do PDF e Finalização
        st.markdown("---")
        st.subheader("📄 Emissão do Relatório Técnico em PDF")
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
                limpar_rascunho_db(st.session_state.usuario_logado)
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
            if st.button("🗑️ Nova Vistoria (Limpar Tudo)", use_container_width=True):
                limpar_rascunho_db(st.session_state.usuario_logado)
                st.session_state.evidencias = []
                st.session_state.fotos_atuais = []
                st.session_state.ia_sugestao = None
                st.session_state.editando_indice = None
                st.session_state.abrir_camera = False
                st.session_state.modo_adicionar = True
                st.rerun()
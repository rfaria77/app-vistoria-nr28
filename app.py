import io
import os
import json
import time
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
from groq import Groq

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage, Table, TableStyle
from reportlab.pdfgen import canvas

# ---------------------------------------------------------
# Configuração de Página e Estilização Universal (Anti-Dark Mode)
# ---------------------------------------------------------
st.set_page_config(page_title="Vistoria SST - NR 28", page_icon="🛡️", layout="centered")

st.markdown("""
<style>
    /* Ocultar elementos padrão do Streamlit */
    #MainMenu, header, footer, [data-testid="stToolbar"] {
        visibility: hidden !important;
        display: none !important;
    }
    
    /* Trava elástica e fundo geral forçado */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        overscroll-behavior-y: none !important;
        overscroll-behavior: none !important;
        background-color: #F8FAFC !important;
        color: #0F172A !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }

    /* FORÇAR CONTRASTE DE TODOS OS TEXTOS NATIVOS E LABELS DO STREAMLIT */
    .stMarkdown, .stMarkdown p, .stMarkdown span, .stMarkdown strong, .stMarkdown b,
    [data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span,
    label, [data-testid="stRadio"] label, [data-testid="stRadio"] div,
    .stCheckbox label, .stSelectbox label, .stTextArea label, .stTextInput label {
        color: #0F172A !important;
        font-weight: 600 !important;
    }

    /* Espaçamento da área útil */
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 720px !important;
    }

    /* Stepper Visual */
    .stepper-container {
        display: flex;
        justify-content: space-between;
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 8px 14px;
        margin-bottom: 14px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .step-item {
        font-size: 0.78rem;
        font-weight: 700;
        color: #64748B !important;
        display: flex;
        align-items: center;
        gap: 5px;
    }
    .step-active {
        color: #2563EB !important;
    }

    /* Cards de KPI Financeiro */
    .kpi-container {
        display: flex;
        gap: 12px;
        margin-top: 8px;
        margin-bottom: 14px;
    }
    .kpi-card {
        flex: 1;
        background: #FFFFFF !important;
        border-radius: 14px;
        padding: 12px 14px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
        border: 1px solid #E2E8F0;
    }
    .kpi-card-danger { border-top: 4px solid #EF4444 !important; }
    .kpi-card-success { border-top: 4px solid #10B981 !important; }
    .kpi-card-info { border-top: 4px solid #3B82F6 !important; }
    .kpi-title {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748B !important;
        margin-bottom: 2px;
    }
    .kpi-value {
        font-size: 1.22rem;
        font-weight: 800;
        line-height: 1.2;
    }
    .kpi-value-danger { color: #DC2626 !important; }
    .kpi-value-success { color: #059669 !important; }
    .kpi-value-info { color: #1D4ED8 !important; }
    .kpi-sub {
        font-size: 0.72rem;
        color: #64748B !important;
        margin-top: 3px;
    }

    /* Badges de Status */
    .badge-pill {
        display: inline-flex;
        align-items: center;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.3px;
        margin-right: 6px;
    }
    .badge-danger { background-color: #FEE2E2; color: #991B1B !important; }
    .badge-warning { background-color: #FEF3C7; color: #92400E !important; }
    .badge-success { background-color: #DCFCE7; color: #166534 !important; }
    .badge-info { background-color: #DBEAFE; color: #1E40AF !important; }

    /* Banners Informativos */
    .ai-assistant-card {
        background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%) !important;
        border: 1px solid #BFDBFE !important;
        border-radius: 14px;
        padding: 12px 14px;
        margin-bottom: 14px;
    }
    .offline-card {
        background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%) !important;
        border: 1px solid #FCD34D !important;
        border-radius: 14px;
        padding: 12px 14px;
        margin-bottom: 14px;
    }

    /* Cartões de Enquadramento Legal */
    .norma-card {
        background-color: #FFFFFF !important;
        border-left: 5px solid #2563EB !important;
        padding: 12px 14px;
        border-radius: 10px;
        margin-top: 10px;
        margin-bottom: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        border-top: 1px solid #E2E8F0;
        border-right: 1px solid #E2E8F0;
        border-bottom: 1px solid #E2E8F0;
    }

    /* Expanders Estilizados */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
        margin-bottom: 8px !important;
    }
    div[data-testid="stExpander"] summary {
        color: #0F172A !important;
        font-weight: 700 !important;
    }

    /* Forçar cores claras nos campos de digitação */
    div[data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 10px !important;
    }
    div[data-baseweb="input"] input {
        color: #0F172A !important;
    }
    div[data-baseweb="textarea"] {
        background-color: #FFFFFF !important;
        border: 1px solid #CBD5E1 !important;
        border-radius: 10px !important;
    }
    div[data-baseweb="textarea"] textarea {
        color: #0F172A !important;
    }

    /* Forçar cores claras nos Selectboxes */
    div[data-baseweb="select"] {
        background-color: #FFFFFF !important;
        border-radius: 10px !important;
    }
    div[data-baseweb="select"] div {
        color: #0F172A !important;
        white-space: normal !important;
        word-break: break-word !important;
    }

    /* Botões */
    .stButton > button {
        border-radius: 10px !important;
        min-height: 48px !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
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
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 24px;">
            <div style="font-size: 2.5rem; margin-bottom: 8px;">🛡️</div>
            <h2 style="margin: 0; color: #0F172A; font-weight: 800;">Vistoria SST</h2>
            <p style="color: #64748B; font-size: 0.88rem; margin-top: 4px;">Auditoria e Gestão de Riscos NR 28</p>
        </div>
        """, unsafe_allow_html=True)
        with st.form("form_login"):
            usuario_in = st.text_input("Usuário:").strip()
            senha_in = st.text_input("Senha:", type="password").strip()
            lembrar = st.checkbox("Manter conectado (7 dias)", value=True)
            entrar = st.form_submit_button("Acessar Painel", type="primary", use_container_width=True)
            if entrar:
                user_data = autenticar_usuario(usuario_in, senha_in)
                if user_data:
                    st.session_state.autenticado = True
                    st.session_state.usuario_logado = user_data[0]
                    st.session_state.perfil_logado = user_data[1]
                    if lembrar:
                        token_novo = criar_sessao(user_data[0], user_data[1])
                        st.query_params["session"] = token_novo
                    st.success("Autenticado!")
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")
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
# Auditoria de Foto com Gemini (Online)
# ---------------------------------------------------------
def analisar_imagem_com_ia(imagem_pil):
    api_key = None
    if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    elif "GEMINI_API_KEY" in os.environ:
        api_key = os.environ["GEMINI_API_KEY"]

    if not api_key:
        return None, "Chave GEMINI_API_KEY não configurada nos Secrets."

    try:
        client = genai.Client(api_key=api_key)
        prompt = """
        Você é um Engenheiro de Segurança do Trabalho especialista nas Normas Regulamentadoras (NRs) do Brasil.
        Analise a imagem desta inspeção e forneça estritamente um JSON estruturado:
        {
            "status": "Não Conformidade" ou "Conformidade",
            "nr_sugerida": "Ex: NR 35",
            "item_provavel": "Ex: 35.2.1",
            "descricao_cenario": "Descrição clara e objetiva do que foi visualizado na cena",
            "acao_corretiva": "Medida corretiva técnica imediata recomendada",
            "prioridade": "Alta", "Média" ou "Baixa"
        }
        """

        img_ia = imagem_pil.copy()
        img_ia.thumbnail((600, 600), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        img_ia.save(buf, format="JPEG", quality=70)

        ultimo_erro = ""
        for tentativa in range(3):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=[
                        types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                        prompt
                    ],
                    config={"response_mime_type": "application/json"}
                )
                return json.loads(response.text), None
            except Exception as e:
                ultimo_erro = str(e)
                if "503" in ultimo_erro or "overloaded" in ultimo_erro.lower() or "429" in ultimo_erro:
                    time.sleep(1.8 * (tentativa + 1))
                    continue
                break

        return None, f"Servidores em alta demanda ({ultimo_erro})"
    except Exception as e:
        return None, f"Instabilidade na rede: {str(e)}"

# ---------------------------------------------------------
# Buscador Local 100% Offline (Sem Internet)
# ---------------------------------------------------------
def enquadrar_local_offline(descricao_texto, df_base_nrs):
    palavras = [p.lower().strip() for p in descricao_texto.split() if len(p) > 2]
    if not palavras:
        return None, "Texto muito curto para busca local."

    df_copia = df_base_nrs.copy()
    df_copia["score"] = 0

    for p in palavras:
        mask = (
            df_copia["descricao"].str.lower().str.contains(p, na=False) |
            df_copia["categoria"].str.lower().str.contains(p, na=False) |
            df_copia["nr"].str.lower().str.contains(p, na=False)
        )
        df_copia.loc[mask, "score"] += 1

    df_ordenado = df_copia.sort_values(by="score", ascending=False)
    if df_ordenado.iloc[0]["score"] > 0:
        melhor = df_ordenado.iloc[0]
        return {
            "status": "Não Conformidade",
            "nr_sugerida": melhor["nr"],
            "item_provavel": melhor["item"],
            "descricao_cenario": f"Constatada condição irregular em campo: {melhor['descricao']}.",
            "acao_corretiva": f"Adequar de imediato as condições operacionais aos requisitos da {melhor['nr']} (Item {melhor['item']}).",
            "prioridade": "Alta" if melhor.get("infracao") in ["I4", "I3"] else "Média"
        }, None
    else:
        return None, "Nenhuma norma coincidente encontrada localmente."

# ---------------------------------------------------------
# Assistente Rápido por Texto/Voz (Groq Turbo / Fallback Gemini)
# ---------------------------------------------------------
def sugerir_enquadramento_por_texto(descricao_problema, df_base_nrs, modo_offline=False):
    if modo_offline:
        return enquadrar_local_offline(descricao_problema, df_base_nrs)

    groq_key = None
    if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
        groq_key = st.secrets["GROQ_API_KEY"]
    elif "GROQ_API_KEY" in os.environ:
        groq_key = os.environ["GROQ_API_KEY"]

    nrs_disponiveis = sorted(df_base_nrs["nr"].unique())

    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            prompt_sistema = f"""
            Você é um Engenheiro de Segurança do Trabalho especialista nas Normas Regulamentadoras (NRs) do Brasil.
            Normas cadastradas: {', '.join(nrs_disponiveis)}.
            Analise a ocorrência e devolva ESTRITAMENTE um JSON:
            {{
                "status": "Não Conformidade" ou "Conformidade",
                "nr_sugerida": "Ex: NR 35",
                "item_provavel": "Ex: 35.2.1",
                "descricao_cenario": "Resumo técnico objetivo do fato",
                "acao_corretiva": "Medida técnica recomendada",
                "prioridade": "Alta", "Média" ou "Baixa"
            }}
            """
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": f"Ocorrência: {descricao_problema}"}
                ],
                model="llama-3.3-70b-versatile",
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            return json.loads(chat_completion.choices[0].message.content), None
        except Exception:
            pass

    gemini_key = None
    if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
        gemini_key = st.secrets["GEMINI_API_KEY"]
    elif "GEMINI_API_KEY" in os.environ:
        gemini_key = os.environ["GEMINI_API_KEY"]

    if gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            prompt = f"""
            Especialista em SST Brasil. Relato: "{descricao_problema}".
            Normas: {', '.join(nrs_disponiveis)}. Formato JSON:
            {{
                "status": "Não Conformidade" ou "Conformidade",
                "nr_sugerida": "Ex: NR 35",
                "item_provavel": "Ex: 35.2.1",
                "descricao_cenario": "Resumo técnico",
                "acao_corretiva": "Medida corretiva",
                "prioridade": "Alta", "Média" ou "Baixa"
            }}
            """
            for _ in range(2):
                try:
                    res = client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    return json.loads(res.text), None
                except Exception:
                    time.sleep(1.2)
                    continue
        except Exception:
            pass

    return enquadrar_local_offline(descricao_problema, df_base_nrs)

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

def gerar_grafico_historico_empresa(df_empresa):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 3.2))
    df_sorted = df_empresa.sort_values(by="id", ascending=True).reset_index(drop=True)

    rotulos_datas = [f"Vistoria #{r['id']}\n({r['data']})" for _, r in df_sorted.iterrows()]

    ax1.plot(range(len(df_sorted)), df_sorted["multa_max"], marker='o', color='#DC2626', linewidth=2.5, label="Multa Máx em Risco")
    ax1.fill_between(range(len(df_sorted)), df_sorted["multa_max"], color='#FEE2E2', alpha=0.5)
    ax1.set_title("Evolução do Passivo (Risco R$)", fontsize=9, fontweight='bold', pad=8)
    ax1.set_xticks(range(len(df_sorted)))
    ax1.set_xticklabels(rotulos_datas, fontsize=7.5)
    ax1.grid(axis='y', linestyle='--', alpha=0.4)
    ax1.legend(fontsize=7.5)

    ax2.bar(range(len(df_sorted)), df_sorted["total_itens"], color='#3B82F6', width=0.4)
    ax2.set_title("Total de Itens Auditados", fontsize=9, fontweight='bold', pad=8)
    ax2.set_xticks(range(len(df_sorted)))
    ax2.set_xticklabels(rotulos_datas, fontsize=7.5)
    ax2.grid(axis='y', linestyle='--', alpha=0.4)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='PNG', dpi=180)
    plt.close(fig)
    buf.seek(0)
    return buf

# ---------------------------------------------------------
# Classe Especial de Canvas para Paginação Dinâmica
# ---------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColorHex("#64748B")
        texto_esquerda = "Laudo Técnico de Auditoria SST & Enquadramento NR 28"
        texto_direita = f"Página {self._pageNumber} de {page_count}"
        
        self.setStrokeColorHex("#CBD5E1")
        self.setLineWidth(0.5)
        self.line(36, 26, A4[0] - 36, 26)
        self.drawString(36, 16, texto_esquerda)
        self.drawRightString(A4[0] - 36, 16, texto_direita)
        self.restoreState()

# ---------------------------------------------------------
# Gerador de Relatório PDF Completo (Design Pericial)
# ---------------------------------------------------------
def gerar_pdf_completo(dados_gerais, lista_evidencias, logo_pil=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=38
    )
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
        Paragraph("Relatório Pericial de Vistoria, Riscos e Conformidades SST", titulo_style),
        Spacer(1, 4),
        Paragraph(f"<b>Emissão Forense:</b> {dados_gerais['data']} | <b>Responsável Técnico:</b> {dados_gerais['inspetor']}", sub_style)
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
        [Paragraph("Empresa Auditada:", cell_label), Paragraph(dados_gerais['empresa_cliente'], cell_value)],
        [Paragraph("Faixa de Funcionários:", cell_label), Paragraph(dados_gerais['faixa_func'], cell_value)],
        [Paragraph("Quadro de Constatações:", cell_label), Paragraph(f"<b>{qtd_nc}</b> Não Conformidade(s)  |  <b>{qtd_conf}</b> Boa(s) Prática(s)", cell_value)],
        [Paragraph("Passivo em Risco (Multas NR 28):", cell_label), Paragraph(f"<font color='#B91C1C'><b>{formata_brl(total_multa_min)} a {formata_brl(total_multa_max)}</b></font>", cell_value)],
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

    elementos.append(Paragraph("<b>4. Análise Gráfica: Riscos de Multas vs Economia Gerada</b>", styles['Heading3']))
    elementos.append(Spacer(1, 6))
    grafico_buf = gerar_grafico_multas(lista_evidencias)
    elementos.append(ReportLabImage(grafico_buf, width=490, height=220))
    elementos.append(Spacer(1, 14))

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

    # 7. Termo de Encerramento e Assinaturas Periciais
    elementos.append(Spacer(1, 24))
    elementos.append(Paragraph("<b>7. Termo de Ciência e Notificação Pericial</b>", styles['Heading3']))
    elementos.append(Paragraph("<i>As partes declaram ciência dos fatos registrados neste relatório técnico e comprometem-se a cumprir os prazos e ações estabelecidos no Plano de Ação:</i>", sub_style))
    elementos.append(Spacer(1, 16))

    dados_assinaturas = [
        [
            Paragraph("____________________________________________<br/><b>Responsável Técnico / Auditor SST</b><br/>Registro Profissional: ___________________", cell_td_center),
            Paragraph("____________________________________________<br/><b>Representante da Empresa / Obra</b><br/>Cargo / Função: ___________________", cell_td_center)
        ]
    ]
    t_ass = Table(dados_assinaturas, colWidths=[261, 262])
    t_ass.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elementos.append(t_ass)

    doc.build(elementos, canvasmaker=NumberedCanvas)
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
    st.markdown(f"👤 **{st.session_state.usuario_logado}** (`{st.session_state.perfil_logado}`)")
    if lat_capturada and lon_capturada:
        st.caption(f"📍 GPS Ativo: `{lat_capturada:.4f}, {lon_capturada:.4f}`")
    else:
        st.caption("📍 GPS: Aguardando sinal...")

    if "modo_offline" not in st.session_state:
        st.session_state.modo_offline = False

    st.markdown("---")
    st.session_state.modo_offline = st.toggle("📴 Modo Campo / Offline", value=st.session_state.modo_offline)
    if st.session_state.modo_offline:
        st.caption("⚡ Busca local ativa no dispositivo. Chamadas em nuvem desativadas.")

    if st.button("🚪 Encerrar Sessão", use_container_width=True):
        token_atual = st.query_params.get("session")
        if token_atual:
            revogar_token_sessao(token_atual)
            st.query_params.clear()
        st.session_state.autenticado = False
        st.session_state.usuario_logado = ""
        st.session_state.perfil_logado = ""
        st.rerun()

    st.markdown("---")
    opcoes_menu = ["📋 Vistoria em Campo"]
    if st.session_state.perfil_logado == "Admin":
        opcoes_menu.append("⚙️ Painel de Administração")
    
    aba_selecionada = st.radio("Navegação:", opcoes_menu)

    st.markdown("---")
    st.subheader("Logomarca do Laudo")
    logo_upload = st.file_uploader("Upload (PNG/JPG):", type=["png", "jpg", "jpeg"])
    logo_para_relatorio = None
    if logo_upload:
        logo_para_relatorio = Image.open(logo_upload)
        st.image(logo_para_relatorio, caption="Logo Ativa", width=140)
    elif os.path.exists("logo.png"):
        logo_para_relatorio = Image.open("logo.png")
        st.image(logo_para_relatorio, caption="Logo padrão", width=140)

# =========================================================
# ABA 1: PAINEL DE ADMINISTRAÇÃO & DASHBOARD POR EMPRESA
# =========================================================
if aba_selecionada == "⚙️ Painel de Administração":
    st.markdown("## ⚙️ Painel Administrativo")
    st.caption("Gestão de acessos e inteligência de dados")

    tab_usuarios, tab_relatorios, tab_dashboard = st.tabs(["👥 Usuários", "📂 Histórico de Laudos", "📈 Dashboard por Empresa"])

    with tab_usuarios:
        usuarios_atuais = listar_usuarios()
        st.dataframe(pd.DataFrame(usuarios_atuais, columns=["Usuário", "Perfil"]), use_container_width=True)

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            with st.form("form_novo_user"):
                st.markdown("**Novo Inspetor/Usuário**")
                novo_nome = st.text_input("Usuário:").strip()
                nova_senha = st.text_input("Senha:", type="password").strip()
                novo_perfil = st.selectbox("Perfil:", ["Inspetor", "Admin"])
                cadastrar = st.form_submit_button("Cadastrar", type="primary", use_container_width=True)
                if cadastrar and novo_nome and nova_senha:
                    sucesso, msg = criar_usuario_db(novo_nome, nova_senha, novo_perfil)
                    if sucesso:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        with col_u2:
            users_para_deletar = [u[0] for u in usuarios_atuais if u[0] != st.session_state.usuario_logado]
            if users_para_deletar:
                st.markdown("**Remover Usuário**")
                user_del = st.selectbox("Selecione:", users_para_deletar)
                if st.button("🗑️ Excluir", type="secondary", use_container_width=True):
                    excluir_usuario_db(user_del)
                    st.success("Usuário removido!")
                    st.rerun()

    with tab_relatorios:
        relatorios_salvos = listar_relatorios()
        if relatorios_salvos:
            df_rel = pd.DataFrame(
                relatorios_salvos,
                columns=["ID", "Data", "Empresa", "Inspetor", "Itens", "Multa Mín", "Multa Máx", "Economia Mín", "Economia Máx"]
            )
            df_rel["Multa Mín"] = df_rel["Multa Mín"].apply(formata_brl)
            df_rel["Multa Máx"] = df_rel["Multa Máx"].apply(formata_brl)
            df_rel["Economia Mín"] = df_rel["Economia Mín"].apply(formata_brl)
            df_rel["Economia Máx"] = df_rel["Economia Máx"].apply(formata_brl)
            st.dataframe(df_rel, use_container_width=True)

            opcoes_rel = {r[0]: f"#{r[0]} - {r[2]} ({r[1]})" for r in relatorios_salvos}
            id_sel = st.selectbox("Download de Laudo Salvo:", list(opcoes_rel.keys()), format_func=lambda x: opcoes_rel[x])
            dados_pdf = obter_pdf_relatorio(id_sel)
            if dados_pdf:
                pdf_bytes, emp_nome, _ = dados_pdf
                st.download_button(
                    label="⬇️ Baixar PDF",
                    data=pdf_bytes,
                    file_name=f"Laudo_{id_sel}_{emp_nome.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        else:
            st.info("Nenhum laudo salvo no sistema.")

    with tab_dashboard:
        st.subheader("Evolução de SST e Redução de Riscos")
        relatorios_salvos = listar_relatorios()
        if relatorios_salvos:
            df_todos = pd.DataFrame(
                relatorios_salvos,
                columns=["id", "data", "empresa", "inspetor", "total_itens", "multa_min", "multa_max", "economia_min", "economia_max"]
            )
            empresas_unicas = sorted(df_todos["empresa"].unique())
            emp_selecionada = st.selectbox("Selecione a Empresa para Análise:", empresas_unicas)

            df_emp = df_todos[df_todos["empresa"] == emp_selecionada].sort_values(by="id", ascending=True)

            if len(df_emp) > 0:
                primeira_multa = df_emp.iloc[0]["multa_max"]
                ultima_multa = df_emp.iloc[-1]["multa_max"]
                total_economizado = df_emp["economia_max"].sum()
                qtd_vistorias = len(df_emp)

                diff_perc = 0
                if primeira_multa > 0:
                    diff_perc = ((primeira_multa - ultima_multa) / primeira_multa) * 100

                st.markdown(f"""
                <div class="kpi-container">
                    <div class="kpi-card kpi-card-info">
                        <div class="kpi-title">Vistorias Realizadas</div>
                        <div class="kpi-value kpi-value-info">{qtd_vistorias}</div>
                        <div class="kpi-sub">Total de inspeções salvas</div>
                    </div>
                    <div class="kpi-card kpi-card-danger">
                        <div class="kpi-title">Risco Atual (Última)</div>
                        <div class="kpi-value kpi-value-danger">{formata_brl(ultima_multa)}</div>
                        <div class="kpi-sub">Inicial: {formata_brl(primeira_multa)}</div>
                    </div>
                    <div class="kpi-card kpi-card-success">
                        <div class="kpi-title">Redução de Passivo</div>
                        <div class="kpi-value kpi-value-success">{diff_perc:.1f}%</div>
                        <div class="kpi-sub">Economia Acum.: {formata_brl(total_economizado)}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if len(df_emp) > 1:
                    st.markdown("**Gráfico de Tendência (Evolução do Passivo Fiscal):**")
                    buf_graf = gerar_grafico_historico_empresa(df_emp)
                    st.image(buf_graf, use_container_width=True)
                else:
                    st.info("Esta empresa possui apenas 1 vistoria salva. Realize a próxima auditoria para habilitar o gráfico evolutivo de redução de riscos.")
        else:
            st.info("Nenhuma vistoria salva para exibição do dashboard.")

# =========================================================
# ABA 2: VISTORIA EM CAMPO (Online & Offline com Sync)
# =========================================================
elif aba_selecionada == "📋 Vistoria em Campo":
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
        st.markdown(f"""
        <div style="background:#FEF3C7; border:1px solid #FCD34D; border-radius:12px; padding:12px 14px; margin-bottom:12px;">
            <b style="color:#92400E;">💾 Vistoria pendente detectada</b><br/>
            <span style="font-size:0.85rem; color:#78350F;">Existe um rascunho de <b>{rascunho_existente['empresa']}</b> atualizado em {rascunho_existente['atualizado_em']}.</span>
        </div>
        """, unsafe_allow_html=True)
        c_ret1, c_ret2 = st.columns(2)
        with c_ret1:
            if st.button("🔄 Retomar Vistoria", type="primary", use_container_width=True):
                st.session_state.evidencias = rascunho_existente["evidencias"]
                st.session_state.modo_adicionar = False
                st.rerun()
        with c_ret2:
            if st.button("🗑️ Descartar", use_container_width=True):
                limpar_rascunho_db(st.session_state.usuario_logado)
                st.rerun()

    passo_1_cls = "step-active" if not st.session_state.evidencias else ""
    passo_2_cls = "step-active" if st.session_state.modo_adicionar else ""
    passo_3_cls = "step-active" if (st.session_state.evidencias and not st.session_state.modo_adicionar) else ""

    st.markdown(f"""
    <div class="stepper-container">
        <div class="step-item {passo_1_cls}"><b>1</b> Identificação</div>
        <div class="step-item {passo_2_cls}"><b>2</b> Apontamentos ({len(st.session_state.evidencias)})</div>
        <div class="step-item {passo_3_cls}"><b>3</b> Laudo & PDF</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("🏢 Dados da Obra & Equipe", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            emp_padrao = rascunho_existente["empresa"] if (rascunho_existente and not st.session_state.evidencias) else "Construtora Exemplo Ltda"
            empresa_cliente = st.text_input("Empresa Cliente:", value=emp_padrao)
            inspetor_padrao = f"{st.session_state.usuario_logado.capitalize()} (SST)"
            inspetor = st.text_input("Responsável Técnico:", value=inspetor_padrao)
        with col2:
            faixa_func = st.selectbox("Quadro de Funcionários:", list(TABELA_MULTAS_SEGURANCA.keys()), index=2)
    
    if "empresa_cliente" not in locals():
        empresa_cliente = "Construtora Exemplo Ltda"
        inspetor = f"{st.session_state.usuario_logado.capitalize()} (SST)"
        faixa_func = list(TABELA_MULTAS_SEGURANCA.keys())[2]

    # BOTÃO DE SINCRONIZAÇÃO EM LOTE
    if st.session_state.evidencias:
        if st.session_state.modo_offline:
            st.info("📴 Você está no Modo Campo (Offline). Quando retornar a um local com sinal, desative o modo offline no menu lateral para sincronizar e reavaliar seus apontamentos com a IA.")
        else:
            col_sync1, col_sync2 = st.columns([2.5, 1])
            with col_sync1:
                st.markdown("<p style='margin:0; font-size:0.85rem; color:#1E293B;'>Deseja aprimorar todos os apontamentos salvos com a IA da nuvem?</p>", unsafe_allow_html=True)
            with col_sync2:
                if st.button("🔄 Sincronizar Tudo", use_container_width=True, type="secondary"):
                    with st.spinner("Refinando laudo com inteligência artificial..."):
                        itens_atualizados = 0
                        for it in st.session_state.evidencias:
                            res, _ = sugerir_enquadramento_por_texto(it["descricao_cenario"], df_nr_base, modo_offline=False)
                            if res:
                                it["acao_corretiva"] = res.get("acao_corretiva", it["acao_corretiva"])
                                it["prioridade"] = res.get("prioridade", it["prioridade"])
                                itens_atualizados += 1
                        salvar_rascunho_db(st.session_state.usuario_logado, empresa_cliente, inspetor, faixa_func, st.session_state.evidencias)
                        st.toast(f"✅ {itens_atualizados} apontamento(s) sincronizados com sucesso!")
                        st.rerun()

    tot_multa_min = sum(e['valor_min'] for e in st.session_state.evidencias if e['status'] == "Não Conformidade")
    tot_multa_max = sum(e['valor_max'] for e in st.session_state.evidencias if e['status'] == "Não Conformidade")
    tot_econ_min = sum(e['valor_min'] for e in st.session_state.evidencias if e['status'] == "Conformidade")
    tot_econ_max = sum(e['valor_max'] for e in st.session_state.evidencias if e['status'] == "Conformidade")

    st.markdown(f"""
    <div class="kpi-container">
        <div class="kpi-card kpi-card-danger">
            <div class="kpi-title">⚠️ Passivo em Risco</div>
            <div class="kpi-value kpi-value-danger">{formata_brl(tot_multa_max)}</div>
            <div class="kpi-sub">Mínimo: {formata_brl(tot_multa_min)}</div>
        </div>
        <div class="kpi-card kpi-card-success">
            <div class="kpi-title">✅ Economia Gerada</div>
            <div class="kpi-value kpi-value-success">{formata_brl(tot_econ_max)}</div>
            <div class="kpi-sub">Mínimo: {formata_brl(tot_econ_min)}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.modo_adicionar or st.session_state.editando_indice is not None:
        idx_edicao = st.session_state.editando_indice
        
        if idx_edicao is not None:
            st.markdown(f"#### ✏️ Editando Apontamento #{idx_edicao + 1}")
            item_edicao = st.session_state.evidencias[idx_edicao]
            if not st.session_state.fotos_atuais and item_edicao.get("imagens"):
                st.session_state.fotos_atuais = list(item_edicao["imagens"])
        else:
            st.markdown(f"#### ➕ Registrar Apontamento #{len(st.session_state.evidencias) + 1}")
            item_edicao = None

        if not st.session_state.modo_offline:
            st.markdown("""
            <div class="ai-assistant-card">
                <div style="font-weight:700; color:#1E40AF; font-size:0.90rem; margin-bottom:2px;">
                    ⚡ Enquadramento Inteligente (Texto ou Voz)
                </div>
                <div style="font-size:0.80rem; color:#1E3A8A;">
                    Dite ou digite o que foi visto na obra para localizar a norma automaticamente:
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="offline-card">
                <div style="font-weight:700; color:#92400E; font-size:0.90rem; margin-bottom:2px;">
                    📴 Buscador Local Ativo (100% Offline)
                </div>
                <div style="font-size:0.80rem; color:#78350F;">
                    Digite palavras-chave (ex: altura, epi, serra, eletrica) para buscar na base interna sem internet:
                </div>
            </div>
            """, unsafe_allow_html=True)

        col_t1, col_t2 = st.columns([3, 1.2])
        with col_t1:
            texto_relato = st.text_input(
                "Descreva a ocorrência:",
                placeholder="Ex: Operários em andaime a 4m sem cinto e sem proteção",
                key=f"texto_ia_{st.session_state.contador_fluxo}",
                label_visibility="collapsed"
            )
        with col_t2:
            botao_label = "🔍 Enquadrar" if not st.session_state.modo_offline else "⚡ Buscar NR"
            if st.button(botao_label, use_container_width=True, type="secondary"):
                if texto_relato.strip():
                    with st.spinner("Localizando norma..."):
                        res_ia, err_ia = sugerir_enquadramento_por_texto(texto_relato, df_nr_base, st.session_state.modo_offline)
                        if res_ia:
                            st.session_state.ia_sugestao = res_ia
                            st.toast(f"✅ Enquadrado na {res_ia.get('nr_sugerida', 'NR')}!")
                            st.rerun()
                        else:
                            st.error(err_ia)
                else:
                    st.warning("Preencha o relato primeiro.")

        st.markdown("**1. Evidências Fotográficas (Carimbo Forense):**")
        col_cam, col_up = st.columns(2)
        with col_cam:
            if not st.session_state.abrir_camera:
                if st.button("📷 Abrir Câmera", use_container_width=True):
                    st.session_state.abrir_camera = True
                    st.rerun()
            else:
                foto_cam = st.camera_input("Foto da evidência:", key=f"cam_{st.session_state.contador_fluxo}")
                c_c1, c_c2 = st.columns(2)
                with c_c1:
                    if foto_cam and st.button("Salvar Foto", type="primary", use_container_width=True):
                        img_proc = otimizar_e_carimbar(Image.open(foto_cam), lat_capturada, lon_capturada)
                        st.session_state.fotos_atuais.append(img_proc)
                        st.session_state.abrir_camera = False
                        st.rerun()
                with c_c2:
                    if st.button("Fechar", use_container_width=True):
                        st.session_state.abrir_camera = False
                        st.rerun()

        with col_up:
            arquivos_up = st.file_uploader("Ou da galeria / câmera nativa:", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"up_{st.session_state.contador_fluxo}")
            if arquivos_up and st.button("➕ Confirmar Anexos", use_container_width=True):
                for arq in arquivos_up:
                    img_proc = otimizar_e_carimbar(Image.open(arq), lat_capturada, lon_capturada)
                    st.session_state.fotos_atuais.append(img_proc)
                st.toast(f"{len(arquivos_up)} foto(s) carimbada(s)!")

        if st.session_state.fotos_atuais:
            st.write(f"Fotos anexadas ({len(st.session_state.fotos_atuais)}):")
            cols_p = st.columns(min(len(st.session_state.fotos_atuais), 4))
            for idx_f, img in enumerate(st.session_state.fotos_atuais):
                cols_p[idx_f % 4].image(img, use_container_width=True)

            col_ia, col_limp = st.columns([1.5, 1])
            with col_ia:
                if not st.session_state.modo_offline:
                    if st.button("✨ Analisar Foto com Gemini", use_container_width=True):
                        with st.spinner("Avaliando imagem..."):
                            res_ia, err_ia = analisar_imagem_com_ia(st.session_state.fotos_atuais[0])
                            if res_ia:
                                st.session_state.ia_sugestao = res_ia
                                st.toast("✅ Sugestão aplicada!")
                                st.rerun()
                            else:
                                st.warning(err_ia)
            with col_limp:
                if st.button("❌ Limpar Fotos", use_container_width=True):
                    st.session_state.fotos_atuais = []
                    st.session_state.ia_sugestao = None
                    st.rerun()

        st.markdown("**2. Condição do Apontamento:**")
        index_status = 0
        if item_edicao:
            index_status = 1 if item_edicao["status"] == "Conformidade" else 0
        elif st.session_state.ia_sugestao and st.session_state.ia_sugestao.get("status") == "Conformidade":
            index_status = 1

        status_selecionado = st.radio(
            "Situação constatada:",
            ["⚠️ Não Conformidade (Passivo Fiscal / Risco)", "✅ Conformidade (Boa Prática / Economia)"],
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

            prioridade_selecionada = st.selectbox("Grau de Prioridade Técnica:", ["Alta", "Média", "Baixa"], index=idx_prio, key=f"prio_{st.session_state.contador_fluxo}")

        st.markdown("**3. Seleção da Norma Regulamentadora:**")
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

        item_idx = st.selectbox("Item correspondente:", range(len(opcoes_itens)), index=idx_item_padrao, format_func=lambda x: opcoes_itens[x], key=f"item_sel_{st.session_state.contador_fluxo}")
        item_escolhido = df_filtrado.iloc[item_idx]
        multa_calc_min, multa_calc_max = calcular_multa(item_escolhido['infracao'], faixa_func, item_escolhido['tipo'])

        if eh_conforme:
            st.markdown(f"""
            <div class="norma-card" style="border-left-color: #10B981;">
                <span class="badge-pill badge-success">BOA PRÁTICA</span>
                <b style="color: #065F46;">{item_escolhido['nr']} (Item {item_escolhido['item']})</b>
                <p style="margin: 4px 0; color: #1E293B; font-size: 0.9rem;">{item_escolhido['descricao']}</p>
                <span style="font-size: 0.82rem; color: #047857;"><b>Economia Gerada Estimada:</b> {formata_brl(multa_calc_min)} a {formata_brl(multa_calc_max)}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            cor_badge = "badge-danger" if prioridade_selecionada == "Alta" else "badge-warning"
            st.markdown(f"""
            <div class="norma-card" style="border-left-color: #EF4444;">
                <span class="badge-pill {cor_badge}">PRIORIDADE {prioridade_selecionada.upper()}</span>
                <b style="color: #991B1B;">{item_escolhido['nr']} (Item {item_escolhido['item']})</b>
                <p style="margin: 4px 0; color: #1E293B; font-size: 0.9rem;">{item_escolhido['descricao']}</p>
                <span style="font-size: 0.82rem; color: #B91C1C;"><b>Multa Prevista (NR 28):</b> {formata_brl(multa_calc_min)} a {formata_brl(multa_calc_max)} | Grau {item_escolhido['infracao']}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("**4. Plano de Ação e Laudo:**")
        if item_edicao:
            valor_padrao_cenario = item_edicao.get("descricao_cenario", "")
            valor_padrao_acao = item_edicao.get("acao_corretiva", "")
        elif st.session_state.ia_sugestao:
            valor_padrao_cenario = st.session_state.ia_sugestao.get("descricao_cenario", "")
            valor_padrao_acao = st.session_state.ia_sugestao.get("acao_corretiva", "")
        else:
            valor_padrao_cenario = ""
            valor_padrao_acao = ""

        desc_cenario = st.text_area("Cenário Observado:", value=valor_padrao_cenario, placeholder="Descreva o que foi visto em campo...", key=f"cenario_{st.session_state.contador_fluxo}")
        label_acao = "Conduta Mantida:" if eh_conforme else "Ação Corretiva Recomendada:"
        acao_corretiva = st.text_area(label_acao, value=valor_padrao_acao, placeholder="Medidas imediatas...", key=f"acao_{st.session_state.contador_fluxo}")

        texto_btn_salvar = "💾 Atualizar Apontamento" if idx_edicao is not None else "💾 Salvar no Laudo"
        if st.button(texto_btn_salvar, type="primary", use_container_width=True):
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
                "descricao_cenario": desc_cenario if desc_cenario else ("Conformidade atendida." if eh_conforme else "Não conformidade constatada."),
                "acao_corretiva": acao_corretiva if acao_corretiva else ("Manter rotina operacional." if eh_conforme else "Regularizar conforme norma."),
                "imagens": list(st.session_state.fotos_atuais)
            }
            if idx_edicao is not None:
                st.session_state.evidencias[idx_edicao] = novo_dado
                st.session_state.editando_indice = None
                st.toast("✅ Apontamento atualizado!")
            else:
                st.session_state.evidencias.append(novo_dado)
                st.toast("✅ Apontamento salvo!")

            salvar_rascunho_db(st.session_state.usuario_logado, empresa_cliente, inspetor, faixa_func, st.session_state.evidencias)

            st.session_state.fotos_atuais = []
            st.session_state.ia_sugestao = None
            st.session_state.modo_adicionar = False
            st.session_state.abrir_camera = False
            st.session_state.contador_fluxo += 1
            st.rerun()

    else:
        st.write("---")
        c_add, c_fin = st.columns(2)
        with c_add:
            if st.button("➕ Novo Apontamento", use_container_width=True):
                st.session_state.modo_adicionar = True
                st.session_state.editando_indice = None
                st.session_state.fotos_atuais = []
                st.rerun()
        with c_fin:
            if st.button("🏁 Fechar e Emitir Laudo", type="primary", use_container_width=True):
                st.session_state.modo_adicionar = False
                st.session_state.editando_indice = None

    if st.session_state.evidencias:
        st.markdown(f"#### 📑 Apontamentos Registrados ({len(st.session_state.evidencias)})")
        for idx, ev in enumerate(st.session_state.evidencias):
            eh_c = (ev["status"] == "Conformidade")
            prio = ev.get("prioridade", "Média")
            badge_html = '<span class="badge-pill badge-success">BOA PRÁTICA</span>' if eh_c else (
                f'<span class="badge-pill badge-danger">PRIORIDADE {prio.upper()}</span>' if prio == "Alta" else f'<span class="badge-pill badge-warning">PRIORIDADE {prio.upper()}</span>'
            )

            with st.expander(f"#{idx + 1} — {ev['nr']} (Item {ev['item_nr']})"):
                st.markdown(f"{badge_html} **{ev['nr']}**", unsafe_allow_html=True)
                st.markdown(f"**Infração / Requisito:** {ev['descricao']}")
                st.markdown(f"**Cenário:** {ev['descricao_cenario']}")
                st.markdown(f"**Ação:** {ev['acao_corretiva']}")
                st.caption(f"Fotos anexadas: {len(ev.get('imagens', []))} registro(s)")
                
                c_ed, c_del = st.columns(2)
                with c_ed:
                    if st.button("✏️ Editar", key=f"btn_e_{idx}", use_container_width=True):
                        st.session_state.editando_indice = idx
                        st.session_state.modo_adicionar = True
                        st.session_state.fotos_atuais = list(ev.get("imagens", []))
                        st.rerun()
                with c_del:
                    if st.button("🗑️ Excluir", key=f"btn_d_{idx}", use_container_width=True):
                        st.session_state.evidencias.pop(idx)
                        salvar_rascunho_db(st.session_state.usuario_logado, empresa_cliente, inspetor, faixa_func, st.session_state.evidencias)
                        st.rerun()

        ncs_atuais = [e for e in st.session_state.evidencias if e['status'] == "Não Conformidade"]
        st.markdown("#### 📲 Envio Imediato por WhatsApp")
        c_w1, c_w2 = st.columns([2, 1.2])
        with c_w1:
            tel_wpp = st.text_input("WhatsApp do Gestor/Cliente:", placeholder="DDD + Número (ex: 34999998888)", label_visibility="collapsed")
        with c_w2:
            if tel_wpp:
                link_wpp = gerar_link_whatsapp(tel_wpp, empresa_cliente, tot_multa_max, tot_econ_max, len(ncs_atuais))
                st.markdown(f'<a href="{link_wpp}" target="_blank"><button style="background-color:#25D366;color:white;border:none;height:48px;border-radius:10px;font-weight:700;width:100%;cursor:pointer;">💬 Enviar</button></a>', unsafe_allow_html=True)

        st.markdown("#### 📄 Laudo Técnico com Plano de Ação")
        data_hoje = datetime.date.today().strftime("%d/%m/%Y")
        dados_relatorio = {
            "empresa_cliente": empresa_cliente,
            "inspetor": inspetor,
            "faixa_func": faixa_func,
            "data": data_hoje
        }

        pdf_buffer = gerar_pdf_completo(dados_relatorio, st.session_state.evidencias, logo_pil=logo_para_relatorio)
        pdf_bytes_final = pdf_buffer.getvalue()

        c_sv, c_bx, c_lp = st.columns([1.2, 1.4, 1])
        with c_sv:
            if st.button("💾 Salvar Histórico", use_container_width=True):
                salvar_relatorio_db(data_hoje, empresa_cliente, inspetor, len(st.session_state.evidencias), tot_multa_min, tot_multa_max, tot_econ_min, tot_econ_max, pdf_bytes_final)
                limpar_rascunho_db(st.session_state.usuario_logado)
                st.toast("✅ Salvo no histórico!")
        with c_bx:
            st.download_button(
                label="⬇️ Baixar PDF",
                data=pdf_bytes_final,
                file_name=f"Laudo_SST_{empresa_cliente.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        with c_lp:
            if st.button("🗑️ Nova", use_container_width=True):
                limpar_rascunho_db(st.session_state.usuario_logado)
                st.session_state.evidencias = []
                st.session_state.fotos_atuais = []
                st.session_state.ia_sugestao = None
                st.session_state.editando_indice = None
                st.session_state.modo_adicionar = True
                st.rerun()
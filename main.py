import io
import os
import json
import sqlite3
import datetime
import urllib.parse
import base64
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt

from nicegui import ui

# ---------------------------------------------------------
# 1. IMPORTAÇÃO DE IA E REPORTLAB
# ---------------------------------------------------------
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as ReportLabImage, Table, TableStyle
from reportlab.pdfgen import canvas

# ---------------------------------------------------------
# 2. BANCO DE DADOS (SQLITE LOCAL)
# ---------------------------------------------------------
DB_FILE = "sst_database.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                usuario TEXT PRIMARY KEY,
                senha TEXT NOT NULL,
                perfil TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS empresas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL,
                cnpj TEXT,
                faixa_func TEXT NOT NULL,
                contato_wpp TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS config_sistema (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
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
                economia_min REAL NOT NULL,
                economia_max REAL NOT NULL,
                pdf_bytes BLOB NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS rascunhos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL,
                empresa TEXT NOT NULL,
                data_atualizacao TEXT NOT NULL,
                estado_json TEXT NOT NULL
            )
        """)
        c.execute("SELECT usuario FROM usuarios WHERE usuario = 'admin'")
        if not c.fetchone():
            c.execute("INSERT INTO usuarios (usuario, senha, perfil) VALUES ('admin', '1234', 'Admin')")
            
        c.execute("SELECT count(*) FROM empresas")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO empresas (nome, cnpj, faixa_func, contato_wpp) VALUES (?, ?, ?, ?)",
                      ("Construtora Exemplo Ltda", "00.000.000/0001-00", "26 a 50", "34999990000"))
        conn.commit()

init_db()

def autenticar_usuario(usuario, senha):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT usuario, perfil FROM usuarios WHERE usuario = ? AND senha = ?", (usuario, senha))
        return c.fetchone()

def listar_usuarios():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT usuario, perfil FROM usuarios ORDER BY usuario ASC")
        return c.fetchall()

def criar_usuario(usuario, senha, perfil):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO usuarios (usuario, senha, perfil) VALUES (?, ?, ?)", (usuario, senha, perfil))
            conn.commit()
        return True, "Usuário cadastrado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Usuário já existente!"

def listar_empresas_db():
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query("SELECT id, nome, cnpj, faixa_func, contato_wpp FROM empresas ORDER BY nome ASC", conn)

def cadastrar_empresa_db(nome, cnpj, faixa, wpp):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO empresas (nome, cnpj, faixa_func, contato_wpp)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(nome) DO UPDATE SET
                cnpj=excluded.cnpj,
                faixa_func=excluded.faixa_func,
                contato_wpp=excluded.contato_wpp
        """, (nome, cnpj, faixa, wpp))
        conn.commit()

def salvar_logo_consultoria_db(b64_str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO config_sistema (chave, valor) VALUES ('logo_consultoria', ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (b64_str,))
        conn.commit()

def carregar_logo_consultoria_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT valor FROM config_sistema WHERE chave = 'logo_consultoria'")
        row = c.fetchone()
        if row and row[0]:
            try:
                return Image.open(io.BytesIO(base64.b64decode(row[0])))
            except Exception:
                return None
    return None

def salvar_relatorio_db(data_str, emp, insp, total, m_min, m_max, e_min, e_max, pdf_bytes):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO relatorios (data, empresa, inspetor, total_itens, multa_min, multa_max, economia_min, economia_max, pdf_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data_str, emp, insp, total, m_min, m_max, e_min, e_max, pdf_bytes))
        conn.commit()

def listar_relatorios_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, data, empresa, inspetor, total_itens, multa_min, multa_max, economia_min, economia_max FROM relatorios ORDER BY id DESC")
        return c.fetchall()

def obter_pdf_relatorio_db(rel_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT pdf_bytes, empresa, data FROM relatorios WHERE id = ?", (rel_id,))
        return c.fetchone()

# Funções de Rascunho
def salvar_rascunho_db(usuario, empresa, estado_dict):
    data_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    estado_copia = estado_dict.copy()
    evs_serializadas = []
    for ev in estado_copia.get('evidencias', []):
        ev_c = ev.copy()
        if ev_c.get('foto_pil'):
            buf = io.BytesIO()
            ev_c['foto_pil'].save(buf, format='JPEG', quality=85)
            ev_c['foto_b64'] = base64.b64encode(buf.getvalue()).decode('utf-8')
            del ev_c['foto_pil']
        evs_serializadas.append(ev_c)
    estado_copia['evidencias'] = evs_serializadas
    json_str = json.dumps(estado_copia)
    
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO rascunhos (usuario, empresa, data_atualizacao, estado_json)
            VALUES (?, ?, ?, ?)
        """, (usuario, empresa, data_str, json_str))
        conn.commit()

def listar_rascunhos_db(usuario):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, empresa, data_atualizacao FROM rascunhos WHERE usuario = ? ORDER BY id DESC", (usuario,))
        return c.fetchall()

def carregar_rascunho_db(rascunho_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT estado_json FROM rascunhos WHERE id = ?", (rascunho_id,))
        row = c.fetchone()
        if row:
            state = json.loads(row[0])
            for ev in state.get('evidencias', []):
                if ev.get('foto_b64'):
                    try:
                        img_bytes = base64.b64decode(ev['foto_b64'])
                        ev['foto_pil'] = Image.open(io.BytesIO(img_bytes))
                    except Exception:
                        ev['foto_pil'] = None
                else:
                    ev['foto_pil'] = None
            return state
    return None

def deletar_rascunho_db(rascunho_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM rascunhos WHERE id = ?", (rascunho_id,))
        conn.commit()

# ---------------------------------------------------------
# 3. TABELAS OFICIAIS NR 28
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
    "501 a 1000":{"I1": (1961, 2240), "I2": (2241, 3080), "I3": (3921, 5040),  "I4": (3921, 5040)},
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
# 4. UTILITÁRIOS (CARIMBO FORENSE, IA E PDF)
# ---------------------------------------------------------
def otimizar_e_carimbar(imagem_original, lat=None, lon=None):
    img = imagem_original.convert("RGB")
    img.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img)
    largura, altura = img.size
    altura_barra = max(34, int(altura * 0.065))
    agora_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    draw.rectangle([0, altura - altura_barra, largura, altura], fill=(15, 23, 42))
    texto_gps = f" | GPS: {lat:.5f}, {lon:.5f}" if (lat and lon) else " | GPS: Vistoria Pericial in loco"
    texto_completo = f"REGISTRO FORENSE SST: {agora_str}{texto_gps}"

    try:
        fonte = ImageFont.load_default()
    except Exception:
        fonte = None

    pos_y = altura - int(altura_barra * 0.65)
    draw.text((15, pos_y), texto_completo, fill=(255, 255, 255), font=fonte)
    return img

def tratar_imagem_assinatura(raw_img):
    arr = np.array(raw_img)
    h, w = arr.shape[:2]
    img_final = np.full((h, w, 3), 255, dtype=np.uint8)
    if arr.ndim == 3 and arr.shape[2] == 4:
        a = arr[:, :, 3]
        mask_desenho = a > 20
        img_final[mask_desenho] = [15, 23, 42]
    else:
        cinza = np.mean(arr[:, :, :3], axis=2)
        if cinza[0, 0] < 50:
            mask_traco = cinza > 30
            img_final[mask_traco] = [15, 23, 42]
        else:
            mask_traco = cinza < 220
            img_final[mask_traco] = [15, 23, 42]
    return Image.fromarray(img_final, 'RGB')

def limpar_resposta_json(texto_bruto):
    t = texto_bruto.strip()
    if t.startswith("```json"):
        t = t[7:]
    elif t.startswith("```"):
        t = t[3:]
    if t.endswith("```"):
        t = t[:-3]
    return t.strip()

def sugerir_enquadramento(texto_relato, df_base):
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    nrs = sorted(df_base["nr"].unique())

    if HAS_GROQ and groq_key:
        try:
            client = Groq(api_key=groq_key)
            prompt = f"Engenheiro SST. Normas: {', '.join(nrs)}. Devolva EXCLUSIVAMENTE um JSON com as chaves: status, nr_sugerida, item_provavel, descricao_cenario, acao_corretiva, prioridade."
            res = client.chat.completions.create(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": texto_relato}],
                model="llama-3.3-70b-versatile",
                response_format={"type": "json_object"}
            )
            return json.loads(limpar_resposta_json(res.choices[0].message.content)), None
        except Exception:
            pass

    if HAS_GEMINI and gemini_key:
        try:
            client = genai.Client(api_key=gemini_key)
            prompt = f"Especialista SST. Normas: {', '.join(nrs)}. Relato: {texto_relato}. Devolva estritamente um JSON com: status, nr_sugerida, item_provavel, descricao_cenario, acao_corretiva, prioridade."
            res = client.models.generate_content(model="gemini-3.6-flash", contents=prompt, config={"response_mime_type": "application/json"})
            return json.loads(limpar_resposta_json(res.text)), None
        except Exception:
            pass

    palavras = [p.lower() for p in texto_relato.split() if len(p) > 2]
    df_copia = df_base.copy()
    df_copia["score"] = 0
    for p in palavras:
        mask = df_copia["descricao"].str.lower().str.contains(p, na=False) | df_copia["categoria"].str.lower().str.contains(p, na=False)
        df_copia.loc[mask, "score"] += 1
    ordenado = df_copia.sort_values(by="score", ascending=False)
    if not ordenado.empty and ordenado.iloc[0]["score"] > 0:
        melhor = ordenado.iloc[0]
        return {
            "status": "Não Conformidade",
            "nr_sugerida": melhor["nr"],
            "item_provavel": melhor["item"],
            "descricao_cenario": f"Constatada irregularidade: {melhor['descricao']}.",
            "acao_corretiva": f"Adequar de imediato as condições aos requisitos da {melhor['nr']} (Item {melhor['item']}).",
            "prioridade": "Alta" if melhor["infracao"] in ["I4", "I3"] else "Média"
        }, None

    return None, "Não foi possível localizar norma correspondente."

def gerar_link_whatsapp(telefone, empresa, tot_multa, tot_econ, qtd_nc):
    msg = (
        f"📋 *VistorIA SST — RELATÓRIO PRELIMINAR (NR 28)*\n\n"
        f"🏢 *Empresa Inspecionada:* {empresa}\n"
        f"📅 *Data:* {datetime.date.today().strftime('%d/%m/%Y')}\n"
        f"⚠️ *Não Conformidades:* {qtd_nc} apontamento(s)\n"
        f"💰 *Passivo em Risco:* {formata_brl(tot_multa)}\n"
        f"🛡️ *Economia Gerada (Risco Evitado):* {formata_brl(tot_econ)}\n\n"
        f"_O laudo pericial detalhado com Plano de Ação já está disponível._"
    )
    tel_limpo = "".join([c for c in telefone if c.isdigit()])
    return f"[https://api.whatsapp.com/send?phone=](https://api.whatsapp.com/send?phone=){tel_limpo}&text={urllib.parse.quote(msg)}"

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
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 28, A4[0] - 36, 28)

        caminho_logo = "logo.png" if os.path.exists("logo.png") else ("icon-192.png" if os.path.exists("icon-192.png") else None)
        x_texto = 36
        if caminho_logo:
            try:
                self.drawImage(caminho_logo, 36, 12, width=32, height=14, preserveAspectRatio=True, mask='auto')
                x_texto = 74
            except Exception:
                pass

        self.drawString(x_texto, 15, "Emitido via VistorIA SST — Auditoria Pericial & Gestão NR 28")
        self.drawRightString(A4[0] - 36, 15, f"Página {self._pageNumber} de {page_count}")
        self.restoreState()

def gerar_grafico_multas(evidencias):
    m_min = sum(e['valor_min'] for e in evidencias if e['status'] == "Não Conformidade")
    m_max = sum(e['valor_max'] for e in evidencias if e['status'] == "Não Conformidade")
    e_min = sum(e['valor_min'] for e in evidencias if e['status'] == "Conformidade")
    e_max = sum(e['valor_max'] for e in evidencias if e['status'] == "Conformidade")

    fig, ax = plt.subplots(figsize=(6, 2.5))
    cats = ['Multas (Risco)', 'Economia (Evitado)']
    x = [0, 1]
    w = 0.35
    ax.bar([p - w/2 for p in x], [m_min, e_min], width=w, label='Mínimo', color=['#F87171', '#34D399'])
    ax.bar([p + w/2 for p in x], [m_max, e_max], width=w, label='Máximo', color=['#DC2626', '#059669'])
    ax.set_title('Balanço Financeiro Geral (NR 28)', fontsize=9.5, fontweight='bold', pad=8)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=8.5, fontweight='bold')
    ax.legend(frameon=True, fontsize=7.5)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='PNG', dpi=180)
    plt.close(fig)
    buf.seek(0)
    return buf

def gerar_pdf_pericial_completo(dados, evidencias, logo_cons=None, ass_insp_pil=None, ass_acomp_pil=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=38)
    styles = getSampleStyleSheet()
    elementos = []

    titulo_style = ParagraphStyle('T1', parent=styles['Heading1'], fontSize=14, textColor=colors.HexColor('#0F172A'), leading=17)
    sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=8.5, textColor=colors.HexColor('#475569'), leading=11)
    cell_label = ParagraphStyle('CellL', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, textColor=colors.HexColor('#1E293B'))
    cell_val = ParagraphStyle('CellV', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, textColor=colors.HexColor('#334155'))
    cell_td_center = ParagraphStyle('CellC', parent=styles['Normal'], fontSize=7.5, textColor=colors.HexColor('#0F172A'), alignment=1, leading=10)

    texto_cab = [
        Paragraph("<b>Relatório Pericial de Vistoria, Riscos e Conformidades SST</b>", titulo_style),
        Spacer(1, 3),
        Paragraph(f"<b>Empresa Inspecionada:</b> {dados['empresa']}", ParagraphStyle('Emp', parent=styles['Normal'], fontSize=9.5, fontName='Helvetica-Bold', textColor=colors.HexColor('#1E3A8A'))),
        Paragraph(f"<b>Emissão:</b> {dados['data']} | <b>Auditor:</b> {dados['inspetor']} ({dados.get('reg_inspetor', 'MTE')})", sub_style)
    ]
    if logo_cons:
        l_buf = io.BytesIO()
        logo_cons.save(l_buf, format='PNG')
        l_buf.seek(0)
        img_c = ReportLabImage(l_buf, width=125, height=52)
        elementos.append(Table([[img_c, texto_cab]], colWidths=[135, 388], style=[('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
    else:
        elementos.extend(texto_cab)
    elementos.append(Spacer(1, 14))

    m_min = sum(e['valor_min'] for e in evidencias if e['status'] == "Não Conformidade")
    m_max = sum(e['valor_max'] for e in evidencias if e['status'] == "Não Conformidade")
    e_min = sum(e['valor_min'] for e in evidencias if e['status'] == "Conformidade")
    e_max = sum(e['valor_max'] for e in evidencias if e['status'] == "Conformidade")

    info_q = [
        [Paragraph("Empresa Auditada:", cell_label), Paragraph(dados['empresa'], cell_val)],
        [Paragraph("Faixa de Funcionários:", cell_label), Paragraph(dados['faixa'], cell_val)],
        [Paragraph("Passivo em Risco (NR 28):", cell_label), Paragraph(f"<font color='#B91C1C'><b>{formata_brl(m_min)} a {formata_brl(m_max)}</b></font>", cell_val)],
        [Paragraph("Economia (Risco Evitado):", cell_label), Paragraph(f"<font color='#047857'><b>{formata_brl(e_min)} a {formata_brl(e_max)}</b></font>", cell_val)],
    ]
    t_info = Table(info_q, colWidths=[160, 363], style=[
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1F5F9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ])
    elementos.append(t_info)
    elementos.append(Spacer(1, 12))

    for ev in evidencias:
        eh_c = (ev['status'] == 'Conformidade')
        cor = '#059669' if eh_c else '#DC2626'
        tag = 'BOA PRÁTICA' if eh_c else f"NÃO CONFORMIDADE (PRIORIDADE {ev.get('prioridade', 'Média').upper()})"
        elementos.append(Paragraph(f"<b>[{tag}] — {ev['nr']} (Item {ev['item_nr']})</b>", ParagraphStyle('TitEv', parent=styles['Heading3'], textColor=colors.HexColor(cor), fontSize=9.5)))
        
        det = [
            [Paragraph("Infração / Requisito:", cell_label), Paragraph(f"{ev['descricao']} ({ev['infracao']})", cell_val)],
            [Paragraph("Cenário Observado:", cell_label), Paragraph(ev.get('descricao_cenario', '-'), cell_val)],
            [Paragraph("Medida Recomendada:", cell_label), Paragraph(ev.get('acao_corretiva', '-'), cell_val)],
            [Paragraph("Valor NR 28:", cell_label), Paragraph(f"<b>{formata_brl(ev['valor_min'])} a {formata_brl(ev['valor_max'])}</b>", cell_val)]
        ]
        bg = '#F0FDF4' if eh_c else '#FEF2F2'
        t_det = Table(det, colWidths=[140, 383], style=[
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg)),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])
        elementos.append(t_det)
        elementos.append(Spacer(1, 4))

        if ev.get('foto_pil'):
            b_foto = io.BytesIO()
            ev['foto_pil'].save(b_foto, format='JPEG', quality=80)
            b_foto.seek(0)
            elementos.append(ReportLabImage(b_foto, width=240, height=160))
            elementos.append(Spacer(1, 4))

    elementos.append(Paragraph("<b>4. Balanço Gráfico de Impacto Financeiro</b>", styles['Heading3']))
    buf_g = gerar_grafico_multas(evidencias)
    elementos.append(ReportLabImage(buf_g, width=480, height=200))
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph("<b>7. Termo de Ciência e Assinaturas</b>", styles['Heading3']))
    elementos.append(Paragraph("<i>As partes declaram ciência dos fatos registrados neste relatório técnico e das ações acordadas:</i>", sub_style))
    elementos.append(Spacer(1, 8))

    img_ass_insp = Paragraph("<br/><br/>", cell_td_center)
    if ass_insp_pil:
        buf_i = io.BytesIO()
        ass_insp_pil.save(buf_i, format='PNG')
        buf_i.seek(0)
        img_ass_insp = ReportLabImage(buf_i, width=160, height=55)

    img_ass_acomp = Paragraph("<br/><br/>", cell_td_center)
    if ass_acomp_pil:
        buf_ass = io.BytesIO()
        ass_acomp_pil.save(buf_ass, format='PNG')
        buf_ass.seek(0)
        img_ass_acomp = ReportLabImage(buf_ass, width=160, height=55)

    linha_ass = [img_ass_insp, img_ass_acomp]
    linha_nomes = [
        Paragraph(f"____________________________________________<br/><b>{dados['inspetor']}</b><br/>Auditor SST<br/><font color='#64748B'>{dados.get('reg_inspetor', 'MTE')}</font>", cell_td_center),
        Paragraph(f"____________________________________________<br/><b>{dados['acomp_nome']}</b><br/>Acompanhante da Vistoria in loco<br/><font color='#64748B'>{dados.get('acomp_cargo', 'Preposto')}</font>", cell_td_center)
    ]
    t_ass = Table([linha_ass, linha_nomes], colWidths=[261, 262], style=[
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('VALIGN', (0, 1), (-1, 1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
    ])
    elementos.append(t_ass)

    doc.build(elementos, canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf.getvalue()

# ---------------------------------------------------------
# 5. INTERFACE NICEGUI (Com renderização blindada por abas)
# ---------------------------------------------------------
@ui.page('/')
def index():
    ui.add_head_html("""
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #F8FAFC; color: #0F172A; }
            .kpi-card { background: white; border-radius: 12px; padding: 12px; border: 1px solid #E2E8F0; box-shadow: 0 1px 4px rgba(0,0,0,0.05); }
        </style>
    """)

    ui.add_body_html("""
        <script>
            function inicializarCanvas(idCanvas) {
                var canvas = document.getElementById(idCanvas);
                if (!canvas) return;
                var ctx = canvas.getContext('2d');
                ctx.strokeStyle = '#0F172A';
                ctx.lineWidth = 3;
                ctx.lineCap = 'round';

                var desenhando = false;
                var pos = {x: 0, y: 0};

                function getPos(e) {
                    var rect = canvas.getBoundingClientRect();
                    var clientX = e.clientX;
                    var clientY = e.clientY;
                    if (e.touches && e.touches.length > 0) {
                        clientX = e.touches[0].clientX;
                        clientY = e.touches[0].clientY;
                    }
                    return { x: clientX - rect.left, y: clientY - rect.top };
                }

                canvas.onmousedown = function(e) { desenhando = true; pos = getPos(e); };
                canvas.onmousemove = function(e) {
                    if (!desenhando) return;
                    e.preventDefault();
                    var novaPos = getPos(e);
                    ctx.beginPath();
                    ctx.moveTo(pos.x, pos.y);
                    ctx.lineTo(novaPos.x, novaPos.y);
                    ctx.stroke();
                    pos = novaPos;
                };
                window.onmouseup = function() { desenhando = false; };

                canvas.ontouchstart = function(e) { desenhando = true; pos = getPos(e); e.preventDefault(); };
                canvas.ontouchmove = function(e) {
                    if (!desenhando) return;
                    e.preventDefault();
                    var novaPos = getPos(e);
                    ctx.beginPath();
                    ctx.moveTo(pos.x, pos.y);
                    ctx.lineTo(novaPos.x, novaPos.y);
                    ctx.stroke();
                    pos = novaPos;
                };
                canvas.ontouchend = function() { desenhando = false; };
            }

            function limparCanvas(idCanvas) {
                var canvas = document.getElementById(idCanvas);
                if (!canvas) return;
                var ctx = canvas.getContext('2d');
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = "#FFFFFF";
                ctx.fillRect(0, 0, canvas.width, canvas.height);
            }

            function exportarPNG(idCanvas) {
                var canvas = document.getElementById(idCanvas);
                if (!canvas) return '';
                return canvas.toDataURL('image/png');
            }

            function converterFotoParaBase64(event) {
                var file = event.target.files[0];
                if (!file) return;
                var reader = new FileReader();
                reader.onload = function(e) {
                    var base64Data = e.target.result;
                    var storageInput = document.getElementById('foto-base64-storage');
                    if (storageInput) {
                        storageInput.value = base64Data;
                    }
                    var imgVisivel = document.getElementById('img-preview-visivel');
                    if (imgVisivel) {
                        imgVisivel.src = base64Data;
                        document.getElementById('preview-container').style.display = 'block';
                    }
                };
                reader.readAsDataURL(file);
            }
        </script>
    """)

    st_state = {
        'autenticado': False,
        'usuario': '',
        'perfil': '',
        'visao': 'vistoria',
        'etapa': 1,
        'empresa': 'Construtora Exemplo Ltda',
        'inspetor': 'Auditor SST',
        'reg_inspetor': 'MTE: 000000/UF',
        'acomp_nome': 'Preposto da Obra',
        'acomp_cargo': 'Encarregado Geral',
        'faixa': '26 a 50',
        'wpp': '34999990000',
        'evidencias': [],
    }
    
    container_principal = ui.column().classes('w-full max-w-2xl mx-auto p-2')

    def renderizar_login():
        container_principal.clear()
        with container_principal:
            with ui.card().classes('w-full max-w-sm mx-auto p-6 mt-12 text-center shadow-lg'):
                if os.path.exists("icon-192.png"):
                    ui.image("icon-192.png").classes('w-16 h-16 mx-auto mb-2 rounded-xl')
                ui.label("VistorIA SST").classes('text-2xl font-black text-slate-900')
                ui.label("Auditoria Pericial & Gestão NR 28").classes('text-xs text-slate-500 mb-6')

                txt_user = ui.input("Usuário:").classes('w-full mb-2')
                txt_pass = ui.input("Senha:", password=True, password_toggle_button=True).classes('w-full mb-4')

                def tentar_login():
                    row = autenticar_usuario(txt_user.value.strip(), txt_pass.value.strip())
                    if row:
                        st_state['autenticado'] = True
                        st_state['usuario'] = row[0]
                        st_state['perfil'] = row[1]
                        st_state['inspetor'] = f"{row[0].capitalize()} (SST)"
                        ui.notify(f"Bem-vindo, {row[0]}!", type='positive')
                        renderizar_sistema()
                    else:
                        ui.notify("Credenciais inválidas!", type='negative')

                ui.button("Acessar Painel", on_click=tentar_login).classes('w-full bg-blue-600 text-white font-bold h-11')

    def renderizar_sistema():
        container_principal.clear()
        with container_principal:
            with ui.row().classes('w-full items-center justify-between bg-slate-900 text-white px-4 py-3 rounded-xl mb-4'):
                with ui.row().classes('items-center gap-2'):
                    if os.path.exists("icon-192.png"):
                        ui.image("icon-192.png").classes('w-8 h-8 rounded')
                    ui.label("VistorIA SST").classes('text-lg font-bold')
                
                with ui.row().classes('items-center gap-2'):
                    if st_state['perfil'] == 'Admin':
                        btn_label = "⚙️ ADM" if st_state['visao'] == 'vistoria' else "📋 Vistoria"
                        def toggle_visao():
                            st_state['visao'] = 'admin' if st_state['visao'] == 'vistoria' else 'vistoria'
                            renderizar_sistema()
                        ui.button(btn_label, on_click=toggle_visao).props('flat dense color=white')
                    
                    def sair():
                        st_state['autenticado'] = False
                        renderizar_login()
                    ui.button("Sair", on_click=sair).props('flat dense color=negative')

            # =====================================================
            # VISÃO ADM
            # =====================================================
            if st_state['visao'] == 'admin' and st_state['perfil'] == 'Admin':
                ui.label("⚙️ Painel de Gestão Corporativa").classes('text-xl font-bold mb-2')
                with ui.tabs().classes('w-full') as t_adm:
                    tab_emp = ui.tab('🏢 Empresas')
                    tab_logo = ui.tab('🎨 Identidade')
                    tab_usr = ui.tab('👥 Usuários')
                    tab_hist = ui.tab('📂 Laudos')

                with ui.tab_panels(t_adm, value=tab_emp).classes('w-full p-2'):
                    with ui.tab_panel(tab_emp):
                        ui.label("Cadastrar Empresa").classes('font-bold mb-2')
                        ne_nome = ui.input("Razão Social:").classes('w-full')
                        ne_cnpj = ui.input("CNPJ:").classes('w-full')
                        ne_faixa = ui.select(list(TABELA_MULTAS_SEGURANCA.keys()), value="26 a 50", label="Faixa de Funcionários:").classes('w-full')
                        ne_wpp = ui.input("WhatsApp Gestor:").classes('w-full')
                        def salvar_emp_adm():
                            if ne_nome.value.strip():
                                cadastrar_empresa_db(ne_nome.value.strip(), ne_cnpj.value.strip(), ne_faixa.value, ne_wpp.value.strip())
                                ui.notify("✅ Empresa salva!", type='positive')
                                renderizar_sistema()
                        ui.button("💾 Salvar Empresa", on_click=salvar_emp_adm).classes('w-full bg-blue-600 text-white font-bold mt-2')

                    with ui.tab_panel(tab_logo):
                        ui.label("Logomarca da Consultoria SST").classes('font-bold mb-1')
                        def up_logo(e):
                            salvar_logo_consultoria_db(base64.b64encode(e.content.read()).decode('utf-8'))
                            ui.notify("✅ Logomarca salva!", type='positive')
                            renderizar_sistema()
                        ui.upload(on_upload=up_logo, max_files=1, auto_upload=True).classes('w-full mb-4')
                        logo_a = carregar_logo_consultoria_db()
                        if logo_a:
                            b_l = io.BytesIO()
                            logo_a.save(b_l, format='PNG')
                            ui.image(f"data:image/png;base64,{base64.b64encode(b_l.getvalue()).decode()}").classes('w-40 border rounded p-1')

                    with ui.tab_panel(tab_usr):
                        ui.label("Novo Usuário").classes('font-bold mb-2')
                        nu_nome = ui.input("Usuário:").classes('w-full')
                        nu_pass = ui.input("Senha:", password=True).classes('w-full')
                        nu_perf = ui.select(["Inspetor", "Admin"], value="Inspetor", label="Perfil:").classes('w-full')
                        def salvar_usr():
                            if nu_nome.value and nu_pass.value:
                                ok, msg = criar_usuario(nu_nome.value.strip(), nu_pass.value.strip(), nu_perf.value)
                                ui.notify(msg, type='positive' if ok else 'negative')
                                renderizar_sistema()
                        ui.button("Cadastrar Usuário", on_click=salvar_usr).classes('w-full bg-slate-800 text-white font-bold mt-2')

                    with ui.tab_panel(tab_hist):
                        ui.label("Histórico de Laudos Emitidos").classes('font-bold mb-2')
                        relatorios = listar_relatorios_db()
                        if relatorios:
                            for r in relatorios:
                                with ui.card().classes('w-full mb-2 p-3 flex-row items-center justify-between'):
                                    ui.label(f"#{r[0]} — {r[2]} ({r[1]}) | Inspetor: {r[3]}").classes('font-bold text-sm')
                                    def baixar_laudo_adm(id_r=r[0], emp=r[2]):
                                        d = obter_pdf_relatorio_db(id_r)
                                        if d:
                                            ui.download(d[0], f"Laudo_{id_r}_{emp.replace(' ', '_')}.pdf")
                                    ui.button("⬇️ Baixar PDF", on_click=baixar_laudo_adm).props('dense outline color=primary')
                        else:
                            ui.label("Nenhum laudo emitido ainda.").classes('text-gray-500 text-sm')

            # =====================================================
            # VISÃO VISTORIA DE CAMPO (Navegação por Abas Nativas Sólidas)
            # =====================================================
            else:
                # Botões de Navegação entre Etapas Blindados
                with ui.row().classes('w-full gap-2 mb-4'):
                    ui.button("1️⃣ Identificação", on_click=lambda: (st_state.update({'etapa': 1}), renderizar_sistema())).classes('flex-1 ' + ('bg-blue-600 text-white font-bold' if st_state['etapa'] == 1 else 'bg-slate-200 text-slate-700'))
                    
                    qtd_ev = len(st_state['evidencias'])
                    lbl_ap = f"2️⃣ Apontamentos ({qtd_ev})" if qtd_ev > 0 else "2️⃣ Apontamentos"
                    ui.button(lbl_ap, on_click=lambda: (st_state.update({'etapa': 2}), renderizar_sistema())).classes('flex-1 ' + ('bg-blue-600 text-white font-bold' if st_state['etapa'] == 2 else 'bg-slate-200 text-slate-700'))
                    
                    ui.button("3️⃣ Fechamento", on_click=lambda: (st_state.update({'etapa': 3}), renderizar_sistema(), ui.run_javascript("setTimeout(function(){ inicializarCanvas('signature-pad-insp'); inicializarCanvas('signature-pad-acomp'); }, 250)"))).classes('flex-1 ' + ('bg-blue-600 text-white font-bold' if st_state['etapa'] == 3 else 'bg-slate-200 text-slate-700'))

                # ETAPA 1: Identificação, Cadastro Rápido & Gestão de Rascunhos
                if st_state['etapa'] == 1:
                    ui.label("1️⃣ Identificação da Empresa Inspecionada").classes('text-lg font-bold mb-3')
                    
                    rascunhos_disponiveis = listar_rascunhos_db(st_state['usuario'])
                    if rascunhos_disponiveis:
                        with ui.expansion("📂 Continuar Vistoria em Rascunho Salvo", icon="folder_open").classes('w-full bg-amber-50 border border-amber-200 rounded-lg mb-3'):
                            for r_id, r_emp, r_data in rascunhos_disponiveis:
                                with ui.row().classes('w-full items-center justify-between p-2 border-b border-amber-100'):
                                    ui.label(f"{r_emp} ({r_data})").classes('text-xs font-bold text-amber-900')
                                    with ui.row().classes('gap-1'):
                                        def carregar_rasc(rid=r_id):
                                            estado_carregado = carregar_rascunho_db(rid)
                                            if estado_carregado:
                                                st_state.update(estado_carregado)
                                                ui.notify("✅ Rascunho carregado com sucesso!", type='positive')
                                                renderizar_sistema()
                                        def excluir_rasc(rid=r_id):
                                            deletar_rascunho_db(rid)
                                            ui.notify("🗑️ Rascunho excluído.", type='info')
                                            renderizar_sistema()
                                        ui.button("Continuar", on_click=carregar_rasc).props('dense color=amber-800 text-white text-xs')
                                        ui.button("Excluir", on_click=excluir_rasc).props('dense flat color=negative text-xs')

                    df_emp = listar_empresas_db()
                    nomes_emp = df_emp['nome'].tolist()
                    sel_emp = ui.select(nomes_emp, value=st_state['empresa'] if st_state['empresa'] in nomes_emp else (nomes_emp[0] if nomes_emp else ''), label="Empresa a ser auditada:").classes('w-full')

                    with ui.dialog() as dialog_novo_cliente, ui.card().classes('w-full max-w-sm p-4'):
                        ui.label("➕ Cadastrar Novo Cliente").classes('font-bold text-lg mb-2')
                        cad_nome = ui.input("Razão Social:").classes('w-full')
                        cad_cnpj = ui.input("CNPJ:").classes('w-full')
                        cad_faixa = ui.select(list(TABELA_MULTAS_SEGURANCA.keys()), value="26 a 50", label="Faixa de Funcionários:").classes('w-full')
                        cad_wpp = ui.input("WhatsApp Gestor:").classes('w-full')
                        
                        def salvar_cliente_rapido():
                            if cad_nome.value.strip():
                                cadastrar_empresa_db(cad_nome.value.strip(), cad_cnpj.value.strip(), cad_faixa.value, cad_wpp.value.strip())
                                st_state['empresa'] = cad_nome.value.strip()
                                ui.notify(f"✅ Cliente '{cad_nome.value}' cadastrado!", type='positive')
                                dialog_novo_cliente.close()
                                renderizar_sistema()
                            else:
                                ui.notify("Informe o nome da empresa.", type='warning')

                        ui.button("💾 Salvar e Selecionar", on_click=salvar_cliente_rapido).classes('w-full bg-blue-600 text-white font-bold mt-2')
                        ui.button("Fechar", on_click=dialog_novo_cliente.close).props('flat dense')

                    ui.button("➕ Cadastrar Novo Cliente / Obra", on_click=dialog_novo_cliente.open).props('outline dense color=primary').classes('w-full my-2')

                    txt_insp = ui.input("Auditor / Responsável Técnico:", value=st_state['inspetor']).classes('w-full')
                    txt_reg = ui.input("Registro Profissional (MTE / CREA):", value=st_state['reg_inspetor']).classes('w-full')
                    sel_faixa = ui.select(list(TABELA_MULTAS_SEGURANCA.keys()), value=st_state['faixa'], label="Quadro de Funcionários (NR 28):").classes('w-full')
                    txt_wpp = ui.input("WhatsApp do Gestor da Empresa:", value=st_state['wpp']).classes('w-full')

                    def avancar_etapa2():
                        st_state['empresa'] = sel_emp.value if sel_emp.value else "Construtora Exemplo Ltda"
                        st_state['inspetor'] = txt_insp.value
                        st_state['reg_inspetor'] = txt_reg.value
                        st_state['faixa'] = sel_faixa.value
                        st_state['wpp'] = txt_wpp.value
                        st_state['etapa'] = 2
                        renderizar_sistema()

                    ui.button("Avançar para Apontamentos ➡️", on_click=avancar_etapa2).classes('w-full bg-blue-600 text-white font-bold h-12 mt-4')

                # ETAPA 2: Apontamentos com IA, Câmera/Galeria e Rascunho
                elif st_state['etapa'] == 2:
                    def acao_salvar_rascunho():
                        salvar_rascunho_db(st_state['usuario'], st_state['empresa'], st_state)
                        ui.notify("💾 Vistoria salva em rascunho com sucesso!", type='positive')

                    with ui.row().classes('w-full justify-between items-center mb-3'):
                        ui.label("2️⃣ Registo de Apontamentos").classes('text-lg font-bold')
                        ui.button("💾 Salvar Rascunho", on_click=acao_salvar_rascunho).props('dense outline color=amber-900').classes('text-xs font-bold')

                    tot_m = sum(e['valor_max'] for e in st_state['evidencias'] if e['status'] == 'Não Conformidade')
                    tot_e = sum(e['valor_max'] for e in st_state['evidencias'] if e['status'] == 'Conformidade')
                    with ui.row().classes('w-full gap-2 mb-4'):
                        with ui.column().classes('kpi-card flex-1 border-l-4 border-red-500'):
                            ui.label("PASSIVO EM RISCO").classes('text-xs text-gray-500 font-bold')
                            ui.label(formata_brl(tot_m)).classes('text-lg font-black text-red-600')
                        with ui.column().classes('kpi-card flex-1 border-l-4 border-green-500'):
                            ui.label("ECONOMIA GERADA").classes('text-xs text-gray-500 font-bold')
                            ui.label(formata_brl(tot_e)).classes('text-lg font-black text-green-600')

                    # IA com Spinner
                    with ui.card().classes('w-full p-3 bg-blue-50 border border-blue-200 mb-3'):
                        ui.label("⚡ Enquadramento Inteligente (Texto ou Voz)").classes('font-bold text-blue-900 text-sm')
                        txt_ia = ui.input(placeholder="Ex: Operários em andaime sem cinto a 4m").classes('w-full')
                        
                        async def buscar_ia():
                            if txt_ia.value.strip():
                                with ui.dialog() as dlg, ui.card().classes('p-4 items-center'):
                                    ui.spinner(size='lg')
                                    ui.label("Analisando com Inteligência Artificial...")
                                    dlg.open()
                                
                                res, err = sugerir_enquadramento(txt_ia.value.strip(), df_nr_base)
                                dlg.close()
                                
                                if res:
                                    sel_nr_ap.value = res.get('nr_sugerida', 'NR 35')
                                    atualizar_itens_nr(res.get('nr_sugerida', 'NR 35'))
                                    txt_cenario.value = res.get('descricao_cenario', '')
                                    txt_acao.value = res.get('acao_corretiva', '')
                                    sel_prio.value = res.get('prioridade', 'Média')
                                    ui.notify(f"✅ Enquadrado na {res.get('nr_sugerida', 'NR')}!", type='positive')
                                else:
                                    ui.notify(err, type='warning')

                        ui.button("🔍 Enquadrar com IA", on_click=buscar_ia).props('dense color=primary')

                    # Sistema Duplo de Captura (Câmera ou Galeria)
                    ui.label("📷 Evidência Fotográfica (Carimbo Forense):").classes('font-bold text-sm mt-2')
                    ui.html("""
                        <div style="width: 100%; text-align: center; margin-top: 5px; display: flex; flex-direction: column; gap: 8px;">
                            <label for="input-camera-direta" style="background: #0F172A; color: #FFF; padding: 12px 16px; border-radius: 8px; font-weight: bold; display: block; cursor: pointer; text-align: center; width: 100%; box-sizing: border-box;">
                                📸 Tirar Foto com a Câmera
                            </label>
                            <input type="file" id="input-camera-direta" accept="image/*" capture="environment" style="display:none;" onchange="converterFotoParaBase64(event)">
                            
                            <label for="input-galeria-direta" style="background: #334155; color: #FFF; padding: 10px 16px; border-radius: 8px; font-size: 13px; font-weight: bold; display: block; cursor: pointer; text-align: center; width: 100%; box-sizing: border-box;">
                                📁 Carregar Foto da Galeria / Arquivo
                            </label>
                            <input type="file" id="input-galeria-direta" accept="image/*" style="display:none;" onchange="converterFotoParaBase64(event)">

                            <input type="hidden" id="foto-base64-storage">
                            
                            <div id="preview-container" style="margin-top: 6px; display: none;">
                                <img id="img-preview-visivel" src="" style="max-width: 100%; max-height: 180px; border-radius: 8px; border: 1px solid #CBD5E1; display: block; margin: 0 auto;">
                                <p style="color: #059669; font-size: 12px; font-weight: bold; margin-top: 4px;">✅ Imagem anexada e pronta para salvar!</p>
                            </div>
                        </div>
                    """)

                    # Dados da Norma
                    sel_nr_ap = ui.select(sorted(df_nr_base['nr'].unique()), value="NR 35", label="Norma Regulamentadora:").classes('w-full')
                    sel_item_ap = ui.select([], label="Item correspondente (NR 28):").classes('w-full')

                    def atualizar_itens_nr(nr_escolhida):
                        filtro = df_nr_base[df_nr_base['nr'] == nr_escolhida]
                        opcs = [f"Item {r['item']} — {r['descricao']}" for _, r in filtro.iterrows()]
                        sel_item_ap.options = opcs
                        if opcs:
                            sel_item_ap.value = opcs[0]
                    
                    sel_nr_ap.on_value_change(lambda e: atualizar_itens_nr(e.value))
                    atualizar_itens_nr("NR 35")

                    rad_status = ui.radio(["Não Conformidade", "Conformidade"], value="Não Conformidade").props('inline')
                    sel_prio = ui.select(["Alta", "Média", "Baixa"], value="Média", label="Prioridade Técnica:").classes('w-full')
                    txt_cenario = ui.textarea("Cenário Observado:", placeholder="Descreva a situação em campo...").classes('w-full')
                    txt_acao = ui.textarea("Ação Corretiva Recomendada:", placeholder="Medida imediata...").classes('w-full')

                    async def salvar_apontamento():
                        b64_foto = await ui.run_javascript("document.getElementById('foto-base64-storage').value")
                        foto_pil = None
                        if b64_foto and "base64," in b64_foto:
                            img_bytes = base64.b64decode(b64_foto.split("base64,")[1])
                            img_raw = Image.open(io.BytesIO(img_bytes))
                            foto_pil = otimizar_e_carimbar(img_raw)

                        it_cod = sel_item_ap.value.split(" — ")[0].replace("Item ", "").strip()
                        linha = df_nr_base[df_nr_base['item'] == it_cod].iloc[0]
                        val_min, val_max = calcular_multa(linha['infracao'], st_state['faixa'], linha['tipo'])

                        st_state['evidencias'].append({
                            'nr': sel_nr_ap.value,
                            'item_nr': it_cod,
                            'descricao': linha['descricao'],
                            'infracao': linha['infracao'],
                            'tipo': linha['tipo'],
                            'status': rad_status.value,
                            'prioridade': sel_prio.value,
                            'descricao_cenario': txt_cenario.value if txt_cenario.value.strip() else "Constatado em campo.",
                            'acao_corretiva': txt_acao.value if txt_acao.value.strip() else "Adequar conforme norma.",
                            'valor_min': val_min,
                            'valor_max': val_max,
                            'foto_pil': foto_pil
                        })
                        ui.notify(f"✅ Apontamento salvo com sucesso ({len(st_state['evidencias'])} itens)!", type='positive')
                        renderizar_sistema()

                    ui.button("💾 Salvar Apontamento", on_click=salvar_apontamento).classes('w-full bg-slate-800 text-white font-bold h-10 mt-2')

                    # Listagem
                    if st_state['evidencias']:
                        ui.label(f"Apontamentos Registrados ({len(st_state['evidencias'])}):").classes('font-bold text-sm mt-4')
                        for i, ev in enumerate(st_state['evidencias']):
                            with ui.card().classes('w-full p-2 mb-1'):
                                with ui.row().classes('w-full justify-between items-center'):
                                    ui.label(f"#{i+1} - {ev['nr']} (Item {ev['item_nr']})").classes('font-bold text-sm')
                                    def deletar_item(idx=i):
                                        st_state['evidencias'].pop(idx)
                                        renderizar_sistema()
                                    ui.button(icon='delete', on_click=deletar_item).props('flat dense color=negative')

                    def ir_etapa3():
                        st_state['etapa'] = 3
                        renderizar_sistema()
                        ui.run_javascript("setTimeout(function(){ inicializarCanvas('signature-pad-insp'); inicializarCanvas('signature-pad-acomp'); }, 250)")

                    ui.button("Concluir Campo e Ir para Laudo ➡️", on_click=ir_etapa3).classes('w-full bg-blue-600 text-white font-bold h-12 mt-4')

                # ETAPA 3: Assinatura Dupla Clicável & Emissão de Laudo
                elif st_state['etapa'] == 3:
                    ui.label("3️⃣ Fechamento do Laudo & Assinatura").classes('text-lg font-bold mb-2')
                    txt_ac_nome = ui.input("Acompanhante da Empresa:", value=st_state['acomp_nome']).classes('w-full')
                    txt_ac_cargo = ui.input("Cargo / Função:", value=st_state['acomp_cargo']).classes('w-full')

                    ui.label("✍️ 1. Assinatura do Auditor / Técnico SST:").classes('font-bold text-sm mt-3')
                    ui.html("""
                        <div style="border: 2px solid #0F172A; border-radius: 10px; background: #FFF; width: 100%; text-align: center; padding: 4px;">
                            <canvas id="signature-pad-insp" width="400" height="150" style="width: 100%; height: 150px; touch-action: none; background: #FFF; display: block;"></canvas>
                            <div style="padding: 4px; background: #F8FAFC; border-top: 1px solid #E2E8F0; border-radius: 0 0 8px 8px;">
                                <button type="button" onclick="limparCanvas('signature-pad-insp')" style="background:#EF4444; color:#FFF; border:none; padding:4px 12px; border-radius:6px; font-size:12px; font-weight:bold; cursor:pointer;">🗑️ Limpar Auditor</button>
                            </div>
                        </div>
                    """)

                    ui.label("✍️ 2. Assinatura do Acompanhante da Empresa:").classes('font-bold text-sm mt-3')
                    ui.html("""
                        <div style="border: 2px solid #0F172A; border-radius: 10px; background: #FFF; width: 100%; text-align: center; padding: 4px;">
                            <canvas id="signature-pad-acomp" width="400" height="150" style="width: 100%; height: 150px; touch-action: none; background: #FFF; display: block;"></canvas>
                            <div style="padding: 4px; background: #F8FAFC; border-top: 1px solid #E2E8F0; border-radius: 0 0 8px 8px;">
                                <button type="button" onclick="limparCanvas('signature-pad-acomp')" style="background:#EF4444; color:#FFF; border:none; padding:4px 12px; border-radius:6px; font-size:12px; font-weight:bold; cursor:pointer;">🗑️ Limpar Acompanhante</button>
                            </div>
                        </div>
                    """)

                    ui.run_javascript("setTimeout(function(){ inicializarCanvas('signature-pad-insp'); inicializarCanvas('signature-pad-acomp'); }, 200)")

                    tot_multa_fim = sum(e['valor_max'] for e in st_state['evidencias'] if e['status'] == 'Não Conformidade')
                    tot_econ_fim = sum(e['valor_max'] for e in st_state['evidencias'] if e['status'] == 'Conformidade')
                    qtd_nc_fim = sum(1 for e in st_state['evidencias'] if e['status'] == 'Não Conformidade')
                    link_wpp = gerar_link_whatsapp(st_state.get('wpp', '34999990000'), st_state['empresa'], tot_multa_fim, tot_econ_fim, qtd_nc_fim)
                    
                    ui.link("📲 Enviar Notificação via WhatsApp", link_wpp, new_tab=True).classes('w-full text-center bg-green-600 text-white font-bold p-3 rounded-lg block my-3 no-underline')

                    async def emitir_pdf_final():
                        st_state['acomp_nome'] = txt_ac_nome.value
                        st_state['acomp_cargo'] = txt_ac_cargo.value

                        b64_sig_insp = await ui.run_javascript("exportarPNG('signature-pad-insp')")
                        b64_sig_acomp = await ui.run_javascript("exportarPNG('signature-pad-acomp')")
                        
                        ass_insp_pil = None
                        if b64_sig_insp and "base64," in b64_sig_insp:
                            ib_i = base64.b64decode(b64_sig_insp.split("base64,")[1])
                            ass_insp_pil = tratar_imagem_assinatura(Image.open(io.BytesIO(ib_i)))

                        ass_acomp_pil = None
                        if b64_sig_acomp and "base64," in b64_sig_acomp:
                            ib_a = base64.b64decode(b64_sig_acomp.split("base64,")[1])
                            ass_acomp_pil = tratar_imagem_assinatura(Image.open(io.BytesIO(ib_a)))

                        logo_cons = carregar_logo_consultoria_db()
                        data_hoje = datetime.date.today().strftime("%d/%m/%Y")

                        pdf_bytes = gerar_pdf_pericial_completo({
                            'empresa': st_state['empresa'],
                            'inspetor': st_state['inspetor'],
                            'reg_inspetor': st_state['reg_inspetor'],
                            'acomp_nome': st_state['acomp_nome'],
                            'acomp_cargo': st_state['acomp_cargo'],
                            'faixa': st_state['faixa'],
                            'data': data_hoje
                        }, st_state['evidencias'], logo_cons=logo_cons, ass_insp_pil=ass_insp_pil, ass_acomp_pil=ass_acomp_pil)

                        salvar_relatorio_db(data_hoje, st_state['empresa'], st_state['inspetor'], len(st_state['evidencias']), 0, tot_multa_fim, 0, tot_econ_fim, pdf_bytes)
                        ui.download(pdf_bytes, f"Laudo_SST_{st_state['empresa'].replace(' ', '_')}.pdf")
                        ui.notify("✅ Laudo Pericial emitido e baixado com sucesso!", type='positive')

                    ui.button("📄 Emitir Laudo Pericial Completo (PDF)", on_click=emitir_pdf_final).classes('w-full bg-emerald-600 text-white font-bold h-12 mt-2')

    if not st_state['autenticado']:
        renderizar_login()
    else:
        renderizar_sistema()

ui.run(title="VistorIA SST", port=int(os.environ.get("PORT", 8080)), host='0.0.0.0', reload=False)
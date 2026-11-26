import os
import io
import re
import time
import hmac
import tempfile
from datetime import datetime

import pandas as pd
import pypdf
import streamlit as st
import streamlit.components.v1 as components
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

# ---------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------
PRECO_MIN, PRECO_MAX = 3.0, 15.0
LITROS_MAX = 600.0
TOL_TOTAL = 0.02
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_SEGUNDOS = 60
STATUS_SUCESSO = [
    'Já correto', 'Atualizado', 'Criado Novo',
    'Simulação: atualizaria', 'Simulação: criaria'
]
COLUNAS_BASE = [
    'data', 'hora', 'cupom', 'placa', 'produto',
    'quantidade', 'valor_unitario', 'valor_total', 'km'
]

XP_LITROS = "//label[contains(text(),'Litros')]/following::input[1]"
XP_KM = "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]"
XP_VEICULO = "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]"
XP_FORNECEDOR = "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]"
XP_DOC = "//label[contains(text(),'Documento fiscal')]/following::input[1]"
JS_SET = (
    "arguments[0].focus();"
    "arguments[0].value = arguments[1];"
    "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));"
    "arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));"
    "if (window.angular) {"
    "  var el = angular.element(arguments[0]);"
    "  el.val(arguments[1]);"
    "  el.triggerHandler('input');"
    "  el.triggerHandler('change');"
    "  el.triggerHandler('blur');"
    "}"
)

try:
    _v = tuple(int(x) for x in st.__version__.split('.')[:2])
except Exception:
    _v = (0, 0)
STRETCH = {"width": "stretch"} if _v >= (1, 50) else {"use_container_width": True}

# ---------------------------------------------------------
# CONFIGURAÇÃO DE PÁGINA E ESTILO APPLE GLASS
# ---------------------------------------------------------
st.set_page_config(
    page_title="ZUQ Fleet - Conciliação & Edição Automática",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Plus Jakarta Sans', sans-serif !important;
    }

    .stApp {
        background: radial-gradient(circle at 0% 0%, rgba(10, 132, 255, 0.16) 0%, transparent 45%),
                    radial-gradient(circle at 100% 40%, rgba(191, 90, 242, 0.12) 0%, transparent 50%),
                    #0b0f19 !important;
        color: #FFFFFF !important;
    }

    #MainMenu, footer, header { visibility: hidden; }

    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2.5rem !important;
        max-width: 1280px !important;
    }

    .glass-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 14px 20px;
        background: rgba(22, 28, 45, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 18px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28);
    }

    .glass-logo {
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 1.25rem;
        font-weight: 700;
        color: #FFFFFF;
        letter-spacing: -0.5px;
    }

    .glass-badge {
        background: rgba(10, 132, 255, 0.2);
        color: #0A84FF;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 999px;
        border: 1px solid rgba(10, 132, 255, 0.3);
    }

    div[data-testid="stMetric"] {
        background: rgba(24, 31, 48, 0.82) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 16px !important;
        padding: 14px 18px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.2) !important;
    }

    div[data-testid="stMetricLabel"] {
        color: rgba(255, 255, 255, 0.65) !important;
        font-size: 0.72rem !important;
        font-weight: 700 !important;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }

    div[data-testid="stMetricValue"] {
        color: #FFFFFF !important;
        font-size: 1.45rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }

    .stButton > button {
        background: #0A84FF !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        border: none !important;
        border-radius: 999px !important;
        height: 3.1rem !important;
        box-shadow: 0 4px 14px rgba(10, 132, 255, 0.35) !important;
        transition: transform 0.15s ease, background 0.15s ease !important;
    }

    .stButton > button:hover {
        transform: scale(0.99) !important;
        background: #1c8eff !important;
    }

    div[data-baseweb="input"] {
        background: rgba(255, 255, 255, 0.08) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 12px !important;
        color: #FFFFFF !important;
    }

    div[data-baseweb="input"] input {
        color: #FFFFFF !important;
    }

    details {
        background: rgba(22, 28, 45, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 16px !important;
        padding: 10px 16px !important;
        color: #FFFFFF !important;
    }

    summary {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }

    div[data-testid="stFileUploader"] {
        background: rgba(255, 255, 255, 0.05) !important;
        border: 1px dashed rgba(255, 255, 255, 0.2) !important;
        border-radius: 20px !important;
        padding: 15px !important;
    }

    .stMarkdown h3, .stMarkdown label {
        color: rgba(255, 255, 255, 0.85) !important;
    }
    </style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# SEGREDOS E AUTENTICAÇÃO
# ---------------------------------------------------------
def _segredo(chave, padrao=""):
    try:
        if chave in st.secrets:
            return str(st.secrets[chave])
    except Exception:
        pass
    return os.environ.get(chave, padrao)


def verificar_senha():
    senha_correta = _segredo("APP_PASSWORD")

    st.session_state.setdefault("autenticado", False)
    st.session_state.setdefault("tentativas", 0)
    st.session_state.setdefault("bloqueado_ate", 0.0)

    if st.session_state["autenticado"]:
        return True

    st.markdown('<div style="text-align: center; margin-top: 5rem;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 2.2rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.6px;">⚡ ZUQ Auto</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 0.95rem; color: rgba(255,255,255,0.65); margin-bottom: 2rem;">Acesso restrito. Digite a senha corporativa para continuar.</div>', unsafe_allow_html=True)

    if not senha_correta:
        st.error("🔒 APP_PASSWORD não configurada em st.secrets ou variável de ambiente. Acesso bloqueado por segurança.")
        st.markdown('</div>', unsafe_allow_html=True)
        return False

    col1, col2, col3 = st.columns([1.2, 1, 1.2])
    with col2:
        restante = st.session_state["bloqueado_ate"] - time.time()
        if restante > 0:
            st.error(f"⏳ Muitas tentativas. Aguarde {int(restante)}s.")
        else:
            with st.form("form_login"):
                senha_digitada = st.text_input("Senha de Acesso", type="password", placeholder="Digite a senha")
                btn_login = st.form_submit_button("Entrar", **STRETCH)

                if btn_login:
                    if hmac.compare_digest(senha_digitada.encode(), senha_correta.encode()):
                        st.session_state["autenticado"] = True
                        st.session_state["tentativas"] = 0
                        st.rerun()
                    else:
                        st.session_state["tentativas"] += 1
                        if st.session_state["tentativas"] >= MAX_TENTATIVAS_LOGIN:
                            st.session_state["bloqueado_ate"] = time.time() + BLOQUEIO_SEGUNDOS
                            st.session_state["tentativas"] = 0
                        st.error("❌ Credencial inválida.")
    st.markdown('</div>', unsafe_allow_html=True)
    return False


# ---------------------------------------------------------
# UTILITÁRIOS
# ---------------------------------------------------------
def digitar_devagar(elemento, texto, atraso=0.015):
    for caractere in str(texto):
        elemento.send_keys(caractere)
        time.sleep(atraso)


def preencher_campo_angular(driver, elemento, valor):
    elemento.click()
    elemento.send_keys(Keys.CONTROL + "a")
    elemento.send_keys(Keys.BACKSPACE)
    digitar_devagar(elemento, str(valor), atraso=0.015)
    elemento.send_keys(Keys.TAB)


def limpa_numero(val_str):
    if val_str is None:
        return 0.0
    s = re.sub(r'[^\d,\.]', '', str(val_str))
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def set_js(driver, elemento, valor):
    driver.execute_script(JS_SET, elemento, str(valor))


def data_no_texto(texto, data_str):
    partes = str(data_str).split('/')
    variantes = {str(data_str)}
    if len(partes) == 3:
        try:
            variantes.add(f"{int(partes[0])}/{int(partes[1])}/{partes[2]}")
        except ValueError:
            pass
    return any(re.search(r'(?<!\d)' + re.escape(v) + r'(?!\d)', texto) for v in variantes)


# ---------------------------------------------------------
# PARSER LIVEPOSTO
# ---------------------------------------------------------
def extrair_dados_multiplos_arquivos(uploaded_files):
    if not uploaded_files:
        return pd.DataFrame()
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    frames = []
    postos_detectados = []
    for up_f in uploaded_files:
        df_item, posto_item = _extrair_unico_arquivo(up_f)
        if posto_item and posto_item not in postos_detectados:
            postos_detectados.append(posto_item)
        if df_item is not None and not df_item.empty:
            frames.append(df_item)

    if postos_detectados:
        st.session_state["posto_detectado_pdf"] = " | ".join(postos_detectados)

    if not frames:
        return pd.DataFrame()

    df_unificado = pd.concat(frames, ignore_index=True)
    df_unificado = df_unificado.assign(
        _dt_ord=pd.to_datetime(df_unificado['data'].astype(str).str.strip(), format='%d/%m/%Y', errors='coerce'),
        _hr_ord=df_unificado['hora'].astype(str).str.strip()
    ).sort_values(by=["_dt_ord", "_hr_ord", "placa"], kind="stable").drop(columns=["_dt_ord", "_hr_ord"]).reset_index(drop=True)
    return auditar_e_validar_dados(df_unificado)


def _extrair_unico_arquivo(uploaded_file):
    registos = []
    lines = []
    nome_orig = getattr(uploaded_file, "name", "arquivo")

    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        nome_arquivo = nome_orig.lower()

        if nome_arquivo.endswith('.pdf'):
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                texto_pag = page.extract_text()
                if texto_pag:
                    lines.extend(texto_pag.split('\n'))
        else:
            lines = file_bytes.decode('latin1', errors='ignore').split('\n')
    except Exception as e:
        st.error(f"❌ Erro ao ler o arquivo {nome_orig}: {e}")
        return pd.DataFrame(), ""

    if not lines:
        return pd.DataFrame(), ""

    combustiveis_validos = ("DIESEL", "GASOLINA", "ETANOL", "ALCOOL", "ÁLCOOL")
    re_placa = r'([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})'

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "Total da Placa:" in line:
            i += 1
            continue

        m_placa = re.search(re_placa, line)
        m_data = re.search(r'(\d{2}/\d{2}/\d{2,4})', line)

        if m_placa and m_data:
            placa = m_placa.group(1).replace('-', '')
            dt_str = m_data.group(1)

            partes_dt = dt_str.split('/')
            if len(partes_dt[2]) == 2:
                dt_str = f"{partes_dt[0]}/{partes_dt[1]}/20{partes_dt[2]}"

            m_hora = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
            hora = m_hora.group(1) if m_hora else "08:00:00"

            antes_placa = line[:m_placa.start()]
            if m_hora:
                antes_placa = antes_placa[m_hora.end():]
            elif m_data:
                antes_placa = antes_placa[m_data.end():]
            cupons = re.findall(r'\b(\d{5,7})\b', antes_placa)
            cupom = cupons[0] if cupons else "0"

            j = i + 1
            while j < len(lines):
                sub_line = lines[j].strip()

                if "Total da Placa:" in sub_line or re.search(re_placa, sub_line):
                    break

                if any(comb in sub_line.upper() for comb in combustiveis_validos):
                    u_sub = sub_line.upper()
                    if "DIESEL" in u_sub:
                        produto_nome = "DIESEL B S10 ADITIVADO" if "ADITIV" in u_sub or "S10" in u_sub or "S-10" in u_sub else "DIESEL"
                    elif "GASOLINA" in u_sub:
                        produto_nome = "GASOLINA ADITIVADA" if "ADITIV" in u_sub else "GASOLINA COMUM"
                    elif "ETANOL" in u_sub or "ALCOOL" in u_sub or "ÁLCOOL" in u_sub:
                        produto_nome = "ETANOL"
                    else:
                        produto_nome = sub_line.split()[0]

                    nums_validos = re.findall(r'\d+(?:\.\d{3})*,\d+', sub_line)
                    vlr_unit, quantidade, valor_total = "0,00", "0,00", "0,00"
                    if len(nums_validos) >= 3:
                        vlr_unit, quantidade, valor_total = nums_validos[0], nums_validos[1], nums_validos[2]
                    elif len(nums_validos) == 2:
                        vlr_unit, quantidade = nums_validos[0], nums_validos[1]
                    elif len(nums_validos) == 1:
                        vlr_unit = nums_validos[0]

                    depois_placa = line[m_placa.end():]
                    depois_sem_dep = re.sub(r'\bCARRO\s+\d+\b', ' ', depois_placa, flags=re.IGNORECASE)

                    km = ""
                    m_km_ponto = re.search(r'(?<!\d)(\d{1,3}(?:\.\d{3})+)', depois_sem_dep)
                    if m_km_ponto:
                        km = m_km_ponto.group(1).replace('.', '')
                    else:
                        m_colado = re.search(r'(?<!\d)(\d+,\d{2})\b', depois_sem_dep)
                        if m_colado:
                            bloco_antes_virgula = m_colado.group(1).split(',')[0]
                            qtd_num = limpa_numero(quantidade)
                            qtd_int = str(int(round(qtd_num))) if qtd_num > 0 else ""
                            if qtd_int and len(bloco_antes_virgula) > len(qtd_int) and bloco_antes_virgula.endswith(qtd_int):
                                km = bloco_antes_virgula[:-len(qtd_int)]
                            elif len(bloco_antes_virgula) > 3:
                                km = bloco_antes_virgula[:-2] if int(bloco_antes_virgula[-3:]) > 600 else bloco_antes_virgula[:-3]

                    registos.append({
                        'data': dt_str, 'hora': hora, 'cupom': cupom, 'placa': placa,
                        'produto': produto_nome, 'quantidade': quantidade,
                        'valor_unitario': vlr_unit, 'valor_total': valor_total, 'km': km,
                        'linha_bruta': line, 'arquivo_origem': nome_orig,
                    })
                    break
                j += 1
        i += 1

    posto_detectado = ""
    for ln in lines[:25]:
        m_emp = re.search(r'Empresa:\s*(.+)', ln, flags=re.IGNORECASE)
        if m_emp and "GROWTH" not in m_emp.group(1).upper():
            posto_detectado = m_emp.group(1).strip()
            break

    return pd.DataFrame(registos), posto_detectado


# ---------------------------------------------------------
# AUDITORIA
# ---------------------------------------------------------
def auditar_e_validar_dados(df):
    if df is None or df.empty:
        return df

    df = df.copy()
    for col in COLUNAS_BASE:
        if col not in df.columns:
            df[col] = ''
    df = df.fillna('')

    datas = pd.to_datetime(df['data'].astype(str).str.strip(), format='%d/%m/%Y', errors='coerce')

    placas_norm = df['placa'].astype(str).str.strip().str.upper().str.replace('-', '', regex=False)
    contagem_placas = placas_norm.value_counts().to_dict()
    sugestao_placa = {}
    placas_unicas = list(contagem_placas.keys())
    for p in placas_unicas:
        if len(p) != 7:
            continue
        candidatas = [
            q for q in placas_unicas
            if q != p and len(q) == 7
            and sum(a != b for a, b in zip(p, q)) == 1
            and contagem_placas[q] > contagem_placas[p]
        ]
        if len(candidatas) == 1:
            sugestao_placa[p] = candidatas[0]

    chave = df[['placa', 'data', 'hora', 'cupom', 'quantidade']].astype(str).agg('|'.join, axis=1)
    duplicado = chave.duplicated(keep='first')

    regressao = pd.Series(False, index=df.index)
    tmp = pd.DataFrame({
        'placa': df['placa'].astype(str),
        'dt': datas,
        'hora': df['hora'].astype(str),
        'km': df['km'].map(limpa_numero),
    }, index=df.index)
    tmp = tmp[(tmp['km'] > 0) & tmp['dt'].notna()].sort_values(['placa', 'dt', 'hora'])
    if not tmp.empty:
        anterior = tmp.groupby('placa')['km'].shift()
        mask = (anterior.notna() & (tmp['km'] < anterior)).values
        regressao.loc[tmp.index[mask]] = True

    alertas_col = []
    for idx, row in df.iterrows():
        alertas = []
        km_val = limpa_numero(row['km'])
        preco = limpa_numero(row['valor_unitario'])
        litros = limpa_numero(row['quantidade'])
        total = limpa_numero(row['valor_total'])
        placa = str(row['placa']).strip().upper().replace('-', '')

        if km_val == 0:
            alertas.append("⚠️ KM Ausente")
        if preco == 0:
            alertas.append("❌ Preço zerado")
        elif not (PRECO_MIN <= preco <= PRECO_MAX):
            alertas.append("⚠️ Preço fora da faixa")
        if litros == 0:
            alertas.append("❌ Litros zerados")
        elif litros > LITROS_MAX:
            alertas.append("⚠️ Volume atípico")
        if preco > 0 and litros > 0 and total > 0:
            esperado = preco * litros
            if abs(esperado - total) > max(0.5, TOL_TOTAL * total):
                alertas.append("⚠️ Total inconsistente")
        if not re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', placa):
            alertas.append("⚠️ Placa suspeita")
        if pd.isna(datas.loc[idx]):
            alertas.append("❌ Data inválida")
        if duplicado.loc[idx]:
            alertas.append("🔁 Duplicado")
        if regressao.loc[idx]:
            alertas.append("⚠️ KM menor que o anterior")
        if placa in sugestao_placa:
            alertas.append(f"⚠️ Placa parecida com {sugestao_placa[placa]} (1 dígito)")

        alertas_col.append(" | ".join(alertas) if alertas else "✅ Prontos para conciliar")

    df['alertas_auditoria'] = alertas_col
    return df


def calcular_metricas_pre(df):
    if df is None or df.empty:
        return dict(registros=0, litros=0.0, valor=0.0, com_alerta=0, criticos=0, duplicados=0, preco_medio=0.0)
    litros = df['quantidade'].map(limpa_numero)
    preco = df['valor_unitario'].map(limpa_numero)
    alertas = df['alertas_auditoria'].astype(str)
    valor_total = float((litros * preco).sum())
    litros_total = float(litros.sum())
    return dict(
        registros=len(df),
        litros=litros_total,
        valor=valor_total,
        com_alerta=int((~alertas.str.startswith("✅")).sum()),
        criticos=int(alertas.str.contains("❌").sum()),
        duplicados=int(alertas.str.contains("🔁").sum()),
        preco_medio=(valor_total / litros_total) if litros_total else 0.0,
    )


def fmt_brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar_resumo_executivo_frota(df):
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()

    tmp = df.copy()
    tmp["_litros"] = tmp["quantidade"].map(limpa_numero)
    tmp["_preco"] = tmp["valor_unitario"].map(limpa_numero)
    tmp["_valor"] = tmp["_litros"] * tmp["_preco"]
    tmp["_km"] = tmp["km"].map(limpa_numero)
    tmp["_dt"] = pd.to_datetime(tmp["data"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce")

    linhas_placa = []
    for placa, grp in tmp.groupby("placa", sort=True):
        grp_ord = grp.sort_values(["_dt", "hora"])
        kms_validos = grp_ord.loc[grp_ord["_km"] > 0, "_km"]
        km_ini = float(kms_validos.iloc[0]) if len(kms_validos) >= 1 else 0.0
        km_fim = float(kms_validos.iloc[-1]) if len(kms_validos) >= 1 else 0.0
        km_rodado = max(0.0, km_fim - km_ini) if len(kms_validos) >= 2 else 0.0
        litros_tot = float(grp["_litros"].sum())
        valor_tot = float(grp["_valor"].sum())
        litros_pos_ini = float(grp_ord.iloc[1:]["_litros"].sum()) if len(grp_ord) >= 2 else 0.0
        kml = (km_rodado / litros_pos_ini) if (km_rodado > 0 and litros_pos_ini > 0) else 0.0

        linhas_placa.append({
            "Placa": placa,
            "Abastecimentos": int(len(grp)),
            "Litros Totais": round(litros_tot, 2),
            "Valor Total (R$)": round(valor_tot, 2),
            "Preço Médio (R$/L)": round(valor_tot / litros_tot, 3) if litros_tot > 0 else 0.0,
            "KM Inicial": int(km_ini) if km_ini > 0 else None,
            "KM Final": int(km_fim) if km_fim > 0 else None,
            "KM Rodado": int(km_rodado) if km_rodado > 0 else None,
            "Média Est. (km/L)": round(kml, 2) if kml > 0 else None,
        })

    df_placa = pd.DataFrame(linhas_placa).sort_values("Valor Total (R$)", ascending=False).reset_index(drop=True)

    linhas_comb = []
    if "produto" in tmp.columns:
        for prod, grp in tmp.groupby("produto", sort=True):
            l_tot = float(grp["_litros"].sum())
            v_tot = float(grp["_valor"].sum())
            linhas_comb.append({
                "Combustível": prod or "NÃO INFORMADO",
                "Abastecimentos": int(len(grp)),
                "Litros Totais": round(l_tot, 2),
                "Valor Total (R$)": round(v_tot, 2),
                "Preço Médio (R$/L)": round(v_tot / l_tot, 3) if l_tot > 0 else 0.0,
            })
    df_comb = pd.DataFrame(linhas_comb).sort_values("Litros Totais", ascending=False).reset_index(drop=True) if linhas_comb else pd.DataFrame()
    return df_placa, df_comb


# ---------------------------------------------------------
# SELENIUM - SUPORTE
# ---------------------------------------------------------
def fechar_alerta_se_existir(driver, log_container):
    try:
        alert = driver.switch_to.alert
        texto = alert.text
        alert.accept()
        log_container.warning(f"⚠️ Alerta retornado: {texto}")
        time.sleep(0.8)
        return True
    except Exception:
        return False


def navegar_com_timeout_seguro(driver, url, timeout=15, log_container=None):
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
    except TimeoutException:
        if log_container:
            log_container.warning(f"⏳ Interrompendo scripts em {url}...")
        driver.execute_script("window.stop();")
        time.sleep(0.5)


def executar_com_retry(func, max_tentativas=3, intervalo_base=2.0, log_container=None):
    excecoes = (WebDriverException, TimeoutException, NoSuchElementException, StaleElementReferenceException)
    for tentativa in range(1, max_tentativas + 1):
        try:
            return func()
        except excecoes as e:
            if log_container:
                log_container.warning(f"⚠️ Tentativa {tentativa}/{max_tentativas}...")
            if tentativa == max_tentativas:
                raise e
            time.sleep(intervalo_base * (2 ** (tentativa - 1)))


def criar_driver():
    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--window-size=1920,1080"):
        options.add_argument(arg)

    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(15)
    return driver


def erros_visiveis(driver):
    """Captura alertas de erro, mensagens de validação e campos AngularJS inválidos/vazios."""
    xp = (
        "//*[contains(@class,'alert-danger') or contains(@class,'alert-warning') or contains(@class,'toast-error')] | "
        "//*[contains(@class,'has-error')]//*[contains(@class,'help-block') or contains(@class,'text-danger')]"
    )
    textos = []
    for el in driver.find_elements(By.XPATH, xp):
        try:
            t = el.text.strip()
            if el.is_displayed() and len(t) > 2 and t not in textos:
                textos.append(t)
        except Exception:
            pass

    if not textos:
        campos_inv = driver.find_elements(
            By.CSS_SELECTOR,
            "input.ng-invalid, select.ng-invalid, textarea.ng-invalid"
        )
        nomes_inv = []
        for c in campos_inv:
            try:
                if not c.is_displayed():
                    continue
                lbl = driver.execute_script(
                    "var p = arguments[0].closest('div, .form-group');"
                    "while (p && !p.querySelector('label')) { p = p.parentElement; }"
                    "return p && p.querySelector('label') ? p.querySelector('label').innerText.trim() : '';",
                    c
                )
                msg_err = c.get_attribute("data-error-message") or c.get_attribute("name") or c.get_attribute("id") or ""
                item = f"{lbl} [{msg_err}]".strip(" []") if lbl else msg_err
                if item and item not in nomes_inv:
                    nomes_inv.append(item)
            except Exception:
                pass
        if nomes_inv:
            textos.append("Campos inválidos/obrigatórios: " + ", ".join(nomes_inv))
    return textos


def _limpar_campo_km_angular(driver):
    campo_km = driver.find_element(By.XPATH, XP_KM)
    campo_km.click()
    campo_km.send_keys(Keys.CONTROL + "a")
    campo_km.send_keys(Keys.BACKSPACE)
    driver.execute_script(
        "arguments[0].value = '';"
        "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
        "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));"
        "arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));"
        "if (window.angular) { var el = angular.element(arguments[0]); el.val(''); el.triggerHandler('input'); el.triggerHandler('change'); }",
        campo_km
    )


def _aguardar_resposta_save(driver, sair_do_novo=False, timeout=8.0):
    """Aguarda a conclusão do save no AngularJS (mudança de rota ou erro visível)."""
    limite = time.time() + timeout
    while time.time() < limite:
        url = driver.current_url
        if sair_do_novo and "/fuel/new" not in url:
            return "SALVO"
        if not sair_do_novo and "/edit" not in url:
            return "SALVO"

        erros = erros_visiveis(driver)
        if erros:
            return "ERRO_VALIDACAO"

        erros_km = driver.find_elements(
            By.XPATH,
            "//*[contains(text(),'Odômetro Inválido') or contains(text(),'Hodômetro Inválido') or contains(text(),'entra em conflito')]"
        )
        if any(el.is_displayed() for el in erros_km):
            return "CONFLITO_KM"

        time.sleep(0.25)
    return "TIMEOUT"


def _clicar_botao_salvar(driver, wait):
    """Localiza e clica no botão Salvar (elemento <a> ou <button> que contém 'Salvar')."""
    xpaths = [
        "//a[contains(@class,'btn') and .//span[normalize-space()='Salvar']]",
        "//button[contains(@class,'btn') and (.//span[normalize-space()='Salvar'] or normalize-space()='Salvar')]",
        "//*[contains(@class,'btn-success') and contains(.,'Salvar')]",
    ]
    ultimo_erro = None
    for xp in xpaths:
        try:
            el = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(0.2)
            wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)
            return True
        except Exception as e:
            ultimo_erro = e
            continue
    raise ultimo_erro or NoSuchElementException("Botão Salvar não encontrado")


def salvar_formulario(driver, wait, log_container, exigir_sair_do_novo=False,
                      base_url="", placa="", data_str="", km_str=""):
    """Clica em Salvar, trata conflito de odômetro se ocorrer e retorna (ok, nota)."""
    try:
        _clicar_botao_salvar(driver, wait)
        estado = _aguardar_resposta_save(driver, sair_do_novo=exigir_sair_do_novo, timeout=8.0)

        sem_km = False
        if estado == "CONFLITO_KM":
            log_container.warning("⚠️ Conflito de Odômetro no ZUQ! Limpando KM e tentando salvar novamente...")
            _limpar_campo_km_angular(driver)
            time.sleep(0.3)
            _clicar_botao_salvar(driver, wait)
            estado = _aguardar_resposta_save(driver, sair_do_novo=exigir_sair_do_novo, timeout=8.0)
            sem_km = True

        erros = erros_visiveis(driver)
        if erros:
            return False, f"Rejeitado pelo ZUQ: {' | '.join(erros)[:240]}"

        if exigir_sair_do_novo and "/fuel/new" in driver.current_url:
            return False, "Formulário permaneceu em /fuel/new (verifique campos obrigatórios como Natureza, Combustível ou Fornecedor)"

        if estado == "TIMEOUT" and exigir_sair_do_novo:
            return False, "Tempo esgotado aguardando resposta do ZUQ após clicar em Salvar"

        return True, ("Salvo sem KM (conflito de odômetro)" if sem_km else "")
    except Exception as e_save:
        return False, f"Falha ao acionar Salvar: {e_save}"


# ---------------------------------------------------------
# CONCILIAÇÃO E EDIÇÃO ATIVA NO ZUQ
# ---------------------------------------------------------
def conciliar_ou_criar_registro(driver, wait, base_url, placa, data, km, litros, preco,
                                ultima_placa_filtrada, log_container, simular=False):
    try:
        url_atual = driver.current_url.rstrip('/')
        na_lista = url_atual.endswith("#/fuel")
        precisa_filtrar = (placa != ultima_placa_filtrada) or (not na_lista)

        if precisa_filtrar:
            navegar_com_timeout_seguro(driver, f"{base_url}/secure/manager/maintenance/#/fuel", timeout=12, log_container=log_container)
            time.sleep(1.5)

            try:
                wait.until(EC.element_to_be_clickable((By.ID, "btn-allvehicles"))).click()
                time.sleep(0.8)

                select_filtro = driver.find_elements(By.XPATH, "//select[@ng-model='filter.type']")
                if select_filtro:
                    Select(select_filtro[0]).select_by_visible_text("Placa")
                    time.sleep(0.3)

                input_modal = driver.find_element(By.XPATH, "//div[contains(@class,'selectize-input')]//input")
                input_modal.click()
                time.sleep(0.3)

                for item in driver.find_elements(By.XPATH, "//div[contains(@class,'selectize-input')]//div[contains(@class,'item')]"):
                    try:
                        item.find_element(By.XPATH, ".//a[contains(@class,'remove')]").click()
                        time.sleep(0.2)
                    except Exception:
                        pass

                input_modal.send_keys(Keys.CONTROL + "a")
                input_modal.send_keys(Keys.BACKSPACE)
                time.sleep(0.3)
                digitar_devagar(input_modal, placa, atraso=0.015)
                xp_opc_f = f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{placa}')]"
                try:
                    WebDriverWait(driver, 2.5).until(EC.presence_of_element_located((By.XPATH, xp_opc_f)))
                except TimeoutException:
                    pass
                opcoes = driver.find_elements(By.XPATH, xp_opc_f)
                placa_corrigida_de = ""
                if not opcoes and len(placa) == 7:
                    sufixo = placa[-4:]
                    input_modal.send_keys(Keys.CONTROL + "a")
                    input_modal.send_keys(Keys.BACKSPACE)
                    time.sleep(0.2)
                    digitar_devagar(input_modal, sufixo, atraso=0.015)
                    xp_opc_suf = f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{sufixo}')]"
                    try:
                        WebDriverWait(driver, 2.0).until(EC.presence_of_element_located((By.XPATH, xp_opc_suf)))
                    except TimeoutException:
                        pass
                    candidatos_zuq = []
                    for el_op in driver.find_elements(By.XPATH, xp_opc_suf):
                        m_p_zuq = re.search(r'([A-Z]{3}[0-9][A-Z0-9][0-9]{2})', el_op.text.upper().replace('-', ''))
                        if m_p_zuq:
                            p_cand = m_p_zuq.group(1)
                            if len(p_cand) == 7 and sum(a != b for a, b in zip(placa, p_cand)) == 1:
                                candidatos_zuq.append((p_cand, el_op))
                    placas_distintas = {p for p, _ in candidatos_zuq}
                    if len(placas_distintas) == 1:
                        placa_nova = next(iter(placas_distintas))
                        opcoes = [el for p, el in candidatos_zuq if p == placa_nova]
                        placa_corrigida_de = placa
                        placa = placa_nova
                        log_container.warning(f"🔄 Placa {placa_corrigida_de} não existe no ZUQ; corrigida automaticamente para **{placa}** (1 dígito divergente).")

                if not opcoes:
                    log_container.warning(f"🚨 DIVERGÊNCIA: Placa {placa} não existe no ZUQ!")
                    driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]").click()
                    time.sleep(0.8)
                    fechar_alerta_se_existir(driver, log_container)
                    return "NAO_ENCONTRADA", "Placa não encontrada no ZUQ", ""

                opcoes[0].click()
                time.sleep(0.4)
                try:
                    driver.find_element(By.XPATH, "//h5[contains(.,'Filtrar os veículos')]").click()
                except Exception:
                    input_modal.send_keys(Keys.ESCAPE)
                time.sleep(0.5)

                wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'btn-primary') and contains(.,'Confirmar')]"))).click()
                time.sleep(1.5)
                fechar_alerta_se_existir(driver, log_container)

            except Exception:
                try:
                    driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]").click()
                except Exception:
                    pass
                fechar_alerta_se_existir(driver, log_container)
                return "ERRO", "Erro ao filtrar placa", ""

        target_litros = limpa_numero(litros)
        target_preco = limpa_numero(preco)
        target_km = re.sub(r'\D', '', str(km)) if km else ""

        candidatos = []
        for linha in driver.find_elements(By.XPATH, "//tr[contains(@ng-repeat,'fuel')]"):
            texto = linha.text
            if not texto or not data_no_texto(texto, data):
                continue
            tds = linha.find_elements(By.TAG_NAME, "td")
            nums = [limpa_numero(td.text) for td in tds]
            nums = [n for n in nums if n > 0]
            l_ok = target_litros > 0 and any(abs(n - target_litros) < 0.1 for n in nums)
            p_ok = target_preco > 0 and any(abs(n - target_preco) < 0.05 for n in nums)
            k_ok = bool(target_km) and any(re.sub(r'\D', '', td.text) == target_km for td in tds)
            candidatos.append((int(l_ok) + int(p_ok) + int(k_ok), linha, l_ok, p_ok, k_ok))

        candidatos.sort(key=lambda c: c[0], reverse=True)

        if not candidatos or candidatos[0][0] == 0:
            log_container.info(f"➕ Nenhum registro correspondente. Criando novo para {placa}...")
            return "CRIAR", "Criar Novo", placa

        melhor_score, linha_encontrada, l_ok, p_ok, k_ok = candidatos[0]
        if melhor_score == 1 and len(candidatos) > 1:
            log_container.warning(f"❓ Correspondência ambígua para {placa} ({data}). Revisar manualmente.")
            return "ERRO", "Ambíguo: várias linhas na mesma data, revisar manualmente", placa

        log_container.info(f"🔍 Registro localizado no ZUQ para {placa} ({data}). Verificando divergências...")

        tds_texto = [td.text.strip() for td in linha_encontrada.find_elements(By.TAG_NAME, "td")]
        tem_zerado = any(t in ("0,00", "0.00") for t in tds_texto)
        precisa_editar = (target_km and not k_ok) or (target_preco > 0 and not p_ok) \
            or (target_litros > 0 and not l_ok) or tem_zerado

        if not precisa_editar:
            log_container.info("✅ Registro no ZUQ já está 100% correto.")
            return "OK", "Já cadastrado (sem divergência)", placa

        zuq_km_atual = ""
        zuq_vals_dec = []
        for t_cel in tds_texto:
            if re.search(r'\bkm\b', t_cel, flags=re.IGNORECASE) or (t_cel.replace('.', '').isdigit() and len(t_cel.replace('.', '')) >= 4):
                zuq_km_atual = re.sub(r'\D', '', t_cel)
            if ',' in t_cel or '.' in t_cel:
                v_cel = limpa_numero(t_cel)
                if v_cel > 0:
                    zuq_vals_dec.append(v_cel)

        divergencias = []
        if target_km and not k_ok:
            divergencias.append(f"KM: {zuq_km_atual or 'vazio'} → {target_km}")
        if target_preco > 0 and not p_ok:
            p_ant = next((v for v in zuq_vals_dec if PRECO_MIN <= v <= PRECO_MAX), None)
            divergencias.append(f"Preço: {f'R$ {p_ant:.3f}'.replace('.', ',') if p_ant else 'divergente'} → R$ {preco}")
        if target_litros > 0 and not l_ok:
            divergencias.append(f"Litros: → {litros}L")
        if tem_zerado:
            divergencias.append("campo zerado")

        detalhe_div = " | ".join(divergencias)
        if simular:
            log_container.warning(f"🧪 [SIMULAÇÃO] {placa} seria atualizado ({detalhe_div}).")
            return "SIM_ATUALIZAR", f"Simulação: atualizaria ({detalhe_div})", placa

        log_container.warning(f"✏️ Divergência em {placa} ({detalhe_div}). Editando no ZUQ...")
        try:
            link = linha_encontrada.find_element(By.XPATH, ".//a[contains(@href,'/fuel/')]")
            navegar_com_timeout_seguro(driver, link.get_attribute("href"), timeout=12, log_container=log_container)
        except Exception:
            linha_encontrada.click()
        time.sleep(1.8)

        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class,'btn') and .//i[contains(@class,'icon-pencil') or contains(@class,'fa-pencil')]]"))).click()
            time.sleep(1.5)
        except Exception as e_ed:
            log_container.error(f"❌ Não foi possível abrir edição: {e_ed}")
            return "ERRO", "Erro ao abrir edição", ""

        if target_preco > 0:
            try:
                set_js(driver, driver.find_element(By.NAME, "price"), preco)
                log_container.info(f"✏️ Preço unitário corrigido para R$ {preco}")
            except Exception:
                pass
        if target_litros > 0:
            try:
                set_js(driver, driver.find_element(By.XPATH, XP_LITROS), litros)
                log_container.info(f"✏️ Volume corrigido para {litros} L")
            except Exception:
                pass
        if km and km != "0":
            try:
                preencher_campo_angular(driver, driver.find_element(By.XPATH, XP_KM), km)
                log_container.info(f"✏️ KM corrigido para {km}")
            except Exception:
                pass

        ok_save, nota = salvar_formulario(
            driver, wait, log_container,
            base_url=base_url, placa=placa, data_str=data, km_str=km
        )
        if ok_save:
            log_container.success(f"✅ Atualizado no ZUQ ({placa}): {detalhe_div}")
            return "ATUALIZADO", f"Corrigido ({detalhe_div})" + (f" — {nota}" if nota else ""), ""
        return "ERRO", f"Falha ao salvar edição: {nota}", ""

    except Exception as e:
        fechar_alerta_se_existir(driver, log_container)
        return "ERRO", f"Erro na análise: {e}", ""


# ---------------------------------------------------------
# AUTOMAÇÃO DE LANÇAMENTO E EDIÇÃO ZUQ
# ---------------------------------------------------------
class LogPersistente:
    def __init__(self, container, historico, scroll_placeholder=None):
        self.c, self.h = container, historico
        self._placeholder = container.empty()
        self._scroll_ph = scroll_placeholder
        self._linhas = []
        self._tick = 0

    def _rolar_para_baixo(self):
        if self._scroll_ph is None:
            return
        self._tick += 1
        with self._scroll_ph:
            components.html(
                f"""<script>
                (function() {{
                    const boxes = window.parent.document.querySelectorAll('div[data-testid="stVerticalBlockBorderWrapper"]');
                    boxes.forEach(b => {{
                        const inner = b.querySelector('div[style*="overflow"]');
                        if (inner && inner.scrollHeight > inner.clientHeight) {{
                            inner.scrollTop = inner.scrollHeight;
                        }}
                        if (b.scrollHeight > b.clientHeight) {{
                            b.scrollTop = b.scrollHeight;
                        }}
                    }});
                }})();
                // tick {self._tick}
                </script>""",
                height=0,
            )

    def _render(self, animar_ultima=False):
        if not self._linhas:
            self._placeholder.empty()
            return
        ultima = self._linhas[-1]
        visiveis = self._linhas[-40:]
        if animar_ultima and len(ultima) > 4:
            ant_v = "\n\n".join(visiveis[:-1])
            passo = max(5, len(ultima) // 8)
            for k in range(passo, len(ultima) + 1, passo):
                parcial = ultima[:k] + " ▌"
                bloco = f"{ant_v}\n\n{parcial}" if ant_v else parcial
                self._placeholder.markdown(bloco)
                time.sleep(0.006)
        self._placeholder.markdown("\n\n".join(visiveis))
        self.h[:] = [("item", x) for x in self._linhas]
        self._rolar_para_baixo()

    def _reg(self, nivel, msg, animar=True):
        if msg.startswith("📌") and self._linhas:
            self._linhas.append("---")
        self._linhas.append(msg)
        self._render(animar_ultima=animar)

    def info(self, m): self._reg("info", m, animar=True)
    def warning(self, m): self._reg("warning", m, animar=True)
    def error(self, m): self._reg("error", m, animar=True)
    def success(self, m): self._reg("success", m, animar=True)
    def write(self, m): self._reg("write", m, animar=True)


def _parse_data_hora_zuq(texto_dt):
    if not texto_dt:
        return None
    s = str(texto_dt).strip()
    for fmt in ("%d/%m/%y %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _ler_todas_leituras_odometro_zuq(driver, wait, log_container):
    leituras = []
    vistas = set()
    pagina = 1
    while True:
        novas_na_pag = 0
        for tr in driver.find_elements(By.XPATH, "//table//tbody//tr"):
            tds = [td.text.strip() for td in tr.find_elements(By.TAG_NAME, "td")]
            if len(tds) < 4:
                continue
            origem_txt = f"{tds[0]} {tds[1]}".strip()
            km_tr = 0
            dt_obj = None
            dt_raw = ""
            for cel in tds:
                m_km_cel = re.search(r'([\d\.]+)\s*km', cel, flags=re.IGNORECASE)
                if m_km_cel:
                    km_tr = int(re.sub(r'\D', '', m_km_cel.group(1)) or 0)
                m_dt_cel = re.search(r'(\d{2}/\d{2}/\d{2,4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?)', cel)
                if m_dt_cel:
                    dt_raw = m_dt_cel.group(1)
                    dt_obj = _parse_data_hora_zuq(dt_raw)
            if km_tr > 0 and dt_obj is not None:
                chave = (dt_raw, km_tr, origem_txt)
                if chave not in vistas:
                    vistas.add(chave)
                    leituras.append((dt_obj, dt_raw, km_tr, origem_txt))
                    novas_na_pag += 1

        prox_btns = driver.find_elements(
            By.XPATH,
            "//ul[contains(@class,'pagination')]//li[not(contains(@class,'disabled'))]//a[contains(.,'Próxim') or contains(.,'Next') or contains(.,'›') or contains(.,'»')]"
        )
        if prox_btns and novas_na_pag > 0 and pagina < 30:
            try:
                prox_btns[0].click()
                time.sleep(0.9)
                pagina += 1
                continue
            except Exception:
                break
        break

    leituras.sort(key=lambda x: x[0])
    return leituras


def executar_checkup_km_zuq(df, URL_ZUQ, USUARIO, SENHA, log_container, progress_bar,
                            driver_externo=None, wait_externo=None):
    df_ord = df.assign(
        _dt_ord=pd.to_datetime(df['data'].astype(str).str.strip(), format='%d/%m/%Y', errors='coerce'),
        _hr_ord=df['hora'].astype(str).str.strip()
    ).sort_values(by=["placa", "_dt_ord", "_hr_ord"], kind="stable").drop(columns=["_dt_ord", "_hr_ord"]).reset_index(drop=True)

    resultados = []
    fechar_driver_ao_final = driver_externo is None
    driver = driver_externo if driver_externo is not None else criar_driver()
    wait = wait_externo if wait_externo is not None else WebDriverWait(driver, 15)

    try:
        if fechar_driver_ao_final:
            log_container.info("🩺 Conectando ao ZUQ para pré-análise 100% de Hodômetro...")

            def acao_login():
                navegar_com_timeout_seguro(driver, URL_ZUQ, timeout=12, log_container=log_container)
                campo_usuario = wait.until(EC.element_to_be_clickable((By.ID, "j_username")))
                campo_usuario.clear()
                digitar_devagar(campo_usuario, USUARIO, atraso=0.04)
                try:
                    campo_senha = driver.find_element(By.NAME, "password")
                except NoSuchElementException:
                    campo_senha = driver.find_element(By.XPATH, "//input[@type='password']")
                campo_senha.clear()
                digitar_devagar(campo_senha, SENHA, atraso=0.04)
                time.sleep(0.25)
                try:
                    driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]").click()
                except NoSuchElementException:
                    campo_senha.send_keys(Keys.ENTER)

            executar_com_retry(acao_login, max_tentativas=3, log_container=log_container)
            log_container.info("🔐 Login efetuado. Iniciando varredura 100% na aba Hodômetro...")
            time.sleep(2.5)
        else:
            log_container.info("🩺 Fase 1/2 — Varredura 100% do histórico na aba Hodômetro antes das entradas...")

        base_url = URL_ZUQ.rsplit('/secure', 1)[0] if '/secure' in URL_ZUQ else URL_ZUQ.rstrip('/')
        navegar_com_timeout_seguro(driver, f"{base_url}/secure/manager/maintenance/#/odometer", timeout=12, log_container=log_container)
        time.sleep(1.3)

        placas_unicas = list(dict.fromkeys(
            re.sub(r'[^A-Z0-9]', '', str(p).upper()) for p in df_ord['placa'] if str(p).strip()
        ))
        cache_odo_placa = {}

        total_p = max(1, len(placas_unicas))
        for idx_p, placa in enumerate(placas_unicas):
            progress_bar.progress(
                (idx_p + 1) / total_p,
                text=f"[Pré-Análise 100%] Lendo hodômetro {idx_p + 1}/{total_p} ({placa})..."
            )
            try:
                wait.until(EC.element_to_be_clickable((By.ID, "btn-allvehicles"))).click()
                time.sleep(0.5)

                select_filtro = driver.find_elements(By.XPATH, "//select[@ng-model='filter.type']")
                if select_filtro:
                    Select(select_filtro[0]).select_by_visible_text("Placa")
                    time.sleep(0.2)

                input_modal = driver.find_element(By.XPATH, "//div[contains(@class,'selectize-input')]//input")
                input_modal.click()
                time.sleep(0.2)
                for item in driver.find_elements(By.XPATH, "//div[contains(@class,'selectize-input')]//div[contains(@class,'item')]"):
                    try:
                        item.find_element(By.XPATH, ".//a[contains(@class,'remove')]").click()
                        time.sleep(0.1)
                    except Exception:
                        pass

                input_modal.send_keys(Keys.CONTROL + "a")
                input_modal.send_keys(Keys.BACKSPACE)
                digitar_devagar(input_modal, placa, atraso=0.015)

                xp_opc = f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{placa}')]"
                try:
                    WebDriverWait(driver, 2.0).until(EC.presence_of_element_located((By.XPATH, xp_opc)))
                except TimeoutException:
                    pass
                opcoes = driver.find_elements(By.XPATH, xp_opc)
                placa_real = placa

                if not opcoes and len(placa) == 7:
                    sufixo = placa[-4:]
                    input_modal.send_keys(Keys.CONTROL + "a")
                    input_modal.send_keys(Keys.BACKSPACE)
                    digitar_devagar(input_modal, sufixo, atraso=0.015)
                    xp_suf = f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{sufixo}')]"
                    try:
                        WebDriverWait(driver, 1.8).until(EC.presence_of_element_located((By.XPATH, xp_suf)))
                    except TimeoutException:
                        pass
                    cands = []
                    for el_op in driver.find_elements(By.XPATH, xp_suf):
                        m_p = re.search(r'([A-Z]{3}[0-9][A-Z0-9][0-9]{2})', el_op.text.upper().replace('-', ''))
                        if m_p and len(m_p.group(1)) == 7 and sum(a != b for a, b in zip(placa, m_p.group(1))) == 1:
                            cands.append((m_p.group(1), el_op))
                    distintas = {p for p, _ in cands}
                    if len(distintas) == 1:
                        placa_real = next(iter(distintas))
                        opcoes = [el for p, el in cands if p == placa_real]

                if not opcoes:
                    driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]").click()
                    time.sleep(0.4)
                    fechar_alerta_se_existir(driver, log_container)
                    cache_odo_placa[placa] = {"existe": False, "placa_real": placa, "leituras": []}
                    log_container.warning(f"🚨 Placa {placa} não encontrada no ZUQ.")
                    continue

                opcoes[0].click()
                time.sleep(0.25)
                try:
                    driver.find_element(By.XPATH, "//h5[contains(.,'Filtrar os veículos')]").click()
                except Exception:
                    input_modal.send_keys(Keys.ESCAPE)
                time.sleep(0.25)

                wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'btn-primary') and contains(.,'Confirmar')]"))).click()
                time.sleep(1.2)
                fechar_alerta_se_existir(driver, log_container)

                leituras = _ler_todas_leituras_odometro_zuq(driver, wait, log_container)
                cache_odo_placa[placa] = {
                    "existe": True,
                    "placa_real": placa_real,
                    "leituras": leituras,
                }
                log_container.info(f"✅ {placa_real}: {len(leituras)} leitura(s) completas lidas no Hodômetro.")
            except Exception as e_p:
                try:
                    driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]").click()
                except Exception:
                    pass
                cache_odo_placa[placa] = {"existe": True, "placa_real": placa, "leituras": []}
                log_container.warning(f"⚠️ Falha ao ler hodômetro de {placa}: {e_p}")

        ultimo_lote_dt_km = {}
        for _, row in df_ord.iterrows():
            placa = re.sub(r'[^A-Z0-9]', '', str(row['placa']).upper())
            data_s = str(row['data']).strip()
            hora_s = str(row.get('hora', '08:00:00')).strip()
            cupom_s = str(row.get('cupom', '0')).strip()
            litros_f = limpa_numero(row['quantidade'])
            km_arq = int(re.sub(r'\D', '', str(row['km'])) or 0)
            dt_arq = _parse_data_hora_zuq(f"{data_s} {hora_s}") or _parse_data_hora_zuq(data_s)

            info = cache_odo_placa.get(placa, {"existe": False, "placa_real": placa, "leituras": []})
            if not info["existe"]:
                resultados.append({
                    "_chave": f"{placa}|{data_s}|{hora_s}|{cupom_s}",
                    "Placa": placa,
                    "Placa ZUQ": "NÃO EXISTE",
                    "Data/Hora": f"{data_s} {hora_s[:5]}",
                    "Litros": litros_f,
                    "KM Anterior ZUQ": None,
                    "KM Arquivo": km_arq if km_arq > 0 else None,
                    "KM Posterior ZUQ": None,
                    "Diagnóstico KM": "🚨 Placa ausente no ZUQ",
                })
                continue

            leituras = info["leituras"]
            leitura_mesma_data = None
            anterior = None
            posterior = None

            if dt_arq is not None:
                for dt_l, dt_raw, km_l, orig_l in leituras:
                    if dt_l.date() == dt_arq.date() and abs((dt_l - dt_arq).total_seconds()) <= 600:
                        leitura_mesma_data = (dt_l, dt_raw, km_l)
                    elif dt_l < dt_arq:
                        anterior = (dt_l, dt_raw, km_l)
                    elif dt_l > dt_arq and posterior is None:
                        posterior = (dt_l, dt_raw, km_l)

            if placa in ultimo_lote_dt_km and dt_arq is not None:
                dt_prev_lote, km_prev_lote = ultimo_lote_dt_km[placa]
                if dt_prev_lote <= dt_arq and (anterior is None or dt_prev_lote >= anterior[0]):
                    anterior = (dt_prev_lote, dt_prev_lote.strftime("%d/%m/%y %H:%M") + " (lote)", km_prev_lote)

            km_ant = anterior[2] if anterior else None
            km_post = posterior[2] if posterior else None
            lbl_ant = f"{km_ant} ({anterior[1]})" if anterior else "—"
            lbl_post = f"{km_post} ({posterior[1]})" if posterior else "—"

            if km_arq == 0:
                diag = "⚠️ KM ausente no ficheiro"
            elif leitura_mesma_data is not None and leitura_mesma_data[2] == km_arq:
                diag = "✅ KM bate exato na data/hora"
            elif leitura_mesma_data is not None and leitura_mesma_data[2] != km_arq:
                diag = f"⚠️ Divergente no mesmo horário ({leitura_mesma_data[2]} → {km_arq})"
            elif km_ant is not None and km_arq < km_ant:
                diag = f"❌ Conflito: menor que anterior ({km_ant} em {anterior[1]})"
            elif km_post is not None and km_arq > km_post:
                diag = f"❌ Conflito: maior que posterior ({km_post} em {posterior[1]})"
            elif km_ant is not None and km_post is not None:
                diag = f"✅ Encaixa na janela ({km_ant} ≤ {km_arq} ≤ {km_post})"
            elif km_ant is not None and (km_arq - km_ant) > 3000:
                diag = f"⚠️ Salto alto (+{km_arq - km_ant} km desde {anterior[1]})"
            else:
                diag = "✅ KM coerente na linha do tempo"

            if km_arq > 0 and dt_arq is not None:
                ultimo_lote_dt_km[placa] = (dt_arq, km_arq)

            resultados.append({
                "_chave": f"{placa}|{data_s}|{hora_s}|{cupom_s}",
                "Placa": placa,
                "Placa ZUQ": info["placa_real"],
                "Data/Hora": f"{data_s} {hora_s[:5]}",
                "Litros": litros_f,
                "KM Anterior ZUQ": lbl_ant,
                "KM Arquivo": km_arq if km_arq > 0 else None,
                "KM Posterior ZUQ": lbl_post,
                "Diagnóstico KM": diag,
            })

        log_container.success("🩺 Pré-análise 100% de Hodômetro concluída!")
    except Exception as e_chk:
        log_container.error(f"❌ Erro durante a pré-análise de Hodômetro: {e_chk}")
    finally:
        if fechar_driver_ao_final:
            try:
                driver.quit()
            except Exception:
                pass

    return pd.DataFrame(resultados)


def lancar_no_zuq(df, URL_ZUQ, USUARIO, SENHA, FORNECEDOR, log_container, progress_bar,
                  ui, pular_criticos=True, simular=False, stop_flag_path=None):
    df = df.assign(
        _dt_ord=pd.to_datetime(df['data'].astype(str).str.strip(), format='%d/%m/%Y', errors='coerce'),
        _hr_ord=df['hora'].astype(str).str.strip()
    ).sort_values(by=["placa", "_dt_ord", "_hr_ord"], kind="stable").drop(columns=["_dt_ord", "_hr_ord"]).reset_index(drop=True)
    df_relatorio = df.copy()
    df_relatorio['status_lancamento'] = 'Pendente'
    df_relatorio['data_processamento'] = ''
    df_relatorio['observacao'] = ''
    df_relatorio['segundos'] = 0.0

    contadores = dict(ok=0, atualizados=0, criados=0, erros=0)
    total_registros = len(df)
    t0 = time.time()
    rot_atual, rot_cria = (("Atualizariam", "Criariam") if simular else ("Atualizados", "Criados"))

    def atualizar_kpis():
        proc = contadores['ok'] + contadores['atualizados'] + contadores['criados']
        feitos = proc + contadores['erros']
        vals = {
            'ok': ("Já corretos", contadores['ok']),
            'atualizados': (rot_atual, contadores['atualizados']),
            'criados': (rot_cria, contadores['criados']),
            'erros': ("Erros / Ignorados", contadores['erros']),
            'taxa': ("Taxa de sucesso", f"{proc / feitos * 100:.0f}%" if feitos else "—"),
            'tempo': ("Tempo decorrido", f"{time.time() - t0:.0f}s"),
        }
        for k, (rot, val) in vals.items():
            ui[k].metric(rot, val)
        st.session_state["kpis"] = vals

    def registrar(idx, status, obs, chave, t_ini):
        contadores[chave] += 1
        df_relatorio.at[idx, 'status_lancamento'] = status
        df_relatorio.at[idx, 'data_processamento'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_relatorio.at[idx, 'observacao'] = obs
        df_relatorio.at[idx, 'segundos'] = round(time.time() - t_ini, 1)
        if (idx + 1) % 5 == 0 or (idx + 1) == total_registros:
            st.session_state["resultado"] = {
                "df": df_relatorio.copy(), "tempo": time.time() - t0,
                "parcial": True, "simulacao": simular
            }
        atualizar_kpis()

    atualizar_kpis()
    driver = criar_driver()
    wait = WebDriverWait(driver, 15)

    try:
        log_container.info("🌐 Conectando ao ZUQ...")

        def acao_login():
            navegar_com_timeout_seguro(driver, URL_ZUQ, timeout=12, log_container=log_container)
            campo_usuario = wait.until(EC.element_to_be_clickable((By.ID, "j_username")))
            campo_usuario.clear()
            digitar_devagar(campo_usuario, USUARIO, atraso=0.05)
            try:
                campo_senha = driver.find_element(By.NAME, "password")
            except NoSuchElementException:
                campo_senha = driver.find_element(By.XPATH, "//input[@type='password']")
            campo_senha.clear()
            digitar_devagar(campo_senha, SENHA, atraso=0.05)
            time.sleep(0.3)
            try:
                driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]").click()
            except NoSuchElementException:
                campo_senha.send_keys(Keys.ENTER)

        executar_com_retry(acao_login, max_tentativas=3, log_container=log_container)
        log_container.info("🔐 Autenticação efetuada com sucesso.")
        time.sleep(3)

        df_chk_direto = executar_checkup_km_zuq(
            df, URL_ZUQ, USUARIO, SENHA, log_container, progress_bar,
            driver_externo=driver, wait_externo=wait
        )
        mapa_diag_km = {}
        if df_chk_direto is not None and not df_chk_direto.empty:
            st.session_state["checkup_km_df"] = df_chk_direto.drop(columns=["_chave"], errors="ignore")
            for _, r_chk in df_chk_direto.iterrows():
                mapa_diag_km[r_chk["_chave"]] = str(r_chk["Diagnóstico KM"])
            qtd_conflitos = int(df_chk_direto["Diagnóstico KM"].astype(str).str.startswith("❌").sum())
            if qtd_conflitos > 0:
                log_container.warning(f"⚠️ Pré-análise detectou {qtd_conflitos} conflito(s) de odômetro na linha do tempo. Iniciando Fase 2 (entradas) com proteção ativa...")
            else:
                log_container.info("✅ 100% dos KMs validados na linha do tempo do Hodômetro. Iniciando Fase 2 (entradas)...")
        df_relatorio['diagnostico_hodometro'] = ''

        base_url = URL_ZUQ.rsplit('/secure', 1)[0] if '/secure' in URL_ZUQ else URL_ZUQ.rstrip('/')
        ultima_placa_filtrada = ""
        placas_inexistentes_zuq = set()
        placas_mapeadas_zuq = {}

        for idx, row in df.iterrows():
            if stop_flag_path and os.path.exists(stop_flag_path):
                log_container.warning("🛑 Execução interrompida pelo utilizador! Salvando progresso parcial...")
                st.session_state["resultado"] = {
                    "df": df_relatorio.copy(), "tempo": time.time() - t0,
                    "parcial": True, "simulacao": simular
                }
                break
            t_ini = time.time()
            feitos = idx
            if feitos > 0:
                eta = (time.time() - t0) / feitos * (total_registros - feitos)
                texto_prog = f"Processando {idx + 1} de {total_registros} · ETA ~{int(eta)}s"
            else:
                texto_prog = f"Processando 1 de {total_registros}"
            progress_bar.progress((idx + 1) / total_registros, text=texto_prog)

            placa_str = re.sub(r'[^A-Z0-9]', '', str(row['placa']).upper())
            km_str = re.sub(r'\D', '', str(row['km'])) if pd.notna(row['km']) else ""
            cupom_str = str(row['cupom']) if pd.notna(row.get('cupom')) else "0"
            hora_str = str(row['hora']) if pd.notna(row.get('hora')) else "08:00:00"
            data_str = str(row['data']).strip()
            litros_str = str(row['quantidade'])
            preco_str = str(row['valor_unitario'])

            chave_chk = f"{placa_str}|{data_str}|{hora_str}|{cupom_str}"
            diag_odo = mapa_diag_km.get(chave_chk, "")
            df_relatorio.at[idx, 'diagnostico_hodometro'] = diag_odo
            if diag_odo.startswith("❌"):
                log_container.warning(f"🩺 Pré-análise Hodômetro ({placa_str}): {diag_odo} — KM será omitido na entrada para não gerar erro no ZUQ.")
                km_str = ""

            log_container.write(f"📌 **[{idx + 1}/{total_registros}] Placa {placa_str}** | Data: {data_str} | Vol: {litros_str}L | Preço/L: R$ {preco_str} | KM: {km_str or 'N/A'}")
            fechar_alerta_se_existir(driver, log_container)

            if pular_criticos and "❌" in str(row.get('alertas_auditoria', '')):
                log_container.warning(f"⏭️ Ignorado por erro crítico de auditoria: {row['alertas_auditoria']}")
                registrar(idx, 'Ignorado', f"Auditoria: {row['alertas_auditoria']}", 'erros', t_ini)
                continue

            if placa_str in placas_inexistentes_zuq:
                log_container.warning(f"⏭️ Placa {placa_str} já verificada como inexistente no ZUQ — pulando consulta repetida.")
                registrar(idx, 'Ignorado', 'Placa não encontrada no ZUQ (cache)', 'erros', t_ini)
                continue

            placa_orig_pdf = placa_str
            if placa_str in placas_mapeadas_zuq:
                placa_str = placas_mapeadas_zuq[placa_str]
                df_relatorio.at[idx, 'placa'] = placa_str

            acao, obs, ultima_placa_filtrada = conciliar_ou_criar_registro(
                driver, wait, base_url, placa_str, data_str, km_str, litros_str, preco_str,
                ultima_placa_filtrada, log_container, simular
            )
            if acao == "NAO_ENCONTRADA":
                placas_inexistentes_zuq.add(placa_orig_pdf)
            elif ultima_placa_filtrada and ultima_placa_filtrada != placa_orig_pdf:
                placas_mapeadas_zuq[placa_orig_pdf] = ultima_placa_filtrada
                obs = f"{obs} (Placa corrigida: {placa_orig_pdf} -> {ultima_placa_filtrada})"
                placa_str = ultima_placa_filtrada
                df_relatorio.at[idx, 'placa'] = placa_str
                if st.session_state.get("dados_df") is not None and "placa" in st.session_state["dados_df"].columns:
                    mask_p = st.session_state["dados_df"]["placa"].astype(str).str.upper().str.replace("-", "", regex=False) == placa_orig_pdf
                    st.session_state["dados_df"].loc[mask_p, "placa"] = ultima_placa_filtrada

            if acao == "OK":
                registrar(idx, 'Já correto', obs, 'ok', t_ini)
                continue
            if acao == "ATUALIZADO":
                registrar(idx, 'Atualizado', obs, 'atualizados', t_ini)
                continue
            if acao == "SIM_ATUALIZAR":
                registrar(idx, 'Simulação: atualizaria', obs, 'atualizados', t_ini)
                continue
            if acao == "NAO_ENCONTRADA":
                registrar(idx, 'Ignorado', obs, 'erros', t_ini)
                continue
            if acao == "ERRO":
                registrar(idx, 'Erro', obs, 'erros', t_ini)
                continue

            # ---------------- acao == "CRIAR" ----------------
            if simular:
                log_container.warning(f"🧪 [SIMULAÇÃO] {placa_str} seria criado no ZUQ.")
                registrar(idx, 'Simulação: criaria', 'Simulação: criaria novo abastecimento', 'criados', t_ini)
                continue
            ultima_placa_filtrada = ""

            def abrir_formulario():
                navegar_com_timeout_seguro(driver, f"{base_url}/secure/manager/maintenance/#/fuel/new", timeout=12, log_container=log_container)
                wait.until(EC.element_to_be_clickable((By.XPATH, XP_VEICULO)))

            try:
                executar_com_retry(abrir_formulario, max_tentativas=3, log_container=log_container)
            except Exception as e_nav:
                log_container.error(f"❌ Falha no formulário: {e_nav}")
                registrar(idx, 'Erro', f"Falha no formulário: {e_nav}", 'erros', t_ini)
                continue

            def selecionar_veiculo():
                box_v = wait.until(EC.element_to_be_clickable((By.XPATH, XP_VEICULO)))
                box_v.click()
                time.sleep(0.35)
                inp = driver.find_element(By.XPATH, XP_VEICULO + "//input")
                inp.send_keys(Keys.CONTROL + "a")
                inp.send_keys(Keys.BACKSPACE)
                digitar_devagar(inp, placa_str, atraso=0.02)
                xp_opc_v = f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(@class,'option') and contains(.,'{placa_str}')]"
                try:
                    WebDriverWait(driver, 3.0).until(EC.element_to_be_clickable((By.XPATH, xp_opc_v)))
                except TimeoutException:
                    pass
                opcoes = driver.find_elements(By.XPATH, xp_opc_v)
                if not opcoes:
                    return False
                opcoes[0].click()
                time.sleep(0.5)
                return True

            try:
                if not executar_com_retry(selecionar_veiculo, max_tentativas=3, log_container=log_container):
                    log_container.warning(f"⚠️ Veículo {placa_str} não localizado no ZUQ.")
                    registrar(idx, 'Ignorado', 'Veículo não localizado', 'erros', t_ini)
                    continue
            except Exception as e_v:
                log_container.error(f"Erro no veículo {placa_str}: {e_v}")
                registrar(idx, 'Erro', f"Erro no veículo: {e_v}", 'erros', t_ini)
                continue

            try:
                data_iso = datetime.strptime(data_str, "%d/%m/%Y").strftime("%Y-%m-%d")
                set_js(driver, driver.find_element(By.ID, "fuelDate"), data_iso)
            except Exception:
                pass

            try:
                campo_hora = driver.find_element(By.ID, "additionTime")
                campo_hora.click()
                campo_hora.send_keys(Keys.CONTROL + "a")
                campo_hora.send_keys(Keys.BACKSPACE)
                digitar_devagar(campo_hora, hora_str[:5] if len(hora_str) >= 5 else hora_str, atraso=0.05)
                campo_hora.send_keys(Keys.TAB)
            except Exception:
                pass

            for xp, val in ((XP_LITROS, litros_str), (None, preco_str)):
                try:
                    elem = driver.find_element(By.NAME, "price") if xp is None else driver.find_element(By.XPATH, xp)
                    set_js(driver, elem, val)
                except Exception:
                    pass

            if km_str and km_str != "0":
                try:
                    preencher_campo_angular(driver, driver.find_element(By.XPATH, XP_KM), km_str)
                except Exception:
                    pass

            try:
                prod_str = str(row.get('produto', 'DIESEL')).strip().upper()
                if "S10" in prod_str or "S-10" in prod_str:
                    prioridades = ["S-10 ADITIVADO", "S-10", "S10", "DIESEL"]
                elif "DIESEL" in prod_str:
                    prioridades = ["S-10", "S-10 ADITIVADO", "DIESEL"]
                elif "GASOLINA" in prod_str and "ADITIV" in prod_str:
                    prioridades = ["GASOLINA ADITIVADA", "GASOLINA C ADITIVADA", "GASOLINA COMUM", "GASOLINA"]
                elif "GASOLINA" in prod_str:
                    prioridades = ["GASOLINA COMUM", "GASOLINA C COMUM", "GASOLINA", "GASOLINA ADITIVADA"]
                elif "ETANOL" in prod_str or "ALCOOL" in prod_str or "ÁLCOOL" in prod_str:
                    prioridades = ["ETANOL", "ETANOL HIDRATADO", "ÁLCOOL", "ALCOOL"]
                else:
                    prioridades = [prod_str]

                sel_el = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//select[@ng-model='fuel.payable.id'] | //label[contains(.,'Combustível')]/following::select[1]")
                ))
                time.sleep(0.5)

                esta_desabilitado = sel_el.get_attribute("disabled") is not None or not sel_el.is_enabled()
                sel_obj = Select(sel_el)
                valor_atual = sel_el.get_attribute("value") or ""

                if esta_desabilitado:
                    txt_atual = sel_obj.first_selected_option.text.strip() if sel_obj.options else ""
                    log_container.info(f"🔒 Combustível fixo na configuração do veículo: {txt_atual or 'Automático'}")
                elif not valor_atual or "?" in valor_atual:
                    escolhido = None
                    for alvo in prioridades:
                        for opt in sel_obj.options:
                            txt_opt = opt.text.strip().upper()
                            if txt_opt == alvo or alvo in txt_opt:
                                escolhido = opt.text
                                break
                        if escolhido:
                            break

                    if not escolhido:
                        for opt in sel_obj.options:
                            val_o = opt.get_attribute("value") or ""
                            if val_o and "?" not in val_o and opt.text.strip():
                                escolhido = opt.text
                                break

                    if escolhido:
                        sel_obj.select_by_visible_text(escolhido)
                        driver.execute_script(
                            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));"
                            "if (window.angular) { angular.element(arguments[0]).triggerHandler('change'); }",
                            sel_el
                        )
                        log_container.info(f"⛽ Combustível selecionado: {escolhido.strip()}")
                time.sleep(0.3)
            except Exception as e_comb:
                log_container.warning(f"⚠️ Aviso ao selecionar combustível: {e_comb}")

            try:
                el_forn = wait.until(EC.element_to_be_clickable((By.XPATH, XP_FORNECEDOR)))
                el_forn.click()
                time.sleep(0.3)
                inp_f = el_forn.find_element(By.XPATH, ".//input")
                inp_f.send_keys(Keys.CONTROL + "a")
                inp_f.send_keys(Keys.BACKSPACE)
                digitar_devagar(inp_f, FORNECEDOR, atraso=0.015)
                xp_opc_forn = "//div[contains(@class,'selectize-dropdown-content') and not(contains(@style,'display: none'))]//div[contains(@class,'option')]"
                try:
                    WebDriverWait(driver, 2.5).until(EC.element_to_be_clickable((By.XPATH, xp_opc_forn)))
                except TimeoutException:
                    pass
                opcoes_f = driver.find_elements(By.XPATH, xp_opc_forn)
                if opcoes_f:
                    opcoes_f[0].click()
                else:
                    inp_f.send_keys(Keys.ENTER)
                time.sleep(0.3)
            except Exception as e_forn:
                log_container.warning(f"⚠️ Aviso ao selecionar fornecedor: {e_forn}")

            try:
                set_js(driver, driver.find_element(By.XPATH, XP_DOC), cupom_str)
            except Exception:
                pass

            salvo, nota_save = False, ""
            try:
                salvo, nota_save = salvar_formulario(
                    driver, wait, log_container, exigir_sair_do_novo=True,
                    base_url=base_url, placa=placa_str, data_str=data_str, km_str=km_str
                )
            except Exception as e_save:
                nota_save = f"Erro ao salvar: {e_save}"
                log_container.error(f"❌ Erro ao salvar {placa_str}: {e_save}")

            time.sleep(1.0)
            fechar_alerta_se_existir(driver, log_container)

            if salvo:
                registrar(idx, 'Criado Novo', 'Lançado com sucesso' + (f" — {nota_save}" if nota_save else ""), 'criados', t_ini)
            else:
                log_container.error(f"❌ Falha ao salvar {placa_str}: {nota_save}")
                registrar(idx, 'Erro', nota_save or 'Falha ao salvar', 'erros', t_ini)

        progress_bar.progress(1.0, text="Concluído")
        log_container.success("🎉 Processamento e conciliação finalizados!")

    except Exception as e:
        log_container.error(f"❌ Erro crítico: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return df_relatorio, time.time() - t0


# ---------------------------------------------------------
# RELATÓRIO FINAL
# ---------------------------------------------------------
def mostrar_resultado():
    res = st.session_state.get("resultado")
    if not res:
        return
    df_res, tempo = res["df"], res["tempo"]
    prefixo = "simulacao" if res.get("simulacao") else "relatorio"
    if res.get("parcial"):
        st.warning("⚠️ Resultado PARCIAL: a execução foi interrompida (ou a página recarregou). Registros 'Pendente' não foram processados.")
    if res.get("simulacao"):
        st.info("🧪 Relatório de SIMULAÇÃO: nada foi salvo no ZUQ.")

    st.divider()
    st.markdown("### 📋 Relatório de Conciliação")

    if "observacao" in df_res.columns and "placa" in df_res.columns:
        nao_enc = df_res[df_res["observacao"].astype(str).str.contains("Placa não encontrada", na=False)]
        if not nao_enc.empty:
            contagem_ne = nao_enc["placa"].value_counts()
            resumo_placas = ", ".join(f"**{p}** ({qtd}x)" for p, qtd in contagem_ne.items())
            st.warning(f"🚨 **Placas ausentes no cadastro do ZUQ ({len(contagem_ne)} veículo(s) / {len(nao_enc)} registo(s)):** {resumo_placas}")

    ok_mask = df_res['status_lancamento'].isin(STATUS_SUCESSO)
    sucesso = int(ok_mask.sum())
    total = int((df_res['status_lancamento'] != 'Pendente').sum())
    litros = float(df_res.loc[ok_mask, 'quantidade'].map(limpa_numero).sum() or 0.0) if ok_mask.any() else 0.0
    media = df_res.loc[df_res['segundos'] > 0, 'segundos'].mean()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Taxa de sucesso", f"{sucesso / total * 100:.0f}%" if total else "—")
    m2.metric("Tempo total", f"{tempo:.0f}s")
    m3.metric("Média / registro", f"{media:.1f}s" if pd.notna(media) else "—")
    m4.metric("Litros conciliados", f"{litros:,.0f}".replace(",", "."))

    falhas_mask = ~ok_mask
    qtd_falhas = int(falhas_mask.sum())

    c_filt, c_reproc = st.columns([2, 1])
    filtro_status = c_filt.radio(
        "Visualizar registos:",
        options=[f"Todos ({len(df_res)})", f"Somente Erros / Pendentes ({qtd_falhas})", f"Somente Concluídos ({sucesso})"],
        horizontal=True,
        label_visibility="collapsed"
    )
    if filtro_status.startswith("Somente Erros"):
        df_visivel = df_res[falhas_mask]
    elif filtro_status.startswith("Somente Concluídos"):
        df_visivel = df_res[ok_mask]
    else:
        df_visivel = df_res

    if qtd_falhas > 0 and not res.get("simulacao"):
        if c_reproc.button(f"🔄 Carregar {qtd_falhas} falha(s) para reprocessar", **STRETCH):
            cols_orig = [c for c in df_res.columns if c not in ('status_lancamento', 'data_processamento', 'observacao', 'segundos')]
            st.session_state["dados_df"] = auditar_e_validar_dados(df_res.loc[falhas_mask, cols_orig].reset_index(drop=True))
            st.session_state["dados_final"] = st.session_state["dados_df"]
            st.session_state["resultado"] = None
            st.session_state["kpis"] = None
            st.session_state["log_hist"] = []
            st.rerun()

    df_resumo_placa, df_resumo_comb = gerar_resumo_executivo_frota(df_res)

    tab_det, tab_placas, tab_comb = st.tabs([
        f"📄 Detalhado ({len(df_visivel)})",
        f"🚛 Resumo por Placa & km/L ({len(df_resumo_placa)})",
        f"⛽ Por Combustível ({len(df_resumo_comb)})"
    ])
    with tab_det:
        cols_det = [c for c in ['placa', 'data', 'quantidade', 'valor_unitario', 'km',
                                'diagnostico_hodometro', 'status_lancamento', 'observacao', 'arquivo_origem', 'segundos'] if c in df_visivel.columns]
        st.dataframe(df_visivel[cols_det], **STRETCH)
    with tab_placas:
        if not df_resumo_placa.empty:
            st.dataframe(df_resumo_placa, **STRETCH)
    with tab_comb:
        if not df_resumo_comb.empty:
            st.dataframe(df_resumo_comb, **STRETCH)

    col_dl1, col_dl2 = st.columns(2)
    csv_data = df_res.to_csv(index=False, sep=';', encoding='utf-8-sig')
    col_dl1.download_button(
        label="📥 Baixar Relatório (CSV)",
        data=csv_data,
        file_name=f"{prefixo}_conciliacao_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        **STRETCH
    )

    try:
        buf_xlsx = io.BytesIO()
        cols_export = [c for c in ['placa', 'data', 'hora', 'cupom', 'produto', 'quantidade',
                                   'valor_unitario', 'valor_total', 'km', 'diagnostico_hodometro', 'status_lancamento',
                                   'observacao', 'arquivo_origem', 'data_processamento', 'segundos'] if c in df_res.columns]
        with pd.ExcelWriter(buf_xlsx) as writer:
            df_res[cols_export].to_excel(writer, index=False, sheet_name="Conciliacao_ZUQ")
            if not df_resumo_placa.empty:
                df_resumo_placa.to_excel(writer, index=False, sheet_name="Resumo_Por_Placa")
            if not df_resumo_comb.empty:
                df_resumo_comb.to_excel(writer, index=False, sheet_name="Resumo_Combustivel")
        col_dl2.download_button(
            label="📊 Baixar Relatório Completo (Excel 3 Abas)",
            data=buf_xlsx.getvalue(),
            file_name=f"{prefixo}_conciliacao_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            **STRETCH
        )
    except Exception:
        pass


# ---------------------------------------------------------
# INTERFACE PRINCIPAL
# ---------------------------------------------------------
if verificar_senha():
    st.markdown("""
        <div class="glass-header">
            <div class="glass-logo">⚡ ZUQ Fleet <span class="glass-badge">Conciliação & Edição Automática</span></div>
        </div>
    """, unsafe_allow_html=True)

    with st.expander("⚙️ Parâmetros de Conexão ZUQ", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        usuario_zuq = c1.text_input("Usuário", value=_segredo("ZUQ_USER", "manutencaoverdesmares"))
        senha_zuq = c2.text_input("Senha ZUQ", type="password", value=_segredo("ZUQ_PASSWORD", ""))
        url_zuq = c3.text_input("URL ZUQ", value=_segredo("ZUQ_URL", "https://app.zuq.com.br"))
        fornecedor_zuq = c4.text_input("Fornecedor Padrão", value=_segredo("ZUQ_FORNECEDOR", "POSTO GURI - MACEIÓ"))

    posto_pdf = st.session_state.get("posto_detectado_pdf", "")
    if posto_pdf and posto_pdf.upper() not in fornecedor_zuq.upper():
        st.warning(f"⛽ O ficheiro carregado parece ser de **{posto_pdf}**, mas o Fornecedor configurado está como **{fornecedor_zuq}**. Ajuste em *Parâmetros de Conexão ZUQ* se necessário.")

    st.markdown("<br>", unsafe_allow_html=True)
    col_upload, col_control = st.columns([1.1, 1], gap="large")

    with col_upload:
        st.markdown("### 📁 1. Ficheiros Liveposto (1 ou vários)")
        uploaded_files = st.file_uploader(
            "Upload de um ou mais relatórios em PDF ou TXT",
            type=["pdf", "txt"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

        if uploaded_files:
            file_id = "|".join(sorted(f"{f.name}_{f.size}" for f in uploaded_files))
            if st.session_state.get("ultimo_arquivo_id") != file_id:
                st.session_state["dados_df"] = extrair_dados_multiplos_arquivos(uploaded_files)
                st.session_state["ultimo_arquivo_id"] = file_id
                st.session_state["resultado"] = None
                st.session_state["checkup_km_df"] = None
                st.session_state["kpis"] = None
                st.session_state["log_hist"] = []
        else:
            st.session_state["dados_df"] = None
            st.session_state["ultimo_arquivo_id"] = None
            st.session_state["posto_detectado_pdf"] = ""

        if st.session_state.get("dados_df") is not None:
            if st.session_state["dados_df"].empty:
                st.warning("⚠️ Nenhum registo encontrado neste arquivo. Verifique se o PDF contém texto selecionável (não é imagem digitalizada) e se segue o layout do relatório Liveposto.")
                st.session_state["dados_final"] = None
            else:
                st.info("💡 **Conciliação Ativa**: registros existentes no ZUQ com KM, Preço ou Litros divergentes serão **editados automaticamente** pelo robô.")

                _df0 = st.session_state["dados_df"]
                if 'linha_bruta' in _df0.columns:
                    _sem_km = _df0[_df0['km'].astype(str).str.strip() == ""]
                    if not _sem_km.empty:
                        with st.expander(f"🔎 {len(_sem_km)} linhas sem KM: texto bruto lido do PDF"):
                            st.code("\n".join(_sem_km['linha_bruta'].astype(str).head(15)), language=None)

                with st.form("form_edicao_dados", border=False):
                    df_editado = st.data_editor(
                        st.session_state["dados_df"],
                        column_order=['placa', 'data', 'quantidade', 'valor_unitario', 'km', 'alertas_auditoria'],
                        column_config={
                            "placa": st.column_config.TextColumn("Placa", required=True),
                            "data": st.column_config.TextColumn("Data", required=True),
                            "quantidade": st.column_config.TextColumn("Litros", required=True),
                            "valor_unitario": st.column_config.TextColumn("Preço / L", required=True),
                            "km": st.column_config.TextColumn("KM (Edição livre)", required=False),
                            "alertas_auditoria": st.column_config.TextColumn("Status", disabled=True),
                        },
                        num_rows="dynamic",
                        height=350,
                        **STRETCH
                    )
                    aplicar_edicao = st.form_submit_button("✅ Aplicar alterações na tabela", **STRETCH)
                if aplicar_edicao or st.session_state.get("dados_final") is None:
                    st.session_state["dados_df"] = auditar_e_validar_dados(df_editado)
                    st.session_state["dados_final"] = st.session_state["dados_df"]
        else:
            st.session_state["dados_final"] = None

    with col_control:
        st.markdown("### 📊 2. Lançamento e Conciliação ZUQ")
        df_para_processar = st.session_state.get("dados_final")
        mp = calcular_metricas_pre(df_para_processar)

        st.caption("Análise do arquivo")
        a1, a2, a3 = st.columns(3)
        a1.metric("Registros", mp['registros'])
        a2.metric("Litros totais", f"{mp['litros']:,.0f}".replace(",", "."))
        a3.metric("Valor estimado", fmt_brl(mp['valor']))
        b1, b2, b3 = st.columns(3)
        b1.metric("Preço médio/L", fmt_brl(mp['preco_medio']))
        b2.metric("Com alertas", mp['com_alerta'])
        b3.metric("Críticos / Dupl.", f"{mp['criticos']} / {mp['duplicados']}")

        st.caption("Execução em tempo real")
        r1 = st.columns(3)
        r2 = st.columns(3)
        ui = {
            'ok': r1[0].empty(), 'atualizados': r1[1].empty(), 'criados': r1[2].empty(),
            'erros': r2[0].empty(), 'taxa': r2[1].empty(), 'tempo': r2[2].empty(),
        }
        salvos = st.session_state.get("kpis") or {}
        for chave, rotulo in (('ok', "Já corretos"), ('atualizados', "Atualizados"), ('criados', "Criados"),
                              ('erros', "Erros / Ignorados"), ('taxa', "Taxa de sucesso"), ('tempo', "Tempo decorrido")):
            rot, val = salvos.get(chave, (rotulo, "—" if chave in ('taxa', 'tempo') else 0))
            ui[chave].metric(rot, val)

        pular_criticos = st.checkbox("Ignorar linhas com erro crítico (❌) na auditoria", value=True)
        simular = st.checkbox("🧪 Modo simulação (analisa e mostra o que faria, sem salvar nada no ZUQ)", value=True)

        stop_flag_path = os.path.join(tempfile.gettempdir(), "zuq_auto_stop.flag")

        btn_checkup_km = st.button(
            "🩺 Rodar Somente Pré-Análise 100% de Hodômetro (Sem Entradas)",
            help="Consulta o ZUQ em modo somente leitura para conferir se os KMs batem antes de fazer qualquer entrada",
            **STRETCH
        )

        col_b1, col_b2 = st.columns([3, 1])
        btn_iniciar = col_b1.button("🧪 Simular (Pré-Análise 100% + Conciliação)" if simular else "🚀 Iniciar (Pré-Análise 100% Hodômetro + Entrada Direta)", **STRETCH)
        btn_parar = col_b2.button("🛑 Parar", help="Interrompe o lote atual com segurança e salva o progresso parcial", **STRETCH)

        if btn_parar:
            try:
                with open(stop_flag_path, "w") as _f:
                    _f.write("stop")
                st.warning("⏳ Sinal de parada enviado! Aguardar conclusão do item atual...")
            except Exception:
                pass

        _res = st.session_state.get("resultado")
        if _res and not _res.get("parcial") and not btn_iniciar:
            progress_bar = st.progress(1.0, text="Concluído")
        else:
            progress_bar = st.progress(0, text="Aguardando disparo...")
        log_container = st.container(height=185, border=True)
        scroll_placeholder = st.empty()
        if not btn_iniciar and st.session_state.get("log_hist"):
            log_container.markdown("\n\n".join(msg for _, msg in st.session_state["log_hist"][-40:]))

        if btn_checkup_km:
            if df_para_processar is None or df_para_processar.empty:
                st.error("Faça o upload de um ficheiro PDF/TXT válido antes do checkup.")
            elif not senha_zuq:
                st.error("Informe a senha do ZUQ nas configurações acima.")
            else:
                st.session_state["log_hist"] = []
                log_chk = LogPersistente(log_container, st.session_state["log_hist"], scroll_placeholder=scroll_placeholder)
                df_chk = executar_checkup_km_zuq(
                    df_para_processar, url_zuq, usuario_zuq, senha_zuq, log_chk, progress_bar
                )
                st.session_state["checkup_km_df"] = df_chk

        if btn_iniciar:
            if os.path.exists(stop_flag_path):
                try:
                    os.remove(stop_flag_path)
                except Exception:
                    pass
            if df_para_processar is None or df_para_processar.empty:
                st.error("Faça o upload de um ficheiro PDF/TXT válido antes de iniciar.")
            elif not senha_zuq:
                st.error("Informe a senha do ZUQ nas configurações acima.")
            else:
                st.session_state["log_hist"] = []
                log = LogPersistente(log_container, st.session_state["log_hist"], scroll_placeholder=scroll_placeholder)
                df_resultado, tempo_total = lancar_no_zuq(
                    df_para_processar, url_zuq, usuario_zuq, senha_zuq,
                    fornecedor_zuq, log, progress_bar, ui, pular_criticos, simular,
                    stop_flag_path=stop_flag_path
                )
                interrompido = os.path.exists(stop_flag_path)
                if interrompido:
                    try:
                        os.remove(stop_flag_path)
                    except Exception:
                        pass
                st.session_state["resultado"] = {
                    "df": df_resultado, "tempo": tempo_total,
                    "simulacao": simular, "parcial": interrompido
                }

    df_chk_vis = st.session_state.get("checkup_km_df")
    if df_chk_vis is not None and not df_chk_vis.empty:
        st.divider()
        st.markdown("### 🩺 Checkup Prévio de KM (Ficheiro vs. ZUQ)")
        diag_s = df_chk_vis["Diagnóstico KM"].astype(str)
        qtd_ok_km = int(diag_s.str.startswith("✅").sum())
        qtd_div_km = int(diag_s.str.contains("⚠️|❌|🚨|✏️").sum())

        ck1, ck2, ck3 = st.columns(3)
        ck1.metric("Total verificado", len(df_chk_vis))
        ck2.metric("KMs que batem / coerentes", qtd_ok_km)
        ck3.metric("Divergências / Atenção", qtd_div_km)

        somente_div_km = st.checkbox("Mostrar apenas KMs com divergência ou atenção", value=False, key="chk_only_div")
        df_chk_show = df_chk_vis[~diag_s.str.startswith("✅")] if somente_div_km else df_chk_vis
        st.dataframe(df_chk_show, **STRETCH)

        csv_chk = df_chk_vis.to_csv(index=False, sep=';', encoding='utf-8-sig')
        st.download_button(
            label="📥 Baixar Checkup de KM (CSV)",
            data=csv_chk,
            file_name=f"checkup_km_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            **STRETCH
        )

    mostrar_resultado()

import os
import io
import re
import time
import hmac
from datetime import datetime

import pandas as pd
import pypdf
import streamlit as st
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
PRECO_MIN, PRECO_MAX = 3.0, 15.0      # faixa plausível de R$/L
LITROS_MAX = 600.0                    # volume atípico por abastecimento
TOL_TOTAL = 0.02                      # tolerância litros x preço vs total (2%)
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_SEGUNDOS = 60
STATUS_SUCESSO = ['Já correto', 'Atualizado', 'Criado Novo',
                  'Simulação: atualizaria', 'Simulação: criaria']
COLUNAS_BASE = ['data', 'hora', 'cupom', 'placa', 'produto',
                'quantidade', 'valor_unitario', 'valor_total', 'km']

XP_LITROS = "//label[contains(text(),'Litros')]/following::input[1]"
XP_KM = "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]"
XP_VEICULO = "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]"
XP_FORNECEDOR = "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]"
XP_DOC = "//label[contains(text(),'Documento fiscal')]/following::input[1]"
JS_SET = ("arguments[0].value = arguments[1];"
          "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
          "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));")

# Compatibilidade entre versões do Streamlit (use_container_width -> width="stretch")
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
        background: radial-gradient(circle at 0% 0%, rgba(10, 132, 255, 0.22) 0%, transparent 45%),
                    radial-gradient(circle at 100% 40%, rgba(191, 90, 242, 0.18) 0%, transparent 50%),
                    radial-gradient(circle at 50% 100%, rgba(48, 209, 88, 0.15) 0%, transparent 55%),
                    #0b0f19 !important;
        background-attachment: fixed !important;
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
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(28px) saturate(190%);
        -webkit-backdrop-filter: blur(28px) saturate(190%);
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 20px;
        margin-bottom: 1.8rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
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
        background: rgba(255, 255, 255, 0.06) !important;
        backdrop-filter: blur(28px) saturate(190%) !important;
        -webkit-backdrop-filter: blur(28px) saturate(190%) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 20px !important;
        padding: 16px 20px !important;
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25) !important;
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
        font-size: 1.5rem !important;
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
        height: 3.2rem !important;
        box-shadow: 0 8px 24px rgba(10, 132, 255, 0.4) !important;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    .stButton > button:hover {
        transform: scale(0.98) !important;
        box-shadow: 0 12px 28px rgba(10, 132, 255, 0.5) !important;
    }

    div[data-baseweb="input"] {
        background: rgba(255, 255, 255, 0.08) !important;
        backdrop-filter: blur(28px) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 14px !important;
        color: #FFFFFF !important;
    }

    div[data-baseweb="input"] input {
        color: #FFFFFF !important;
    }

    details {
        background: rgba(255, 255, 255, 0.05) !important;
        backdrop-filter: blur(28px) !important;
        border: 1px solid rgba(255, 255, 255, 0.14) !important;
        border-radius: 20px !important;
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
    """Lê de st.secrets, depois de variável de ambiente, depois padrão."""
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
def digitar_devagar(elemento, texto, atraso=0.05):
    for caractere in str(texto):
        elemento.send_keys(caractere)
        time.sleep(atraso)


def preencher_campo_angular(driver, elemento, valor):
    """Simula digitação real + TAB para o AngularJS atualizar o ng-model (blur)."""
    elemento.click()
    elemento.send_keys(Keys.CONTROL + "a")
    elemento.send_keys(Keys.BACKSPACE)
    digitar_devagar(elemento, str(valor), atraso=0.04)
    elemento.send_keys(Keys.TAB)


def limpa_numero(val_str):
    """Converte '1.234,56', '7,600', '7.600' ou 'R$ 7,60' em float."""
    if val_str is None:
        return 0.0
    s = re.sub(r'[^\d,\.]', '', str(val_str))
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        # O último separador é o decimal; o outro é milhar
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
    """Casa a data sem confundir 5/11/2026 com 15/11/2026."""
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
def extrair_dados_txt_ou_pdf(uploaded_file):
    registos = []
    lines = []

    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        nome_arquivo = uploaded_file.name.lower()

        if nome_arquivo.endswith('.pdf'):
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                texto_pag = page.extract_text()
                if texto_pag:
                    lines.extend(texto_pag.split('\n'))
        else:
            lines = file_bytes.decode('latin1', errors='ignore').split('\n')
    except Exception as e:
        st.error(f"❌ Erro ao ler o arquivo: {e}")
        return pd.DataFrame()

    if not lines:
        return pd.DataFrame()

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
                    produto_nome = "DIESEL B S10 ADITIVADO" if "DIESEL" in sub_line.upper() else sub_line.split()[0]

                    nums_validos = re.findall(r'\d+(?:\.\d{3})*,\d+', sub_line)
                    vlr_unit, quantidade, valor_total = "0,00", "0,00", "0,00"
                    if len(nums_validos) >= 3:
                        vlr_unit, quantidade, valor_total = nums_validos[0], nums_validos[1], nums_validos[2]
                    elif len(nums_validos) == 2:
                        vlr_unit, quantidade = nums_validos[0], nums_validos[1]
                    elif len(nums_validos) == 1:
                        vlr_unit = nums_validos[0]

                    # Extrai KM Atual da linha principal removendo texto do dependente (ex.: CARRO 26)
                    depois_placa = line[m_placa.end():]
                    depois_sem_dep = re.sub(r'\bCARRO\s+\d+\b', ' ', depois_placa, flags=re.IGNORECASE)

                    km = ""
                    # 1º Caso: KM >= 1.000 com ponto de milhar (ex.: 2.689106,13 ou 1.26987,39)
                    m_km_ponto = re.search(r'(?<!\d)(\d{1,3}(?:\.\d{3})+)', depois_sem_dep)
                    if m_km_ponto:
                        km = m_km_ponto.group(1).replace('.', '')
                    else:
                        # 2º Caso: KM < 1.000 sem ponto de milhar colado com Quant. (ex.: 629107,42 ou 86671,96)
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
                        'linha_bruta': line,
                    })
                    break
                j += 1
        i += 1

    df_ext = pd.DataFrame(registos)
    if not df_ext.empty:
        df_ext = df_ext.assign(
            _dt_ord=pd.to_datetime(df_ext['data'].astype(str).str.strip(), format='%d/%m/%Y', errors='coerce'),
            _hr_ord=df_ext['hora'].astype(str).str.strip()
        ).sort_values(by=["_dt_ord", "_hr_ord", "placa"], kind="stable").drop(columns=["_dt_ord", "_hr_ord"]).reset_index(drop=True)
    return auditar_e_validar_dados(df_ext)


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

    chave = df[['placa', 'data', 'hora', 'cupom', 'quantidade']].astype(str).agg('|'.join, axis=1)
    duplicado = chave.duplicated(keep='first')

    # KM menor que o abastecimento anterior da mesma placa
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

        alertas_col.append(" | ".join(alertas) if alertas else "✅ Prontos para conciliar")

    df['alertas_auditoria'] = alertas_col
    return df


def calcular_metricas_pre(df):
    """Métricas descritivas do arquivo carregado."""
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
    """Mensagens de validação/erro visíveis na tela (heurística)."""
    xp = ("//*[contains(@class,'alert-danger')] | "
          "//*[contains(@class,'has-error')]//*[contains(@class,'help-block')]")
    textos = []
    for el in driver.find_elements(By.XPATH, xp):
        try:
            t = el.text.strip()
            if el.is_displayed() and len(t) > 2:
                textos.append(t)
        except Exception:
            pass
    return textos


def salvar_formulario(driver, wait, log_container, exigir_sair_do_novo=False):
    """Clica em Salvar e confirma o resultado. Retorna (ok, nota)."""
    for xpath in ["//*[contains(@class,'btn') and contains(.,'Salvar')]", "//button[contains(.,'Salvar')]"]:
        try:
            btn = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            btn.click()
            time.sleep(1.2)

            sem_km = False
            erros_km = driver.find_elements(By.XPATH, "//*[contains(text(),'Odômetro Inválido') or contains(text(),'entra em conflito')]")
            if erros_km and erros_km[0].is_displayed():
                log_container.warning("⚠️ Conflito de Odômetro. Salvando sem KM...")
                campo_km = driver.find_element(By.XPATH, XP_KM)
                driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_km)
                time.sleep(0.5)
                btn.click()
                time.sleep(1.2)
                sem_km = True

            # Confirmação do salvamento
            if exigir_sair_do_novo:
                limite = time.time() + 5
                while "/fuel/new" in driver.current_url and time.time() < limite:
                    time.sleep(0.5)
                if "/fuel/new" in driver.current_url:
                    erros = erros_visiveis(driver)
                    detalhe = f": {' | '.join(erros)[:200]}" if erros else " (permaneceu na tela de novo registro)"
                    return False, "Formulário não foi salvo" + detalhe
            else:
                erros = erros_visiveis(driver)
                if erros:
                    return False, f"Rejeitado pelo ZUQ: {' | '.join(erros)[:200]}"

            return True, ("Salvo sem KM (conflito de odômetro)" if sem_km else "")
        except Exception:
            continue
    return False, "Botão Salvar não encontrado"


# ---------------------------------------------------------
# CONCILIAÇÃO E EDIÇÃO ATIVA NO ZUQ
# Retorna (acao, observacao, ultima_placa_filtrada)
# acao: OK | ATUALIZADO | CRIAR | ERRO | NAO_ENCONTRADA
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
                digitar_devagar(input_modal, placa, atraso=0.05)
                time.sleep(1.2)

                opcoes = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{placa}')]")
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
                # NÃO cria registro quando o filtro falha: evita duplicar abastecimento
                return "ERRO", "Erro ao filtrar placa", ""

        target_litros = limpa_numero(litros)
        target_preco = limpa_numero(preco)
        target_km = re.sub(r'\D', '', str(km)) if km else ""

        # --- Localiza candidatos pela data e pontua por litros/preço/KM ---
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

        divergencias = []
        if target_km and not k_ok:
            divergencias.append("KM")
        if target_preco > 0 and not p_ok:
            divergencias.append("preço")
        if target_litros > 0 and not l_ok:
            divergencias.append("litros")
        if tem_zerado:
            divergencias.append("campo zerado")

        if simular:
            log_container.warning(f"🧪 [SIMULAÇÃO] {placa} seria atualizado ({', '.join(divergencias)}).")
            return "SIM_ATUALIZAR", f"Simulação: atualizaria ({', '.join(divergencias)})", placa

        log_container.warning(f"✏️ Divergência detectada na placa {placa}. Editando no ZUQ...")
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

        ok_save, nota = salvar_formulario(driver, wait, log_container)
        if ok_save:
            log_container.success(f"✅ Preço/Litros/KM atualizados no ZUQ para {placa}!")
            # Saímos da lista: força novo filtro no próximo registro
            return "ATUALIZADO", "Preço e dados corrigidos no ZUQ" + (f" — {nota}" if nota else ""), ""
        return "ERRO", f"Falha ao salvar edição: {nota}", ""

    except Exception as e:
        fechar_alerta_se_existir(driver, log_container)
        return "ERRO", f"Erro na análise: {e}", ""


# ---------------------------------------------------------
# AUTOMAÇÃO DE LANÇAMENTO E EDIÇÃO ZUQ
# ---------------------------------------------------------
class LogPersistente:
    """Escreve no container e guarda o histórico para reexibir após reruns."""
    def __init__(self, container, historico):
        self.c, self.h = container, historico

    def _reg(self, nivel, msg):
        self.h.append((nivel, msg))
        del self.h[:-500]
        getattr(self.c, nivel)(msg)

    def info(self, m): self._reg("info", m)
    def warning(self, m): self._reg("warning", m)
    def error(self, m): self._reg("error", m)
    def success(self, m): self._reg("success", m)
    def write(self, m): self._reg("write", m)


def lancar_no_zuq(df, URL_ZUQ, USUARIO, SENHA, FORNECEDOR, log_container, progress_bar,
                  ui, pular_criticos=True, simular=False):
    # Ordena ANTES de copiar para manter os índices alinhados com o relatório
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
        # Guarda resultado parcial: se a página recarregar, nada se perde
        st.session_state["resultado"] = {"df": df_relatorio.copy(), "tempo": time.time() - t0,
                                         "parcial": True, "simulacao": simular}
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

        base_url = URL_ZUQ.rsplit('/secure', 1)[0] if '/secure' in URL_ZUQ else URL_ZUQ.rstrip('/')
        ultima_placa_filtrada = ""

        for idx, row in df.iterrows():
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

            log_container.write(f"📌 **[{idx + 1}/{total_registros}] Placa {placa_str}** | Data: {data_str} | Vol: {litros_str}L | Preço/L: R$ {preco_str} | KM: {km_str or 'N/A'}")
            fechar_alerta_se_existir(driver, log_container)

            if pular_criticos and "❌" in str(row.get('alertas_auditoria', '')):
                log_container.warning(f"⏭️ Ignorado por erro crítico de auditoria: {row['alertas_auditoria']}")
                registrar(idx, 'Ignorado', f"Auditoria: {row['alertas_auditoria']}", 'erros', t_ini)
                continue

            acao, obs, ultima_placa_filtrada = conciliar_ou_criar_registro(
                driver, wait, base_url, placa_str, data_str, km_str, litros_str, preco_str,
                ultima_placa_filtrada, log_container, simular
            )

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
                navegar_com_timeout_seguro(driver, f"{base_url}/secure/manager/maintenance/#/fuel/new", timeout=10, log_container=log_container)
                wait.until(EC.element_to_be_clickable((By.XPATH, XP_VEICULO)))

            try:
                executar_com_retry(abrir_formulario, max_tentativas=3, log_container=log_container)
            except Exception as e_nav:
                log_container.error(f"❌ Falha no formulário: {e_nav}")
                registrar(idx, 'Erro', f"Falha no formulário: {e_nav}", 'erros', t_ini)
                continue

            def selecionar_veiculo():
                wait.until(EC.element_to_be_clickable((By.XPATH, XP_VEICULO))).click()
                time.sleep(0.3)
                inp = driver.find_element(By.XPATH, XP_VEICULO + "//input")
                inp.send_keys(Keys.CONTROL + "a")
                inp.send_keys(Keys.BACKSPACE)
                digitar_devagar(inp, placa_str, atraso=0.05)
                time.sleep(1.0)
                opcoes = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown')]//div[contains(.,'{placa_str}')]")
                if not opcoes:
                    return False
                opcoes[0].click()
                time.sleep(0.4)
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

            # Seleciona o combustível no <select ng-model="fuel.payable.id">
            try:
                prod_str = str(row.get('produto', 'DIESEL')).strip().upper()
                # Ordem de prioridade exata conforme as opções do ZUQ: S-10 ADITIVADO / S-10 / DIESEL
                if "S10" in prod_str or "S-10" in prod_str:
                    prioridades = ["S-10 ADITIVADO", "S-10", "S10", "DIESEL"]
                elif "DIESEL" in prod_str:
                    prioridades = ["S-10", "S-10 ADITIVADO", "DIESEL"]
                else:
                    prioridades = [prod_str]

                sel_el = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//select[@ng-model='fuel.payable.id'] | //label[contains(.,'Combustível')]/following::select[1]")
                ))
                time.sleep(0.4)  # aguarda AngularJS carregar availableFuels após seleção do veículo

                # Quando o veículo já tem combustível bloqueado na configuração (ex: image_f8a561.png),
                # o <select> fica desabilitado (ng-disabled="... availableFuels.length < 2") e já vem preenchido!
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
                wait.until(EC.element_to_be_clickable((By.XPATH, XP_FORNECEDOR))).click()
                time.sleep(0.3)
                inp_f = driver.find_element(By.XPATH, XP_FORNECEDOR + "//input")
                digitar_devagar(inp_f, FORNECEDOR, atraso=0.05)
                time.sleep(1.0)
                inp_f.send_keys(Keys.ARROW_DOWN)
                inp_f.send_keys(Keys.ENTER)
                time.sleep(0.3)
            except Exception:
                pass

            try:
                set_js(driver, driver.find_element(By.XPATH, XP_DOC), cupom_str)
            except Exception:
                pass

            salvo, nota_save = False, ""
            try:
                salvo, nota_save = executar_com_retry(
                    lambda: salvar_formulario(driver, wait, log_container, exigir_sair_do_novo=True),
                    max_tentativas=3, log_container=log_container)
            except Exception as e_save:
                nota_save = f"Erro ao salvar: {e_save}"
                log_container.error(f"❌ Erro ao salvar {placa_str}: {e_save}")

            time.sleep(1.0)
            fechar_alerta_se_existir(driver, log_container)

            if salvo:
                registrar(idx, 'Criado Novo', 'Lançado com sucesso' + (f" — {nota_save}" if nota_save else ""), 'criados', t_ini)
            else:
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
# RELATÓRIO FINAL (persistente entre reruns)
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

    ok_mask = df_res['status_lancamento'].isin(STATUS_SUCESSO)
    sucesso = int(ok_mask.sum())
    total = int((df_res['status_lancamento'] != 'Pendente').sum())
    litros = df_res.loc[ok_mask, 'quantidade'].map(limpa_numero).sum()
    media = df_res.loc[df_res['segundos'] > 0, 'segundos'].mean()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Taxa de sucesso", f"{sucesso / total * 100:.0f}%" if total else "—")
    m2.metric("Tempo total", f"{tempo:.0f}s")
    m3.metric("Média / registro", f"{media:.1f}s" if pd.notna(media) else "—")
    m4.metric("Litros conciliados", f"{litros:,.0f}".replace(",", "."))

    st.dataframe(
        df_res[['placa', 'data', 'quantidade', 'valor_unitario', 'km',
                'status_lancamento', 'observacao', 'segundos']],
        **STRETCH
    )

    csv_data = df_res.to_csv(index=False, sep=';', encoding='utf-8-sig')
    st.download_button(
        label="📥 Baixar Relatório (CSV)",
        data=csv_data,
        file_name=f"{prefixo}_conciliacao_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        **STRETCH
    )


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

    st.markdown("<br>", unsafe_allow_html=True)
    col_upload, col_control = st.columns([1.1, 1], gap="large")

    with col_upload:
        st.markdown("### 📁 1. Ficheiro Liveposto")
        uploaded_file = st.file_uploader("Upload de relatório em PDF ou TXT", type=["pdf", "txt"], label_visibility="collapsed")

        if uploaded_file is not None:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.get("ultimo_arquivo_id") != file_id:
                st.session_state["dados_df"] = extrair_dados_txt_ou_pdf(uploaded_file)
                st.session_state["ultimo_arquivo_id"] = file_id
                st.session_state["resultado"] = None  # novo arquivo, limpa relatório antigo
                st.session_state["kpis"] = None
                st.session_state["log_hist"] = []
        else:
            st.session_state["dados_df"] = None
            st.session_state["ultimo_arquivo_id"] = None

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
                st.session_state["dados_final"] = auditar_e_validar_dados(df_editado)
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

        btn_iniciar = st.button("🧪 Simular Conciliação no ZUQ" if simular else "🚀 Iniciar Conciliação e Correção no ZUQ", **STRETCH)

        _res = st.session_state.get("resultado")
        if _res and not _res.get("parcial") and not btn_iniciar:
            progress_bar = st.progress(1.0, text="Concluído")
        else:
            progress_bar = st.progress(0, text="Aguardando disparo...")
        log_container = st.container(height=300, border=True)
        if not btn_iniciar:
            for nivel, msg in st.session_state.get("log_hist", []):
                getattr(log_container, nivel)(msg)

        if btn_iniciar:
            if df_para_processar is None or df_para_processar.empty:
                st.error("Faça o upload de um ficheiro PDF/TXT válido antes de iniciar.")
            elif not senha_zuq:
                st.error("Informe a senha do ZUQ nas configurações acima.")
            else:
                st.session_state["log_hist"] = []
                log = LogPersistente(log_container, st.session_state["log_hist"])
                df_resultado, tempo_total = lancar_no_zuq(
                    df_para_processar, url_zuq, usuario_zuq, senha_zuq,
                    fornecedor_zuq, log, progress_bar, ui, pular_criticos, simular
                )
                st.session_state["resultado"] = {"df": df_resultado, "tempo": tempo_total, "simulacao": simular}

    mostrar_resultado()

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
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_SEGUNDOS = 60
COLUNAS_BASE = [
    "data",
    "hora",
    "cupom",
    "placa",
    "produto",
    "quantidade",
    "valor_unitario",
    "valor_total",
    "km",
]

XP_LITROS = "//label[contains(text(),'Litros')]/following::input[1]"
XP_KM = "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]"
XP_VEICULO = "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]"
XP_FORNECEDOR = "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]"
XP_DOC = "//label[contains(text(),'Documento fiscal')]/following::input[1]"

try:
    _v = tuple(int(x) for x in st.__version__.split(".")[:2])
except Exception:
    _v = (0, 0)
STRETCH = {"width": "stretch"} if _v >= (1, 50) else {"use_container_width": True}

# ---------------------------------------------------------
# VISUAL E LOGIN
# ---------------------------------------------------------
st.set_page_config(
    page_title="ZUQ Auto",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&display=swap');
    html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, 'Plus Jakarta Sans', sans-serif !important; }
    .stApp { background: #0b0f19 !important; color: #FFFFFF !important; }
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.4rem !important; padding-bottom: 2rem !important; max-width: 1120px !important; }
    .top-bar {
        display: flex; align-items: center; justify-content: space-between;
        padding: 12px 18px; background: rgba(22, 28, 45, 0.85);
        border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px;
        margin-bottom: 1.2rem; font-size: 1.15rem; font-weight: 700;
    }
    div[data-testid="stMetric"] {
        background: rgba(24, 31, 48, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 12px !important; padding: 10px 14px !important;
    }
    div[data-testid="stMetricLabel"] { color: rgba(255, 255, 255, 0.6) !important; font-size: 0.72rem !important; text-transform: uppercase; }
    div[data-testid="stMetricValue"] { color: #FFFFFF !important; font-size: 1.35rem !important; font-weight: 800 !important; }
    .stButton > button {
        background: #0A84FF !important; color: #FFFFFF !important;
        font-weight: 700 !important; border: none !important;
        border-radius: 999px !important; height: 3rem !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)


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

    st.markdown('<div style="text-align:center; margin-top:5rem;"><h2>⚡ ZUQ Auto</h2></div>', unsafe_allow_html=True)
    if not senha_correta:
        st.error("🔒 APP_PASSWORD não configurada.")
        return False

    _, col2, _ = st.columns([1.2, 1, 1.2])
    with col2:
        restante = st.session_state["bloqueado_ate"] - time.time()
        if restante > 0:
            st.error(f"⏳ Aguarde {int(restante)}s.")
        else:
            with st.form("form_login"):
                senha_digitada = st.text_input("Senha", type="password", placeholder="Digite a senha")
                if st.form_submit_button("Entrar", **STRETCH):
                    if hmac.compare_digest(senha_digitada.encode(), senha_correta.encode()):
                        st.session_state["autenticado"] = True
                        st.session_state["tentativas"] = 0
                        st.rerun()
                    else:
                        st.session_state["tentativas"] += 1
                        if st.session_state["tentativas"] >= MAX_TENTATIVAS_LOGIN:
                            st.session_state["bloqueado_ate"] = time.time() + BLOQUEIO_SEGUNDOS
                            st.session_state["tentativas"] = 0
                        st.error("❌ Senha inválida.")
    return False


# ---------------------------------------------------------
# UTILITÁRIOS
# ---------------------------------------------------------
def limpa_numero(val_str):
    if val_str is None:
        return 0.0
    s = re.sub(r"[^\d,\.]", "", str(val_str))
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def set_angular_value(driver, elemento, valor):
    driver.execute_script(
        """
        const el = arguments[0];
        const val = String(arguments[1]);
        el.value = val;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        if (window.angular) {
            const scopeEl = angular.element(el);
            scopeEl.val(val);
            scopeEl.triggerHandler('input');
            scopeEl.triggerHandler('change');
            scopeEl.triggerHandler('blur');
        }
        """,
        elemento,
        valor,
    )


def preencher_campo_texto(driver, elemento, valor):
    elemento.click()
    elemento.send_keys(Keys.CONTROL + "a")
    elemento.send_keys(Keys.BACKSPACE)
    if str(valor) != "":
        elemento.send_keys(str(valor))
    set_angular_value(driver, elemento, valor)
    elemento.send_keys(Keys.TAB)


def data_no_texto(texto, data_str):
    partes = str(data_str).split("/")
    variantes = {str(data_str)}
    if len(partes) == 3:
        try:
            variantes.add(f"{int(partes[0])}/{int(partes[1])}/{partes[2]}")
        except ValueError:
            pass
    return any(re.search(r"(?<!\d)" + re.escape(v) + r"(?!\d)", texto) for v in variantes)


# ---------------------------------------------------------
# LEITURA DOS ARQUIVOS LIVEPOSTO
# ---------------------------------------------------------
def _ordenar_df(df):
    return (
        df.assign(
            _dt_ord=pd.to_datetime(df["data"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce"),
            _hr_ord=df["hora"].astype(str).str.strip(),
        )
        .sort_values(by=["placa", "_dt_ord", "_hr_ord"], kind="stable")
        .drop(columns=["_dt_ord", "_hr_ord"])
        .reset_index(drop=True)
    )


def extrair_dados_multiplos_arquivos(uploaded_files):
    if not uploaded_files:
        return pd.DataFrame()
    if not isinstance(uploaded_files, list):
        uploaded_files = [uploaded_files]

    frames = []
    for up_f in uploaded_files:
        df_item = _extrair_unico_arquivo(up_f)
        if df_item is not None and not df_item.empty:
            frames.append(df_item)

    if not frames:
        return pd.DataFrame()

    df_unificado = pd.concat(frames, ignore_index=True)
    return auditar_e_validar_dados(_ordenar_df(df_unificado))


def _extrair_unico_arquivo(uploaded_file):
    registos, lines = [], []
    nome_orig = getattr(uploaded_file, "name", "arquivo")

    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        if nome_orig.lower().endswith(".pdf"):
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                texto_pag = page.extract_text()
                if texto_pag:
                    lines.extend(texto_pag.splitlines())
        else:
            lines = file_bytes.decode("latin1", errors="ignore").splitlines()
    except Exception as e:
        st.error(f"❌ Erro ao ler {nome_orig}: {e}")
        return pd.DataFrame()

    if not lines:
        return pd.DataFrame()

    combustiveis_validos = ("DIESEL", "GASOLINA", "ETANOL", "ALCOOL", "ÁLCOOL")
    re_placa = r"([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})"

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "Total da Placa:" in line:
            i += 1
            continue

        m_placa = re.search(re_placa, line)
        m_data = re.search(r"(\d{2}/\d{2}/\d{2,4})", line)

        if m_placa and m_data:
            placa = re.sub(r"[^A-Z0-9]", "", m_placa.group(1).upper())
            dt_str = m_data.group(1)
            partes_dt = dt_str.split("/")
            if len(partes_dt[2]) == 2:
                dt_str = f"{partes_dt[0]}/{partes_dt[1]}/20{partes_dt[2]}"

            m_hora = re.search(r"(\d{1,2}:\d{2}:\d{2})", line)
            hora = m_hora.group(1) if m_hora else "08:00:00"

            antes_placa = line[: m_placa.start()]
            if m_hora:
                antes_placa = antes_placa[m_hora.end() :]
            elif m_data:
                antes_placa = antes_placa[m_data.end() :]
            cupons = re.findall(r"(?<!\d)(\d{5,7})(?!\d)", antes_placa)
            cupom = cupons[0] if cupons else "0"

            depois_placa = line[m_placa.end() :]
            depois_sem_dep = re.sub(r"\bCARRO\s+\d+\b", " ", depois_placa, flags=re.IGNORECASE)

            km = ""
            m_km_ponto = re.search(r"(?<!\d)(\d{1,3}(?:\.\d{3})+)", depois_sem_dep)
            if m_km_ponto:
                km = m_km_ponto.group(1).replace(".", "")

            j = i + 1
            while j < len(lines):
                sub_line = lines[j].strip()
                if "Total da Placa:" in sub_line or re.search(re_placa, sub_line):
                    break

                if any(comb in sub_line.upper() for comb in combustiveis_validos):
                    u_sub = sub_line.upper()
                    if "DIESEL" in u_sub:
                        produto_nome = (
                            "DIESEL B S10 ADITIVADO"
                            if ("ADITIV" in u_sub or "S10" in u_sub or "S-10" in u_sub)
                            else "DIESEL"
                        )
                    elif "GASOLINA" in u_sub:
                        produto_nome = "GASOLINA ADITIVADA" if "ADITIV" in u_sub else "GASOLINA COMUM"
                    elif "ETANOL" in u_sub or "ALCOOL" in u_sub or "ÁLCOOL" in u_sub:
                        produto_nome = "ETANOL"
                    else:
                        produto_nome = sub_line.split()[0]

                    nums_validos = re.findall(r"\d+(?:\.\d{3})*,\d+", sub_line)
                    vlr_unit, quantidade, valor_total = "0,00", "0,00", "0,00"
                    if len(nums_validos) >= 3:
                        vlr_unit, quantidade, valor_total = nums_validos[0], nums_validos[1], nums_validos[2]
                    elif len(nums_validos) == 2:
                        vlr_unit, quantidade = nums_validos[0], nums_validos[1]
                    elif len(nums_validos) == 1:
                        vlr_unit = nums_validos[0]

                    if not km:
                        m_colado = re.search(r"(?<!\d)(\d+,\d{2})\b", depois_sem_dep)
                        if m_colado:
                            bloco_antes_virgula = m_colado.group(1).split(",")[0]
                            qtd_num = limpa_numero(quantidade)
                            qtd_int = str(int(round(qtd_num))) if qtd_num > 0 else ""
                            if (
                                qtd_int
                                and len(bloco_antes_virgula) > len(qtd_int)
                                and bloco_antes_virgula.endswith(qtd_int)
                            ):
                                km = bloco_antes_virgula[: -len(qtd_int)]
                            elif len(bloco_antes_virgula) > 3:
                                km = (
                                    bloco_antes_virgula[:-2]
                                    if int(bloco_antes_virgula[-3:]) > 600
                                    else bloco_antes_virgula[:-3]
                                )

                    registos.append(
                        {
                            "data": dt_str,
                            "hora": hora,
                            "cupom": cupom,
                            "placa": placa,
                            "produto": produto_nome,
                            "quantidade": quantidade,
                            "valor_unitario": vlr_unit,
                            "valor_total": valor_total,
                            "km": km,
                        }
                    )
                    break
                j += 1
        i += 1

    return pd.DataFrame(registos)


def auditar_e_validar_dados(df):
    if df is None or df.empty:
        return df

    df = df.copy()
    for col in COLUNAS_BASE:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    datas = pd.to_datetime(df["data"].astype(str).str.strip(), format="%d/%m/%Y", errors="coerce")

    alertas_col = []
    for idx, row in df.iterrows():
        alertas = []
        if limpa_numero(row["km"]) == 0:
            alertas.append("⚠️ Sem KM")
        if limpa_numero(row["valor_unitario"]) == 0:
            alertas.append("❌ Preço 0")
        if limpa_numero(row["quantidade"]) == 0:
            alertas.append("❌ Litros 0")
        if pd.isna(datas.loc[idx]):
            alertas.append("❌ Data inválida")
        alertas_col.append(" | ".join(alertas) if alertas else "✅ OK")

    df["status"] = alertas_col
    return df


# ---------------------------------------------------------
# SELENIUM ZUQ
# ---------------------------------------------------------
def fechar_alerta_se_existir(driver):
    try:
        driver.switch_to.alert.accept()
        return True
    except Exception:
        return False


def limpar_sobreposicoes(driver):
    """Remove ou aguarda sumir backdrops/loaders que interceptam cliques no ZUQ."""
    try:
        driver.execute_script(
            """
            document.querySelectorAll('.modal-backdrop, .blockUI, .blockOverlay, .ngx-overlay').forEach(el => {
                if (el && el.parentNode) el.remove();
            });
            document.body.classList.remove('modal-open');
            document.body.style.overflow = 'auto';
            document.body.style.paddingRight = '0px';
            """
        )
    except Exception:
        pass


def clicar_seguro(driver, elemento):
    limpar_sobreposicoes(driver)
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elemento)
    except Exception:
        pass
    try:
        elemento.click()
    except Exception:
        limpar_sobreposicoes(driver)
        driver.execute_script("arguments[0].click();", elemento)


def navegar_rapido(driver, url, timeout=20):
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
    except TimeoutException:
        driver.execute_script("window.stop();")
    time.sleep(0.4)
    limpar_sobreposicoes(driver)


def executar_com_retry(func, max_tentativas=3, intervalo_base=1.0):
    excecoes = (WebDriverException, TimeoutException, NoSuchElementException, StaleElementReferenceException)
    for tentativa in range(1, max_tentativas + 1):
        try:
            return func()
        except excecoes as e:
            if tentativa == max_tentativas:
                raise e
            time.sleep(intervalo_base * tentativa)


def criar_driver():
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    for arg in (
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--blink-settings=imagesEnabled=false",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
    ):
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
    driver.set_page_load_timeout(20)
    return driver


def _filtrar_placa_modal(driver, wait, placa):
    """Abre modal de veículos, seleciona placa (com fallback de 1 caractere) e confirma."""
    limpar_sobreposicoes(driver)
    btn_all = wait.until(EC.presence_of_element_located((By.ID, "btn-allvehicles")))
    clicar_seguro(driver, btn_all)
    time.sleep(0.35)

    input_modal = wait.until(
        EC.visibility_of_element_located((By.XPATH, "//div[contains(@class,'selectize-input')]//input"))
    )

    select_filtro = driver.find_elements(By.XPATH, "//select[@ng-model='filter.type']")
    if select_filtro:
        try:
            Select(select_filtro[0]).select_by_visible_text("Placa")
            time.sleep(0.25)
        except Exception:
            pass

    for rem in driver.find_elements(By.XPATH, "//div[contains(@class,'selectize-input')]//a[contains(@class,'remove')]"):
        try:
            driver.execute_script("arguments[0].click();", rem)
            time.sleep(0.15)
        except Exception:
            pass

    driver.execute_script("arguments[0].focus();", input_modal)
    input_modal.send_keys(Keys.CONTROL + "a")
    input_modal.send_keys(Keys.BACKSPACE)
    input_modal.send_keys(placa)
    time.sleep(0.5)

    xp_opc = (
        f"//div[contains(@class,'selectize-dropdown') and not(contains(@style,'display: none'))]"
        f"//div[contains(@class,'option') and contains(.,'{placa}')]"
    )
    try:
        WebDriverWait(driver, 3.0).until(EC.visibility_of_element_located((By.XPATH, xp_opc)))
    except TimeoutException:
        pass
    opcoes = [el for el in driver.find_elements(By.XPATH, xp_opc) if el.is_displayed()]
    placa_real = placa

    if not opcoes and len(placa) == 7:
        sufixo = placa[-4:]
        driver.execute_script("arguments[0].focus();", input_modal)
        input_modal.send_keys(Keys.CONTROL + "a")
        input_modal.send_keys(Keys.BACKSPACE)
        input_modal.send_keys(sufixo)
        time.sleep(0.5)
        xp_suf = (
            f"//div[contains(@class,'selectize-dropdown') and not(contains(@style,'display: none'))]"
            f"//div[contains(@class,'option') and contains(.,'{sufixo}')]"
        )
        try:
            WebDriverWait(driver, 2.5).until(EC.visibility_of_element_located((By.XPATH, xp_suf)))
        except TimeoutException:
            pass
        cands = []
        for el_op in driver.find_elements(By.XPATH, xp_suf):
            if not el_op.is_displayed():
                continue
            m_p = re.search(r"([A-Z]{3}[0-9][A-Z0-9][0-9]{2})", el_op.text.upper().replace("-", ""))
            if m_p and len(m_p.group(1)) == 7 and sum(a != b for a, b in zip(placa, m_p.group(1))) == 1:
                cands.append((m_p.group(1), el_op))
        distintas = {p for p, _ in cands}
        if len(distintas) == 1:
            placa_real = next(iter(distintas))
            opcoes = [el for p, el in cands if p == placa_real]

    if not opcoes:
        for xp_cancel in ("//button[contains(.,'Cancelar')]", "//button[@class='close']"):
            btns = driver.find_elements(By.XPATH, xp_cancel)
            if btns:
                try:
                    driver.execute_script("arguments[0].click();", btns[0])
                    break
                except Exception:
                    pass
        fechar_alerta_se_existir(driver)
        limpar_sobreposicoes(driver)
        return None

    clicar_seguro(driver, opcoes[0])
    time.sleep(0.25)

    try:
        driver.find_element(By.XPATH, "//h5[contains(.,'Filtrar os veículos')]").click()
    except Exception:
        try:
            input_modal.send_keys(Keys.ESCAPE)
        except Exception:
            pass
    time.sleep(0.2)

    btn_conf = wait.until(
        EC.presence_of_element_located((By.XPATH, "//button[contains(@class,'btn-primary') and contains(.,'Confirmar')]"))
    )
    clicar_seguro(driver, btn_conf)
    time.sleep(0.75)
    fechar_alerta_se_existir(driver)
    limpar_sobreposicoes(driver)
    return placa_real


def _limpar_campo_km_angular(driver):
    campo_km = driver.find_element(By.XPATH, XP_KM)
    campo_km.click()
    campo_km.send_keys(Keys.CONTROL + "a")
    campo_km.send_keys(Keys.BACKSPACE)
    set_angular_value(driver, campo_km, "")


def _aguardar_resposta_save(driver, sair_do_novo=False, timeout=3.0):
    limite = time.time() + timeout
    while time.time() < limite:
        if sair_do_novo and "/fuel/new" not in driver.current_url:
            return
        if not sair_do_novo and "/edit" not in driver.current_url:
            return
        erros_km = driver.find_elements(
            By.XPATH, "//*[contains(text(),'Odômetro Inválido') or contains(text(),'entra em conflito')]"
        )
        if any(el.is_displayed() for el in erros_km):
            return
        time.sleep(0.12)


def salvar_formulario(driver, wait, log_container, exigir_sair_do_novo=False):
    """Retorna (salvou, km_removido)."""
    for xpath in ["//*[contains(@class,'btn') and contains(.,'Salvar')]", "//button[contains(.,'Salvar')]"]:
        try:
            btn = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            clicar_seguro(driver, btn)
            _aguardar_resposta_save(driver, sair_do_novo=exigir_sair_do_novo, timeout=3.0)

            km_removido = False
            erros_km = driver.find_elements(
                By.XPATH, "//*[contains(text(),'Odômetro Inválido') or contains(text(),'entra em conflito')]"
            )
            if any(el.is_displayed() for el in erros_km):
                log_container.warning("⚠️ Conflito de KM no ZUQ — salvando sem KM...")
                _limpar_campo_km_angular(driver)
                km_removido = True
                btn = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                clicar_seguro(driver, btn)
                _aguardar_resposta_save(driver, sair_do_novo=exigir_sair_do_novo, timeout=3.0)

            if exigir_sair_do_novo and "/fuel/new" in driver.current_url:
                return False, km_removido
            return True, km_removido
        except Exception:
            continue
    return False, False


# ---------------------------------------------------------
# CONCILIAÇÃO E ENTRADA POR VEÍCULO
# ---------------------------------------------------------
def conciliar_ou_criar_registro(
    driver, wait, base_url, placa, data, km, litros, preco, ultima_placa_filtrada, log_container
):
    for tentativa in range(2):
        try:
            url_atual = driver.current_url.rstrip("/")
            precisa_filtrar = (placa != ultima_placa_filtrada) or (not url_atual.endswith("#/fuel")) or (tentativa > 0)

            if precisa_filtrar:
                navegar_rapido(driver, f"{base_url}/secure/manager/maintenance/#/fuel", timeout=20)
                wait.until(EC.presence_of_element_located((By.ID, "btn-allvehicles")))
                placa_real = _filtrar_placa_modal(driver, wait, placa)
                if not placa_real:
                    log_container.warning(f"🚨 Placa {placa} não encontrada no ZUQ.")
                    return "NAO_ENCONTRADA", ""
                placa = placa_real

            target_litros = limpa_numero(litros)
            target_preco = limpa_numero(preco)
            target_km = re.sub(r"\D", "", str(km)) if km else ""

            candidatos = []
            for linha in driver.find_elements(By.XPATH, "//tr[contains(@ng-repeat,'fuel')]"):
                texto = linha.text
                if not texto or not data_no_texto(texto, data):
                    continue
                tds = linha.find_elements(By.TAG_NAME, "td")
                nums = [limpa_numero(td.text) for td in tds if limpa_numero(td.text) > 0]
                l_ok = target_litros > 0 and any(abs(n - target_litros) < 0.1 for n in nums)
                p_ok = target_preco > 0 and any(abs(n - target_preco) < 0.05 for n in nums)
                k_ok = bool(target_km) and any(re.sub(r"\D", "", td.text) == target_km for td in tds)
                candidatos.append((int(l_ok) + int(p_ok) + int(k_ok), linha, l_ok, p_ok, k_ok))

            candidatos.sort(key=lambda c: c[0], reverse=True)
            if not candidatos or candidatos[0][0] == 0:
                return "CRIAR", placa

            melhor_score, linha_encontrada, l_ok, p_ok, k_ok = candidatos[0]
            if melhor_score == 1 and len(candidatos) > 1:
                log_container.warning(f"⚠️ Ambíguo em {placa} ({data}) — pulando para conferência manual.")
                return "ERRO", placa

            tds_texto = [td.text.strip() for td in linha_encontrada.find_elements(By.TAG_NAME, "td")]
            tem_zerado = any(t in ("0,00", "0.00") for t in tds_texto)
            precisa_editar = (
                (target_km and not k_ok)
                or (target_preco > 0 and not p_ok)
                or (target_litros > 0 and not l_ok)
                or tem_zerado
            )

            if not precisa_editar:
                log_container.info(f"✅ {placa} ({data}) já lançado e correto.")
                return "OK", placa

            try:
                link = linha_encontrada.find_element(By.XPATH, ".//a[contains(@href,'/fuel/')]")
                navegar_rapido(driver, link.get_attribute("href"), timeout=20)
            except Exception:
                clicar_seguro(driver, linha_encontrada)

            btn_edit = wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//a[contains(@class,'btn') and .//i[contains(@class,'icon-pencil') or contains(@class,'fa-pencil')]]",
                    )
                )
            )
            clicar_seguro(driver, btn_edit)
            wait.until(EC.presence_of_element_located((By.NAME, "price")))

            if target_preco > 0:
                try:
                    preencher_campo_texto(driver, driver.find_element(By.NAME, "price"), preco)
                except Exception:
                    pass
            if target_litros > 0:
                try:
                    preencher_campo_texto(driver, driver.find_element(By.XPATH, XP_LITROS), litros)
                except Exception:
                    pass
            if km and km != "0":
                try:
                    preencher_campo_texto(driver, driver.find_element(By.XPATH, XP_KM), km)
                except Exception:
                    pass

            salvou, km_removido = salvar_formulario(driver, wait, log_container)
            if salvou and km_removido:
                log_container.warning(f"⚠️ {placa} ({data}) atualizado sem KM (ZUQ rejeitou o KM {km}).")
                return "ATUALIZADO_SEM_KM", ""
            if salvou:
                log_container.success(f"✏️ {placa} ({data}) atualizado!")
                return "ATUALIZADO", ""
            return "ERRO", ""

        except Exception as e:
            fechar_alerta_se_existir(driver)
            limpar_sobreposicoes(driver)
            if tentativa == 0:
                time.sleep(0.5)
                continue
            msg_curta = str(e).splitlines()[0] if str(e) else type(e).__name__
            log_container.error(f"❌ Erro ao conciliar {placa} ({data}) [{type(e).__name__}]: {msg_curta}")
            return "ERRO", ""


class LogSimples:
    def __init__(self, container, historico):
        self._ph = container.empty()
        self.h = historico
        self._linhas = []

    def _add(self, msg):
        self._linhas.append(msg)
        self.h[:] = self._linhas[-30:]
        self._ph.markdown("\n".join(self.h))

    def info(self, m):
        self._add(m)

    def warning(self, m):
        self._add(m)

    def error(self, m):
        self._add(m)

    def success(self, m):
        self._add(m)


def lancar_no_zuq(df, URL_ZUQ, USUARIO, SENHA, FORNECEDOR, log_container, progress_bar, ui, stop_flag_path=None):
    df = _ordenar_df(df)
    contadores = dict(ok=0, atualizados=0, criados=0, erros=0)
    total = len(df)
    t0 = time.time()

    def atualizar_kpis():
        ui["ok"].metric("Já corretos", contadores["ok"])
        ui["atualizados"].metric("Atualizados", contadores["atualizados"])
        ui["criados"].metric("Criados", contadores["criados"])
        ui["erros"].metric("Erros", contadores["erros"])
        st.session_state["kpis_simples"] = contadores.copy()

    atualizar_kpis()
    driver = criar_driver()
    wait = WebDriverWait(driver, 20)

    try:
        log_container.info("🌐 Conectando ao ZUQ...")

        def acao_login():
            navegar_rapido(driver, URL_ZUQ, timeout=20)
            campo_usuario = wait.until(EC.element_to_be_clickable((By.ID, "j_username")))
            campo_usuario.clear()
            campo_usuario.send_keys(USUARIO)
            try:
                campo_senha = driver.find_element(By.NAME, "password")
            except NoSuchElementException:
                campo_senha = driver.find_element(By.XPATH, "//input[@type='password']")
            campo_senha.clear()
            campo_senha.send_keys(SENHA)
            try:
                driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]").click()
            except NoSuchElementException:
                campo_senha.send_keys(Keys.ENTER)
            WebDriverWait(driver, 15).until(lambda d: "login" not in d.current_url.lower())

        executar_com_retry(acao_login, max_tentativas=3)

        base_url = URL_ZUQ.rsplit("/secure", 1)[0] if "/secure" in URL_ZUQ else URL_ZUQ.rstrip("/")
        navegar_rapido(driver, f"{base_url}/secure/manager/maintenance/#/fuel", timeout=20)
        wait.until(EC.presence_of_element_located((By.ID, "btn-allvehicles")))

        placas_inexistentes = set()
        placas_mapeadas = {}
        ultima_placa_filtrada = ""

        for idx, row in df.iterrows():
            if stop_flag_path and os.path.exists(stop_flag_path):
                log_container.warning("🛑 Parado pelo usuário.")
                break

            eta = ((time.time() - t0) / idx * (total - idx)) if idx > 0 else 0
            progress_bar.progress((idx + 1) / total, text=f"{idx + 1}/{total} · ~{int(eta)}s restantes")

            placa_str = re.sub(r"[^A-Z0-9]", "", str(row["placa"]).upper())
            km_str = re.sub(r"\D", "", str(row["km"])) if pd.notna(row["km"]) else ""
            cupom_str = str(row["cupom"]).strip() if pd.notna(row.get("cupom")) and str(row.get("cupom")).strip() else "0"
            hora_str = str(row["hora"]).strip() if pd.notna(row.get("hora")) and str(row.get("hora")).strip() else "08:00:00"
            data_str = str(row["data"]).strip()
            litros_str = str(row["quantidade"]).strip()
            preco_str = str(row["valor_unitario"]).strip()

            if not placa_str or not data_str or "❌" in str(row.get("status", "")) or placa_str in placas_inexistentes:
                log_container.warning(f"⏭️ Pulando {placa_str or '?'} ({data_str or '?'}) por status/placa inválida.")
                contadores["erros"] += 1
                atualizar_kpis()
                continue

            placa_orig = placa_str
            if placa_str in placas_mapeadas:
                placa_str = placas_mapeadas[placa_str]

            acao, ultima_placa_filtrada = conciliar_ou_criar_registro(
                driver,
                wait,
                base_url,
                placa_str,
                data_str,
                km_str,
                litros_str,
                preco_str,
                ultima_placa_filtrada,
                log_container,
            )

            if acao == "NAO_ENCONTRADA":
                placas_inexistentes.add(placa_orig)
                contadores["erros"] += 1
                atualizar_kpis()
                continue
            if ultima_placa_filtrada and ultima_placa_filtrada != placa_orig:
                placas_mapeadas[placa_orig] = ultima_placa_filtrada
                placa_str = ultima_placa_filtrada

            if acao == "OK":
                contadores["ok"] += 1
                atualizar_kpis()
                continue
            if acao in ("ATUALIZADO", "ATUALIZADO_SEM_KM"):
                contadores["atualizados"] += 1
                atualizar_kpis()
                continue
            if acao == "ERRO":
                contadores["erros"] += 1
                atualizar_kpis()
                continue

            # CRIAR NOVO ABASTECIMENTO
            ultima_placa_filtrada = ""
            try:
                navegar_rapido(driver, f"{base_url}/secure/manager/maintenance/#/fuel/new", timeout=20)
                el_veic = wait.until(EC.presence_of_element_located((By.XPATH, XP_VEICULO)))
                clicar_seguro(driver, el_veic)
                time.sleep(0.25)
                inp = driver.find_element(By.XPATH, XP_VEICULO + "//input")
                inp.send_keys(Keys.CONTROL + "a")
                inp.send_keys(Keys.BACKSPACE)
                inp.send_keys(placa_str)
                time.sleep(0.45)

                xp_opc_v = (
                    f"//div[contains(@class,'selectize-dropdown') and not(contains(@style,'display: none'))]"
                    f"//div[contains(@class,'option') and contains(.,'{placa_str}')]"
                )
                WebDriverWait(driver, 3.0).until(EC.presence_of_element_located((By.XPATH, xp_opc_v)))
                opcoes_v = [el for el in driver.find_elements(By.XPATH, xp_opc_v) if el.is_displayed()]
                if not opcoes_v:
                    raise RuntimeError(f"Veículo {placa_str} não apareceu no dropdown")
                clicar_seguro(driver, opcoes_v[0])
                time.sleep(0.25)

                data_iso = datetime.strptime(data_str, "%d/%m/%Y").strftime("%Y-%m-%d")
                set_angular_value(driver, driver.find_element(By.ID, "fuelDate"), data_iso)
                time.sleep(0.15)

                campo_hora = driver.find_element(By.ID, "additionTime")
                preencher_campo_texto(driver, campo_hora, hora_str[:5])
                time.sleep(0.15)

                preencher_campo_texto(driver, driver.find_element(By.XPATH, XP_LITROS), litros_str)
                time.sleep(0.15)
                preencher_campo_texto(driver, driver.find_element(By.NAME, "price"), preco_str)
                time.sleep(0.15)

                if km_str and km_str != "0":
                    preencher_campo_texto(driver, driver.find_element(By.XPATH, XP_KM), km_str)
                    time.sleep(0.15)

                # Combustível
                prod_str = str(row.get("produto", "DIESEL")).strip().upper()
                if "S10" in prod_str or "S-10" in prod_str:
                    prioridades = ["S-10 ADITIVADO", "S-10", "S10", "DIESEL"]
                elif "DIESEL" in prod_str:
                    prioridades = ["S-10", "S-10 ADITIVADO", "DIESEL"]
                elif "GASOLINA" in prod_str and "ADITIV" in prod_str:
                    prioridades = ["GASOLINA ADITIVADA", "GASOLINA COMUM", "GASOLINA"]
                elif "GASOLINA" in prod_str:
                    prioridades = ["GASOLINA COMUM", "GASOLINA", "GASOLINA ADITIVADA"]
                else:
                    prioridades = ["ETANOL", "ÁLCOOL", prod_str]

                sel_el = wait.until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//select[@ng-model='fuel.payable.id'] | //label[contains(.,'Combustível')]/following::select[1]",
                        )
                    )
                )
                if sel_el.get_attribute("disabled") is None and sel_el.is_enabled():
                    sel_obj = Select(sel_el)
                    val_atual = sel_el.get_attribute("value") or ""
                    if not val_atual or "?" in val_atual:
                        escolhido = None
                        for alvo in prioridades:
                            for opt in sel_obj.options:
                                if alvo in opt.text.strip().upper():
                                    escolhido = opt.text
                                    break
                            if escolhido:
                                break
                        if not escolhido:
                            for opt in sel_obj.options:
                                v_o = opt.get_attribute("value") or ""
                                if v_o and "?" not in v_o and opt.text.strip():
                                    escolhido = opt.text
                                    break
                        if escolhido:
                            sel_obj.select_by_visible_text(escolhido)
                            set_angular_value(driver, sel_el, sel_el.get_attribute("value") or "")
                            time.sleep(0.2)

                # Fornecedor
                if FORNECEDOR.strip():
                    el_forn = wait.until(EC.presence_of_element_located((By.XPATH, XP_FORNECEDOR)))
                    clicar_seguro(driver, el_forn)
                    time.sleep(0.25)
                    inp_f = el_forn.find_element(By.XPATH, ".//input")
                    inp_f.send_keys(Keys.CONTROL + "a")
                    inp_f.send_keys(Keys.BACKSPACE)
                    inp_f.send_keys(FORNECEDOR)
                    time.sleep(0.45)
                    xp_opc_forn = (
                        "//div[contains(@class,'selectize-dropdown') and not(contains(@style,'display: none'))]"
                        "//div[contains(@class,'option')]"
                    )
                    try:
                        WebDriverWait(driver, 2.5).until(EC.presence_of_element_located((By.XPATH, xp_opc_forn)))
                    except TimeoutException:
                        pass
                    opcoes_f = [el for el in driver.find_elements(By.XPATH, xp_opc_forn) if el.is_displayed()]
                    if opcoes_f:
                        clicar_seguro(driver, opcoes_f[0])
                    else:
                        inp_f.send_keys(Keys.ENTER)
                    time.sleep(0.25)

                preencher_campo_texto(driver, driver.find_element(By.XPATH, XP_DOC), cupom_str)
                time.sleep(0.15)

                salvou, km_removido = salvar_formulario(driver, wait, log_container, exigir_sair_do_novo=True)
                if salvou and km_removido:
                    log_container.warning(f"⚠️ {placa_str} ({data_str}) lançado sem KM (ZUQ rejeitou o KM).")
                    contadores["criados"] += 1
                elif salvou:
                    log_container.success(f"➕ {placa_str} ({data_str}) lançado!")
                    contadores["criados"] += 1
                else:
                    log_container.error(f"❌ Falha ao salvar {placa_str} ({data_str}).")
                    contadores["erros"] += 1
            except Exception as e_c:
                limpar_sobreposicoes(driver)
                msg_curta = str(e_c).splitlines()[0] if str(e_c) else type(e_c).__name__
                log_container.error(f"❌ Erro ao lançar {placa_str} ({data_str}) [{type(e_c).__name__}]: {msg_curta}")
                contadores["erros"] += 1

            atualizar_kpis()
            fechar_alerta_se_existir(driver)

        progress_bar.progress(1.0, text=f"Concluído em {time.time() - t0:.0f}s!")
        log_container.success(f"🎉 Finalizado em {time.time() - t0:.0f} segundos!")
    except Exception as e:
        msg_curta = str(e).splitlines()[0] if str(e) else type(e).__name__
        log_container.error(f"❌ Erro geral [{type(e).__name__}]: {msg_curta}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if stop_flag_path and os.path.exists(stop_flag_path):
            try:
                os.remove(stop_flag_path)
            except Exception:
                pass


# ---------------------------------------------------------
# TELA PRINCIPAL
# ---------------------------------------------------------
if verificar_senha():
    st.markdown('<div class="top-bar">⚡ ZUQ Auto</div>', unsafe_allow_html=True)

    with st.expander("⚙️ Login ZUQ e Posto", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        usuario_zuq = c1.text_input("Usuário", value=_segredo("ZUQ_USER", "manutencaoverdesmares"))
        senha_zuq = c2.text_input("Senha", type="password", value=_segredo("ZUQ_PASSWORD", ""))
        url_zuq = c3.text_input("URL", value=_segredo("ZUQ_URL", "https://app.zuq.com.br"))
        fornecedor_zuq = c4.text_input("Fornecedor", value=_segredo("ZUQ_FORNECEDOR", "POSTO GURI - MACEIÓ"))

    col_esq, col_dir = st.columns([1.15, 1], gap="large")
    df_editado = None

    with col_esq:
        st.markdown("#### 1. Envie os PDFs / TXT")
        uploaded_files = st.file_uploader(
            "PDF ou TXT", type=["pdf", "txt"], accept_multiple_files=True, label_visibility="collapsed"
        )

        if uploaded_files:
            file_id = "|".join(sorted(f"{f.name}_{f.size}" for f in uploaded_files))
            if st.session_state.get("ultimo_arquivo_id") != file_id:
                df_extraido = extrair_dados_multiplos_arquivos(uploaded_files)
                st.session_state["dados_df"] = df_extraido
                st.session_state["dados_final"] = df_extraido
                st.session_state["ultimo_arquivo_id"] = file_id
                st.session_state["kpis_simples"] = None
                st.session_state["log_simples"] = []

        if st.session_state.get("dados_df") is not None and not st.session_state["dados_df"].empty:
            with st.form("form_tabela", border=False):
                df_editado = st.data_editor(
                    st.session_state["dados_df"],
                    column_order=["placa", "data", "quantidade", "valor_unitario", "km", "status"],
                    column_config={
                        "placa": st.column_config.TextColumn("Placa"),
                        "data": st.column_config.TextColumn("Data"),
                        "quantidade": st.column_config.TextColumn("Litros"),
                        "valor_unitario": st.column_config.TextColumn("Preço/L"),
                        "km": st.column_config.TextColumn("KM"),
                        "status": st.column_config.TextColumn("Status", disabled=True),
                    },
                    num_rows="dynamic",
                    height=330,
                    **STRETCH,
                )
                if st.form_submit_button("✅ Atualizar tabela", **STRETCH):
                    df_validado = auditar_e_validar_dados(df_editado)
                    st.session_state["dados_df"] = df_validado
                    st.session_state["dados_final"] = df_validado
                    st.rerun()

    with col_dir:
        st.markdown("#### 2. Dar entrada no ZUQ")

        k1, k2, k3, k4 = st.columns(4)
        ui = {"ok": k1.empty(), "atualizados": k2.empty(), "criados": k3.empty(), "erros": k4.empty()}
        ks = st.session_state.get("kpis_simples") or {"ok": 0, "atualizados": 0, "criados": 0, "erros": 0}
        ui["ok"].metric("Já corretos", ks["ok"])
        ui["atualizados"].metric("Atualizados", ks["atualizados"])
        ui["criados"].metric("Criados", ks["criados"])
        ui["erros"].metric("Erros", ks["erros"])

        stop_flag_path = os.path.join(tempfile.gettempdir(), "zuq_auto_stop.flag")

        b1, b2 = st.columns([3, 1])
        btn_iniciar = b1.button("🚀 Lançar abastecimentos", **STRETCH)
        btn_parar = b2.button("🛑 Parar", **STRETCH)

        if btn_parar:
            try:
                with open(stop_flag_path, "w") as _f:
                    _f.write("stop")
                st.warning("Parando...")
            except Exception:
                pass

        progress_bar = st.progress(0, text="Pronto para iniciar")
        log_box = st.container(height=230, border=True)
        if not btn_iniciar and st.session_state.get("log_simples"):
            log_box.markdown("\n".join(st.session_state["log_simples"]))

        if btn_iniciar:
            if os.path.exists(stop_flag_path):
                try:
                    os.remove(stop_flag_path)
                except Exception:
                    pass

            df_proc = df_editado if df_editado is not None else st.session_state.get("dados_final")
            if df_proc is not None and not df_proc.empty:
                df_proc = auditar_e_validar_dados(df_proc)
                st.session_state["dados_final"] = df_proc

            if df_proc is None or df_proc.empty:
                st.error("Envie um PDF ou TXT primeiro.")
            elif not senha_zuq:
                st.error("Preencha a senha do ZUQ em 'Login ZUQ e Posto'.")
            else:
                st.session_state["log_simples"] = []
                log_s = LogSimples(log_box, st.session_state["log_simples"])
                lancar_no_zuq(
                    df_proc,
                    url_zuq,
                    usuario_zuq,
                    senha_zuq,
                    fornecedor_zuq,
                    log_s,
                    progress_bar,
                    ui,
                    stop_flag_path,
                )

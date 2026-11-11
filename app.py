import os
import re
import time
import traceback
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
    StaleElementReferenceException
)

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
        font-size: 1.7rem !important;
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
# AUTENTICAÇÃO
# ---------------------------------------------------------
def verificar_senha():
    SENHA_CORRETA = st.secrets.get("APP_PASSWORD", "zuq123")

    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if st.session_state["autenticado"]:
        return True

    st.markdown('<div style="text-align: center; margin-top: 5rem;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 2.2rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.6px;">⚡ ZUQ Auto</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 0.95rem; color: rgba(255,255,255,0.65); margin-bottom: 2rem;">Acesso restrito. Digite a senha corporativa para continuar.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1.2, 1, 1.2])
    with col2:
        with st.form("form_login"):
            senha_digitada = st.text_input("Senha de Acesso", type="password", placeholder="Digite a senha")
            btn_login = st.form_submit_button("Entrar", use_container_width=True)

            if btn_login:
                if senha_digitada == SENHA_CORRETA:
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("❌ Credencial inválida.")
    st.markdown('</div>', unsafe_allow_html=True)
                    
    return False

# ---------------------------------------------------------
# PARSER DE PDF / TXT LIVEPOSTO
# ---------------------------------------------------------
def digitar_devagar(elemento, texto, atraso=0.05):
    for caractere in str(texto):
        elemento.send_keys(caractere)
        time.sleep(atraso)

def limpa_numero(val_str):
    if not val_str:
        return 0.0
    s = re.sub(r'[^\d,\.]', '', str(val_str)).replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

def extrair_dados_txt_ou_pdf(caminho_ou_stream):
    registos = []
    lines = []

    if hasattr(caminho_ou_stream, 'name') and caminho_ou_stream.name.lower().endswith('.pdf'):
        try:
            reader = pypdf.PdfReader(caminho_ou_stream)
            for page in reader.pages:
                lines.extend(page.extract_text().split('\n'))
        except Exception:
            pass
    elif hasattr(caminho_ou_stream, 'read'):
        caminho_ou_stream.seek(0)
        lines = [l.decode('latin1', errors='ignore') for l in caminho_ou_stream.readlines()]
    elif isinstance(caminho_ou_stream, str) and os.path.exists(caminho_ou_stream):
        if caminho_ou_stream.lower().endswith('.pdf'):
            reader = pypdf.PdfReader(caminho_ou_stream)
            for page in reader.pages:
                lines.extend(page.extract_text().split('\n'))
        else:
            with open(caminho_ou_stream, 'r', encoding='latin1', errors='ignore') as f:
                lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        m_placa = re.search(r'([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})', line)
        m_data = re.search(r'(\d{2}/\d{2}/\d{2,4})', line)

        if m_placa and m_data:
            placa = m_placa.group(1).replace('-', '')
            dt_str = m_data.group(1)

            partes_dt = dt_str.split('/')
            if len(partes_dt[2]) == 2:
                dt_str = f"{partes_dt[0]}/{partes_dt[1]}/20{partes_dt[2]}"

            m_cupom = re.search(r'\b(\d{5,7})\b', line)
            cupom = m_cupom.group(1) if m_cupom else "0"

            m_hora = re.search(r'(\d{1,2}:\d{2}:\d{2})', line)
            hora = m_hora.group(1) if m_hora else "08:00:00"

            km = ""
            m_km_ponto = re.search(r'(\d{2,3}\.\d{3})', line)
            if m_km_ponto:
                km = m_km_ponto.group(1).replace('.', '')
            else:
                nums_linha = re.findall(r'\b(\d{5,6})\b', line)
                nums_filtrados = [n for n in nums_linha if n != cupom]
                if nums_filtrados:
                    km = nums_filtrados[0]

            j = i + 1
            while j < len(lines):
                sub_line = lines[j].strip()
                
                if "Total da Placa:" in sub_line or (j > i + 1 and re.search(r'([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})', sub_line)):
                    break

                if "DIESEL" in sub_line.upper():
                    produto_nome = "DIESEL B S10 ADITIVADO"
                    
                    busca_linha = sub_line
                    if j + 1 < len(lines):
                        busca_linha += " " + lines[j+1].strip()

                    numeros = re.findall(r'(\d+(?:[\.,]\d+)?)', busca_linha)
                    nums_validos = [n for n in numeros if ',' in n or '.' in n]

                    if nums_validos:
                        vlr_unit = "7,600"
                        quantidade = "0,00"
                        valor_total = "0,00"

                        for num in nums_validos:
                            val_float = limpa_numero(num)
                            if 5.0 <= val_float <= 10.0 and vlr_unit == "7,600":
                                vlr_unit = num
                            elif val_float > 15.0 and quantidade == "0,00":
                                quantidade = num
                            elif val_float > 200.0 and valor_total == "0,00":
                                valor_total = num

                        if quantidade == "0,00" and len(nums_validos) >= 2:
                            vlr_unit = nums_validos[0]
                            quantidade = nums_validos[1]
                            if len(nums_validos) >= 3:
                                valor_total = nums_validos[2]

                        registos.append({
                            'data': dt_str,
                            'hora': hora,
                            'cupom': cupom,
                            'placa': placa,
                            'produto': produto_nome,
                            'quantidade': quantidade,
                            'valor_unitario': vlr_unit,
                            'valor_total': valor_total,
                            'km': km
                        })
                        break
                j += 1

        i += 1

    df = pd.DataFrame(registos)
    return auditar_e_validar_dados(df)

def auditar_e_validar_dados(df):
    if df.empty:
        return df

    df['alertas_auditoria'] = ''

    for idx, row in df.iterrows():
        alertas = []

        km_val = limpa_numero(row['km'])
        if km_val == 0:
            alertas.append("⚠️ KM Ausente (Pode editar abaixo)")

        preco_val = limpa_numero(row['valor_unitario'])
        if preco_val == 0:
            alertas.append("❌ Preço zerado")

        litros_val = limpa_numero(row['quantidade'])
        if litros_val == 0:
            alertas.append("❌ Litros zerados")

        if not re.match(r'^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$', str(row['placa']).strip()):
            alertas.append("⚠️ Placa suspeita")

        if alertas:
            df.at[idx, 'alertas_auditoria'] = " | ".join(alertas)
        else:
            df.at[idx, 'alertas_auditoria'] = "✅ Prontos para conciliar"

    return df

def fechar_alerta_se_existir(driver, log_container):
    try:
        alert = driver.switch_to.alert
        texto = alert.text
        alert.accept()
        log_container.warning(f"⚠️ Alerta retornado: {texto}")
        time.sleep(0.8)
        return True
    except:
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
    excecoes_capturadas = (
        WebDriverException, 
        TimeoutException, 
        NoSuchElementException, 
        StaleElementReferenceException
    )
    
    for tentativa in range(1, max_tentativas + 1):
        try:
            return func()
        except excecoes_capturadas as e:
            tempo_espera = intervalo_base * (2 ** (tentativa - 1))
            if log_container:
                log_container.warning(f"⚠️ Tentativa {tentativa}/{max_tentativas}...")
            
            if tentativa == max_tentativas:
                raise e
            time.sleep(tempo_espera)

# ---------------------------------------------------------
# VERIFICAÇÃO, CONCILIAÇÃO E EDIÇÃO ATIVA NO ZUQ
# ---------------------------------------------------------
def conciliar_ou_criar_registro(driver, wait, base_url, placa, data, km, litros, preco, cupom, hora, FORNECEDOR, ultima_placa_filtrada, log_container):
    try:
        precisa_filtrar = (placa != ultima_placa_filtrada) or ("/fuel" not in driver.current_url)

        if precisa_filtrar:
            navegar_com_timeout_seguro(driver, f"{base_url}/secure/manager/maintenance/#/fuel", timeout=12, log_container=log_container)
            time.sleep(1.5)

            try:
                btn_filtro = wait.until(EC.element_to_be_clickable((By.ID, "btn-allvehicles")))
                btn_filtro.click()
                time.sleep(0.8)

                select_filtro = driver.find_elements(By.XPATH, "//select[@ng-model='filter.type']")
                if select_filtro:
                    Select(select_filtro[0]).select_by_visible_text("Placa")
                    time.sleep(0.3)

                input_modal = driver.find_element(By.XPATH, "//div[contains(@class,'selectize-input')]//input")
                input_modal.click()
                time.sleep(0.3)

                itens_selecionados = driver.find_elements(By.XPATH, "//div[contains(@class,'selectize-input')]//div[contains(@class,'item')]")
                for item in itens_selecionados:
                    try:
                        item.find_element(By.XPATH, ".//a[contains(@class,'remove')]").click()
                        time.sleep(0.2)
                    except:
                        pass

                input_modal.send_keys(Keys.CONTROL + "a")
                input_modal.send_keys(Keys.BACKSPACE)
                time.sleep(0.3)

                digitar_devagar(input_modal, placa, atraso=0.05)
                time.sleep(1.2)

                opcoes = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{placa}')]")
                
                if not opcoes:
                    log_container.warning(f"🚨 DIVERGÊNCIA: Placa {placa} não existe no ZUQ!")
                    btn_cancelar = driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]")
                    btn_cancelar.click()
                    time.sleep(0.8)
                    fechar_alerta_se_existir(driver, log_container)
                    return False, "Placa não encontrada", placa

                opcoes[0].click()
                time.sleep(0.4)

                try:
                    driver.find_element(By.XPATH, "//h5[contains(.,'Filtrar os veículos')]").click()
                except:
                    input_modal.send_keys(Keys.ESCAPE)
                
                time.sleep(0.5)

                btn_confirmar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'btn-primary') and contains(.,'Confirmar')]")))
                btn_confirmar.click()
                time.sleep(1.5)

                fechar_alerta_se_existir(driver, log_container)

            except Exception:
                try:
                    driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]").click()
                except:
                    pass
                fechar_alerta_se_existir(driver, log_container)
                return False, "Erro ao filtrar", placa

        target_litros = limpa_numero(litros)
        target_preco = limpa_numero(preco)
        target_km = re.sub(r'\D', '', str(km)) if km else ""
        
        partes_data = str(data).split('/')
        data_curta = f"{int(partes_data[0])}/{int(partes_data[1])}/{partes_data[2]}" if len(partes_data) == 3 else data

        linhas = driver.find_elements(By.XPATH, "//tr[contains(@ng-repeat,'fuel')]")
        linha_encontrada = None

        for linha in linhas:
            texto_linha = linha.text
            if not texto_linha:
                continue

            if (data in texto_linha) or (data_curta in texto_linha):
                tds = linha.find_elements(By.TAG_NAME, "td")
                numeros_celulas = [limpa_numero(td.text) for td in tds if limpa_numero(td.text) > 0]

                litros_coincide = any(abs(n - target_litros) < 0.1 for n in numeros_celulas) if target_litros > 0 else False
                preco_coincide = any(abs(n - target_preco) < 0.05 for n in numeros_celulas) if target_preco > 0 else False
                km_coincide = target_km != "" and target_km in re.sub(r'\D', '', texto_linha)

                if litros_coincide or preco_coincide or km_coincide:
                    linha_encontrada = linha
                    break

        # CASO 1: Registro EXISTE no ZUQ -> Verifica e Atualiza Divergências
        if linha_encontrada:
            texto_linha = linha_encontrada.text
            log_container.info(f"🔍 Registro encontrado no ZUQ para {placa} em {data}. Verificando divergências...")

            km_no_zuq = target_km in re.sub(r'\D', '', texto_linha) if target_km else True

            # Se o KM não bater ou estiver zerado no ZUQ, abrimos para EDITAR
            if not km_no_zuq or "0,00" in texto_linha or "0.00" in texto_linha:
                log_container.warning(f"✏️ Divergência detectada no ZUQ. Editando registro de {placa}...")

                try:
                    link_registro = linha_encontrada.find_element(By.XPATH, ".//a[contains(@href,'/fuel/')]")
                    navegar_com_timeout_seguro(driver, link_registro.get_attribute("href"), timeout=12, log_container=log_container)
                except:
                    linha_encontrada.click()

                time.sleep(1.8)

                # Clica em Editar
                try:
                    btn_editar = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class,'btn') and .//i[contains(@class,'icon-pencil') or contains(@class,'fa-pencil')]]")))
                    btn_editar.click()
                    time.sleep(1.5)
                except Exception as e_ed:
                    log_container.error(f"❌ Não foi possível clicar no botão Editar: {e_ed}")
                    return True, "Erro ao abrir edição", placa

                # Atualiza os campos necessários com os dados do PDF
                if km and km != "0":
                    try:
                        campo_km = driver.find_element(By.XPATH, "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]")
                        driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_km, km)
                        log_container.info(f"✏️ KM no ZUQ atualizado para: {km}")
                    except Exception: pass

                if target_litros > 0:
                    try:
                        campo_litros = driver.find_element(By.XPATH, "//label[contains(text(),'Litros')]/following::input[1]")
                        driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_litros, litros)
                    except Exception: pass

                if target_preco > 0:
                    try:
                        campo_preco = driver.find_element(By.NAME, "price")
                        driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_preco, preco)
                    except Exception: pass

                # Clica em Salvar
                for xpath in ["//*[contains(@class,'btn') and contains(.,'Salvar')]", "//button[contains(.,'Salvar')]"]:
                    try:
                        btn_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                        btn_salvar.click()
                        time.sleep(1.5)
                        break
                    except Exception: 
                        continue

                log_container.success(f"✅ ZUQ Atualizado com sucesso para {placa}!")
                return True, "Atualizado no ZUQ (Editado)", placa
            else:
                log_container.info(f"✅ Registro já está 100% correto no ZUQ.")
                return True, "Já Cadastrado (Sem divergência)", placa

        # CASO 2: Registro NÃO existe no ZUQ -> Criar do zero
        else:
            log_container.info(f"➕ Registro não encontrado no ZUQ. Criando novo lançamento para {placa}...")
            return False, "Criar Novo", placa

    except Exception as e:
        fechar_alerta_se_existir(driver, log_container)
        return False, f"Erro na análise: {str(e)}", placa

# ---------------------------------------------------------
# AUTOMAÇÃO DE LANÇAMENTO E EDICAO ZUQ
# ---------------------------------------------------------
def lancar_no_zuq(df, URL_ZUQ, USUARIO, SENHA, FORNECEDOR, log_container, progress_bar, metric_lancados, metric_ignorados):
    df_relatorio = df.copy()
    df_relatorio['status_lancamento'] = 'Pendente'
    df_relatorio['data_processamento'] = ''
    df_relatorio['observacao'] = ''

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

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
    wait = WebDriverWait(driver, 15)

    df = df.sort_values(by="placa").reset_index(drop=True)

    qtd_lancados = 0
    qtd_ignorados = 0
    total_registros = len(df)

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
            progress = (idx + 1) / total_registros
            progress_bar.progress(progress, text=f"Processando {idx+1} de {total_registros}")
            horario_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            placa_str = str(row['placa']).strip()
            km_str = str(row['km']).strip() if pd.notna(row['km']) else ""
            cupom_str = str(row['cupom']) if 'cupom' in row and pd.notna(row['cupom']) else "0"
            hora_str = str(row['hora']) if 'hora' in row and pd.notna(row['hora']) else "08:00:00"

            log_container.write(f"📌 **[{idx+1}/{total_registros}] Placa {placa_str}** | Data: {row['data']} | Vol: {row['quantidade']}L | KM: {km_str if km_str else 'N/A'}")

            fechar_alerta_se_existir(driver, log_container)

            # Analisa se já existe no ZUQ e edita caso haja divergências
            existe, status_obs, ultima_placa_filtrada = conciliar_ou_criar_registro(
                driver, wait, base_url, placa_str, str(row['data']), km_str, str(row['quantidade']), str(row['valor_unitario']), cupom_str, hora_str, FORNECEDOR, ultima_placa_filtrada, log_container
            )

            if existe:
                qtd_lancados += 1
                metric_lancados.metric("Processados", qtd_lancados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Conciliado/Atualizado'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = status_obs
                continue

            # Se não existia, faz a inserção do novo registro
            def abrir_formulario():
                url_form = f"{base_url}/secure/manager/maintenance/#/fuel/new"
                navegar_com_timeout_seguro(driver, url_form, timeout=10, log_container=log_container)
                wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]")))

            try:
                executar_com_retry(abrir_formulario, max_tentativas=3, log_container=log_container)
            except Exception as e_nav:
                log_container.error(f"❌ Falha no formulário: {e_nav}")
                qtd_ignorados += 1
                metric_ignorados.metric("Erros", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Falha no formulário: {str(e_nav)}"
                continue

            def selecionar_veiculo():
                elem_veiculo = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]")))
                elem_veiculo.click()
                time.sleep(0.3)
                
                input_veiculo = driver.find_element(By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]//input")
                input_veiculo.send_keys(Keys.CONTROL + "a")
                input_veiculo.send_keys(Keys.BACKSPACE)
                digitar_devagar(input_veiculo, placa_str, atraso=0.05)
                time.sleep(1.0)
                
                opcoes_form = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown')]//div[contains(.,'{placa_str}')]")
                if not opcoes_form:
                    return False

                opcoes_form[0].click()
                time.sleep(0.4)
                return True

            try:
                veiculo_encontrado = executar_com_retry(selecionar_veiculo, max_tentativas=3, log_container=log_container)
                if not veiculo_encontrado:
                    log_container.warning(f"⚠️ Veículo {placa_str} não localizado no ZUQ.")
                    qtd_ignorados += 1
                    metric_ignorados.metric("Erros", qtd_ignorados)
                    
                    df_relatorio.at[idx, 'status_lancamento'] = 'Ignorado'
                    df_relatorio.at[idx, 'data_processamento'] = horario_atual
                    df_relatorio.at[idx, 'observacao'] = 'Veículo não localizado'
                    continue
            except Exception as e_v:
                log_container.error(f"Erro no veículo {placa_str}: {e_v}")
                qtd_ignorados += 1
                metric_ignorados.metric("Erros", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Erro no veículo: {str(e_v)}"
                continue

            try:
                data_iso = datetime.strptime(str(row['data']), "%d/%m/%Y").strftime("%Y-%m-%d")
                campo_data = driver.find_element(By.ID, "fuelDate")
                driver.execute_script("""
                    var elem = arguments[0]; elem.value = arguments[1];
                    elem.dispatchEvent(new Event('input', { bubbles: true }));
                    elem.dispatchEvent(new Event('change', { bubbles: true }));
                """, campo_data, data_iso)
            except Exception: pass

            try:
                campo_hora = driver.find_element(By.ID, "additionTime")
                campo_hora.click()
                campo_hora.send_keys(Keys.CONTROL + "a")
                campo_hora.send_keys(Keys.BACKSPACE)
                hora_formatada = hora_str[:5] if len(hora_str) >= 5 else hora_str
                digitar_devagar(campo_hora, hora_formatada, atraso=0.05)
            except Exception: pass

            try:
                campo_litros = driver.find_element(By.XPATH, "//label[contains(text(),'Litros')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_litros, str(row['quantidade']))
            except Exception: pass

            try:
                campo_preco = driver.find_element(By.NAME, "price")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_preco, str(row['valor_unitario']))
            except Exception: pass

            try:
                if km_str and km_str != "0":
                    campo_km = driver.find_element(By.XPATH, "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]")
                    driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_km, km_str)
            except Exception: pass

            try:
                elem_fornecedor = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]")))
                elem_fornecedor.click()
                time.sleep(0.3)
                
                input_fornecedor = driver.find_element(By.XPATH, "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]//input")
                digitar_devagar(input_fornecedor, FORNECEDOR, atraso=0.05)
                time.sleep(1.0)
                input_fornecedor.send_keys(Keys.ARROW_DOWN)
                input_fornecedor.send_keys(Keys.ENTER)
                time.sleep(0.3)
            except Exception: pass

            try:
                campo_doc = driver.find_element(By.XPATH, "//label[contains(text(),'Documento fiscal')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_doc, cupom_str)
            except Exception: pass

            def salvar_registro():
                for xpath in ["//*[contains(@class,'btn') and contains(.,'Salvar')]", "//button[contains(.,'Salvar')]"]:
                    try:
                        btn_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                        btn_salvar.click()
                        time.sleep(1.2)

                        erros_km = driver.find_elements(By.XPATH, "//*[contains(text(),'Odômetro Inválido') or contains(text(),'entra em conflito')]")
                        if erros_km and erros_km[0].is_displayed():
                            log_container.warning(f"⚠️ Conflito de Odômetro. Salvando sem KM...")
                            campo_km = driver.find_element(By.XPATH, "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]")
                            driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_km)
                            time.sleep(0.5)
                            btn_salvar.click()
                            time.sleep(1.2)

                        return True
                    except Exception: 
                        continue
                return False

            salvo = False
            try:
                salvo = executar_com_retry(salvar_registro, max_tentativas=3, log_container=log_container)
                if salvo:
                    ultima_placa_filtrada = ""
            except Exception as e_save:
                log_container.error(f"❌ Erro ao salvar {placa_str}: {e_save}")
                df_relatorio.at[idx, 'observacao'] = f"Erro ao salvar: {str(e_save)}"

            time.sleep(1.0)
            fechar_alerta_se_existir(driver, log_container)

            if salvo:
                qtd_lancados += 1
                metric_lancados.metric("Processados", qtd_lancados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Criado Novo'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Lançado com sucesso'
            else:
                qtd_ignorados += 1
                metric_ignorados.metric("Erros", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                if not df_relatorio.at[idx, 'observacao']:
                    df_relatorio.at[idx, 'observacao'] = 'Falha ao salvar'

        log_container.success("🎉 Processamento e conciliação finalizados!")

    except Exception as e:
        log_container.error(f"❌ Erro crítico: {e}")
    finally:
        driver.quit()

    return df_relatorio

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
        usuario_zuq = c1.text_input("Usuário", value="manutencaoverdesmares")
        senha_zuq = c2.text_input("Senha ZUQ", type="password")
        url_zuq = c3.text_input("URL ZUQ", value="https://app.zuq.com.br")
        fornecedor_zuq = c4.text_input("Fornecedor Padrão", value="POSTO GURI - MACEIÓ")

    st.markdown("<br>", unsafe_allow_html=True)

    col_upload, col_control = st.columns([1.1, 1], gap="large")

    with col_upload:
        st.markdown("### 📁 1. Ficheiro Liveposto")
        uploaded_file = st.file_uploader("Upload de relatório em PDF ou TXT", type=["pdf", "txt"], label_visibility="collapsed")

        if uploaded_file and "dados_df" not in st.session_state:
            st.session_state["dados_df"] = extrair_dados_txt_ou_pdf(uploaded_file)

        if "dados_df" in st.session_state and st.session_state["dados_df"] is not None:
            st.info("💡 **Conciliação Ativa**: Registros existentes no ZUQ com KM ou valores divergentes serão **editados e corrigidos automaticamente** pelo robô.")

            # Tabela Interativa
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
                use_container_width=True,
                num_rows="dynamic",
                height=350
            )

            st.session_state["dados_final"] = auditar_e_validar_dados(df_editado)

    with col_control:
        st.markdown("### 📊 2. Lançamento e Conciliação ZUQ")
        
        df_para_processar = st.session_state.get("dados_final", None)

        kpi1, kpi2, kpi3 = st.columns(3)
        metric_total = kpi1.metric("Total a Analisar", len(df_para_processar) if df_para_processar is not None else 0)
        metric_lancados = kpi2.metric("Conciliados/Lançados", 0)
        metric_ignorados = kpi3.metric("Erros", 0)

        st.markdown("<br>", unsafe_allow_html=True)
        
        btn_iniciar = st.button("🚀 Iniciar Conciliação e Correção no ZUQ", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        progress_bar = st.progress(0, text="Aguardando disparo...")
        log_container = st.container(height=300, border=True)

        if btn_iniciar:
            if df_para_processar is None or df_para_processar.empty:
                st.error("Faça o upload do ficheiro PDF/TXT antes de iniciar.")
            elif not senha_zuq:
                st.error("Informe a senha do ZUQ nas configurações acima.")
            else:
                df_resultado = lancar_no_zuq(
                    df_para_processar, url_zuq, usuario_zuq, senha_zuq, 
                    fornecedor_zuq, log_container, 
                    progress_bar, metric_lancados, metric_ignorados
                )

                if df_resultado is not None:
                    csv_data = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig')

                    st.divider()
                    st.markdown("### 📋 Relatório de Conciliação")
                    st.dataframe(
                        df_resultado[['placa', 'data', 'quantidade', 'valor_unitario', 'km', 'status_lancamento', 'observacao']], 
                        use_container_width=True
                    )

                    st.download_button(
                        label="📥 Baixar Relatório (CSV)",
                        data=csv_data,
                        file_name=f"relatorio_conciliacao_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

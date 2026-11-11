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
# CONFIGURAÇÃO DA PÁGINA E DESIGN SYSTEM (NETLIFY / VERCEL STYLE)
# ---------------------------------------------------------
st.set_page_config(
    page_title="ZUQ Auto - Central de Abastecimentos",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilização CSS completa para simular Web App Nativo (Netlify Style)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Reset global de fonte e fundo */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .stApp {
        background-color: #F8FAFC !important;
        color: #0F172A !important;
    }

    #MainMenu, footer, header { visibility: hidden; }
    
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1280px !important;
    }

    /* Top Bar / Header App */
    .app-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
        border-bottom: 1px solid #E2E8F0;
    }
    
    .app-brand {
        font-size: 1.3rem;
        font-weight: 700;
        color: #0F172A;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .app-badge {
        background-color: #EFF6FF;
        color: #2563EB;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.2rem 0.6rem;
        border-radius: 9999px;
        border: 1px solid #DBEAFE;
    }

    /* Cards Estilo Netlify */
    .netlify-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.02);
    }

    .card-title-text {
        font-size: 0.95rem;
        font-weight: 600;
        color: #0F172A;
        margin-bottom: 0.8rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    /* Input & Form Styling */
    div[data-baseweb="input"] {
        background-color: #FFFFFF !important;
        border-radius: 6px !important;
    }

    /* Metrics Styling */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        border-radius: 10px !important;
        padding: 0.8rem 1rem !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    }

    div[data-testid="stMetricLabel"] {
        color: #64748B !important;
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
    }

    div[data-testid="stMetricValue"] {
        color: #0F172A !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }

    /* Botão Principal Estilo SaaS */
    .stButton > button {
        background-color: #0066FF !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        border: none !important;
        border-radius: 8px !important;
        height: 2.8rem !important;
        transition: all 0.15s ease !important;
        box-shadow: 0 1px 2px rgba(0, 102, 255, 0.2) !important;
    }

    .stButton > button:hover {
        background-color: #0052CC !important;
        box-shadow: 0 4px 8px rgba(0, 102, 255, 0.25) !important;
    }

    /* Terminal de Logs Estilo Netlify Build Logs */
    div[data-testid="stVerticalBlock"] > div[style*="height"] {
        border-radius: 8px !important;
        border: 1px solid #E2E8F0 !important;
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

    st.markdown('<div style="text-align: center; padding-top: 5rem;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 1.8rem; font-weight: 700; color: #0F172A;">⚡ ZUQ Auto</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 0.9rem; color: #64748B; margin-bottom: 2rem;">Acesso restrito à plataforma de automação corporativa.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1.2, 1, 1.2])
    with col2:
        with st.form("form_login"):
            senha_digitada = st.text_input("Chave de Acesso", type="password", placeholder="Digite sua senha")
            btn_login = st.form_submit_button("Entrar no Painel", use_container_width=True)

            if btn_login:
                if senha_digitada == SENHA_CORRETA:
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("❌ Credencial inválida.")
    st.markdown('</div>', unsafe_allow_html=True)
                    
    return False

# ---------------------------------------------------------
# FUNÇÕES DE LEITURA (TXT / PDF)
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

        m_data = re.match(r'^(\d{2}/\d{2}/\d{2,4})\s*(\d{1,2}:\d{2}:\d{2})?(\d{3,6})?\s+(.*)', line)
        if m_data:
            dt_str, hr_raw, cupom_raw, resto_linha = m_data.groups()
            
            partes_dt = dt_str.split('/')
            if len(partes_dt[2]) == 2:
                dt_str = f"{partes_dt[0]}/{partes_dt[1]}/20{partes_dt[2]}"

            m_placa = re.search(r'([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})', resto_linha)
            placa = m_placa.group(1).replace('-', '') if m_placa else ""

            nxt_line = lines[i+1].strip() if i+1 < len(lines) else ""
            
            numeros_nxt = re.findall(r'(\d+(?:[\.,]\d+)?)', nxt_line)
            numeros_linha = re.findall(r'(\d+(?:[\.,]\d+)?)', resto_linha)

            vlr_unit = "0,00"
            quantidade = "0,00"
            valor_total = "0,00"
            km = ""

            if numeros_nxt:
                vlr_unit = numeros_nxt[0]
                if len(numeros_nxt) >= 2:
                    quantidade = numeros_nxt[1]
                if len(numeros_nxt) >= 3:
                    valor_total = numeros_nxt[-1]

            if quantidade == "0,00" and numeros_linha:
                quantidade = numeros_linha[0]
                if len(numeros_linha) >= 2:
                    valor_total = numeros_linha[1]

            m_km = re.search(r'(\d{2,3}\.\d{3}|\d{5,6})', resto_linha)
            if m_km:
                km = m_km.group(1).replace('.', '')

            if placa:
                registos.append({
                    'data': dt_str,
                    'hora': hr_raw if hr_raw else "08:00:00",
                    'cupom': cupom_raw if cupom_raw else "0",
                    'placa': placa,
                    'produto': "DIESEL B S10 ADITIVADO",
                    'quantidade': quantidade,
                    'valor_unitario': vlr_unit,
                    'valor_total': valor_total,
                    'km': km
                })
        i += 1

    return pd.DataFrame(registos)

def fechar_alerta_se_existir(driver, log_container):
    try:
        alert = driver.switch_to.alert
        texto = alert.text
        alert.accept()
        log_container.warning(f"⚠️ Alerta: {texto}")
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
            log_container.warning(f"⏳ Interrompendo requisições em {url}...")
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
# CHECAGEM DE DUPLICATAS ROBUSTA
# ---------------------------------------------------------
def tratar_duplicados_se_existirem(driver, wait, base_url, placa, data, km, litros, preco, ultima_placa_filtrada, log_container):
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
                    log_container.warning(f"⚠️ Placa {placa} não encontrada no ZUQ.")
                    btn_cancelar = driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]")
                    btn_cancelar.click()
                    time.sleep(0.8)
                    fechar_alerta_se_existir(driver, log_container)
                    return False, False, placa

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
                return False, False, placa
        else:
            time.sleep(0.3)

        target_litros = limpa_numero(litros)
        target_preco = limpa_numero(preco)
        target_km = re.sub(r'\D', '', str(km)) if km else ""
        
        partes_data = data.split('/')
        data_curta = f"{int(partes_data[0])}/{int(partes_data[1])}/{partes_data[2]}" if len(partes_data) == 3 else data

        linhas = driver.find_elements(By.XPATH, "//tr[contains(@ng-repeat,'fuel')]")
        linhas_duplicadas = []

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

                if litros_coincide or (preco_coincide and km_coincide):
                    linhas_duplicadas.append(linha)

        if len(linhas_duplicadas) >= 2:
            log_container.warning(f"🚨 Duplicado em {data} ({litros}L). Removendo...")
            linha_para_remover = linhas_duplicadas[0]

            try:
                link_registro = linha_para_remover.find_element(By.XPATH, ".//a[contains(@href,'/fuel/')]")
                navegar_com_timeout_seguro(driver, link_registro.get_attribute("href"), timeout=12, log_container=log_container)
            except:
                linha_para_remover.click()

            time.sleep(1.8)

            try:
                btn_editar = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class,'btn') and .//i[contains(@class,'icon-pencil') or contains(@class,'fa-pencil')]]")))
                btn_editar.click()
                time.sleep(1.5)
            except:
                pass

            try:
                btn_remover = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@ng-click='deleteFuel()' or contains(.,'Remover')]")))
                btn_remover.click()
                time.sleep(1.2)

                fechar_alerta_se_existir(driver, log_container)
                log_container.info("✅ Registro removido.")
                time.sleep(1.2)
                return True, True, ""
            except Exception as e_rem:
                log_container.error(f"❌ Erro ao remover: {e_rem}")

        elif len(linhas_duplicadas) == 1:
            log_container.info(f"🔍 Abastecimento em {data} ({litros}L) já existe. Ignorando...")
            return True, True, placa

    except Exception:
        fechar_alerta_se_existir(driver, log_container)

    return True, False, placa

# ---------------------------------------------------------
# AUTOMAÇÃO DE LANÇAMENTO ZUQ
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
        log_container.info("🌐 Conectando à instância ZUQ...")

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
        log_container.info("🔐 Autenticação concluída com sucesso.")
        time.sleep(3)

        base_url = URL_ZUQ.rsplit('/secure', 1)[0] if '/secure' in URL_ZUQ else URL_ZUQ.rstrip('/')
        ultima_placa_filtrada = ""

        for idx, row in df.iterrows():
            progress = (idx + 1) / total_registros
            progress_bar.progress(progress, text=f"Lançando {idx+1} de {total_registros}")
            horario_atual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            log_container.write(f"📌 **[{idx+1}/{total_registros}] Placa {row['placa']}** | Data: {row['data']} | Vol: {row['quantidade']}L")

            fechar_alerta_se_existir(driver, log_container)

            try:
                placa_existe, ja_cadastrado, ultima_placa_filtrada = executar_com_retry(
                    lambda: tratar_duplicados_se_existirem(
                        driver, wait, base_url, row['placa'], row['data'], row['km'], row['quantidade'], row['valor_unitario'], ultima_placa_filtrada, log_container
                    ),
                    max_tentativas=3,
                    log_container=log_container
                )
            except Exception as e_dup:
                log_container.error(f"❌ Erro ao validar {row['placa']}: {e_dup}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Falha na validação: {str(e_dup)}"
                continue

            if not placa_existe:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Ignorado'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Placa não cadastrada'
                continue

            if ja_cadastrado:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Duplicado'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Registro já existe'
                continue

            def abrir_formulario():
                url_form = f"{base_url}/secure/manager/maintenance/#/fuel/new"
                navegar_com_timeout_seguro(driver, url_form, timeout=10, log_container=log_container)
                wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]")))

            try:
                executar_com_retry(abrir_formulario, max_tentativas=3, log_container=log_container)
            except Exception as e_nav:
                log_container.error(f"❌ Falha ao carregar formulário: {e_nav}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados", qtd_ignorados)
                
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
                digitar_devagar(input_veiculo, row['placa'], atraso=0.05)
                time.sleep(1.0)
                
                opcoes_form = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown')]//div[contains(.,'{row['placa']}')]")
                if not opcoes_form:
                    return False

                opcoes_form[0].click()
                time.sleep(0.4)
                return True

            try:
                veiculo_encontrado = executar_com_retry(selecionar_veiculo, max_tentativas=3, log_container=log_container)
                if not veiculo_encontrado:
                    log_container.warning(f"⚠️ Veículo {row['placa']} não localizado.")
                    qtd_ignorados += 1
                    metric_ignorados.metric("Ignorados", qtd_ignorados)
                    
                    df_relatorio.at[idx, 'status_lancamento'] = 'Ignorado'
                    df_relatorio.at[idx, 'data_processamento'] = horario_atual
                    df_relatorio.at[idx, 'observacao'] = 'Veículo não localizado'
                    continue
            except Exception as e_v:
                log_container.error(f"Erro no veículo {row['placa']}: {e_v}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Erro no veículo: {str(e_v)}"
                continue

            try:
                data_iso = datetime.strptime(row['data'], "%d/%m/%Y").strftime("%Y-%m-%d")
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
                hora_formatada = row['hora'][:5] if len(row['hora']) >= 5 else row['hora']
                digitar_devagar(campo_hora, hora_formatada, atraso=0.05)
            except Exception: pass

            try:
                campo_litros = driver.find_element(By.XPATH, "//label[contains(text(),'Litros')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_litros, row['quantidade'])
            except Exception: pass

            try:
                campo_preco = driver.find_element(By.NAME, "price")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_preco, row['valor_unitario'])
            except Exception: pass

            try:
                campo_km = driver.find_element(By.XPATH, "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_km, row['km'])
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
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_doc, row['cupom'])
            except Exception: pass

            def salvar_registro():
                for xpath in ["//*[contains(@class,'btn') and contains(.,'Salvar')]", "//button[contains(.,'Salvar')]"]:
                    try:
                        btn_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                        btn_salvar.click()
                        time.sleep(1.2)

                        erros_km = driver.find_elements(By.XPATH, "//*[contains(text(),'Odômetro Inválido') or contains(text(),'entra em conflito')]")
                        if erros_km and erros_km[0].is_displayed():
                            log_container.warning("⚠️ Conflito no Odômetro! Limpando...")
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
                log_container.error(f"❌ Erro ao salvar {row['placa']}: {e_save}")
                df_relatorio.at[idx, 'observacao'] = f"Erro ao salvar: {str(e_save)}"

            time.sleep(1.0)
            fechar_alerta_se_existir(driver, log_container)

            if salvo:
                qtd_lancados += 1
                metric_lancados.metric("Lançados", qtd_lancados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Sucesso'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Lançado com sucesso'
            else:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                if not df_relatorio.at[idx, 'observacao']:
                    df_relatorio.at[idx, 'observacao'] = 'Falha ao salvar'

        log_container.success("🎉 Todos os abastecimentos foram processados!")

    except Exception as e:
        log_container.error(f"❌ Erro crítico: {e}")
    finally:
        driver.quit()

    return df_relatorio

# ---------------------------------------------------------
# INTERFACE PRINCIPAL (SAAS / NETLIFY STYLE)
# ---------------------------------------------------------
if verificar_senha():
    # Header Limpo
    st.markdown("""
        <div class="app-header">
            <div class="app-brand">⚡ ZUQ Auto <span class="app-badge">v2.4 Production</span></div>
        </div>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1.1], gap="large")

    with col_left:
        # Card 1: Credenciais ZUQ
        st.markdown('<div class="card-title-text">⚙️ Credenciais ZUQ</div>', unsafe_allow_html=True)
        with st.container():
            c1, c2 = st.columns(2)
            usuario_zuq = c1.text_input("Usuário ZUQ", value="manutencaoverdesmares")
            senha_zuq = c2.text_input("Senha ZUQ", type="password")
            
            c3, c4 = st.columns(2)
            url_zuq = c3.text_input("URL ZUQ", value="https://app.zuq.com.br")
            fornecedor_zuq = c4.text_input("Fornecedor Padrão", value="POSTO GURI - MACEIÓ")

        st.markdown("<br>", unsafe_allow_html=True)

        # Card 2: Upload de Arquivo
        st.markdown('<div class="card-title-text">📁 Arquivo de Abastecimentos (Liveposto)</div>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Upload de relatório em PDF ou TXT", type=["pdf", "txt"], label_visibility="collapsed")
        
        dados_df = None
        if uploaded_file:
            dados_df = extrair_dados_txt_ou_pdf(uploaded_file)
            st.success(f"✅ **{len(dados_df)}** registros de abastecimentos validados no arquivo.")

            with st.expander("👁️ Visualizar Prévia da Tabela de Abastecimentos", expanded=False):
                st.dataframe(
                    dados_df[['placa', 'data', 'quantidade', 'valor_unitario', 'km']], 
                    use_container_width=True,
                    height=250
                )

    with col_right:
        # Card 3: Painel de Controle e Métricas
        st.markdown('<div class="card-title-text">📊 Painel de Controle da Automação</div>', unsafe_allow_html=True)
        
        m1, m2, m3 = st.columns(3)
        metric_total = m1.metric("Total de Registros", len(dados_df) if dados_df is not None else 0)
        metric_lancados = m2.metric("Lançados", 0)
        metric_ignorados = m3.metric("Ignorados", 0)

        st.markdown("<br>", unsafe_allow_html=True)
        
        btn_iniciar = st.button("🚀 Iniciar Lançamento Automático", use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        progress_bar = st.progress(0, text="Aguardando disparo...")
        log_container = st.container(height=280, border=True)

        if btn_iniciar:
            if dados_df is None or dados_df.empty:
                st.error("Selecione um arquivo PDF ou TXT válido do Liveposto.")
            elif not senha_zuq:
                st.error("Preencha a senha do ZUQ no formulário à esquerda.")
            else:
                df_resultado = lancar_no_zuq(
                    dados_df, url_zuq, usuario_zuq, senha_zuq, 
                    fornecedor_zuq, log_container, 
                    progress_bar, metric_lancados, metric_ignorados
                )

                if df_resultado is not None:
                    csv_data = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig')

                    st.divider()
                    st.markdown("### 📋 Relatório de Auditoria")
                    st.dataframe(
                        df_resultado[['placa', 'data', 'quantidade', 'status_lancamento', 'observacao']], 
                        use_container_width=True
                    )

                    st.download_button(
                        label="📥 Baixar Relatório Completo (CSV)",
                        data=csv_data,
                        file_name=f"relatorio_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

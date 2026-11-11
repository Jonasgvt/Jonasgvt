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
# CONFIGURAÇÃO DE ESTILO E PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestão de Abastecimentos ZUQ",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #1E3A8A; margin-bottom: 0.5rem; }
    .sub-header { font-size: 1rem; color: #6B7280; margin-bottom: 1.5rem; }
    .stButton>button { background-color: #2563EB; color: white; font-weight: 600; border-radius: 8px; height: 3rem; }
    .stButton>button:hover { background-color: #1D4ED8; }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# AUTENTICAÇÃO E SEGURANÇA DO PAINEL
# ---------------------------------------------------------
def verificar_senha():
    SENHA_CORRETA = st.secrets.get("APP_PASSWORD", "zuq123")

    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if st.session_state["autenticado"]:
        return True

    st.markdown('<div class="main-header">🔒 Acesso Restrito</div>', unsafe_allow_html=True)
    st.markdown("Por favor, introduza a senha de acesso para utilizar a Central de Automação ZUQ.")

    with st.form("form_login"):
        senha_digitada = st.text_input("Senha do Painel", type="password")
        btn_login = st.form_submit_button("🔑 Entrar no Painel")

        if btn_login:
            if senha_digitada == SENHA_CORRETA:
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("❌ Senha incorreta. Tente novamente.")
                
    return False

# ---------------------------------------------------------
# PARSER DE LEITURA (TXT / PDF DO LIVEPOSTO)
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
    """Extrai os dados de abastecimento lendo arquivos TXT exportados do Liveposto ou PDFs."""
    registos = []
    lines = []

    # Leitura do conteúdo (Arquivo enviado via Upload)
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

    # Processamento por Expressão Regular
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
        log_container.warning(f"⚠️ Alerta confirmado: {texto}")
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
            log_container.warning(f"⏳ Tempo limite de {timeout}s atingido em {url}. Interrompendo carregamentos secundários...")
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
            msg_erro = f"⚠️ Instabilidade/timeout (Tentativa {tentativa}/{max_tentativas}). Aguardando {tempo_espera:.1f}s..."
            
            if log_container:
                log_container.warning(msg_erro)
            
            if tentativa == max_tentativas:
                raise e
            
            time.sleep(tempo_espera)

# ---------------------------------------------------------
# CHECAGEM DE DUPLICATAS ROBUSTA (ZUQ)
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
                    log_container.warning(f"⚠️ Placa {placa} não cadastrada no ZUQ.")
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

            except Exception as e_modal:
                log_container.warning(f"⚠️ Aviso no filtro por placa: {e_modal}")
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
            log_container.warning(f"🚨 Réplica detectada em {data} ({litros}L). Removendo excedente...")
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
                log_container.info("✅ Réplica removida com sucesso.")
                time.sleep(1.2)
                return True, True, ""
            except Exception as e_rem:
                log_container.error(f"❌ Erro ao remover duplicado: {e_rem}")

        elif len(linhas_duplicadas) == 1:
            log_container.info(f"🔍 Registro já existente em {data} ({litros}L). Pulando...")
            return True, True, placa

    except Exception as e:
        log_container.warning(f"⚠️ Erro na checagem: {e}")
        fechar_alerta_se_existir(driver, log_container)

    return True, False, placa

# ---------------------------------------------------------
# PROCESSAMENTO PRINCIPAL DE LANÇAMENTO NO ZUQ
# ---------------------------------------------------------
def lancar_no_zuq(df, URL_ZUQ, USUARIO, SENHA, FORNECEDOR, MODO_VISIVEL, log_container, progress_bar, metric_lancados, metric_ignorados):
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
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1920,1080")
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

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
    driver.set_script_timeout(10)
    wait = WebDriverWait(driver, 15)

    df = df.sort_values(by="placa").reset_index(drop=True)

    qtd_lancados = 0
    qtd_ignorados = 0
    total_registros = len(df)

    try:
        log_container.info("🌐 Conectando ao portal ZUQ...")

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
        
        log_container.info("Autenticando no sistema...")
        time.sleep(3)

        base_url = URL_ZUQ.rsplit('/secure', 1)[0] if '/secure' in URL_ZUQ else URL_ZUQ.rstrip('/')
        ultima_placa_filtrada = ""

        for idx, row in df.iterrows():
            progress = (idx + 1) / total_registros
            progress_bar.progress(progress, text=f"Abastecimento {idx+1} de {total_registros}")
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
                log_container.error(f"❌ Erro ao verificar duplicatas para a placa {row['placa']}: {e_dup}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Falha na verificação de duplicados: {str(e_dup)}"
                continue

            if not placa_existe:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Ignorado'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Placa não cadastrada no ZUQ'
                continue

            if ja_cadastrado:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Duplicado'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Registro já existente no sistema ZUQ'
                continue

            def abrir_formulario():
                url_form = f"{base_url}/secure/manager/maintenance/#/fuel/new"
                navegar_com_timeout_seguro(driver, url_form, timeout=10, log_container=log_container)
                wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]")))

            try:
                executar_com_retry(abrir_formulario, max_tentativas=3, log_container=log_container)
            except Exception as e_nav:
                log_container.error(f"❌ Falha ao carregar formulário para {row['placa']}: {e_nav}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Falha ao carregar formulário: {str(e_nav)}"
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
                    log_container.warning(f"⚠️ Veículo {row['placa']} não localizado nas opções.")
                    qtd_ignorados += 1
                    metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                    
                    df_relatorio.at[idx, 'status_lancamento'] = 'Ignorado'
                    df_relatorio.at[idx, 'data_processamento'] = horario_atual
                    df_relatorio.at[idx, 'observacao'] = 'Veículo não localizado nas opções do formulário'
                    continue
            except Exception as e_v:
                log_container.error(f"Erro na seleção do veículo {row['placa']}: {e_v}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = f"Erro ao selecionar veículo: {str(e_v)}"
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
                            log_container.warning("⚠️ Conflito no Odômetro! Limpando campo e salvando...")
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
                log_container.error(f"❌ Não foi possível salvar o registro para {row['placa']}: {e_save}")
                df_relatorio.at[idx, 'observacao'] = f"Erro no clique de salvar: {str(e_save)}"

            time.sleep(1.0)
            fechar_alerta_se_existir(driver, log_container)

            if salvo:
                qtd_lancados += 1
                metric_lancados.metric("Lançados com Sucesso", qtd_lancados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Sucesso'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                df_relatorio.at[idx, 'observacao'] = 'Lançado com sucesso no ZUQ'
            else:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                
                df_relatorio.at[idx, 'status_lancamento'] = 'Erro'
                df_relatorio.at[idx, 'data_processamento'] = horario_atual
                if not df_relatorio.at[idx, 'observacao']:
                    df_relatorio.at[idx, 'observacao'] = 'Falha no salvamento do formulário'

        log_container.success("🎉 Todos os abastecimentos foram processados!")

    except Exception as e:
        log_container.error(f"❌ Erro crítico durante o processamento: {e}")
    finally:
        driver.quit()

    return df_relatorio

# ---------------------------------------------------------
# FLUXO PRINCIPAL DA APLICAÇÃO STREAMLIT
# ---------------------------------------------------------
if verificar_senha():
    st.markdown('<div class="main-header">⛽ Central de Automação ZUQ</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Importe o relatório de abastecimentos (PDF ou TXT) baixado do Liveposto para sincronização automática no ZUQ.</div>', unsafe_allow_html=True)

    with st.sidebar:
        st.header("⚙️ Configurações do ZUQ")
        usuario_zuq = st.text_input("Usuário ZUQ", value="manutencaoverdesmares")
        senha_zuq = st.text_input("Senha ZUQ", type="password")
        url_zuq = st.text_input("URL ZUQ", value="https://app.zuq.com.br")
        fornecedor_zuq = st.text_input("Fornecedor Padrão", value="POSTO GURI - MACEIÓ")
        
        st.divider()
        modo_visivel = st.checkbox("Exibir Janela do Navegador", value=False, help="Marque se quiser ver a janela abrindo na tela (funciona apenas em testes locais).")

        st.divider()
        if st.button("🚪 Sair do Painel", use_container_width=True):
            st.session_state["autenticado"] = False
            st.rerun()

    col_upload, col_dashboard = st.columns([1.1, 1])

    with col_upload:
        st.subheader("1. Carregar Relatório (Manual)")
        
        uploaded_file = st.file_uploader("Selecione o arquivo de abastecimento (PDF ou TXT baixado do Liveposto)", type=["pdf", "txt"])
        dados_df = None

        if uploaded_file:
            dados_df = extrair_dados_txt_ou_pdf(uploaded_file)
            st.success(f"Ficheiro lido com sucesso! **{len(dados_df)}** abastecimentos identificados.")

        if dados_df is not None and not dados_df.empty:
            with st.expander("👁️ Ver prévia dos abastecimentos lidos"):
                st.dataframe(dados_df[['placa', 'data', 'quantidade', 'valor_unitario', 'km']], use_container_width=True)

    with col_dashboard:
        st.subheader("2. Painel de Lançamento ZUQ")
        
        m1, m2, m3 = st.columns(3)
        metric_total = m1.metric("Total de Registros", len(dados_df) if dados_df is not None else 0)
        metric_lancados = m2.metric("Lançados com Sucesso", 0)
        metric_ignorados = m3.metric("Ignorados / Duplicados", 0)

        progress_bar = st.progress(0, text="Aguardando início...")
        log_container = st.container(height=350, border=True)

        if st.button("🚀 Iniciar Lançamento no ZUQ", use_container_width=True):
            if dados_df is None or dados_df.empty:
                st.error("Carregue um arquivo PDF ou TXT primeiro.")
            elif not senha_zuq:
                st.error("Informe a senha do ZUQ na barra lateral.")
            else:
                df_resultado = lancar_no_zuq(
                    dados_df, url_zuq, usuario_zuq, senha_zuq, 
                    fornecedor_zuq, modo_visivel, log_container, 
                    progress_bar, metric_lancados, metric_ignorados
                )

                if df_resultado is not None:
                    csv_data = df_resultado.to_csv(index=False, sep=';', encoding='utf-8-sig')

                    st.divider()
                    st.subheader("📋 Relatório Final de Auditoria")
                    
                    st.dataframe(
                        df_resultado[['placa', 'data', 'quantidade', 'status_lancamento', 'observacao']], 
                        use_container_width=True
                    )

                    st.download_button(
                        label="📥 Baixar Relatório de Processamento (CSV)",
                        data=csv_data,
                        file_name=f"relatorio_zuq_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

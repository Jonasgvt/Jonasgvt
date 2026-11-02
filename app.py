import os
import re
import time
import pandas as pd
import pypdf
import streamlit as st
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------------------------------------
# CONFIGURAÇÃO DE ESTILO E PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestão de Abastecimentos ZUQ",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Personalizada
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
    """Retorna True se o utilizador introduzir a senha correta."""
    # Procura a senha definida em Secrets no Streamlit Cloud, ou usa 'zuq123' como padrão local
    SENHA_CORRETA = st.secrets.get("APP_PASSWORD", "zuq123")

    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False

    if st.session_state["autenticado"]:
        return True

    # Tela de Login caso não esteja autenticado
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
# FUNÇÕES AUXILIARES E EXTRAÇÃO
# ---------------------------------------------------------
def digitar_devagar(elemento, texto, atraso=0.08):
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

def extrair_dados_pdf(stream_pdf):
    reader = pypdf.PdfReader(stream_pdf)
    registos = []

    for page in reader.pages:
        lines = page.extract_text().split('\n')
        for i, line in enumerate(lines):
            if re.match(r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+\d+', line):
                hdr = line
                nxt = lines[i+1] if i+1 < len(lines) else ""
                
                m_h = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\s+(\d+)\s+(.*)', hdr)
                if not m_h:
                    continue
                dt, tm, cupom, rest = m_h.groups()

                m_placa = re.match(r'^([A-Z0-9\-]+)\s+(.*)', rest)
                placa = m_placa.group(1).replace('-', '') if m_placa else ""
                rest2 = m_placa.group(2) if m_placa else rest

                m_n = re.search(r'^(.*?)\s+([\d\.,]+)\s+([\d\.,]+)\s+([\d\.,]+)$', nxt.strip())
                if m_n:
                    prod, vlr_unit, quant, total = m_n.groups()
                else:
                    prod = nxt.strip()
                    vlr_unit, quant, total = "", "", ""

                km_match = re.search(r'(\d{1,3}(?:\.\d{3})+|\d{3,6})', rest2)
                km = km_match.group(1) if km_match else ""

                registos.append({
                    'data': dt,
                    'hora': tm,
                    'cupom': cupom,
                    'placa': placa,
                    'produto': prod,
                    'quantidade': quant,
                    'valor_unitario': vlr_unit,
                    'valor_total': total,
                    'km': km
                })

    return pd.DataFrame(registos)

def fechar_alerta_se_existir(driver, log_container):
    try:
        alert = driver.switch_to.alert
        texto = alert.text
        alert.accept()
        log_container.warning(f"⚠️ Alerta confirmado: {texto}")
        time.sleep(1)
        return True
    except:
        return False

# ---------------------------------------------------------
# CHECAGEM DE DUPLICATAS ROBUSTA
# ---------------------------------------------------------
def tratar_duplicados_se_existirem(driver, wait, base_url, placa, data, km, litros, preco, ultima_placa_filtrada, log_container):
    try:
        precisa_filtrar = (placa != ultima_placa_filtrada) or ("/fuel" not in driver.current_url)

        if precisa_filtrar:
            driver.get(f"{base_url}/secure/manager/maintenance/#/fuel")
            time.sleep(2.5)

            try:
                btn_filtro = wait.until(EC.element_to_be_clickable((By.ID, "btn-allvehicles")))
                btn_filtro.click()
                time.sleep(1.0)

                select_filtro = driver.find_elements(By.XPATH, "//select[@ng-model='filter.type']")
                if select_filtro:
                    from selenium.webdriver.support.ui import Select
                    Select(select_filtro[0]).select_by_visible_text("Placa")
                    time.sleep(0.3)

                input_modal = driver.find_element(By.XPATH, "//div[contains(@class,'selectize-input')]//input")
                input_modal.click()
                time.sleep(0.3)

                # Limpeza Selectize
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

                digitar_devagar(input_modal, placa, atraso=0.08)
                time.sleep(1.5)

                opcoes = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown-content')]//div[contains(.,'{placa}')]")
                
                if not opcoes:
                    log_container.warning(f"⚠️ Placa {placa} não cadastrada no ZUQ.")
                    btn_cancelar = driver.find_element(By.XPATH, "//button[contains(.,'Cancelar')]")
                    btn_cancelar.click()
                    time.sleep(1.0)
                    fechar_alerta_se_existir(driver, log_container)
                    return False, False, placa

                opcoes[0].click()
                time.sleep(0.5)

                try:
                    driver.find_element(By.XPATH, "//h5[contains(.,'Filtrar os veículos')]").click()
                except:
                    input_modal.send_keys(Keys.ESCAPE)
                
                time.sleep(0.8)

                btn_confirmar = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@class,'btn-primary') and contains(.,'Confirmar')]")))
                btn_confirmar.click()
                time.sleep(2.0)

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
                driver.get(link_registro.get_attribute("href"))
            except:
                linha_para_remover.click()

            time.sleep(2.5)

            try:
                btn_editar = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class,'btn') and .//i[contains(@class,'icon-pencil') or contains(@class,'fa-pencil')]]")))
                btn_editar.click()
                time.sleep(2.0)
            except:
                pass

            try:
                btn_remover = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@ng-click='deleteFuel()' or contains(.,'Remover')]")))
                btn_remover.click()
                time.sleep(1.5)

                fechar_alerta_se_existir(driver, log_container)
                log_container.info("✅ Réplica removida com sucesso.")
                time.sleep(1.5)
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
# AUTOMAÇÃO DE LANÇAMENTO COM SUPORTE A NUVEM
# ---------------------------------------------------------
def lancar_no_zuq(df, URL_ZUQ, USUARIO, SENHA, FORNECEDOR, MODO_VISIVEL, log_container, progress_bar, metric_lancados, metric_ignorados):
    options = webdriver.ChromeOptions()
    
    # Modo Headless e argumentos de desempenho para Linux / Nuvem
    if not MODO_VISIVEL:
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    # Configuração de binários para ambiente Linux (Streamlit Cloud) vs Local
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
        service = Service("/usr/bin/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    df = df.sort_values(by="placa").reset_index(drop=True)

    qtd_lancados = 0
    qtd_ignorados = 0

    try:
        log_container.info("🌐 Conectando ao portal ZUQ...")
        driver.get(URL_ZUQ)
        time.sleep(2)
        
        # Login
        campo_usuario = wait.until(EC.element_to_be_clickable((By.ID, "j_username")))
        campo_usuario.clear()
        digitar_devagar(campo_usuario, USUARIO, atraso=0.05)
        
        try:
            campo_senha = driver.find_element(By.NAME, "password")
        except:
            campo_senha = driver.find_element(By.XPATH, "//input[@type='password']")
            
        campo_senha.clear()
        digitar_devagar(campo_senha, SENHA, atraso=0.05)
        time.sleep(0.3)
        
        try:
            driver.find_element(By.XPATH, "//button[contains(text(), 'Entrar')]").click()
        except:
            campo_senha.send_keys(Keys.ENTER)
        
        log_container.info("Autenticando no sistema...")
        time.sleep(5)

        base_url = URL_ZUQ.rsplit('/secure', 1)[0] if '/secure' in URL_ZUQ else URL_ZUQ.rstrip('/')
        total_registros = len(df)
        ultima_placa_filtrada = ""

        for idx, row in df.iterrows():
            progress = (idx + 1) / total_registros
            progress_bar.progress(progress, text=f"Abastecimento {idx+1} de {total_registros}")

            log_container.write(f"📌 **[{idx+1}/{total_registros}] Placa {row['placa']}** | Data: {row['data']} | Vol: {row['quantidade']}L | R${row['valor_unitario']}")

            fechar_alerta_se_existir(driver, log_container)

            placa_existe, ja_cadastrado, ultima_placa_filtrada = tratar_duplicados_se_existirem(
                driver, wait, base_url, row['placa'], row['data'], row['km'], row['quantidade'], row['valor_unitario'], ultima_placa_filtrada, log_container
            )

            if not placa_existe or ja_cadastrado:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                continue

            # Lançamento
            driver.get(f"{base_url}/secure/manager/maintenance/#/fuel/new")
            time.sleep(2.5)

            try:
                elem_veiculo = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]")))
                elem_veiculo.click()
                time.sleep(0.5)
                
                input_veiculo = driver.find_element(By.XPATH, "//label[contains(text(),'Veículo')]/following::div[contains(@class,'selectize-input')][1]//input")
                digitar_devagar(input_veiculo, row['placa'], atraso=0.08)
                time.sleep(1.8)
                
                opcoes_form = driver.find_elements(By.XPATH, f"//div[contains(@class,'selectize-dropdown')]//div[contains(.,'{row['placa']}')]")
                if not opcoes_form:
                    qtd_ignorados += 1
                    metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                    continue

                opcoes_form[0].click()
                time.sleep(0.8)
            except Exception as e:
                log_container.error(f"Erro na seleção do veículo {row['placa']}: {e}")
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)
                continue

            # Data
            try:
                data_iso = datetime.strptime(row['data'], "%d/%m/%Y").strftime("%Y-%m-%d")
                campo_data = driver.find_element(By.ID, "fuelDate")
                driver.execute_script("""
                    var elem = arguments[0]; elem.value = arguments[1];
                    elem.dispatchEvent(new Event('input', { bubbles: true }));
                    elem.dispatchEvent(new Event('change', { bubbles: true }));
                """, campo_data, data_iso)
            except: pass

            # Hora
            try:
                campo_hora = driver.find_element(By.ID, "additionTime")
                campo_hora.click()
                campo_hora.send_keys(Keys.CONTROL + "a")
                campo_hora.send_keys(Keys.BACKSPACE)
                hora_formatada = row['hora'][:5] if len(row['hora']) >= 5 else row['hora']
                digitar_devagar(campo_hora, hora_formatada, atraso=0.08)
            except: pass

            # Litros
            try:
                campo_litros = driver.find_element(By.XPATH, "//label[contains(text(),'Litros')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_litros, row['quantidade'])
            except: pass

            # Preço
            try:
                campo_preco = driver.find_element(By.NAME, "price")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_preco, row['valor_unitario'])
            except: pass

            # Odômetro
            try:
                campo_km = driver.find_element(By.XPATH, "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_km, row['km'])
            except: pass

            # Fornecedor
            try:
                elem_fornecedor = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]")))
                elem_fornecedor.click()
                time.sleep(0.5)
                
                input_fornecedor = driver.find_element(By.XPATH, "//label[contains(text(),'Fornecedor')]/following::div[contains(@class,'selectize-input')][1]//input")
                digitar_devagar(input_fornecedor, FORNECEDOR, atraso=0.08)
                time.sleep(1.8)
                input_fornecedor.send_keys(Keys.ARROW_DOWN)
                input_fornecedor.send_keys(Keys.ENTER)
                time.sleep(0.5)
            except: pass

            # Documento fiscal
            try:
                campo_doc = driver.find_element(By.XPATH, "//label[contains(text(),'Documento fiscal')]/following::input[1]")
                driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input', { bubbles: true })); arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", campo_doc, row['cupom'])
            except: pass

            # Salvar
            salvo = False
            for xpath in ["//*[contains(@class,'btn') and contains(.,'Salvar')]", "//button[contains(.,'Salvar')]"]:
                try:
                    btn_salvar = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    btn_salvar.click()
                    time.sleep(1.8)

                    erros_km = driver.find_elements(By.XPATH, "//*[contains(text(),'Odômetro Inválido') or contains(text(),'entra em conflito')]")
                    if erros_km and erros_km[0].is_displayed():
                        log_container.warning("⚠️ Conflito no Odômetro! Limpando campo e salvando...")
                        campo_km = driver.find_element(By.XPATH, "//label[contains(text(),'Odometro') or contains(text(),'Hodômetro')]/following::input[1]")
                        driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", campo_km)
                        time.sleep(0.8)
                        btn_salvar.click()
                        time.sleep(1.8)

                    salvo = True
                    ultima_placa_filtrada = ""
                    break
                except: continue

            time.sleep(1.5)
            fechar_alerta_se_existir(driver, log_container)

            if salvo:
                qtd_lancados += 1
                metric_lancados.metric("Lançados com Sucesso", qtd_lancados)
            else:
                qtd_ignorados += 1
                metric_ignorados.metric("Ignorados / Duplicados", qtd_ignorados)

        log_container.success("🎉 Todos os abastecimentos foram processados com sucesso!")

    except Exception as e:
        log_container.error(f"❌ Erro durante o processo: {e}")
    finally:
        driver.quit()

# ---------------------------------------------------------
# FLUXO PRINCIPAL COM BLOQUEIO DE SEGURANÇA
# ---------------------------------------------------------
if verificar_senha():
    # Cabeçalho Principal
    st.markdown('<div class="main-header">⛽ Central de Automação ZUQ</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Importe o relatório PDF de abastecimentos para sincronização automática com o sistema ZUQ.</div>', unsafe_allow_html=True)

    # Sidebar para Configurações e Encerramento de Sessão
    with st.sidebar:
        st.header("⚙️ Configurações do ZUQ")
        usuario_zuq = st.text_input("Usuário", value="manutencaoverdesmares")
        senha_zuq = st.text_input("Senha", type="password")
        url_zuq = st.text_input("URL ZUQ", value="https://app.zuq.com.br")
        fornecedor_zuq = st.text_input("Fornecedor Padrão", value="POSTO GURI - MACEIÓ")
        
        st.divider()
        modo_visivel = st.checkbox("Exibir Janela do Navegador", value=False, help="Marque se quiser ver a janela abrindo na tela (funciona apenas em testes locais).")

        st.divider()
        if st.button("🚪 Sair do Painel", use_container_width=True):
            st.session_state["autenticado"] = False
            st.rerun()

    # Área Principal
    col_upload, col_dashboard = st.columns([1, 1.2])

    with col_upload:
        st.subheader("1. Ficheiro PDF")
        uploaded_file = st.file_uploader("Selecione ou arraste o relatório de abastecimento", type=["pdf"])

        if uploaded_file:
            dados_df = extrair_dados_pdf(uploaded_file)
            st.success(f"Ficheiro lido! **{len(dados_df)}** abastecimentos identificados.")
            
            with st.expander("👁️ Ver prévia dos abastecimentos lidos"):
                st.dataframe(dados_df[['placa', 'data', 'quantidade', 'valor_unitario', 'km']], use_container_width=True)

    with col_dashboard:
        st.subheader("2. Painel de Progresso")
        
        m1, m2, m3 = st.columns(3)
        metric_total = m1.metric("Total no PDF", len(dados_df) if uploaded_file else 0)
        metric_lancados = m2.metric("Lançados com Sucesso", 0)
        metric_ignorados = m3.metric("Ignorados / Duplicados", 0)

        progress_bar = st.progress(0, text="Aguardando início...")
        log_container = st.container(height=350, border=True)

        if st.button("🚀 Iniciar Processamento", use_container_width=True):
            if not uploaded_file:
                st.error("Por favor, selecione um ficheiro PDF primeiro.")
            elif not senha_zuq:
                st.error("Por favor, informe a senha do ZUQ na barra lateral.")
            else:
                lancar_no_zuq(dados_df, url_zuq, usuario_zuq, senha_zuq, fornecedor_zuq, modo_visivel, log_container, progress_bar, metric_lancados, metric_ignorados)

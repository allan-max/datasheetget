# scrapers/epson.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class EpsonScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Epson] A iniciar Scraper (Motor SAP/CMS + Removedor de Rodapés)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Epson] A aceder a: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Epson] A aguardar renderização inicial...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.name, div.name"))
                )
            except:
                print("   ⚠️ Aviso: Título não encontrado rapidamente. A forçar a extração.")
            
            # --- ROLAGEM PROGRESSIVA ---
            print("   [Epson] A executar rolagem para carregar descrições e imagens...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- AUTO-CLICKER ---
            print("   [Epson] A expandir abas e painéis...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('.panel-heading a, .category-link, button');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto.includes('especificações') || 
                            texto.includes('visão geral') || 
                            texto.includes('ver mais')) {
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- LIMPEZA DE NOTAS DE RODAPÉ (Remove os <sup>1</sup>, <sup>2</sup>...) ---
            for sup in soup.find_all('sup'):
                sup.decompose()

            # --- TÍTULO ---
            titulo = "Produto Epson"
            h1 = soup.find('h1', class_=re.compile(r'name'))
            if h1:
                # Se tiver um span de SKU lá dentro, removemos para não colar ao título
                span_sku = h1.find('span', class_='sku')
                if span_sku: span_sku.decompose()
                titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Epson] A extrair Descrição...")
            descricao_bruta = ""
            
            # 1. Pega no texto principal (div.description)
            desc_div = soup.find('div', class_='description')
            if desc_div:
                # Extrai apenas os parágrafos normais (ignorando a Ficha Técnica que fica nas <ul> da descrição)
                ps = desc_div.find_all('p', recursive=False)
                for p in ps:
                    texto = p.get_text(separator=" ", strip=True)
                    if texto and "Calculadora de Distância" not in texto and "Informações de Segurança" not in texto:
                        descricao_bruta += texto + "\n\n"
            
            # 2. Pega nos blocos de texto extra (ex: Características Ambientais)
            modulos_texto = soup.find_all('div', class_='module-text-list')
            for modulo in modulos_texto:
                # Evita apanhar a parte do "O que está na caixa" para a descrição, pois vai para as specs
                if "O que está na caixa" not in modulo.get_text():
                    for li in modulo.find_all('li'):
                        txt_li = li.get_text(separator=" ", strip=True)
                        if txt_li:
                            descricao_bruta += f"• {txt_li}\n"
                    descricao_bruta += "\n"

            descricao = self.limpar_descricao_epson(descricao_bruta)
            if descricao and descricao != "Descrição indisponível.":
                print("   ✅ Descrição capturada com sucesso.")
            else:
                print("   ⚠️ Aviso: Não foi possível extrair a descrição completa.")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [Epson] A extrair Ficha Técnica e O que está na caixa...")
            specs = {}
            try:
                # 1. Extração dos "Category Items" (Imagens Mais Brilhantes, Instalação Simplificada, etc.)
                itens_categoria = soup.find_all('div', class_='category-item')
                for item in itens_categoria:
                    nome = item.find('div', class_='item-name')
                    info = item.find('div', class_='item-information')
                    if nome and info:
                        chave = self.limpar_texto(nome.get_text(strip=True))
                        valor = self.limpar_texto(info.get_text(strip=True))
                        if chave and valor:
                            specs[chave] = valor
                
                # 2. Extração do Modelo / SKU
                detalhes = soup.find('ul', class_='details')
                if detalhes:
                    li_modelo = detalhes.find('li', string=re.compile(r'Modelo|SKU', re.I))
                    if not li_modelo: # Estrutura <span class="key">Modelo:</span> <span class="value">V11H...</span>
                        span_keys = detalhes.find_all('span', class_='key')
                        span_vals = detalhes.find_all('span', class_='value')
                        for k, v in zip(span_keys, span_vals):
                            specs[self.limpar_texto(k.get_text()).replace(":", "")] = self.limpar_texto(v.get_text())

                # 3. Extração "O que está na caixa:"
                caixa_header = soup.find('h4', string=re.compile(r'O que está na caixa', re.I))
                if caixa_header:
                    ul_caixa = caixa_header.find_next_sibling('ul')
                    if ul_caixa:
                        itens_caixa = [li.get_text(strip=True) for li in ul_caixa.find_all('li') if li.get_text(strip=True)]
                        if itens_caixa:
                            specs["Conteúdo da Embalagem"] = "; ".join(itens_caixa)

                # Limpeza final
                specs_limpas = {}
                termos_proibidos_specs = ["garantia", "calculadora", "informações de segurança"]
                for k, v in specs.items():
                    k_lower = k.lower()
                    if not any(t in k_lower for t in termos_proibidos_specs):
                        specs_limpas[k] = v
                
                specs = specs_limpas
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs: {e}")

            # --- IMAGEM ---
            print("   [Epson] A extrair Imagem em Alta Resolução...")
            url_img = None
            caminho_imagem = None
            
            # Procura no meta tag (costuma ser a mais limpa)
            meta_img = soup.find("meta", property="og:image")
            if meta_img: 
                url_img = meta_img.get("content")
                
            # Se não encontrar, procura na galeria
            if not url_img:
                img_tag = soup.find('img', src=re.compile(r'mediaserver\.goepson\.com'))
                if img_tag: url_img = img_tag.get('src')

            if url_img:
                # TRUQUE EPSON: Alterar os parâmetros do URL para forçar o tamanho original
                # O URL geralmente tem &prid=1200Wx1200H ou similar. Substituímos por original.
                url_img = re.sub(r'&prid=[^&]+', '&prid=original', url_img)
                print(f"   [Epson] URL da imagem original encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Epson] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, ".modalImageWrapper img, .slick-active img")
                    if el_img:
                        filename = f"temp_img_epson_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Epson] A gerar ficheiros PDF/Word...")
            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1 if caminho_imagem else 0,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO EPSON] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_epson(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."

        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        termos_proibidos = [
            "garantia", "calculadora de distância", "informações de segurança", 
            "frete", "entrega", "pagamento"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                continue

            linha_lower = linha_clean.lower()

            if any(termo in linha_lower for termo in termos_proibidos):
                continue 
            
            linhas_limpas.append(linha_clean)

        return "\n\n".join(linhas_limpas)
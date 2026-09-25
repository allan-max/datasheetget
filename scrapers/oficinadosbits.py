# scrapers/oficinadosbits.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class OficinaDosBitsScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Oficina dos Bits] Iniciando Scraper (Extração de Specs corrigida e versão 153)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # --- Configuração Selenium Blindado ---
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument("--no-first-run")
            options.add_argument("--password-store=basic")
            options.add_argument(f'--user-agent={self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")}')
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=153)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Oficina dos Bits] Acessando: {self.url}")
            driver.get(self.url)

            # 1. Espera o título carregar
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "title-product"))
                )
            except:
                print("   [Oficina dos Bits] Aviso: Timeout esperando título h1.")

            # 2. Scroll para garantir carregamento de imagens e tabelas em lazy load
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 1500);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, 2500);")
            time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- 1. TÍTULO ---
            titulo = "Produto Oficina dos Bits"
            title_tag = soup.find('h1', class_=re.compile(r'title-product'))
            if title_tag: 
                titulo = self.limpar_texto(title_tag.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- 2. IMAGEM (ALTA RESOLUÇÃO) ---
            print("   [Oficina dos Bits] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_container = soup.find('a', class_=re.compile(r'sp-current-big'))
            if img_container and img_container.find('img'):
                url_img = img_container.find('img').get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img and meta_img.get("content"):
                    url_img = meta_img.get("content")

            if url_img:
                print(f"   [Oficina dos Bits] URL da Imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)
                
            if not caminho_imagem or not os.path.exists(caminho_imagem):
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    el_img = driver.find_element(By.CSS_SELECTOR, ".sp-large img, .sp-current-big img")
                    if el_img and el_img.is_displayed():
                        filename = f"temp_img_oficinadosbits_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        el_img.screenshot(caminho_imagem)
                except:
                    pass

            # --- 3. FICHA TÉCNICA (AGORA EXTRAÍDA ANTES DA LIMPEZA DA DESCRIÇÃO) ---
            print("   [Oficina dos Bits] Extraindo Ficha Técnica...")
            specs = {}
            tabela = soup.find('table', class_=re.compile(r'vit-tabela'))
            
            if tabela:
                linhas = tabela.find_all('tr')
                categoria_atual = ""
                
                for linha in linhas:
                    if 'vit-grupo' in linha.get('class', []) or linha.find('td', colspan="2"):
                        td_grupo = linha.find('td')
                        if td_grupo:
                            categoria_atual = self.limpar_texto(td_grupo.get_text())
                        continue
                        
                    th = linha.find('th')
                    td = linha.find('td')
                    
                    if th and td:
                        chave = self.limpar_texto(th.get_text())
                        valor = self.limpar_texto(td.get_text())
                        
                        ignorar = False
                        termos_proibidos = ["garantia", "sku", "código", "ean", "estoque"]
                        if any(t in chave.lower() for t in termos_proibidos):
                            ignorar = True
                            
                        if not ignorar and chave and valor:
                            nome_chave = f"[{categoria_atual}] {chave}" if categoria_atual else chave
                            specs[nome_chave] = valor

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- 4. DESCRIÇÃO (FORMATAÇÃO LIMPA E DESTRUTIVA) ---
            print("   [Oficina dos Bits] Formatando Descrição...")
            descricao_bruta = ""
            descricao_linhas = []
            
            desc_container = soup.find('div', class_=re.compile(r'vit-container'))
            
            if desc_container:
                # Remove seções que poluem o documento
                for sec in desc_container.find_all('section', class_=re.compile(r'vit-blog|vit-especificacoes')):
                    sec.decompose()
                
                # Remove spans com textos curtos para evitar texto duplicado
                for lixo in desc_container.find_all('span', class_=re.compile(r'vit-desc-short|vit-desc-card-short|vit-img-tag|vit-mini-section')):
                    lixo.decompose()

                elementos = desc_container.find_all(['h2', 'h3', 'p', 'ul'])
                for elem in elementos:
                    if elem.name in ['h2', 'h3']:
                        txt = self.limpar_texto(elem.get_text(separator=" "))
                        if txt: descricao_linhas.append(f"\n{txt.upper()}")
                    
                    elif elem.name == 'p':
                        txt = self.limpar_texto(elem.get_text(separator=" "))
                        if txt: descricao_linhas.append(txt)
                    
                    elif elem.name == 'ul':
                        for li in elem.find_all('li'):
                            txt = self.limpar_texto(li.get_text(separator=" "))
                            if txt: descricao_linhas.append(f"• {txt}")
                            
                descricao_bruta = "\n\n".join(descricao_linhas).strip()

            descricao = self.limpar_descricao_oficina(descricao_bruta)

            # --- FINALIZAÇÃO E LAVANDARIA DE IMAGEM ---
            arquivos_temporarios = [] 
            
            if caminho_imagem and os.path.exists(caminho_imagem):
                caminho_absoluto = os.path.abspath(caminho_imagem)
                arquivos_temporarios.append(caminho_absoluto) 
                
                try:
                    from PIL import Image
                    with Image.open(caminho_absoluto) as img:
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            fundo_branco = Image.new('RGB', img.size, (255, 255, 255))
                            fundo_branco.paste(img, (0, 0), img if img.mode == 'RGBA' else None)
                            img_final = fundo_branco
                        else:
                            img_final = img.convert('RGB')
                            
                        caminho_jpg = caminho_absoluto.rsplit('.', 1)[0] + '.jpg'
                        img_final.save(caminho_jpg, 'JPEG', quality=95)
                        
                    caminho_imagem = caminho_jpg.replace("\\", "/")
                    arquivos_temporarios.append(caminho_jpg) 
                    print("   ✅ Imagem convertida para JPEG (PDF Compatível)!")
                    
                except Exception as e:
                    print(f"   ⚠️ Erro ao processar imagem para PDF: {e}")
                    caminho_imagem = caminho_absoluto.replace("\\", "/")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            time.sleep(2) 
            
            print("   [Oficina dos Bits] Gerando arquivos finais (Word/PDF)...")
            arquivos = self.gerar_arquivos_finais(dados)
            
            # Limpeza final das imagens temporárias
            time.sleep(1) 
            for arq in set(arquivos_temporarios):
                for tentativa in range(3):
                    try:
                        if os.path.exists(arq):
                            os.remove(arq)
                        break 
                    except Exception:
                        time.sleep(1)
                    
            return {
                'sucesso': True, 
                'titulo': titulo, 
                'descricao': descricao, 
                'caracteristicas': specs, 
                'total_imagens': 1 if caminho_imagem else 0, 
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   ❌ [ERRO OFICINA DOS BITS] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_oficina(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        
        texto_limpo = re.sub(r' +', ' ', texto_bruto).strip()
        linhas = texto_limpo.split('\n')
        linhas_aprovadas = []
        
        termos_proibidos = [
            "tire suas dúvidas", "compre agora", "atendimento", "boleto", 
            "cartão", "entrega", "frete", "pagamento", "devolução"
        ]
        
        for linha in linhas:
            linha_lower = linha.lower()
            if len(linha) < 2: continue
            
            if not any(termo in linha_lower for termo in termos_proibidos):
                linhas_aprovadas.append(linha.strip())
                
        return "\n".join(linhas_aprovadas)
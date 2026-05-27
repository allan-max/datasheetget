# scrapers/xbz.py
import undetected_chromedriver as uc
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class XbzScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [XBZ] Iniciando Scraper (Extração Total de Blocos 'desc')...")
            
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
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.minimize_window() 
            
            print(f"   [XBZ] Acedendo: {self.url}")
            driver.get(self.url)
            time.sleep(3) # Tempo para garantir carregamento

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto XBZ"
            title_tag = soup.find(['p', 'h1'], class_=re.compile(r'produto-nome'))
            if not title_tag: title_tag = soup.find('h1')
            if title_tag: titulo = self.limpar_texto(title_tag.get_text())
            print(f"   ✅ Título: {titulo}")

            # --- PROCESSAMENTO DOS BLOCOS 'desc' ---
            print("   [XBZ] A extrair todos os blocos de informação...")
            descricao = "Descrição indisponível."
            specs = {}
            
            # Pega todas as divs que têm a classe 'desc'
            blocos_desc = soup.find_all('div', class_='desc')
            
            primeira_desc = True
            for bloco in blocos_desc:
                p_tit = bloco.find('p', class_='desc-tit')
                if not p_tit: continue
                
                # O título está no texto do <p>, o valor está no <span>
                texto_completo = p_tit.get_text(separator="|", strip=True)
                # Separamos pelo "|" que colocámos no separator
                partes = texto_completo.split("|")
                
                chave = partes[0].replace("Descrição:", "").strip()
                valor = partes[1] if len(partes) > 1 else ""
                
                # Se for o primeiro bloco e a chave for "Descrição", tratamos como descrição
                if primeira_desc and "descrição" in chave.lower():
                    descricao = self.limpar_lixo_comercial(valor)
                    primeira_desc = False
                else:
                    # Caso contrário, é Ficha Técnica
                    if chave and valor:
                        specs[chave] = valor

            # Filtros de limpeza
            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            
            print(f"   ✅ Descrição e {len(specs)} características capturadas.")

            # --- IMAGEM ---
            url_img = None
            caminho_imagem = None
            img_tag = soup.find('img', class_='media-object') or soup.find('img', id="imagem_principal")
            if img_tag:
                url_img = img_tag.get('data-original') or img_tag.get('src')
                if url_img and url_img.startswith("/"):
                    url_img = "https://www.xbzbrindes.com.br" + url_img
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            arquivos = self.gerar_arquivos_finais(dados)
            return {'sucesso': True, 'titulo': titulo, 'descricao': descricao, 'caracteristicas': specs, 'total_imagens': 1 if caminho_imagem else 0, 'arquivos': arquivos}

        except Exception as e:
            print(f"   ❌ [ERRO XBZ] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver: driver.quit()
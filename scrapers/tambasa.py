# scrapers/tambasa.py
import requests
from bs4 import BeautifulSoup
import os
import re
import time
from .base import BaseScraper

class TambasaScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Tambasa] Iniciando Scraper (Modo Rápido API)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            print(f"   [Tambasa] Acessando: {self.url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            }
            
            response = requests.get(self.url, headers=headers, timeout=30)
            
            if response.status_code == 429:
                print("   [Tambasa] [AVISO] Bloqueio 429 detectado. Aguardando 15s...")
                time.sleep(15)
                response = requests.get(self.url, headers=headers, timeout=30)
                
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Tambasa"
            h1 = soup.find("h1", class_=re.compile(r"product-name"))
            if h1:
                titulo = self.limpar_texto(h1.get_text())
            print(f"   [OK] Título capturado: {titulo}")

            # --- IMAGEM ---
            print("   [Tambasa] Extraindo Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_tag = soup.find("img", class_=re.compile(r"product-detail__large-image"))
            if img_tag:
                src = img_tag.get("data-zoom-image") or img_tag.get("src")
                if src:
                    if src.startswith("/"):
                        url_img = "https://tambasa.com" + src
                    else:
                        url_img = src

            if url_img:
                print(f"   [Tambasa] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- DESCRIÇÃO (COM LIMPEZA PROFUNDA E REMOÇÃO DE FAQ) ---
            descricao = "Descrição indisponível."
            desc_div = soup.find("div", class_="product-detail__descriptions-text")
            
            if desc_div:
                # 1. Remove códigos e scripts ocultos
                for tag in desc_div(["script", "style", "meta"]):
                    tag.decompose()
                
                # 1.5. A GUILHOTINA DO FAQ
                for header in desc_div.find_all(["h2", "h3", "h4", "strong", "p"]):
                    texto_header = header.get_text().lower()
                    if "perguntas frequentes" in texto_header or "faq" in texto_header:
                        for irmao in header.find_next_siblings():
                            irmao.decompose()
                        header.decompose()
                        break 
                
                # 2. Destruidor de parágrafos comerciais
                termos_extras = ["nota fiscal", "faturamento", "condição de pagamento", "faturado", "imposto", "garantia", "boleto", "cartão", "frete"]
                termos_verificacao = self.termos_proibidos + termos_extras
                
                for el in desc_div.find_all(["p", "li", "h2", "h3", "h4", "span", "strong"]):
                    texto_el = el.get_text().lower()
                    if any(termo in texto_el for termo in termos_verificacao):
                        el.decompose()
                
                # 3. Formata o que sobrou
                for br in desc_div.find_all("br"):
                    br.replace_with("\n")
                
                texto_bruto = desc_div.get_text(separator="\n", strip=True)
                linhas = [line.strip() for line in texto_bruto.split('\n') if len(line.strip()) > 0]
                texto_limpo = "\n".join(linhas)
                
                descricao = self.limpar_lixo_comercial(texto_limpo)

            # --- FICHA TÉCNICA (ATRIBUTOS) ---
            specs = {}
            attr_container = soup.find("div", class_="product-detail__descriptions-attributes")
            
            if attr_container:
                atributos = attr_container.find_all("div", class_="product-detail__attribute")
                for attr in atributos:
                    title_span = attr.find("span", class_="product-detail__attribute-title")
                    
                    text_span = attr.find("span", class_="product-detail__attribute-text")
                    if not text_span:
                        text_span = attr.find("a", class_=re.compile(r"product-detail__attribute-text"))
                        
                    if title_span and text_span:
                        chave = self.limpar_texto(title_span.get_text())
                        valor = self.limpar_texto(text_span.get_text())
                        
                        ignorar = False
                        for termo in termos_verificacao:
                            if termo in chave.lower() or termo in valor.lower():
                                ignorar = True
                                break
                                
                        if not ignorar and chave and valor:
                            specs[chave] = valor
                            
            print(f"   [OK] Especificações filtradas e capturadas: {len(specs)} itens.")

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Tambasa] Gerando arquivos finais...")
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
            print(f"   [ERRO TAMBASA] {e}")
            return {'sucesso': False, 'erro': str(e)}
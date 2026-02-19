# scrapers/quasetudo.py
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

# Desabilita avisos de segurança SSL (comum em alguns sites menores)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class QuaseTudoScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [QuaseTudo] Iniciando Scraper...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            # 1. Requisição Simples (Jeito Antigo)
            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            # Baseado no arquivo: <h1 itemprop="name" class="product_title ...">
            titulo = "Produto QuaseTudo"
            h1 = soup.find("h1", class_="product_title")
            if h1:
                titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM ---
            # Baseado no arquivo: <a class="avada-product-gallery-lightbox-trigger" href="...">
            url_img = None
            link_img = soup.find("a", class_="avada-product-gallery-lightbox-trigger")
            
            if link_img:
                url_img = link_img.get("href")
            
            # Fallback: Se não achar no link, tenta na img dentro dele
            if not url_img:
                img_tag = soup.find("img", class_="wp-post-image")
                if img_tag: url_img = img_tag.get("src")

            # --- DESCRIÇÃO E FICHA TÉCNICA ---
            # O site mistura tudo dentro de <div class="post-content">
            descricao = "Descrição indisponível."
            specs = {}
            
            div_content = soup.find("div", class_="post-content")
            
            if div_content:
                # Pega o texto preservando quebras de linha
                texto_bruto = div_content.get_text(separator="\n", strip=True)
                linhas = texto_bruto.splitlines()
                
                buffer_desc = []
                
                for linha in linhas:
                    linha = linha.strip()
                    if not linha: continue
                    
                    # Lógica de Separação baseada no padrão do site:
                    # Ex: "– MARCA: SHINKA"
                    # Verifica se começa com traço (– ou -) e tem dois pontos (:)
                    if (linha.startswith("–") or linha.startswith("-")) and ":" in linha:
                        # Remove o traço do início
                        linha_limpa = linha.lstrip("–- ").strip()
                        if ":" in linha_limpa:
                            chave, valor = linha_limpa.split(":", 1)
                            specs[chave.strip()] = valor.strip()
                    else:
                        # Se não for spec, é descrição
                        # Removemos títulos óbvios como "CARACTERÍSTICAS" ou separadores "----"
                        if "CARACTERÍSTICAS" in linha.upper() or "----" in linha:
                            continue
                        buffer_desc.append(linha)
                
                descricao = "\n".join(buffer_desc)

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": self.baixar_imagem_temp(url_img)
            }

            arquivos = self.gerar_arquivos_finais(dados)

            return {
                'sucesso': True,
                'titulo': titulo,
                'descricao': descricao,
                'caracteristicas': specs,
                'total_imagens': 1,
                'arquivos': arquivos
            }

        except Exception as e:
            print(f"   [ERRO QUASETUDO] {e}")
            return {'sucesso': False, 'erro': str(e)}
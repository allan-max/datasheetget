# scrapers/hayamax.py
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

# Desabilita avisos SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class HayamaxScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Hayamax] Iniciando Scraper (V2 - Filtro de Conteúdo)...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            # 1. Download da página
            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Hayamax"
            h1 = soup.find("h1", id="product-pid-title")
            if h1:
                titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM ---
            url_img = None
            img_tag = soup.find("img", id="product-image")
            
            if img_tag:
                url_img = img_tag.get("data-zoom-image")
                if not url_img:
                    url_img = img_tag.get("src")

            # --- DESCRIÇÃO E FICHA TÉCNICA ---
            descricao_linhas = []
            specs = {}
            
            # LISTA NEGRA: Termos que, se aparecerem, descartamos a linha inteira
            ignorar_termos = [
                "categorias", "conheça mais hayamax", "o que você deseja acessar?",
                "mais produtos", "hayamax utiliza cookies", "política de privacidade",
                "fale conosco", "carrinho", "minha conta", "meus pedidos",
                "procedimento de garantia", "devoluções", "garantias", 
                "voltar ao topo", "televendas", "institucional", "ajuda e suporte"
            ]

            paragrafos = soup.find_all("p")
            
            for p in paragrafos:
                texto = p.get_text(strip=True)
                if not texto: continue
                
                texto_lower = texto.lower()

                # 1. FILTRO GERAL (Lixo do Site e Cookies)
                # Se a linha contiver qualquer termo da lista negra, pula
                if any(termo in texto_lower for termo in ignorar_termos):
                    continue
                
                # Remove linhas muito curtas que não sejam especificações (ex: títulos de menu soltos)
                if len(texto) < 4 and ":" not in texto:
                    continue

                # 2. FILTRO ESPECÍFICO DE GARANTIA
                # Remove se começar com "Garantia" ou tiver link de garantia
                if texto_lower.startswith("garantia") or "hayamax.com.br/garantias" in texto_lower:
                    continue
                if "03 meses" in texto_lower and len(texto) < 20: # Remove prazos soltos
                    continue

                # --- CLASSIFICAÇÃO ---
                
                # É Ficha Técnica? (Tem ':' e é curto)
                if ":" in texto and len(texto) < 100:
                    partes = texto.split(":", 1)
                    chave = self.limpar_texto(partes[0])
                    valor = self.limpar_texto(partes[1])
                    
                    # Filtra garantia também aqui na chave
                    if "garantia" in chave.lower():
                        continue

                    if chave and valor:
                        specs[chave] = valor
                
                # É Descrição? (Texto longo e limpo)
                else:
                    # Verifica se não é um título repetido solto
                    if texto_lower not in ["descrição", "características", "especificações"]:
                        descricao_linhas.append(texto)

            descricao = "\n".join(descricao_linhas) if descricao_linhas else "Descrição indisponível."

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
            print(f"   [ERRO HAYAMAX] {e}")
            return {'sucesso': False, 'erro': str(e)}
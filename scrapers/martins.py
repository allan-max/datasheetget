# scrapers/martins.py
import requests
import re
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

# Desabilita avisos SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MartinsScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Martins] Iniciando Scraper (Requests)...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            # 1. Download
            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Martins"
            # Procura H1. Como as classes são dinâmicas (sc-...), pegamos o primeiro H1 relevante
            h1 = soup.find("h1")
            if h1:
                titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM ---
            url_img = None
            # O site usa data-nimg="responsive" para a imagem principal
            img_tag = soup.find("img", attrs={"data-nimg": "responsive"})
            
            if img_tag:
                url_img = img_tag.get("src")
            
            # Fallback: Procura imagens que tenham 'catalogoimg' na URL
            if not url_img:
                imgs = soup.find_all("img")
                for i in imgs:
                    src = i.get("src", "")
                    if "catalogoimg" in src and "martinsatacado" in src:
                        url_img = src
                        break

            # --- DESCRIÇÃO ---
            descricao_bruta = ""
            
            # O site divide a descrição em blocos com a classe "pdp-row-product-content"
            blocos_desc = soup.find_all("div", class_="pdp-row-product-content")
            
            if blocos_desc:
                texto_acumulado = []
                for bloco in blocos_desc:
                    # Pega o título do bloco (H3) e o texto (P)
                    h3 = bloco.find("h3")
                    p = bloco.find("p")
                    
                    if h3: texto_acumulado.append(h3.get_text(strip=True))
                    if p: texto_acumulado.append(p.get_text(separator="\n", strip=True))
                    texto_acumulado.append("") # Linha em branco entre blocos
                
                descricao_bruta = "\n".join(texto_acumulado)
            else:
                # Caso não tenha descrição (aviso do usuário no arquivo txt)
                print("   [DEBUG] Nenhuma descrição encontrada (padrão esperado para alguns produtos).")
                descricao_bruta = "Descrição indisponível no site."

            descricao = self.limpar_descricao_martins(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            
            # A ficha técnica fica bagunçada dentro de tags <p> com classes dinâmicas (sc-...)
            # Estratégia: Pegar todos os <p> que contêm ":" e parecem chave-valor
            
            # Procura container que tenha "Características" ou pega todos os paragrafos gerais
            paragrafos = soup.find_all("p")
            
            for p in paragrafos:
                texto = p.get_text(strip=True)
                
                # Verifica se tem o formato "Chave: Valor" e não é muito longo
                if ":" in texto and len(texto) < 100:
                    partes = texto.split(":", 1)
                    chave = self.limpar_texto(partes[0])
                    valor = self.limpar_texto(partes[1])
                    
                    # Filtra falsos positivos (ex: horários, frases comuns)
                    if chave and valor and len(chave) > 2 and "http" not in valor:
                        # Evita sobrescrever chaves duplicadas (ex: Altura aparece 2x)
                        if chave in specs:
                            chave = f"{chave} (Detalhe)"
                        specs[chave] = valor

            specs = self.filtrar_specs_martins(specs)

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
            print(f"   [ERRO MARTINS] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def limpar_descricao_martins(self, texto_bruto):
        if not texto_bruto: return ""
        
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        frases_banidas = [
            "garantia", 
            "fornecedor", 
            "imagens meramente ilustrativas"
        ]

        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: 
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            
            linha_lower = linha_clean.lower()
            
            # Remove linhas de garantia conforme solicitado
            if any(banida in linha_lower for banida in frases_banidas):
                continue
            
            # Remove linhas que sejam apenas "Características do Produto" (pois já vai pra ficha técnica)
            if "características do produto" in linha_lower:
                continue

            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas)

    def filtrar_specs_martins(self, specs):
        specs_limpas = {}
        # Lista negra para limpar a ficha técnica
        ignorar = ["garantia", "fornecedor", "informações adicionais", "características do produto"]
        
        for k, v in specs.items():
            k_lower = k.lower()
            
            # Pula se a chave estiver na lista negra
            if any(x in k_lower for x in ignorar):
                continue
                
            specs_limpas[k] = v
            
        return specs_limpas
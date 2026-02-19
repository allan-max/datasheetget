# scrapers/kalunga.py
import requests
import re
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class KalungaScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Kalunga] Iniciando Scraper (V7 - Divisão por Texto)...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Kalunga"
            h1 = soup.find("h1", class_="headerprodutosinfos__title")
            if h1:
                titulo = self.limpar_texto(h1.get_text())

            # --- IMAGEM ---
            url_img = None
            img_tag = soup.find("img", id="imgProduct")
            if img_tag:
                url_img = img_tag.get("src") or img_tag.get("data-src")
            if url_img and not url_img.startswith("http"):
                 url_img = "https:" + url_img if url_img.startswith("//") else "https://www.kalunga.com.br" + url_img

            # --- DIVISÃO ROBUSTA (TEXT SPLIT) ---
            descricao = "Descrição indisponível."
            specs = {}
            
            # Tenta pegar a div mais interna (que tem o texto real)
            div_alvo = soup.find("div", id="descricaoPadrao")
            
            # Fallback para a div pai se a interna não existir
            if not div_alvo:
                div_alvo = soup.find("div", id="descricao-produto")
            
            if div_alvo:
                # 1. Limpeza de Inmetro (se houver)
                junk = div_alvo.find("div", class_="descricaoproduto__inmetro")
                if junk: junk.decompose()

                # 2. Pega TODO o texto bruto com quebras de linha
                texto_completo = div_alvo.get_text(separator="\n", strip=True)
                
                # 3. Corta o texto na palavra "Especificações" (case insensitive)
                # O regex abaixo procura por "Especificações", "Especificacoes", "ESPECIFICAÇÕES"
                divisao = re.split(r'Especifica[çc][õo]es', texto_completo, flags=re.IGNORECASE, maxsplit=1)
                
                if len(divisao) > 1:
                    # Achou o divisor!
                    texto_desc = divisao[0]
                    texto_specs = divisao[1]
                    
                    # Processa a Ficha Técnica (Parte 2)
                    for linha in texto_specs.splitlines():
                        linha = linha.strip()
                        # Ignora linhas vazias ou traços soltos
                        if not linha or set(linha) <= {'-', '_', '.', ' '}: continue
                        
                        if ":" in linha:
                            # Formato "Chave: Valor"
                            partes = linha.split(":", 1)
                            specs[partes[0].strip()] = partes[1].strip()
                        else:
                            # Formato "Item solto" (ex: "Atóxico") -> Vira característica numerada
                            specs[f"Característica {len(specs)+1}"] = linha
                    
                    descricao = texto_desc
                else:
                    # Não achou divisor -> Tudo é Descrição
                    descricao = texto_completo

            descricao = self.limpar_descricao_kalunga(descricao)
            specs = self.filtrar_specs_kalunga(specs)

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
            print(f"   [ERRO KALUNGA] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def limpar_descricao_kalunga(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        ignorar = ["Características do Produto", "Dados Técnicos"]
        
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: 
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            
            # Remove o título que geralmente fica sobrando no topo
            if any(x in linha_clean for x in ignorar): continue
            if set(linha_clean) <= {'-', '_', ' ', '.'}: continue

            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas)

    def filtrar_specs_kalunga(self, specs):
        specs_limpas = {}
        ignorar = ["garantia", "código", "marca", "referência"] 
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                v = v.replace("•", "").strip() # Limpa bullet points que sobraram
                specs_limpas[k] = v
        return specs_limpas
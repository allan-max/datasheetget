# scrapers/dutramaquinas.py
import requests
import re
from bs4 import BeautifulSoup
from .base import BaseScraper
import urllib3

# Desabilita avisos de segurança SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DutraMaquinasScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Dutra] Iniciando Scraper (V3 - Fix Encoding e Interrogações)...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }

            # 1. Download do HTML
            response = requests.get(self.url, headers=headers, timeout=20, verify=False)
            
            # --- CORREÇÃO DE ENCODING ---
            # O requests as vezes erra. Vamos forçar utf-8 se ele achar que é ISO mas o site for moderno
            if response.encoding == 'ISO-8859-1':
                response.encoding = response.apparent_encoding
            
            if response.status_code != 200:
                raise Exception(f"Erro HTTP {response.status_code}")

            soup = BeautifulSoup(response.text, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Dutra"
            h1 = soup.find("h1", class_="titulo")
            if h1:
                titulo = self.limpar_texto_especial(h1.get_text())

            # --- IMAGEM ---
            url_img = None
            meta_img = soup.find("meta", property="og:image")
            if meta_img:
                url_img = meta_img.get("content")
            
            if not url_img:
                img_tag = soup.find("img", class_="image-produto")
                if img_tag:
                    url_img = img_tag.get("data-original") or img_tag.get("src")

            if url_img and not url_img.startswith("http"):
                url_img = "https://www.dutramaquinas.com.br" + url_img

            # --- DESCRIÇÃO (LÓGICA "MELHOR CANDIDATO") ---
            descricao_bruta = ""
            candidatos = soup.find_all("div", class_="texto")
            melhor_texto = ""
            
            for div in candidatos:
                texto = div.get_text(separator="\n", strip=True)
                texto_lower = texto.lower()
                
                # Filtra blocos de pagamento/juros
                if "formas de pagamento" in texto_lower or "cartão de crédito" in texto_lower or "juros" in texto_lower:
                    continue
                
                if len(texto) < 50:
                    continue

                if len(texto) > len(melhor_texto):
                    melhor_texto = texto

            descricao_bruta = melhor_texto
            
            # Fallback
            if not descricao_bruta:
                painel_desc = soup.find(id="descricao")
                if painel_desc:
                    descricao_bruta = painel_desc.get_text(separator="\n", strip=True)

            descricao = self.limpar_descricao_dutra(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            tabela = soup.find("table", class_="dados-tecnicos-produto")
            
            if tabela:
                linhas = tabela.find_all("tr")
                for linha in linhas:
                    colunas = linha.find_all("td")
                    if len(colunas) >= 2:
                        # Limpa chaves e valores removendo ?
                        chave = self.limpar_texto_especial(colunas[0].get_text())
                        valor = self.limpar_texto_especial(colunas[1].get_text())
                        chave = chave.replace(":", "")
                        if chave and valor:
                            specs[chave] = valor

            specs = self.filtrar_specs_dutra(specs)

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
            print(f"   [ERRO DUTRA] {e}")
            return {'sucesso': False, 'erro': str(e)}

    def limpar_texto_especial(self, texto):
        """Versão turbinada do limpar_texto que remove ?"""
        if not texto: return ""
        # Remove espaços extras
        txt = " ".join(texto.split())
        # Substitui ? por espaço (para não grudar palavras)
        txt = txt.replace("?", " ")
        # Remove duplo espaço gerado pela substituição acima
        txt = " ".join(txt.split())
        return txt

    def limpar_descricao_dutra(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean:
                if linhas_limpas and linhas_limpas[-1] != "": linhas_limpas.append("")
                continue
            
            # REMOÇÃO DE INTERROGAÇÕES
            # Substitui por espaço para evitar "Palavra?Outra" -> "PalavraOutra"
            linha_clean = linha_clean.replace("?", " ")
            # Remove excesso de espaços causado pela substituição
            linha_clean = " ".join(linha_clean.split())

            if "garantia" in linha_clean.lower() and "meses" in linha_clean.lower():
                continue

            if linha_clean.lower() == "descrição" or linha_clean.lower() == "detalhes":
                continue

            linhas_limpas.append(linha_clean)

        return "\n".join(linhas_limpas)

    def filtrar_specs_dutra(self, specs):
        specs_limpas = {}
        ignorar = ["itens inclusos", "preço", "parcelas", "juros", "ver parcelas"]
        
        for k, v in specs.items():
            k_lower = k.lower()
            if not any(x in k_lower for x in ignorar):
                specs_limpas[k] = v
        return specs_limpas
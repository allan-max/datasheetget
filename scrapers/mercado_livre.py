# scrapers/mercadolivre.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import os
import re
import json
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Mercado Livre] Iniciando Scraper (Estratégia Híbrida: Chrome + API do Servidor)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # 1. ENGENHARIA REVERSA DO LINK
            match = re.search(r'MLB[-]?(\d+)', self.url, re.IGNORECASE)
            if not match:
                print("   ⚠️ Erro: Não foi possível identificar o código do produto (MLB) no link.")
                return {'sucesso': False, 'erro': 'Código MLB não encontrado no link.'}
                
            item_id = f"MLB{match.group(1)}"
            print(f"   [Mercado Livre] ID do Produto Detetado: {item_id}")

            # 2. INICIALIZAR CHROME BLINDADO
            # O Chrome passa pelo Firewall 403 que bloqueou a biblioteca requests
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

            # 3. ACESSAR A API USANDO O NAVEGADOR (Bypass da Tela de Login)
            url_api = f"https://api.mercadolibre.com/items/{item_id}"
            print("   [Mercado Livre] Lendo dados da API pelo navegador (1/2)...")
            driver.get(url_api)
            time.sleep(1.5) # Aguarda o JSON carregar
            
            # O Chrome vai exibir apenas o texto da API na tela. Vamos extrair isso:
            body = driver.find_element(By.TAG_NAME, "body").text
            
            try:
                dados_ml = json.loads(body)
            except Exception as e:
                print("   ⚠️ Erro ao converter JSON da API.")
                return {'sucesso': False, 'erro': 'Formato inválido retornado pelo ML.'}

            if 'error' in dados_ml:
                return {'sucesso': False, 'erro': f"Erro reportado pelo ML: {dados_ml.get('message')}"}

            # --- TÍTULO ---
            titulo = self.limpar_texto(dados_ml.get('title', 'Produto Mercado Livre'))
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM DE ALTA RESOLUÇÃO ---
            print("   [Mercado Livre] A extrair Imagem Gigante...")
            caminho_imagem = None
            fotos = dados_ml.get('pictures', [])
            if fotos:
                url_img = fotos[0].get('secure_url') or fotos[0].get('url')
                if url_img:
                    caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- DESCRIÇÃO ---
            print("   [Mercado Livre] Lendo descrição da API (2/2)...")
            descricao = "Descrição indisponível."
            url_desc = f"https://api.mercadolibre.com/items/{item_id}/description"
            driver.get(url_desc)
            time.sleep(1.5)
            
            body_desc = driver.find_element(By.TAG_NAME, "body").text
            try:
                dados_desc = json.loads(body_desc)
                descricao_bruta = dados_desc.get('plain_text', '')
                descricao = self.limpar_descricao_ml(descricao_bruta)
                print("   ✅ Descrição formatada.")
            except:
                print("   ⚠️ Aviso: Não foi possível obter a descrição.")

            # --- FICHA TÉCNICA ---
            print("   [Mercado Livre] A compilar Ficha Técnica...")
            specs = {}
            atributos = dados_ml.get('attributes', [])
            
            for attr in atributos:
                chave = attr.get('name')
                valor = attr.get('value_name')
                
                if chave and valor:
                    chave = self.limpar_texto(chave)
                    valor = self.limpar_texto(valor)
                    
                    ignorar = False
                    termos_proibidos = ["garantia", "código universal", "sku", "ean", "gtin", "condição"]
                    if any(t in chave.lower() for t in termos_proibidos): ignorar = True
                        
                    if not ignorar:
                        specs[chave] = valor

            if hasattr(self, 'filtrar_specs'): specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E CORREÇÃO DE PDF ---
            if caminho_imagem and os.path.exists(caminho_imagem):
                caminho_absoluto = os.path.abspath(caminho_imagem)
                caminho_imagem = caminho_absoluto.replace("\\", "/")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Mercado Livre] A gerar PDF e Word instantâneos...")
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
            print(f"   ❌ [ERRO MERCADO LIVRE] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_ml(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        termos_proibidos = [
            "garantia", "mercado envio", "mercado pago", "tire suas dúvidas", 
            "perguntas", "clique em comprar", "aguardamos sua compra", "frete", 
            "atendimento", "nota fiscal", "nf-e", "pronta entrega"
        ]
        
        for linha in linhas:
            linha_lower = linha.lower().strip()
            if not linha_lower: continue
            if any(termo in linha_lower for termo in termos_proibidos): continue
            linhas_limpas.append(linha.strip())
            
        return "\n\n".join(linhas_limpas)
# scrapers/mercadolivre.py
import requests
import os
import re
import time
from .base import BaseScraper

class MercadoLivreScraper(BaseScraper):
    def executar(self):
        try:
            print(f"   [Mercado Livre] Iniciando Scraper (Modo API Fantasma - Zero Bloqueios)...")
            
            if not hasattr(self, 'output_folder') or not self.output_folder: 
                self.output_folder = "output"
            if not os.path.exists(self.output_folder): 
                os.makedirs(self.output_folder)

            # 1. ENGENHARIA REVERSA DO LINK
            # O link do ML tem sempre um ID do tipo "MLB-12345678". Precisamos extrair esse ID.
            match = re.search(r'MLB[-]?(\d+)', self.url, re.IGNORECASE)
            if not match:
                print("   ⚠️ Erro: Não foi possível identificar o código do produto (MLB) no link.")
                return {'sucesso': False, 'erro': 'Código MLB não encontrado no link.'}
                
            item_id = f"MLB{match.group(1)}"
            print(f"   [Mercado Livre] ID do Produto Detetado: {item_id}")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }

            # 2. ACESSO PELA PORTA DOS FUNDOS (API PÚBLICA DO MERCADO LIVRE)
            # Traz todos os dados do produto num formato estruturado, sem bloqueios de login!
            url_api = f"https://api.mercadolibre.com/items/{item_id}"
            resp = requests.get(url_api, headers=headers)
            
            if resp.status_code != 200:
                print(f"   ⚠️ Erro na API do ML: {resp.status_code}")
                return {'sucesso': False, 'erro': f'Erro ao contactar o servidor do Mercado Livre: {resp.status_code}'}

            dados_ml = resp.json()

            # --- TÍTULO ---
            titulo = self.limpar_texto(dados_ml.get('title', 'Produto Mercado Livre'))
            print(f"   ✅ Título capturado: {titulo}")

            # --- IMAGEM DE ALTA RESOLUÇÃO ---
            print("   [Mercado Livre] A extrair Imagem Gigante...")
            caminho_imagem = None
            fotos = dados_ml.get('pictures', [])
            if fotos:
                # O ML entrega a "secure_url" que é a imagem original sem cortes
                url_img = fotos[0].get('secure_url') or fotos[0].get('url')
                if url_img:
                    print(f"   [Mercado Livre] URL da imagem encontrada: {url_img}")
                    caminho_imagem = self.baixar_imagem_temp(url_img)

            # --- DESCRIÇÃO ---
            print("   [Mercado Livre] A puxar Descrição do Servidor...")
            descricao = "Descrição indisponível."
            url_desc = f"https://api.mercadolibre.com/items/{item_id}/description"
            resp_desc = requests.get(url_desc, headers=headers)
            
            if resp_desc.status_code == 200:
                dados_desc = resp_desc.json()
                descricao_bruta = dados_desc.get('plain_text', '')
                descricao = self.limpar_descricao_ml(descricao_bruta)
                print("   ✅ Descrição formatada.")

            # --- FICHA TÉCNICA (Especificações limpas direto do banco de dados) ---
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
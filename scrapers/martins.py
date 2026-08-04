# scrapers/martins.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class MartinsScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Martins Atacado] Iniciando Scraper (Caçador JS e Clicker HTML cru)...")
            
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
            options.add_argument("--window-size=1920,1080")
            
            driver = uc.Chrome(options=options, version_main=109)
            driver.set_window_size(1920, 1080)
            
            print(f"   [Martins Atacado] Acessando: {self.url}")
            driver.get(self.url)

            # 1. Espera a página processar os scripts do React (Pausa humana)
            time.sleep(4) 
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)
            
            # --- O SEGREDO DO CLIQUE: LEITURA DE HTML CRU (Ignora o <!-- -->) ---
            print("   [Martins Atacado] Forçando clique no botão 'Ver Mais'...")
            driver.execute_script("""
                var els = document.querySelectorAll('a, button, span, div');
                for (var i = 0; i < els.length; i++) {
                    var htmlInterno = els[i].innerHTML || '';
                    // Se o HTML cru tiver "Ver" e "Mais", independentemente de comentários no meio, ele clica
                    if (htmlInterno.includes('Ver') && htmlInterno.includes('Mais')) {
                        try { els[i].click(); } catch(e) {}
                    }
                }
            """)
            
            # Aguarda a animação do painel (Collapse) revelar as especificações
            time.sleep(2)
            driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(1)

            # --- CAPTURA DA IMAGEM: O CAÇADOR DE ALTA RESOLUÇÃO ---
            print("   [Martins Atacado] Procurando a imagem de maior resolução...")
            url_img = driver.execute_script("""
                var imgs = document.getElementsByTagName('img');
                var bestImg = '';
                var maxArea = 0;
                for(var i = 0; i < imgs.length; i++) {
                    // Calcula os pixeis reais da imagem (ignora o tamanho no ecrã)
                    var area = imgs[i].naturalWidth * imgs[i].naturalHeight;
                    var src = imgs[i].src || '';
                    
                    // Foge de logotipos, ícones e SVGs
                    if(area > maxArea && src && !src.includes('logo') && !src.includes('icon') && !src.includes('svg')) {
                        maxArea = area;
                        bestImg = src;
                    }
                }
                return bestImg;
            """)

            caminho_imagem = None
            if url_img:
                print(f"   [Martins Atacado] URL da Imagem GIGANTE encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)
            else:
                print("   ⚠️ Nenhuma imagem de alta resolução retornada pelo JS.")

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Martins Atacado"
            h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO E FICHA TÉCNICA (EXTRAÇÃO DO BLOCO MUI) ---
            print("   [Martins Atacado] Lendo o bloco de Especificações revelado...")
            descricao = "Descrição indisponível."
            specs = {}
            
            # Procura a div específica MuiCollapse-wrapperInner
            collapse = soup.find('div', class_=re.compile(r'MuiCollapse-wrapperInner'))
            
            if collapse:
                # Extrai a Descrição (dentro do H2 ou P)
                h2 = collapse.find('h2')
                if h2:
                    for br in h2.find_all("br"): br.replace_with("\n")
                    descricao = self.limpar_texto(h2.get_text(separator="\n"))
                
                # Extrai a Ficha Técnica (Tabela dentro do collapse)
                tabela = collapse.find('table')
                if tabela:
                    linhas = tabela.find_all('tr')
                    for linha in linhas:
                        tds = linha.find_all(['th', 'td'])
                        if len(tds) >= 2:
                            chave = self.limpar_texto(tds[0].get_text())
                            valor = self.limpar_texto(tds[1].get_text())
                            
                            ignorar = False
                            termos_proibidos = ["garantia", "código", "sku", "ean", "gtin", "estoque"]
                            if any(t in chave.lower() for t in termos_proibidos):
                                ignorar = True
                                
                            if not ignorar and chave and valor:
                                specs[chave] = valor
            else:
                print("   ⚠️ Aviso: Bloco MuiCollapse-wrapperInner não encontrado após o clique.")

            if hasattr(self, 'filtrar_specs'):
                specs = self.filtrar_specs(specs)
            print(f"   ✅ Specs encontradas: {len(specs)} itens.")

            # --- FINALIZAÇÃO E CORREÇÃO DE PDF ---
            # Força o caminho absoluto e inverte barras para o gerador de PDF ler sem falhas
            if caminho_imagem and os.path.exists(caminho_imagem):
                caminho_absoluto = os.path.abspath(caminho_imagem)
                caminho_imagem = caminho_absoluto.replace("\\", "/")

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }
            
            print("   [Martins Atacado] Gerando arquivos finais...")
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
            print(f"   ❌ [ERRO MARTINS ATACADO] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    def limpar_descricao_martins(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        
        texto_limpo = re.sub(r'\s+', ' ', texto_bruto).strip()
        frases = re.split(r'(?<=[.!?])\s+', texto_limpo)
        frases_aprovadas = []
        
        termos_proibidos = [
            "garantia", "meses", "tire suas dúvidas", "compre agora",
            "atendimento", "boleto", "cartão", "entrega", "frete",
            "pagamento", "devolução"
        ]
        
        for frase in frases:
            frase_lower = frase.lower()
            if len(frase) < 4: continue
            
            if not any(termo in frase_lower for termo in termos_proibidos):
                frases_aprovadas.append(frase.strip())
                
        return "\n\n".join(frases_aprovadas)
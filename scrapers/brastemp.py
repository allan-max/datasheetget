# scrapers/brastemp.py
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import os
import re
from .base import BaseScraper

class BrastempScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Brastemp] Iniciando Scraper (Motor Whirlpool/VTEX)...")
            
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
            
            print(f"   [Brastemp] Acedendo: {self.url}")
            driver.set_page_load_timeout(30)
            driver.get(self.url)
            
            print("   [Brastemp] A aguardar renderização inicial...")
            try:
                # Aguarda o título específico da Brastemp ou o genérico da VTEX
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.btp-product-title__title-new, h1[class*='productName']"))
                )
            except:
                print("   ⚠️ Aviso: H1 não encontrado rapidamente. A tentar continuar a extração.")
            
            # --- 1. ROLAGEM PROGRESSIVA (Garante o carregamento de imagens e blocos dinâmicos) ---
            print("   [Brastemp] A vasculhar a página para contornar o Lazy Load...")
            for i in range(5):
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(1)
            
            # --- 2. DESTRUIDOR DE BOTÕES DE CATÁLOGO (Expandir) ---
            print("   [Brastemp] A clicar nos botões de expansão de ficha técnica...")
            driver.execute_script("""
                var botoes = document.querySelectorAll('button, a, span, div');
                for (var i = 0; i < botoes.length; i++) {
                    if(botoes[i].innerText) {
                        var texto = botoes[i].innerText.toLowerCase().trim();
                        if (texto === 'ver mais' || 
                            texto.includes('mais informações') || 
                            texto.includes('especificações') || 
                            texto.includes('características')) {
                            
                            if(botoes[i].tagName.toLowerCase() === 'a') {
                                botoes[i].removeAttribute('href');
                            }
                            try { botoes[i].click(); } catch(e) {}
                        }
                    }
                }
            """)
            time.sleep(2)
            
            driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO ---
            titulo = "Produto Brastemp"
            h1 = soup.find('h1', class_=re.compile(r'btp-product-title__title-new|productNameContainer'))
            if not h1: h1 = soup.find('h1')
            if h1: titulo = self.limpar_texto(h1.get_text())
            print(f"   ✅ Título capturado: {titulo}")

            # --- DESCRIÇÃO ---
            print("   [Brastemp] A extrair Descrição...")
            descricao = "Descrição indisponível."
            try:
                descricao_bruta = driver.execute_script("""
                    var text = '';
                    
                    // Estratégia Principal: Layout Whirlpool (Cartões de Diferenciais)
                    var cards = document.querySelectorAll('.whirlpool-styleguide-0-x-whp_styleguide-imageTextCard--texts');
                    if (cards.length > 0) {
                        cards.forEach(c => {
                            var h3 = c.querySelector('h3');
                            var p = c.querySelector('p');
                            if(h3) text += h3.innerText.trim() + '\\n';
                            if(p) text += p.innerText.trim() + '\\n\\n';
                        });
                    }
                    
                    // Estratégia de Fallback: VTEX Genérico
                    if (text.length < 15) {
                        var desc = document.querySelector('.productDescriptionText, .productDescription');
                        if (desc) text = desc.innerText;
                    }
                    
                    return text;
                """)
                
                # Se não apanhou via JS, usa o BeautifulSoup como rede de segurança
                if not descricao_bruta or len(descricao_bruta.strip()) < 15:
                    cards_bs4 = soup.find_all('div', class_=re.compile(r"imageTextCard--texts"))
                    if cards_bs4:
                        linhas = []
                        for card in cards_bs4:
                            h3 = card.find('h3')
                            p = card.find('p')
                            if h3: linhas.append(h3.get_text(strip=True))
                            if p: linhas.append(p.get_text(strip=True) + "\n")
                        descricao_bruta = "\n".join(linhas)

                if descricao_bruta and len(descricao_bruta.strip()) > 10:
                    descricao = self.limpar_lixo_comercial(descricao_bruta.strip())
                    print("   ✅ Descrição capturada com sucesso.")
                else:
                    print("   ⚠️ Aviso: Não foi possível extrair a descrição.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair descrição: {e}")

            # --- CARACTERÍSTICAS TÉCNICAS ---
            print("   [Brastemp] A extrair Ficha Técnica...")
            specs = {}
            try:
                specs_dict = driver.execute_script("""
                    var specs = {};
                    
                    // A Brastemp usa listas onde o texto é "Chave: Valor"
                    var items = document.querySelectorAll('.whp_styleguide-producttechnicaltable p, .whirlpool-styleguide-0-x-whp_styleguide-technicalSpecifications-alert p');
                    
                    if (items.length > 0) {
                        items.forEach(p => {
                            var text = p.innerText.trim();
                            if(text.includes(':')) {
                                var parts = text.split(':');
                                var key = parts.shift().trim(); // Apanha a primeira parte antes dos dois pontos
                                var val = parts.join(':').trim(); // Junta o resto caso o valor também tenha dois pontos
                                if(key && val) {
                                    specs[key] = val;
                                }
                            }
                        });
                    } else {
                        // Fallback para Tabela VTEX tradicional
                        var rows = document.querySelectorAll('tr');
                        rows.forEach(r => {
                            var th = r.querySelector('th');
                            var td = r.querySelector('td');
                            if(th && td) {
                                var key = th.innerText.trim();
                                var val = td.innerText.trim();
                                if(key && val && key !== val) specs[key] = val;
                            }
                        });
                    }
                    return specs;
                """)
                
                if specs_dict:
                    for k, v in specs_dict.items():
                        chave_limpa = self.limpar_texto(k)
                        valor_limpo = self.limpar_texto(v)
                        
                        # Filtro rigoroso adaptado aos textos da Brastemp
                        ignorar = False
                        termos_proibidos_specs = [
                            "garantia", "ean", "referência", "palavra chave", 
                            "sku", "sac", "nota fiscal", "textos legais", "itens inclusos na embalagem"
                        ]
                        if any(t in chave_limpa.lower() or t in valor_limpo.lower() for t in termos_proibidos_specs):
                            ignorar = True

                        if not ignorar and chave_limpa and valor_limpo:
                            specs[chave_limpa] = valor_limpo
                            
                if hasattr(self, 'filtrar_specs'):
                    specs = self.filtrar_specs(specs)
                    
                print(f"   ✅ Specs encontradas: {len(specs)} itens.")
            except Exception as e:
                print(f"   ⚠️ Erro ao extrair specs via JS: {e}")

            # --- IMAGEM ---
            print("   [Brastemp] A extrair Imagem...")
            url_img = None
            caminho_imagem = None
            
            img_container = soup.find('img', class_=re.compile(r'productImageTag--main|productImageTag'))
            if img_container:
                url_img = img_container.get('src')
                
            if not url_img:
                meta_img = soup.find("meta", property="og:image")
                if meta_img: url_img = meta_img.get("content")

            if url_img:
                print(f"   [Brastemp] URL da imagem encontrada: {url_img}")
                caminho_imagem = self.baixar_imagem_temp(url_img)

            if not caminho_imagem or not os.path.exists(caminho_imagem):
                print("   [Brastemp] A recorrer ao Screenshot da imagem principal...")
                try:
                    driver.execute_script("window.scrollTo(0, 0);")
                    el_img = driver.find_element(By.CSS_SELECTOR, "img[class*='productImageTag--main'], img[class*='productImageTag']")
                    if el_img:
                        filename = f"temp_img_brastemp_{int(time.time())}.png"
                        caminho_imagem = os.path.join(self.output_folder, filename)
                        
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el_img)
                        time.sleep(1)
                        el_img.screenshot(caminho_imagem)
                        print("   ✅ Imagem salva via screenshot!")
                except:
                    pass

            # --- FINALIZAÇÃO ---
            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem
            }

            print("   [Brastemp] A gerar ficheiros PDF/Word...")
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
            print(f"   ❌ [ERRO BRASTEMP] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                try: driver.quit()
                except: pass
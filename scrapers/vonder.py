# scrapers/vonder.py
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import re
import requests
import os
import uuid
import ssl
import subprocess
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from .base import BaseScraper

# --- ADAPTADOR SSL (SECLEVEL=0) ---
class UnsafeSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False):
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        try:
            ctx.set_ciphers('ALL:@SECLEVEL=0') 
        except:
            ctx.set_ciphers('DEFAULT')
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=ctx
        )

class VonderScraper(BaseScraper):
    def executar(self):
        driver = None
        try:
            print(f"   [Vonder] Iniciando Scraper (V9 - Validação de Imagem)...")
            
            opts = Options()
            opts.add_argument("--headless=new") 
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument('--ignore-certificate-errors')
            opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")

            driver = webdriver.Chrome(options=opts)
            driver.get(self.url)

            # 1. Espera Título
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "nomeProduto"))
                )
            except: pass
            
            # 2. Scroll
            driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')

            # --- TÍTULO E CÓDIGO ---
            titulo = "Produto Vonder"
            codigo_produto = ""
            h1 = soup.find("h1", class_="nomeProduto")
            if h1:
                label_cod = h1.find("label", id="codigoProduto")
                if label_cod:
                    codigo_produto = self.limpar_texto(label_cod.get_text())
                
                titulo_texto = h1.get_text()
                if codigo_produto:
                    titulo_texto = titulo_texto.replace(codigo_produto, "").strip()
                titulo = self.limpar_texto(titulo_texto)

            # --- CAPTURA URL IMAGEM ---
            url_img = None
            try:
                js_img = """
                    var img = document.getElementById('imgProd1');
                    if (img) return img.currentSrc || img.src;
                    var zoom = document.querySelector('.jqzoom');
                    if (zoom) return zoom.href;
                    return '';
                """
                url_img = driver.execute_script(js_img)
            except: pass

            if not url_img:
                img_tag = soup.find("img", id="imgProd1")
                if img_tag: url_img = img_tag.get("src")

            if url_img:
                if not url_img.startswith("http"):
                    base = "https://www.vonder.com.br"
                    if not url_img.startswith("/"): base += "/"
                    url_img = base + url_img

            # --- DOWNLOAD COM VALIDAÇÃO ---
            caminho_imagem = None
            if url_img:
                print(f"   [DEBUG] URL detectada: {url_img}")
                caminho_imagem = self.baixar_imagem_validada(url_img)

            # --- DESCRIÇÃO ---
            descricao_bruta = ""
            desc_div = soup.find("div", class_="descricaoProd")
            if desc_div:
                descricao_bruta = desc_div.get_text(separator="\n")
            descricao = self.limpar_descricao_vonder(descricao_bruta)

            # --- FICHA TÉCNICA ---
            specs = {}
            if codigo_produto:
                specs["Código"] = codigo_produto

            itens = soup.find_all("span", class_="perguntaseRespostas")
            for item in itens:
                chave_tag = item.find("b")
                valor_tag = item.find("span", class_="listaDetalhesMil")
                if chave_tag and valor_tag:
                    k = self.limpar_texto(chave_tag.get_text())
                    v = self.limpar_texto(valor_tag.get_text())
                    if k and v: specs[k] = v

            specs = self.filtrar_specs_vonder(specs)

            dados = {
                "titulo": titulo,
                "descricao": descricao,
                "caracteristicas": specs,
                "caminho_imagem_temp": caminho_imagem 
            }

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
            print(f"   [ERRO VONDER] {e}")
            return {'sucesso': False, 'erro': str(e)}
        finally:
            if driver:
                driver.quit()

    def baixar_imagem_validada(self, url):
        """Baixa e verifica se o arquivo é realmente uma imagem"""
        
        # Nome simples na pasta atual (evita problemas de path complexo)
        filename = f"vonder_img_temp.jpg"
        filepath = os.path.abspath(filename)
        
        # 1. Tenta Python Unsafe
        print("   [DEBUG] Tentando download Python Unsafe...")
        path_py = self.download_python_unsafe(url, filepath)
        if self.eh_imagem_valida(path_py):
            return path_py
            
        # 2. Tenta Sistema (Curl/Wget)
        print("   [DEBUG] Tentando download Sistema (Curl/Wget)...")
        path_sys = self.download_system_fallback(url, filepath)
        if self.eh_imagem_valida(path_sys):
            return path_sys
            
        print("   [DEBUG] Todas as tentativas falharam ou geraram arquivos inválidos.")
        return None

    def eh_imagem_valida(self, filepath):
        """Verifica os 'Magic Bytes' para saber se é JPG/PNG real"""
        if not filepath or not os.path.exists(filepath):
            return False
            
        try:
            if os.path.getsize(filepath) < 100: # Arquivo muito pequeno = suspeito
                print(f"   [DEBUG] Arquivo muito pequeno ({os.path.getsize(filepath)} bytes). Provável erro.")
                return False

            with open(filepath, 'rb') as f:
                header = f.read(4)
                # Verifica Assinaturas:
                # JPG: FF D8 FF
                # PNG: 89 50 4E 47
                if header.startswith(b'\xff\xd8') or header.startswith(b'\x89PNG'):
                    print(f"   [DEBUG] Arquivo validado! É uma imagem real.")
                    return True
                else:
                    print(f"   [DEBUG] Arquivo baixado NÃO é imagem (Header: {header}). Provável HTML de erro.")
                    return False
        except:
            return False

    def download_python_unsafe(self, url, filepath):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Referer": "https://www.vonder.com.br/"
        }
        try:
            session = requests.Session()
            session.mount('https://', UnsafeSSLAdapter())
            import urllib3
            urllib3.disable_warnings()
            response = session.get(url, headers=headers, timeout=15, verify=False)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return filepath
        except: pass
        return None

    def download_system_fallback(self, url, filepath):
        try:
            if os.path.exists(filepath): os.remove(filepath)
            # Tenta CURL
            cmd = ["curl", "-k", "-L", "-A", "Mozilla/5.0", "-o", filepath, url]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(filepath): return filepath
        except: pass
        
        try:
            # Tenta WGET
            if os.path.exists(filepath): os.remove(filepath)
            cmd = ["wget", "--no-check-certificate", "-U", "Mozilla/5.0", "-O", filepath, url]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(filepath): return filepath
        except: pass

        return None

    def limpar_descricao_vonder(self, texto_bruto):
        if not texto_bruto: return "Descrição indisponível."
        linhas = texto_bruto.splitlines()
        linhas_limpas = []
        for linha in linhas:
            linha_clean = linha.strip()
            if not linha_clean: continue
            linha_lower = linha_clean.lower()
            if "garantia" in linha_lower and ("dias" in linha_lower or "meses" in linha_lower): continue
            if "manual de instruções" in linha_lower or "clique aqui" in linha_lower: continue
            if "certificados:" in linha_lower: continue
            if linha_clean.startswith("Conteúdo da Embalagem:"):
                linha_clean = linha_clean.replace("Conteúdo da Embalagem:", "").strip()
            if linha_clean and len(linha_clean) > 2:
                linhas_limpas.append(linha_clean)
        return "\n\n".join(linhas_limpas)

    def filtrar_specs_vonder(self, specs):
        specs_limpas = {}
        ignorar = ["garantia", "conteúdo", "massa aproximada"]
        for k, v in specs.items():
            k_clean = k.replace(":", "").strip()
            v_clean = v.strip()
            if not any(x in k_clean.lower() for x in ignorar):
                specs_limpas[k_clean] = v_clean
        return specs_limpas
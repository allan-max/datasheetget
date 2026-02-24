# run.py
import sys
import os
import datetime
import re

# ==============================================================================
# 📝 SISTEMA DE LOGS DEFINITIVO (CAPTURA 100% DO CMD)
# ==============================================================================
PASTA_DO_LOG = r"\\SERVIDOR2\Publico\ALLAN\Logs"
ARQUIVO_LOG = os.path.join(PASTA_DO_LOG, "log_python_datasheet.txt")

# 1. Tenta criar a pasta automaticamente (igual fizemos no Node.js)
try:
    if not os.path.exists(PASTA_DO_LOG):
        os.makedirs(PASTA_DO_LOG, exist_ok=True)
except Exception as e:
    # Se falhar por rede/permissão, o código continua e só mostra na tela preta
    print(f"[ERRO CRÍTICO] Falha ao criar pasta de log: {e}")

# 2. Classe que intercepta o CMD e grava no arquivo
class CapturadorDeLog:
    def __init__(self, stream_original, prefixo):
        self.stream_original = stream_original
        self.prefixo = prefixo
        self.padrao_cor = re.compile(r'\x1B\[[0-9;]*[mK]') # Regex para limpar cores do terminal
        try:
            # Abre o arquivo em modo 'a' (append) com encoding UTF-8 para não dar erro com acentos
            self.arquivo = open(ARQUIVO_LOG, "a", encoding="utf-8")
        except Exception:
            self.arquivo = None

    def write(self, mensagem):
        # 2.1 Mostra na tela preta normalmente
        self.stream_original.write(mensagem)
        
        # 2.2 Grava no arquivo (ignorando linhas vazias puras para não sujar o log)
        if self.arquivo and mensagem.strip():
            # Limpa as cores do Flask/Terminal
            mensagem_limpa = self.padrao_cor.sub('', mensagem.strip())
            data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            
            try:
                self.arquivo.write(f"[{data_hora}] {self.prefixo}: {mensagem_limpa}\n")
                self.arquivo.flush() # Força a gravação imediata no disco/rede
            except Exception:
                pass # Evita que a aplicação trave se a rede do SERVIDOR2 oscilar

    def flush(self):
        # Necessário para compatibilidade interna do Python
        self.stream_original.flush()
        if self.arquivo:
            try:
                self.arquivo.flush()
            except Exception:
                pass

# 3. Substitui as saídas nativas pelas nossas customizadas
sys.stdout = CapturadorDeLog(sys.stdout, "INFO")
sys.stderr = CapturadorDeLog(sys.stderr, "ERRO")


# ==============================================================================
# INICIALIZAÇÃO DA API (Deve ficar ABAIXO do sistema de logs)
# ==============================================================================
from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robô Iniciado | Porta ")
    print(" Modo Multi-Thread Ativado")
    print("="*60)
    
    # O parâmetro threaded=True é ESSENCIAL para que o robô 
    # consiga processar várias URLs ao mesmo tempo sem travar.
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)
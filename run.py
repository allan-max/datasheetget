# run.py
import sys
import os
import datetime
import re

PASTA_DO_LOG = r"\\SERVIDOR2\Publico\ALLAN\Logs"
ARQUIVO_LOG = os.path.join(PASTA_DO_LOG, "log_python_datasheet.txt")

try:
    if not os.path.exists(PASTA_DO_LOG):
        os.makedirs(PASTA_DO_LOG, exist_ok=True)
except Exception as e:
    print(f"[ERRO CRÍTICO] Falha ao criar pasta de log: {e}")

class CapturadorDeLog:
    def __init__(self, stream_original, prefixo):
        self.stream_original = stream_original
        self.prefixo = prefixo
        self.padrao_cor = re.compile(r'\x1B\[[0-9;]*[mK]') 
        try:
            self.arquivo = open(ARQUIVO_LOG, 'a', encoding='utf-8')
        except Exception:
            self.arquivo = None

    def write(self, mensagem):
        try:
            self.stream_original.write(mensagem)
            self.stream_original.flush()
        except: pass
        
        if not mensagem.strip() or not self.arquivo: return
        
        mensagem_limpa = self.padrao_cor.sub('', mensagem.strip())
        data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        
        try:
            self.arquivo.write(f"[{data_hora}] {self.prefixo}: {mensagem_limpa}\n")
            self.arquivo.flush() 
        except Exception: pass

    def flush(self):
        try: self.stream_original.flush()
        except: pass
        if self.arquivo:
            try: self.arquivo.flush()
            except: pass

sys.stdout = CapturadorDeLog(sys.stdout, "INFO")
sys.stderr = CapturadorDeLog(sys.stderr, "ERRO")

from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robô Iniciado | Porta 3001 ")
    print(" Logs Restaurados na Tela ")
    print("="*60)
    app.run(host='0.0.0.0', port=3001, threaded=True)
# run.py
import sys
import os
import datetime
import re

# 1. A VACINA DO WINDOWS SERVER: Força o terminal a aceitar UTF-8 (como fizemos no teste)
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

PASTA_DO_LOG = r"\\SERVIDOR2\Publico\ALLAN\Logs"
ARQUIVO_LOG = os.path.join(PASTA_DO_LOG, "log_python_datasheet.txt")

try:
    if not os.path.exists(PASTA_DO_LOG):
        os.makedirs(PASTA_DO_LOG, exist_ok=True)
except Exception:
    pass

class LoggerMestre:
    def __init__(self, stream, prefixo):
        self.stream = stream
        self.prefixo = prefixo
        self.padrao_cor = re.compile(r'\x1B\[[0-9;]*[mK]')

    def write(self, mensagem):
        # 1. Grita na tela preta
        try:
            self.stream.write(mensagem)
            self.stream.flush()
        except UnicodeEncodeError:
            # Se o Windows engasgar com um emoji ou acento, trocamos por "?" e forçamos a impressão!
            msg_limpa = mensagem.encode('ascii', 'replace').decode('ascii')
            try:
                self.stream.write(msg_limpa)
                self.stream.flush()
            except Exception: pass
        except Exception: pass

        # 2. Salva no arquivo de log da rede
        if not mensagem.strip(): return
        
        texto_sem_cor = self.padrao_cor.sub('', mensagem.strip())
        data_hora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        linha = f"[{data_hora}] {self.prefixo}: {texto_sem_cor}\n"
        
        try:
            with open(ARQUIVO_LOG, 'a', encoding='utf-8') as f:
                f.write(linha)
        except Exception: pass

    def flush(self):
        try: self.stream.flush()
        except Exception: pass

# Substitui as saídas do Python pelo nosso LoggerMestre
sys.stdout = LoggerMestre(sys.__stdout__, "INFO")
sys.stderr = LoggerMestre(sys.__stderr__, "ERRO")

# A API é importada por último
from api import app

if __name__ == '__main__':
    print("="*60)
    print(" 🤖 Robô Iniciado | Porta 3001")
    print(" 🗣️ LOGS RESTAURADOS: O terminal vai falar tudo agora!")
    print("="*60)
    
    app.run(host='0.0.0.0', port=3001, threaded=True)
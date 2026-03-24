# run.py
import sys
import os
from datetime import datetime
import logging

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_DEBUG = os.path.join(DIRETORIO_ATUAL, "DEBUG_ROBO.txt")

# A verdadeira interceptação de TUDO o que sai do Python
class ConsoleDuplo:
    def __init__(self, original_stream):
        self.terminal = original_stream
        # Registra a hora de inicialização no TXT
        with open(ARQUIVO_DEBUG, "a", encoding="utf-8") as f:
            f.write(f"\n\n{'='*50}\nROBÔ INICIADO - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n{'='*50}\n")

    def write(self, mensagem):
        # 1. Grita na tela preta
        try:
            self.terminal.write(mensagem)
            self.terminal.flush()
        except: pass
        
        # 2. Guarda no TXT (apenas se tiver algum texto)
        try:
            if mensagem.strip():
                with open(ARQUIVO_DEBUG, "a", encoding="utf-8") as f:
                    f.write(mensagem)
        except: pass

    def flush(self):
        try: self.terminal.flush()
        except: pass

# Substitui a saída padrão e de erros do Python pela nossa classe
sys.stdout = ConsoleDuplo(sys.__stdout__)
sys.stderr = ConsoleDuplo(sys.__stderr__)

# Obriga a API (Flask) a jogar os logs de requisição no nosso ConsoleDuplo
logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(message)s')
log_werkzeug = logging.getLogger('werkzeug')
log_werkzeug.setLevel(logging.INFO)

# A importação da API fica por último
from api import app

if __name__ == '__main__':
    print("🤖 Robô Iniciado com Sucesso | Porta 3001")
    print("📡 CANAL DE COMUNICAÇÃO REESTABELECIDO!")
    print("Aguardando chamadas na API...")
    
    app.run(host='0.0.0.0', port=3001, threaded=True)
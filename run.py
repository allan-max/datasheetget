# run.py
import os
import sys
import builtins
import logging
from datetime import datetime

# 1. FORÇA O SISTEMA OPERACIONAL A NÃO GUARDAR TEXTO
os.environ["PYTHONUNBUFFERED"] = "1"

# Caminho do nosso arquivo "Caixa Preta" local
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_DEBUG = os.path.join(DIRETORIO_ATUAL, "DEBUG_ROBO.txt")

# Escreve um cabeçalho sempre que reiniciar
with open(ARQUIVO_DEBUG, "a", encoding="utf-8") as f:
    f.write(f"\n\n{'='*40}\nROBÔ INICIADO EM {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n{'='*40}\n")

# 2. O HACK DA CAIXA PRETA: Intercepta todos os prints e salva no arquivo
_print_original = builtins.print

def print_caixa_preta(*args, **kwargs):
    texto = " ".join(str(a) for a in args)
    agora = datetime.now().strftime("%H:%M:%S")
    linha_log = f"[{agora}] {texto}"
    
    # Tenta mostrar na tela
    try:
        sys.__stdout__.write(linha_log + "\n")
        sys.__stdout__.flush()
    except: pass
    
    # SALVA FISICAMENTE NO ARQUIVO .TXT
    try:
        with open(ARQUIVO_DEBUG, "a", encoding="utf-8") as f:
            f.write(linha_log + "\n")
    except: pass

builtins.print = print_caixa_preta

# 3. FORÇA A API (FLASK/WERKZEUG) A ANUNCIAR AS REQUISIÇÕES
log_api = logging.getLogger('werkzeug')
log_api.setLevel(logging.INFO)
if not log_api.handlers:
    handler = logging.StreamHandler(sys.__stdout__)
    log_api.addHandler(handler)

from api import app


if __name__ == '__main__':
    print("🤖 Robô Iniciado com Sucesso | Porta 3001")
    print("📦 CAIXA PRETA ATIVADA: Lendo tudo e gravando em DEBUG_ROBO.txt")
    print("Aguardando chamadas na API...")
    
    app.run(host='0.0.0.0', port=3001, threaded=True)
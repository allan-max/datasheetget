# run.py
import os
import sys
import datetime
import builtins
import re

# Tenta forçar o terminal a aceitar UTF-8 nativamente
try:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

PASTA_DO_LOG = r"\\SERVIDOR2\Publico\ALLAN\Logs"
ARQUIVO_LOG = os.path.join(PASTA_DO_LOG, "log_python_datasheet.txt")
padrao_cor = re.compile(r'\x1B\[[0-9;]*[mK]')

try:
    os.makedirs(PASTA_DO_LOG, exist_ok=True)
except:
    pass

_print_original = builtins.print

def print_simples_e_seguro(*args, **kwargs):
    texto = " ".join(str(arg) for arg in args)
    
    # Troca qualquer caractere estranho/emoji por "?" para não travar o Windows
    texto_limpo_cmd = texto.encode('ascii', errors='replace').decode('ascii')
    
    # 1. Tenta mandar para a tela preta com flush imediato
    kwargs['flush'] = True
    try:
        _print_original(texto_limpo_cmd, **kwargs)
    except:
        pass
        
    # 2. Tenta guardar no ficheiro TXT da rede
    try:
        texto_sem_cor = padrao_cor.sub('', texto)
        agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        with open(ARQUIVO_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{agora}] {texto_sem_cor}\n")
    except:
        pass

# Diz ao Python inteiro para usar o nosso print modificado
builtins.print = print_simples_e_seguro

from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robo Iniciado | Porta 3001")
    print(" LOGS REATIVADOS DE FORMA SIMPLES E SEGURA!")
    print("="*60)
    
    app.run(host='0.0.0.0', port=3001, threaded=True)
# run.py
import sys
import os
from datetime import datetime
import builtins

# Define o ficheiro de log NA MESMA PASTA do projeto (Sem bloqueios de rede)
DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_LOG = os.path.join(DIRETORIO_ATUAL, "LOG_LOCAL.txt")

# Escreve o cabeçalho inicial para provar que tem permissão
with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
    f.write(f"\n\n{'='*50}\nROBÔ INICIADO - {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n{'='*50}\n")

class GravadorLocal:
    def write(self, mensagem):
        try:
            msg_str = str(mensagem)
            if not msg_str.strip():
                return
            # Limpa caracteres complexos para evitar crash
            msg_limpa = msg_str.encode('ascii', errors='replace').decode('ascii')
            # Escreve localmente
            with open(ARQUIVO_LOG, "a", encoding="utf-8") as f:
                f.write(msg_limpa + "\n")
        except:
            pass

    def flush(self):
        pass

# Redireciona TUDO do Python para este ficheiro local
sys.stdout = GravadorLocal()
sys.stderr = GravadorLocal()

# Intercepta os prints antigos
_print_original = builtins.print
def print_forcado(*args, **kwargs):
    texto = " ".join(str(a) for a in args)
    sys.stdout.write(texto)
builtins.print = print_forcado

# Importa a API por último
from api import app

if __name__ == '__main__':
    print(">>> SISTEMA ONLINE NO ARQUIVO LOCAL | PORTA 6004 <<<")
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)
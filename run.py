# run.py
import os
import sys
import builtins
import logging

# ==============================================================================
# ☢️ MODO NUCLEAR: ESCRITA DIRETA NO KERNEL DO WINDOWS
# ==============================================================================
def print_nuclear(*args, **kwargs):
    # Junta todo o texto que tentarem imprimir
    mensagem = " ".join(str(a) for a in args) + "\n"
    try:
        # Troca emojis e acentos loucos por "?" para não estourar o CMD
        texto_seguro = mensagem.encode('ascii', 'replace')
        # '1' é a porta física oficial da tela no sistema operativo (Imbloqueável)
        os.write(1, texto_seguro)
    except Exception:
        pass

# Obrigamos o Python a substituir o 'print' normal pelo nosso print nuclear
builtins.print = print_nuclear

# Obrigamos o Flask (API) a usar o nosso canal nuclear
class NuclearHandler(logging.Handler):
    def emit(self, record):
        print_nuclear(self.format(record))

logger_api = logging.getLogger('werkzeug')
logger_api.setLevel(logging.INFO)
# Limpa os bloqueios antigos e coloca o nosso
logger_api.handlers = [NuclearHandler()]

# Importamos a sua API apenas depois de blindar o sistema
from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robo Iniciado com Sucesso | Porta 3001")
    print(" MODO NUCLEAR ATIVADO: Comunicacao direta com o Windows!")
    print(" Nenhuma API consegue silenciar este terminal agora.")
    print("="*60)
    
    app.run(host='0.0.0.0', port=3001, threaded=True)
# run.py
import sys
import os

# Força o Python a tentar usar UTF-8 nativamente
os.environ["PYTHONIOENCODING"] = "utf-8"

class TerminalAProvaDeBalas:
    def __init__(self, terminal_original):
        self.terminal = terminal_original

    def write(self, mensagem):
        try:
            # Tentativa 1: Imprimir a mensagem original
            self.terminal.write(mensagem)
            self.terminal.flush()
        except UnicodeEncodeError:
            # Tentativa 2: O Windows Server 2012 bloqueou o emoji/acento!
            # Vamos substituir o que ele não entende por "?" e imprimir o resto do texto à força.
            mensagem_limpa = mensagem.encode('ascii', errors='replace').decode('ascii')
            try:
                self.terminal.write(mensagem_limpa)
                self.terminal.flush()
            except:
                pass
        except Exception:
            pass

    def flush(self):
        try:
            self.terminal.flush()
        except:
            pass

# Substitui a saída oficial pela nossa blindada
sys.stdout = TerminalAProvaDeBalas(sys.__stdout__)
sys.stderr = TerminalAProvaDeBalas(sys.__stderr__)

# Importa a API por último
from api import app

if __name__ == '__main__':
    print("="*60)
    print(" Robô Iniciado com Sucesso | Porta 3001")
    print(" ESCUDO ANTI-EMOJI ATIVADO: O Windows não vai mais silenciar os logs!")
    print("="*60)
    
    app.run(host='0.0.0.0', port=3001, threaded=True)
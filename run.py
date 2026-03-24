# run.py
import os
import sys

# Força o Windows a entender acentos sem travar o terminal
os.environ["PYTHONIOENCODING"] = "utf-8"
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

from api import app

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" 🚀 SISTEMA DE DATASHEET ONLINE | PORTA 6004")
    print(" 🛡️ Motor do Chrome Liberado e Estável")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=6004, threaded=True, debug=False)
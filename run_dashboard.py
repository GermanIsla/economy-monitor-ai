#!/usr/bin/env python3
# run_dashboard.py
# Punto de entrada: arranca el dashboard web en localhost

# Comprobación de entorno ANTES de importar dependencias de terceros.
from utils.venv_check import ensure_venv
ensure_venv()

from db.engine import init_db
from config.settings import DASH_HOST, DASH_PORT, DASH_DEBUG

if __name__ == "__main__":
    # Asegurar que la base de datos y tablas existen
    print("Inicializando base de datos...")
    init_db()

    # Importar aquí para que init_db se ejecute primero
    from dashboard.app import app

    print(f"\n{'='*50}")
    print(f"  Economy Monitor Dashboard")
    print(f"  http://{DASH_HOST}:{DASH_PORT}")
    print(f"{'='*50}\n")

    app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG)

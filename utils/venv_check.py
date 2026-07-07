# utils/venv_check.py
# Comprobación de entorno: avisa si el proyecto se ejecuta fuera de su venv.
#
# IMPORTANTE: este módulo debe usar SOLO la librería estándar y ser lo primero
# que importan los puntos de entrada (run_*.py), antes que cualquier dependencia
# de terceros (sqlalchemy, dash, ...). Así, si el intérprete es el equivocado
# (p. ej. anaconda base), avisamos con un mensaje claro en lugar de reventar con
# un ModuleNotFoundError.

import importlib.util
import os
import sys

# Raíz del proyecto = carpeta que contiene este archivo (utils/) subiendo un nivel.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VENV_DIR = os.path.join(_PROJECT_ROOT, "venv")

# Dependencia central del proyecto. Si es importable, tenemos el entorno bueno;
# si no, estamos en el intérprete equivocado (p. ej. anaconda base o el del sistema).
# Comprobamos disponibilidad en lugar de comparar rutas: el venv puede estar activado
# bajo una ruta distinta (copiado/renombrado) y aun así ser válido.
_SENTINEL_DEP = "sqlalchemy"


def _deps_available() -> bool:
    """True si las dependencias del proyecto están disponibles en este intérprete."""
    try:
        return importlib.util.find_spec(_SENTINEL_DEP) is not None
    except (ImportError, ValueError):
        return False


def _print_activation_help() -> None:
    activate = os.path.join(_VENV_DIR, "bin", "activate")
    venv_python = os.path.join(_VENV_DIR, "bin", "python")
    lines = [
        "",
        "=" * 60,
        f"  Faltan las dependencias del proyecto ('{_SENTINEL_DEP}' no se encuentra).",
        "  Probablemente estás fuera del entorno virtual del proyecto.",
        "=" * 60,
        f"  Intérprete actual: {sys.executable}",
        f"  Entorno esperado:  {_VENV_DIR}",
        "",
        "  Actívalo antes de continuar:",
        "",
        f"      source {activate}",
        "",
        "  ...o ejecuta directamente con el python del venv:",
        "",
        f"      {venv_python} {' '.join(sys.argv) or '<script>'}",
        "=" * 60,
        "",
    ]
    print("\n".join(lines), file=sys.stderr)


def ensure_venv() -> None:
    """
    Verifica que el intérprete actual tiene las dependencias del proyecto.

    - Si están disponibles: no hace nada (entorno correcto).
    - Si faltan: muestra cómo activar el venv y sale con código 1, en lugar de
      dejar que reviente más tarde con un ModuleNotFoundError confuso.
    """
    if _deps_available():
        return

    _print_activation_help()
    sys.exit(1)

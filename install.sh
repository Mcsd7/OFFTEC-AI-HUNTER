#!/data/data/com.termux/files/usr/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
echo "OFFTEC AI HUNTER — verificação de instalação"
case "${PREFIX:-}" in *com.termux*) echo "Termux: detectado";; *) echo "Aviso: ambiente não identificado como Termux; continuando com Python padrão.";; esac
case "$(uname -m)" in aarch64|arm64) echo "Arquitetura ARM64: compatível";; *) echo "Arquitetura: $(uname -m) (não verificada)";; esac
command -v python >/dev/null 2>&1 || { echo "Python não encontrado. No Termux: pkg install python"; exit 1; }
python -c 'import sys; print("Python:",sys.version.split()[0])'
python -m pip --version >/dev/null 2>&1 || { echo "pip indisponível"; exit 1; }
command -v git >/dev/null 2>&1 && echo "Git: disponível" || echo "Git: ausente (opcional)"
APP_HOME="${OFFTEC_HOME:-$HOME/.offtec-ai-hunter}"
mkdir -p "$APP_HOME/reports" "$APP_HOME/exports"
chmod 700 "$APP_HOME" "$APP_HOME/reports" "$APP_HOME/exports" 2>/dev/null || true
python -c 'import sqlite3, ssl, json, urllib.request; print("Biblioteca padrão: OK")'
if ! python -c 'import rich' >/dev/null 2>&1; then
    if python -m pip install -r "$ROOT/requirements.txt"; then
        echo "Rich: instalado"
    else
        echo "Rich indisponível; a interface ANSI integrada continuará funcional."
    fi
else
    echo "Rich: disponível"
fi
cd "$ROOT"
PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python - <<'PY'
from offtec.database.repository import Repository
from offtec.core.i18n import Translator
from offtec.ai.codex_adapter import CodexAdapter
from offtec.modules.tooling import inventory
Repository(); assert Translator().lang=="pt_BR"
print("Banco SQLite e idioma padrão pt-BR: OK")
print("Codex:",CodexAdapter().status()["reason"])
for name,path in inventory().items(): print(name+":", "disponível" if path else "ausente")
PY
echo "Diagnóstico concluído. Inicie com: python '$ROOT/main.py'"

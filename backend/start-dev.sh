#!/bin/bash
cd "$(dirname "$0")"

# === Tunnel SSH: PostgreSQL (banco de producao) ===
if ! pgrep -f "ssh.*-L 15432" >/dev/null 2>&1; then
    echo "[dev] Configurando tunnel PostgreSQL..."
    ssh -o ConnectTimeout=5 root@ptbd01.viptecnologia.com.br 'bash -s' <<'REMOTE'
if ! ss -tlnp | grep -q ":15432 "; then
    PID=$(docker inspect meuemail_meuemail-db.1.$(docker service ps meuemail_meuemail-db -q --filter desired-state=running --no-trunc | head -1) -f '{{.State.Pid}}' 2>/dev/null)
    if [ -n "$PID" ]; then
        nohup socat TCP-LISTEN:15432,fork,reuseaddr EXEC:"nsenter -t $PID -n socat STDIN TCP\:127.0.0.1\:5432" >/dev/null 2>&1 &
        echo "[remote] socat PostgreSQL iniciado"
    fi
fi
REMOTE
    ssh -f -N -L 15432:127.0.0.1:15432 root@ptbd01.viptecnologia.com.br
    echo "[dev] Tunnel PostgreSQL: localhost:15432"
else
    echo "[dev] Tunnel PostgreSQL ja ativo"
fi

# === Tunnel SSH: MariaDB (iRedMail) ===
if ! pgrep -f "ssh.*-L 13306" >/dev/null 2>&1; then
    echo "[dev] Configurando tunnel MariaDB..."
    ssh -f -N -L 13306:127.0.0.1:3306 root@email2.viptecnologia.com.br
    echo "[dev] Tunnel MariaDB: localhost:13306"
else
    echo "[dev] Tunnel MariaDB ja ativo"
fi

# Ativar venv e iniciar uvicorn
source venv/bin/activate
exec uvicorn main:app --host 0.0.0.0 --port 8467 --reload

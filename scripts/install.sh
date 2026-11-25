#!/usr/bin/env bash
# Installation (ou réinstallation, sans perte de données) sur un VPS Ubuntu,
# à lancer depuis le dossier du projet :
#
#   sudo ./scripts/install.sh                                 # HTTP sur le port 80 (IP du VPS)
#   sudo ./scripts/install.sh --domain iodej.example.fr       # HTTPS auto (Let's Encrypt via Caddy)
#
# Options :
#   --domain <nom>     sous-domaine servi en HTTPS
#   --port <port>      port interne (défaut 8000 ; la 2e instance prend port+1) — 2 ports par projet
#   --data-dir <dir>   base + photos (défaut : <projet>/data)
#   --service <nom>    nom du service systemd et du site Caddy (défaut : iodej)
#   --no-caddy         ne pas toucher à Caddy
#   --skip-system      ne pas lancer apt (déploiements suivants, plus rapide)
#
# Plusieurs projets cohabitent : chacun dépose /etc/caddy/sites/<service>.caddy,
# que le Caddyfile principal importe.
set -euo pipefail

DOMAIN=""
PORT=8000
DATA_DIR=""
SERVICE=iodej
WITH_CADDY=1
SKIP_SYSTEM=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --service) SERVICE="$2"; shift 2 ;;
    --no-caddy) WITH_CADDY=0; shift ;;
    --skip-system) SKIP_SYSTEM=1; shift ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1"; exit 1 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Lance ce script avec sudo."; exit 1; }

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="$(stat -c %U "$APP_DIR")"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
DATA_DIR="${DATA_DIR:-$APP_DIR/data}"
PORT2=$((PORT + 1))   # seconde instance, pour les mises à jour sans coupure

say() { printf '\n\033[1;35m▶ %s\033[0m\n' "$*"; }
as_app() { sudo -u "$APP_USER" -H env IODEJ_DATA_DIR="$DATA_DIR" bash -c "$1"; }

if [[ $SKIP_SYSTEM -eq 0 ]]; then
  say "Paquets système"
  apt-get update -qq
  apt-get install -y -qq curl git rsync ca-certificates >/dev/null
fi

say "uv (gestionnaire Python) pour l'utilisateur $APP_USER"
UV="$APP_HOME/.local/bin/uv"
if [[ ! -x "$UV" ]]; then
  sudo -u "$APP_USER" -H bash -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' >/dev/null
fi
"$UV" --version

say "Dépendances Python"
as_app "cd '$APP_DIR' && '$UV' sync --frozen --no-dev"

say "Base de données & codes d'accès ($DATA_DIR)"
mkdir -p "$DATA_DIR"
chown "$APP_USER": "$DATA_DIR"
as_app "cd '$APP_DIR' && '$UV' run --frozen --no-dev iodej init"
# Les codes ne sont affichés qu'en session interactive (jamais dans les logs de CI).
if [[ -t 1 ]]; then as_app "cd '$APP_DIR' && '$UV' run --frozen --no-dev iodej codes"; fi

say "Services systemd ($SERVICE@$PORT et $SERVICE@$PORT2)"
SECURE=0; [[ -n "$DOMAIN" ]] && SECURE=1
# Modèle d'unité : une instance par port (%i), pour les mises à jour sans coupure.
cat > /etc/systemd/system/$SERVICE@.service <<UNIT
[Unit]
Description=$SERVICE (Iodej — On mange où ?) sur le port %i
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=IODEJ_DATA_DIR=$DATA_DIR
Environment=IODEJ_COOKIE_SECURE=$SECURE
Environment=IODEJ_VAPID_SUB=${DOMAIN:+https://$DOMAIN}
Environment=IODEJ_TZ=${IODEJ_TZ:-Europe/Paris}
Environment=IODEJ_PORT=%i
ExecStart=$UV run --frozen --no-dev iodej serve --host 127.0.0.1 --port %i
Restart=always
RestartSec=3
# Laisse le temps aux requêtes en cours de se terminer à l'arrêt.
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
UNIT

say "Rappels du midi (lun→ven 11h30 et 11h55)"
TZ_NAME="${IODEJ_TZ:-Europe/Paris}"
VAPID_SUB="mailto:iodej@example.com"; [[ -n "$DOMAIN" ]] && VAPID_SUB="https://$DOMAIN"
for KIND in first reminder; do
  [[ $KIND == first ]] && AT="11:30" || AT="11:55"
  cat > /etc/systemd/system/$SERVICE-notify-$KIND.service <<UNIT
[Unit]
Description=$SERVICE : notification « $KIND » du midi
After=network-online.target

[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=IODEJ_DATA_DIR=$DATA_DIR
Environment=IODEJ_TZ=$TZ_NAME
Environment=IODEJ_VAPID_SUB=$VAPID_SUB
ExecStart=$UV run --frozen --no-dev iodej notify $KIND
UNIT
  cat > /etc/systemd/system/$SERVICE-notify-$KIND.timer <<UNIT
[Unit]
Description=$SERVICE : notification « $KIND » à $AT en semaine

[Timer]
OnCalendar=Mon..Fri *-*-* $AT:00 $TZ_NAME
Persistent=false

[Install]
WantedBy=timers.target
UNIT
done
systemctl daemon-reload
for KIND in first reminder; do systemctl enable --now $SERVICE-notify-$KIND.timer >/dev/null 2>&1; done
systemctl list-timers "$SERVICE-notify-*" --no-pager | head -4 || true

if [[ $WITH_CADDY -eq 1 ]]; then
  say "Reverse proxy Caddy"
  if ! command -v caddy >/dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https gnupg >/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      > /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y -qq caddy >/dev/null
  fi

  # Caddyfile principal = une simple liste d'imports, un fichier par site.
  mkdir -p /etc/caddy/sites
  MAIN=/etc/caddy/Caddyfile
  if ! grep -qs "import sites/\*" "$MAIN"; then
    if [[ ! -s "$MAIN" ]] || grep -qs "/usr/share/caddy" "$MAIN" \
       || { grep -qs "reverse_proxy 127.0.0.1:$PORT" "$MAIN" && [[ $(grep -c '{' "$MAIN") -le 1 ]]; }; then
      # Fichier par défaut du paquet, ou généré par une ancienne version de ce script.
      [[ -s "$MAIN" ]] && cp "$MAIN" "$MAIN.bak-$(date +%Y%m%d%H%M%S)"
      echo "import sites/*.caddy" > "$MAIN"
    else
      echo "⚠ Caddyfile personnalisé détecté : ajout de l'import à la fin (vérifie qu'il n'y a pas de doublon)."
      printf '\nimport sites/*.caddy\n' >> "$MAIN"
    fi
  fi

  SITE="${DOMAIN:-:80}"
  # Deux instances : Caddy sert la première disponible et bascule sur l'autre
  # (nouvel essai transparent) pendant qu'on en redémarre une.
  cat > /etc/caddy/sites/$SERVICE.caddy <<CADDY
$SITE {
    encode zstd gzip
    reverse_proxy 127.0.0.1:$PORT 127.0.0.1:$PORT2 {
        lb_policy first
        lb_try_duration 15s
        lb_try_interval 250ms
        fail_duration 10s
        health_uri /healthz/lb
        health_interval 2s
        health_timeout 2s
    }
}
CADDY
  caddy validate --config "$MAIN" --adapter caddyfile >/dev/null

  # Les ports web doivent être à Caddy (pas à un nginx/apache d'un ancien projet).
  for WEBPORT in 80 443; do
    OWNER="$(ss -Hltnp "sport = :$WEBPORT" 2>/dev/null | grep -o '(("[^"]*"' | head -1 | tr -d '("')"
    if [[ -n "$OWNER" && "$OWNER" != "caddy" ]]; then
      echo "✖ Le port $WEBPORT est occupé par « $OWNER » : Caddy ne peut pas servir le site."
      echo "  Si c'est un ancien projet : systemctl disable --now $OWNER   puis relance le déploiement."
      exit 1
    fi
  done

  systemctl enable caddy >/dev/null 2>&1
  systemctl reload caddy 2>/dev/null || systemctl restart caddy
  if ! systemctl is-active --quiet caddy; then
    echo "✖ Caddy ne tourne pas :"; journalctl -u caddy -n 20 --no-pager; exit 1
  fi
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  fi
fi

say "Mise à jour progressive (une instance à la fois)"
port_owner() { ss -Hltnp "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }
owned_by() { local pid; pid="$(port_owner "$1")"; [[ -n "$pid" ]] && grep -q "$2" "/proc/$pid/cgroup" 2>/dev/null; }
healthy() { owned_by "$1" "$SERVICE@$1.service" && curl -fs -m 3 "http://127.0.0.1:$1/healthz" >/dev/null; }

# L'ancienne instance unique (iodej.service, port $PORT) est remplacée au passage.
LEGACY=0; [[ -f /etc/systemd/system/$SERVICE.service ]] && LEGACY=1

for P in $PORT2 $PORT; do
  if [[ $LEGACY -eq 1 && $P == "$PORT" ]]; then
    systemctl disable --now $SERVICE >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/$SERVICE.service; systemctl daemon-reload
  fi
  systemctl enable $SERVICE@$P >/dev/null 2>&1
  if systemctl is-active --quiet $SERVICE@$P; then
    # Mise hors trafic : /healthz répond 503, Caddy bascule sur l'autre instance
    # (health_interval 2s), puis on arrête proprement.
    install -o "$APP_USER" /dev/null "$DATA_DIR/drain-$P"
    sleep 5
  fi
  systemctl stop $SERVICE@$P 2>/dev/null || true
  rm -f "$DATA_DIR/drain-$P"
  for _ in $(seq 1 10); do [[ -z "$(port_owner $P)" ]] && break; sleep 1; done
  if [[ -n "$(port_owner $P)" ]]; then
    PID="$(port_owner $P)"
    echo "✖ Le port $P est déjà utilisé par un autre programme (pid $PID) :"
    ps -o pid,user,cmd -p "$PID" | tail -n +2
    echo "  Arrête-le (kill $PID), ou choisis un autre port avec --port."
    exit 1
  fi
  systemctl start $SERVICE@$P
  for _ in $(seq 1 30); do healthy $P && break; sleep 1; done
  if ! healthy $P; then
    echo "✖ L'instance $SERVICE@$P ne répond pas (l'autre instance continue de servir le site) :"
    journalctl -u $SERVICE@$P -n 25 --no-pager || true
    exit 1
  fi
  echo "  ✔ $SERVICE@$P à jour"
  sleep 3  # le temps que Caddy la voie de nouveau en bonne santé
done

say "C'est en ligne !"
if [[ -n "$DOMAIN" ]]; then echo "  URL     : https://$DOMAIN"; else echo "  URL     : http://<ip-du-vps>"; fi
echo "  Admin   : …/admin"
echo "  Logs    : journalctl -u '$SERVICE@*' -f"

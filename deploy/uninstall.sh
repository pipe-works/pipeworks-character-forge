#!/usr/bin/env bash
# uninstall.sh — remove the systemd unit, nginx vhost, env file, and TLS
# cert installed by deploy/install.sh. Leaves the venv, the repo, and
# /srv/work/pipeworks/runtime/character-forge/ alone (those are deliberate
# data; remove them by hand if you really want to wipe everything).
#
# Idempotent: safe to re-run.

set -euo pipefail

HOST=forge.pipeworks.luminal.local
SERVICE=pipeworks-character-forge.service

ENV_DIR=/etc/pipeworks/character-forge
NGINX_AVAIL=/etc/nginx/sites-available/$HOST
NGINX_ENABLED=/etc/nginx/sites-enabled/$HOST
CERT=/etc/nginx/certs/$HOST.pem
KEY=/etc/nginx/certs/$HOST-key.pem
SYSTEMD_LINK=/etc/systemd/system/$SERVICE

step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }

[[ $EUID -ne 0 ]] || { echo "Run as a regular user; the script will sudo as needed." >&2; exit 1; }

step "Stopping + disabling service"
if systemctl is-enabled --quiet "$SERVICE" 2>/dev/null || systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
    sudo systemctl disable --now "$SERVICE" || true
    ok "Service stopped + disabled"
else
    ok "Service already stopped"
fi

step "Removing systemd unit symlink"
if [[ -L $SYSTEMD_LINK ]]; then
    sudo rm "$SYSTEMD_LINK"
    sudo systemctl daemon-reload
    ok "Removed $SYSTEMD_LINK"
else
    ok "No systemd unit symlink present"
fi

step "Removing nginx vhost"
if sudo test -L "$NGINX_ENABLED"; then sudo rm "$NGINX_ENABLED"; fi
if sudo test -f "$NGINX_AVAIL";  then sudo rm "$NGINX_AVAIL";  fi
sudo nginx -t && sudo systemctl reload nginx
ok "nginx reloaded"

step "Removing TLS cert"
sudo rm -f "$CERT" "$KEY"
ok "Cert + key removed"

step "Removing env file"
if sudo test -d "$ENV_DIR"; then
    sudo rm -rf "$ENV_DIR"
    ok "Removed $ENV_DIR"
else
    ok "Env dir not present"
fi

cat <<'EOF'

Left intact (intentionally — remove by hand if you really want to wipe):

  - /srv/work/pipeworks/venvs/pw-character-forge       (venv with [ml] extras)
  - /srv/work/pipeworks/runtime/character-forge/       (model cache + run outputs)
  - /srv/work/pipeworks/repos/pipeworks-character-forge (the repo itself)

DrayTek DNS entry and /etc/luminal/services.yml registration are also
left alone — remove those by hand if you want a fully clean rollback.
EOF

#!/usr/bin/env bash
# install.sh — install or refresh PipeWorks Character Forge on Luminal.
#
# Run as a regular user (in the pipeworks group). The script invokes sudo
# only for the privileged steps (cert install, nginx vhost, env file,
# systemd link). Idempotent: safe to re-run after editing the env file
# or after pulling new commits.
#
# Usage:
#   bash deploy/install.sh
#
# What it does, in order:
#   1. Pre-flight checks (user, group, mkcert, repo, venv, [ml] extras).
#   2. mkcert leaf cert into /etc/nginx/certs/.
#   3. nginx vhost into /etc/nginx/sites-available/, symlink, reload.
#   4. /etc/pipeworks/character-forge/character-forge.env from the example.
#      First install — exits with a reminder to edit HF_TOKEN.
#      Subsequent runs — verifies HF_TOKEN is set before enabling the unit.
#   5. systemd link + daemon-reload + enable --now.
#   6. Health probe against https://127.0.0.1:8410/api/health.
#
# Manual follow-ups (script prints them at the end):
#   - DrayTek LAN DNS: forge.pipeworks.luminal.local → 192.168.20.11
#   - /etc/luminal/services.yml: register the service entry.

set -euo pipefail

# -- Constants --------------------------------------------------------------

REPO=/srv/work/pipeworks/repos/pipeworks-character-forge
VENV=/srv/work/pipeworks/venvs/pw-character-forge
HOST=forge.pipeworks.luminal.local
PORT=8410
SERVICE=pipeworks-character-forge.service

ENV_DIR=/etc/pipeworks/character-forge
ENV_PATH=$ENV_DIR/character-forge.env
NGINX_AVAIL=/etc/nginx/sites-available/$HOST
NGINX_ENABLED=/etc/nginx/sites-enabled/$HOST
CERT=/etc/nginx/certs/$HOST.pem
KEY=/etc/nginx/certs/$HOST-key.pem
SYSTEMD_LINK=/etc/systemd/system/$SERVICE

# -- Helpers ----------------------------------------------------------------

step() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# -- 1. Pre-flight ----------------------------------------------------------

step "Pre-flight checks"

[[ $EUID -ne 0 ]] || die "Run as a regular user; the script will sudo as needed."
groups | grep -qw pipeworks || die "Current user must be in the 'pipeworks' group."
command -v mkcert >/dev/null || die "mkcert not in PATH (apt install mkcert / cargo install mkcert)."
[[ -d $REPO ]] || die "Repo missing at $REPO."
[[ -x $VENV/bin/pw-forge ]] || die "Venv missing or pw-forge not installed in $VENV."

# Confirm the [ml] extras are present in the venv — the systemd unit will
# fail at first /api/debug/i2i call otherwise.
if ! "$VENV/bin/python" -c 'import torch, diffusers' >/dev/null 2>&1; then
    die "Venv at $VENV is missing torch/diffusers. Install with:
    $VENV/bin/pip install -e '$REPO[ml]'"
fi

ok "User in 'pipeworks' group"
ok "mkcert available"
ok "Repo + venv + [ml] extras OK"

# -- 2. TLS cert ------------------------------------------------------------

step "TLS certificate"

if sudo test -f "$CERT" && sudo test -f "$KEY"; then
    ok "Cert already installed at $CERT"
else
    tmpdir=$(mktemp -d)
    trap 'rm -rf "$tmpdir"' EXIT
    mkcert -cert-file "$tmpdir/cert.pem" -key-file "$tmpdir/key.pem" "$HOST"
    sudo install -m 644 -o root -g root "$tmpdir/cert.pem" "$CERT"
    sudo install -m 600 -o root -g root "$tmpdir/key.pem"  "$KEY"
    rm -rf "$tmpdir"
    trap - EXIT
    ok "Cert issued and installed"
fi

# -- 3. nginx vhost ---------------------------------------------------------

step "nginx vhost"

sudo install -m 644 "$REPO/deploy/nginx/$HOST" "$NGINX_AVAIL"
sudo ln -sf "../sites-available/$HOST" "$NGINX_ENABLED"
sudo nginx -t
sudo systemctl reload nginx
ok "vhost installed and nginx reloaded"

# -- 4. Env file ------------------------------------------------------------

step "Env file"

sudo install -d -m 755 "$ENV_DIR"

if ! sudo test -f "$ENV_PATH"; then
    sudo install -m 640 -o root -g pipeworks \
        "$REPO/deploy/env/character-forge.env.example" "$ENV_PATH"
    cat <<EOF

$(printf '\033[33m!\033[0m') Env file installed at $ENV_PATH
  Edit it now to set HF_TOKEN, then re-run this script:

    sudoedit $ENV_PATH
    bash $REPO/deploy/install.sh

EOF
    exit 0
fi

if ! sudo grep -qE '^HF_TOKEN=hf_' "$ENV_PATH"; then
    die "HF_TOKEN= is not set in $ENV_PATH.
    Edit with: sudoedit $ENV_PATH
    Then re-run this script."
fi

ok "Env file present with HF_TOKEN configured"

# -- 5. systemd unit --------------------------------------------------------

step "systemd unit"

if [[ ! -L $SYSTEMD_LINK ]]; then
    sudo systemctl link "$REPO/deploy/systemd/$SERVICE"
    ok "Linked $SYSTEMD_LINK -> $REPO/deploy/systemd/$SERVICE"
else
    ok "Unit already linked"
fi

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE"
ok "Service enabled and started"

# -- 6. Health probe --------------------------------------------------------

step "Health probe"

# Give uvicorn a moment to bind.
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sk --max-time 2 "https://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if curl -sk --max-time 5 "https://127.0.0.1:$PORT/api/health" | grep -q '"status":"ok"'; then
    ok "Service responding on https://127.0.0.1:$PORT/api/health"
else
    warn "Service did not respond healthily within 10 s."
    warn "Check journalctl -u $SERVICE -n 50 --no-pager"
    exit 1
fi

# -- 7. Manual follow-ups ---------------------------------------------------

step "Manual follow-ups"

cat <<EOF
DrayTek LAN DNS:
    Add A-record  $HOST  ->  192.168.20.11
    (mirror the row used for images.pipeworks.luminal.local)

/etc/luminal/services.yml:
    Add an entry next to images.pipeworks.luminal.local with
    backend 127.0.0.1:$PORT, vhost $NGINX_AVAIL, cert $CERT.

Once DNS is in place, verify from another LAN host:
    curl -sk https://$HOST/api/slots | head -c 200

Done.
EOF

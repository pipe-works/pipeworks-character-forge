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
#   4. /etc/pipeworks/character-forge/character-forge.env from the example
#      (no secrets) + verifies the host-key-encrypted HF token credential
#      at /etc/pipeworks/character-forge/hf_token.cred is in place. First
#      install — exits with a reminder to encrypt one. Subsequent runs —
#      verifies the credential is readable by the pipeworks group before
#      enabling the unit.
#   5. systemd link + daemon-reload + enable + restart (so unit-file or
#      credential changes from `git pull` actually take effect — `enable
#      --now` alone leaves a running service on the old config).
#   6. Health probe against https://127.0.0.1:8420/api/health.
#
# Manual follow-ups (script prints them at the end):
#   - DrayTek LAN DNS: forge.pipeworks.luminal.local → 192.168.20.11
#   - /etc/luminal/services.yml: register the service entry.

set -euo pipefail

# -- Constants --------------------------------------------------------------

REPO=/srv/work/pipeworks/repos/pipeworks-character-forge
VENV=/srv/work/pipeworks/venvs/pw-character-forge
HOST=forge.pipeworks.luminal.local
PORT=8420
SERVICE=pipeworks-character-forge.service

ENV_DIR=/etc/pipeworks/character-forge
ENV_PATH=$ENV_DIR/character-forge.env
HF_CRED_PATH=$ENV_DIR/hf_token.cred
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

# Confirm the systemd user can actually exec the venv's python. A common
# trap: the venv was created with a python under your \$HOME (e.g. pyenv at
# ~/.pyenv), \$HOME is mode 0700, and 'pipeworks' can't traverse the
# symlink target — systemd then crash-loops with status=203/EXEC. Catch
# this in pre-flight rather than after enabling the unit.
if ! sudo -u pipeworks "$VENV/bin/python" --version >/dev/null 2>&1; then
    target=$(readlink -f "$VENV/bin/python" 2>/dev/null || true)
    die "The 'pipeworks' user cannot exec $VENV/bin/python.
    Resolved interpreter: ${target:-unknown}

    This usually means the venv was built against a python under your
    \$HOME (mode 0700) — e.g. pyenv at ~/.pyenv. Rebuild against a
    system-accessible interpreter such as /opt/python/3.12.13/bin/python3.12:

        sudo systemctl disable --now $SERVICE 2>/dev/null || true
        sudo rm -rf $VENV
        /opt/python/3.12.13/bin/python3.12 -m venv $VENV
        sudo chown -R pipeworks:pipeworks $VENV
        sudo chmod -R g+w $VENV
        sudo chmod g+s $VENV
        $VENV/bin/pip install --upgrade pip
        $VENV/bin/pip install -e '$REPO[dev,ml]'

    Then re-run this script."
fi

ok "User in 'pipeworks' group"
ok "mkcert available"
ok "Repo + venv + [ml] extras OK"
ok "Venv exec'able by 'pipeworks' systemd user"

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
    ok "Env file installed at $ENV_PATH"
fi

# Some older installs (pre-systemd-creds migration) baked HF_TOKEN= into
# the env file. The unit no longer reads it from there, but a stale value
# left on disk would defeat the whole point of the migration. Refuse to
# proceed if one is present so the operator notices and removes it.
if sudo grep -qE '^[[:space:]]*HF_TOKEN=' "$ENV_PATH"; then
    die "$ENV_PATH still contains an HF_TOKEN= line.
    HF_TOKEN now lives in $HF_CRED_PATH (encrypted).
    Edit with: sudoedit $ENV_PATH
    Remove the HF_TOKEN= line, then re-run this script."
fi

ok "Env file present and free of plaintext secrets"

# -- 4b. HF token credential ------------------------------------------------

step "HF token (systemd credential)"

if ! sudo test -f "$HF_CRED_PATH"; then
    cat <<EOF

$(printf '\033[33m!\033[0m') HF token credential missing at $HF_CRED_PATH

  Generate a Hugging Face read-scope token at
      https://huggingface.co/settings/tokens
  then encrypt it into a systemd credential:

      printf '%s' "hf_xxxxxxxxxxxx" | sudo systemd-creds encrypt \\
          --name=hf_token - $HF_CRED_PATH
      sudo chown root:pipeworks $HF_CRED_PATH
      sudo chmod 0640           $HF_CRED_PATH

  Then re-run this script:
      bash $REPO/deploy/install.sh

EOF
    exit 0
fi

# Sanity-check perms — the credential ciphertext is opaque without
# /var/lib/systemd/credential.secret, but matching the env file's
# ownership keeps audit grep results consistent.
cred_mode=$(sudo stat -c '%a' "$HF_CRED_PATH")
cred_group=$(sudo stat -c '%G' "$HF_CRED_PATH")
if [[ $cred_mode != "640" ]] || [[ $cred_group != "pipeworks" ]]; then
    warn "HF token credential perms drift: mode=$cred_mode group=$cred_group (want 640 root:pipeworks)."
    warn "Fix with: sudo chown root:pipeworks $HF_CRED_PATH && sudo chmod 0640 $HF_CRED_PATH"
fi

ok "HF token credential present at $HF_CRED_PATH"

# -- 5. systemd unit --------------------------------------------------------

step "systemd unit"

if [[ ! -L $SYSTEMD_LINK ]]; then
    sudo systemctl link "$REPO/deploy/systemd/$SERVICE"
    ok "Linked $SYSTEMD_LINK -> $REPO/deploy/systemd/$SERVICE"
else
    ok "Unit already linked"
fi

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" >/dev/null
# Always restart, never just `enable --now`: a re-run after `git pull`
# (or after rotating the HF credential) needs the new unit content and
# environment to actually take effect. `restart` on a stopped unit is
# equivalent to `start`, so this works on first install too.
sudo systemctl restart "$SERVICE"
ok "Service enabled and (re)started"

# -- 6. Health probe --------------------------------------------------------

step "Health probe"

# Give uvicorn a moment to bind.
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if curl -s --max-time 5 "http://127.0.0.1:$PORT/api/health" | grep -q '"status":"ok"'; then
    ok "Service responding on http://127.0.0.1:$PORT/api/health"

    # Optional end-to-end check through nginx (cert + vhost + proxy).
    if curl -sk --max-time 5 \
            --resolve "$HOST:443:127.0.0.1" \
            "https://$HOST/api/health" 2>/dev/null | grep -q '"status":"ok"'; then
        ok "Service responding through nginx on https://$HOST/api/health"
    else
        warn "Backend OK but nginx proxy did not respond healthily."
        warn "Check sudo nginx -t && sudo journalctl -u nginx -n 20 --no-pager"
    fi
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

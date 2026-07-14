#!/usr/bin/env bash
# update-noso-lxc.sh — update Noso inside an existing LXC container from the
# current checkout. Your config (/etc/noso/noso.toml) and the persisted
# speaker identity (/var/lib/noso) are untouched.
#
# Run ON THE PROXMOX HOST, as root, from the repo root:
#
#   cd Noso && git pull
#   bash lxc/update-noso-lxc.sh          # auto-detects the CT tagged 'noso'
#   bash lxc/update-noso-lxc.sh 140      # or name the CT id explicitly

set -euo pipefail

if [[ -t 1 ]]; then
    C_GRN=$'\e[1;32m'; C_YLW=$'\e[1;33m'; C_RED=$'\e[1;31m'; C_OFF=$'\e[0m'
else
    C_GRN=""; C_YLW=""; C_RED=""; C_OFF=""
fi
log()  { echo -e "${C_GRN}==>${C_OFF} $*"; }
warn() { echo -e "${C_YLW}WARNING:${C_OFF} $*" >&2; }
die()  { echo -e "${C_RED}ERROR:${C_OFF} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root on the Proxmox host"
command -v pct >/dev/null || die "'pct' not found — run this on a Proxmox VE host"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$REPO_ROOT/pyproject.toml" && -d "$REPO_ROOT/noso" ]] \
    || die "cannot find the Noso source tree above $REPO_ROOT/lxc — run from a full checkout"

# ------------------------------------------------------------- find the CT
CTID="${1:-}"
if [[ -z "$CTID" ]]; then
    mapfile -t IDS < <(pct list 2>/dev/null | awk 'NR>1 {print $1}')
    FOUND=()
    for id in "${IDS[@]}"; do
        pct config "$id" 2>/dev/null | grep -Eq '^tags:.*noso' && FOUND+=("$id")
    done
    if [[ ${#FOUND[@]} -eq 1 ]]; then
        CTID="${FOUND[0]}"
        log "Found Noso container: CT ${CTID}"
    elif [[ ${#FOUND[@]} -eq 0 ]]; then
        die "no container tagged 'noso' found — pass the CT id: bash lxc/update-noso-lxc.sh <ctid>"
    else
        die "several containers tagged 'noso' (${FOUND[*]}) — pass the CT id explicitly"
    fi
fi
pct status "$CTID" &>/dev/null || die "CT $CTID does not exist"

if ! pct status "$CTID" | grep -q running; then
    log "CT $CTID is stopped — starting it…"
    pct start "$CTID"
    sleep 5
fi

# ------------------------------------------------------------- push source
log "Pushing the current checkout into CT ${CTID}…"
TARBALL="$(mktemp /tmp/noso-src.XXXXXX.tar.gz)"
trap 'rm -f "$TARBALL"' EXIT
tar -C "$REPO_ROOT" -czf "$TARBALL" \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.pytest_cache' --exclude='*.egg-info' \
    .
pct push "$CTID" "$TARBALL" /tmp/noso-src.tar.gz

# ----------------------------------------------------------------- update
log "Updating /opt/noso and restarting the service…"
pct exec "$CTID" -- bash -c "
    set -euo pipefail
    systemctl stop noso || true
    rm -rf /opt/noso
    mkdir -p /opt/noso
    tar -C /opt/noso -xzf /tmp/noso-src.tar.gz
    rm /tmp/noso-src.tar.gz
    # The [mdns] extra (zeroconf, from PyPI) is what makes the modern Sonos
    # app able to discover Noso; fall back to core-only if PyPI is unreachable.
    if ! pip install --quiet --break-system-packages --no-build-isolation -e '/opt/noso[mdns]'; then
        echo 'WARNING: [mdns] extra failed (no PyPI access?) — installed without mDNS' >&2
        pip install --quiet --break-system-packages --no-build-isolation -e /opt/noso
    fi
    systemctl start noso
"

sleep 2
STATUS="$(pct exec "$CTID" -- systemctl is-active noso 2>/dev/null || true)"
CT_IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"

if [[ "$STATUS" == "active" ]]; then
    log "Done — noso is ${STATUS} on CT ${CTID} (${CT_IP:-ip pending})."
else
    warn "noso is '${STATUS:-unknown}' after the update. Check the logs:"
    warn "  pct exec $CTID -- journalctl -u noso -n 50"
    exit 1
fi

cat <<EOF

  Config kept   : /etc/noso/noso.toml — new options you can add there:
                    household = "Sonos_<your-hhid>"   # join your real household
                                                      # (see tools/capture_real_speaker.sh)
                    mdns_backend = "auto"             # auto | zeroconf | avahi | none
  Follow logs   : pct exec $CTID -- journalctl -u noso -f
EOF

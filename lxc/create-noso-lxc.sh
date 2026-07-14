#!/usr/bin/env bash
# create-noso-lxc.sh — build a Proxmox LXC container that runs Noso.
#
# Run this ON THE PROXMOX HOST, as root, from inside a checkout of the Noso
# repository (the script pushes the surrounding source tree into the CT):
#
#   git clone https://github.com/KevinThibaut89/Noso.git
#   cd Noso
#   bash lxc/create-noso-lxc.sh --room "Kitchen"
#
# What it does:
#   1. Downloads the Debian 12 standard CT template (if not already cached).
#   2. Creates an LXC container with a bridged NIC (SSDP multicast needs the
#      container to sit directly on your LAN — this is why LXC works where a
#      default Docker bridge does not).
#   3. Pushes this Noso checkout into the CT at /opt/noso and installs it.
#   4. Installs the GStreamer audio backend + ALSA utilities.
#   5. Creates the `noso` service user, writes /etc/noso/noso.toml, and
#      enables the systemd service.
#
# Audio: pass --audio to bind-mount the host's sound card (/dev/snd) into the
# container. This implies a PRIVILEGED container (the standard homelab way to
# give an LXC direct ALSA access). Without --audio, Noso still runs and is
# fully controllable — it just plays no sound (NullPlayer) unless you point
# audio_sink at a network sink (see lxc/README.md).

set -euo pipefail

# ---------------------------------------------------------------- defaults --
CTID=""                    # empty -> next free ID from the cluster
HOSTNAME="noso"
ROOM="Noso"
STORAGE=""                 # rootfs storage; empty -> auto-detect (first active
                           # storage that supports container root disks)
TEMPLATE_STORAGE="local"   # storage that holds CT templates (needs 'vztmpl')
BRIDGE="vmbr0"
IP="dhcp"                  # or CIDR like 192.168.1.50/24 (then set --gw)
GW=""
DISK_GB="4"
MEMORY_MB="512"
CORES="1"
AUDIO=0                    # 1 -> bind /dev/snd into the CT (privileged)
UNPRIVILEGED=1
START_ON_BOOT=1

usage() {
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    cat <<EOF

Options:
  --ctid N              container ID            (default: next free ID)
  --hostname NAME       CT hostname             (default: ${HOSTNAME})
  --room NAME           Sonos room name         (default: ${ROOM})
  --storage NAME        rootfs storage          (default: auto-detect)
  --template-storage N  template storage        (default: ${TEMPLATE_STORAGE})
  --bridge NAME         network bridge          (default: ${BRIDGE})
  --ip CIDR|dhcp        IP config               (default: ${IP})
  --gw IP               gateway (with static --ip)
  --disk GB             rootfs size             (default: ${DISK_GB})
  --memory MB           RAM                     (default: ${MEMORY_MB})
  --cores N             CPU cores               (default: ${CORES})
  --audio               bind host /dev/snd into the CT (implies --privileged)
  --privileged          create a privileged container
  --no-onboot           do not start the CT at host boot
  -h, --help            show this help
EOF
    exit "${1:-0}"
}

# ------------------------------------------------------------------- args --
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ctid)             CTID="$2"; shift 2 ;;
        --hostname)         HOSTNAME="$2"; shift 2 ;;
        --room)             ROOM="$2"; shift 2 ;;
        --storage)          STORAGE="$2"; shift 2 ;;
        --template-storage) TEMPLATE_STORAGE="$2"; shift 2 ;;
        --bridge)           BRIDGE="$2"; shift 2 ;;
        --ip)               IP="$2"; shift 2 ;;
        --gw)               GW="$2"; shift 2 ;;
        --disk)             DISK_GB="$2"; shift 2 ;;
        --memory)           MEMORY_MB="$2"; shift 2 ;;
        --cores)            CORES="$2"; shift 2 ;;
        --audio)            AUDIO=1; UNPRIVILEGED=0; shift ;;
        --privileged)       UNPRIVILEGED=0; shift ;;
        --no-onboot)        START_ON_BOOT=0; shift ;;
        -h|--help)          usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

log()  { echo -e "\e[1;32m==>\e[0m $*"; }
warn() { echo -e "\e[1;33mWARNING:\e[0m $*" >&2; }
die()  { echo -e "\e[1;31mERROR:\e[0m $*" >&2; exit 1; }

# ----------------------------------------------------------------- checks --
[[ $EUID -eq 0 ]] || die "run as root on the Proxmox host"
command -v pct  >/dev/null || die "'pct' not found — run this on a Proxmox VE host"
command -v pveam >/dev/null || die "'pveam' not found — run this on a Proxmox VE host"

# Locate the repo root relative to this script and sanity-check it.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$REPO_ROOT/pyproject.toml" && -d "$REPO_ROOT/noso" ]] \
    || die "cannot find the Noso source tree above $REPO_ROOT/lxc — run from a full checkout"

if [[ "$IP" != "dhcp" && -z "$GW" ]]; then
    die "--ip $IP is static; a gateway is required (--gw)"
fi

# Pick a rootfs storage: prefer an explicit --storage, otherwise the first
# active storage that can hold container root disks ('rootdir' content).
if [[ -z "$STORAGE" ]]; then
    STORAGE="$(pvesm status -content rootdir 2>/dev/null \
               | awk 'NR>1 && $3=="active" {print $1}' | head -n1)"
    [[ -n "$STORAGE" ]] || die "no active storage supports container disks (rootdir) — pass --storage NAME (see 'pvesm status')"
    log "Auto-selected rootfs storage: $STORAGE"
else
    pvesm status -content rootdir 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$STORAGE" \
        || die "storage '$STORAGE' does not exist or cannot hold container disks (see 'pvesm status -content rootdir')"
fi

if [[ -z "$CTID" ]]; then
    CTID="$(pvesh get /cluster/nextid)"
fi
pct status "$CTID" &>/dev/null && die "CT $CTID already exists"

if [[ $AUDIO -eq 1 && ! -d /dev/snd ]]; then
    warn "/dev/snd does not exist on this host (no sound card?)."
    warn "Proceeding, but the container will fall back to silent playback."
fi

# --------------------------------------------------------------- template --
log "Looking for a Debian 12 CT template…"
TEMPLATE="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null \
            | awk '{print $1}' | grep -o 'debian-12-standard.*' | sort -V | tail -n1 || true)"
if [[ -z "$TEMPLATE" ]]; then
    log "Not cached — downloading via pveam…"
    pveam update >/dev/null
    TEMPLATE="$(pveam available --section system \
                | awk '{print $2}' | grep '^debian-12-standard' | sort -V | tail -n1)"
    [[ -n "$TEMPLATE" ]] || die "no debian-12-standard template offered by pveam"
    pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi
TEMPLATE_REF="${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE##*/}"
log "Using template: $TEMPLATE_REF"

# ----------------------------------------------------------------- create --
NET0="name=eth0,bridge=${BRIDGE},firewall=0"
if [[ "$IP" == "dhcp" ]]; then
    NET0+=",ip=dhcp"
else
    NET0+=",ip=${IP},gw=${GW}"
fi

log "Creating CT $CTID (${HOSTNAME}, unprivileged=${UNPRIVILEGED})…"
pct create "$CTID" "$TEMPLATE_REF" \
    --hostname "$HOSTNAME" \
    --unprivileged "$UNPRIVILEGED" \
    --ostype debian \
    --rootfs "${STORAGE}:${DISK_GB}" \
    --memory "$MEMORY_MB" \
    --swap 0 \
    --cores "$CORES" \
    --net0 "$NET0" \
    --onboot "$START_ON_BOOT" \
    --tags "noso;sonos" \
    --description "Noso — Sonos ZonePlayer emulator (room: ${ROOM})"

if [[ $AUDIO -eq 1 ]]; then
    log "Enabling sound-card passthrough (/dev/snd)…"
    cat >> "/etc/pve/lxc/${CTID}.conf" <<'EOF'
# Noso: host sound card passthrough (ALSA). 116 = major of /dev/snd devices.
lxc.cgroup2.devices.allow: c 116:* rwm
lxc.mount.entry: /dev/snd dev/snd none bind,optional,create=dir
EOF
fi

log "Starting CT $CTID…"
pct start "$CTID"

# Wait for the container to finish booting and (with DHCP) get networking up.
log "Waiting for the container to come up…"
for _ in $(seq 1 30); do
    STATE="$(pct exec "$CTID" -- systemctl is-system-running 2>/dev/null || true)"
    [[ "$STATE" == "running" || "$STATE" == "degraded" ]] && break
    sleep 2
done
log "Waiting for network inside the container…"
for _ in $(seq 1 30); do
    pct exec "$CTID" -- sh -c 'hostname -I 2>/dev/null | grep -q "[0-9]"' && break
    sleep 2
done

# ------------------------------------------------------------ push source --
log "Pushing the Noso source tree to /opt/noso…"
TARBALL="$(mktemp /tmp/noso-src.XXXXXX.tar.gz)"
trap 'rm -f "$TARBALL"' EXIT
tar -C "$REPO_ROOT" -czf "$TARBALL" \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.pytest_cache' --exclude='*.egg-info' \
    .
pct push "$CTID" "$TARBALL" /tmp/noso-src.tar.gz
pct exec "$CTID" -- bash -c "mkdir -p /opt/noso && tar -C /opt/noso -xzf /tmp/noso-src.tar.gz && rm /tmp/noso-src.tar.gz"

# ---------------------------------------------------------------- install --
log "Installing packages inside the CT (this is the slow part)…"
pct exec "$CTID" -- bash -c "
    set -euo pipefail
    export DEBIAN_FRONTEND=noninteractive
    apt-get -qq update
    apt-get -qq install -y --no-install-recommends \
        python3 python3-pip python3-setuptools python3-gi \
        gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
        gir1.2-gstreamer-1.0 gstreamer1.0-alsa alsa-utils ca-certificates
    # --no-build-isolation: build with the system setuptools so the install
    # needs no PyPI access (noso itself has zero pip dependencies).
    pip install --quiet --break-system-packages --no-build-isolation -e /opt/noso
"

log "Configuring the noso service (room: ${ROOM})…"
ROOM_SED="${ROOM//\//\\/}"; ROOM_SED="${ROOM_SED//&/\\&}"
pct exec "$CTID" -- bash -c "
    set -euo pipefail
    useradd --system --home /var/lib/noso noso 2>/dev/null || true
    usermod -aG audio noso
    mkdir -p /etc/noso
    if [[ ! -f /etc/noso/noso.toml ]]; then
        sed 's/^room_name = .*/room_name = \"${ROOM_SED}\"/' \
            /opt/noso/noso.example.toml > /etc/noso/noso.toml
    fi
    cp /opt/noso/systemd/noso.service /etc/systemd/system/noso.service
    systemctl daemon-reload
    systemctl enable --now noso
"

# ---------------------------------------------------------------- summary --
sleep 2
CT_IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"
STATUS="$(pct exec "$CTID" -- systemctl is-active noso || true)"

echo
log "Done. Container $CTID is up."
cat <<EOF

  Room name : ${ROOM}
  CT IP     : ${CT_IP:-<pending — check 'pct exec $CTID -- hostname -I'>}
  Service   : noso (${STATUS})
  Audio     : $([[ $AUDIO -eq 1 ]] && echo "/dev/snd passed through (host sound card)" || echo "none — silent NullPlayer unless you configure a sink")

  Useful commands (on the Proxmox host):
    pct exec $CTID -- journalctl -u noso -f     # follow logs
    pct exec $CTID -- nano /etc/noso/noso.toml  # edit config, then:
    pct exec $CTID -- systemctl restart noso
    pct enter $CTID                              # shell inside the CT

  Verify from any machine on the LAN (pip install soco):
    python3 -c "import soco; print([z.player_name for z in soco.discover()])"

  NOTE: discovery uses SSDP multicast. The bridge (${BRIDGE}) must be on the
  same L2 network as your controllers, with no IGMP-snooping/VLAN filtering
  in between.
EOF

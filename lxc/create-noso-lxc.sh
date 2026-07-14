#!/usr/bin/env bash
# create-noso-lxc.sh — build a Proxmox LXC container that runs Noso.
#
# Run this ON THE PROXMOX HOST, as root, from inside a checkout of the Noso
# repository (the script pushes the surrounding source tree into the CT):
#
#   git clone https://github.com/KevinThibaut89/Noso.git
#   cd Noso
#   bash lxc/create-noso-lxc.sh              # interactive wizard (whiptail)
#   bash lxc/create-noso-lxc.sh --room "Kitchen" --audio   # non-interactive
#
# With no arguments on a terminal it opens a community-scripts-style wizard
# (Default / Advanced settings). Any flag switches to non-interactive mode.
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
# Audio: --audio (or the wizard question) bind-mounts the host's sound card
# (/dev/snd) into the container. This implies a PRIVILEGED container (the
# standard homelab way to give an LXC direct ALSA access). Without it, Noso
# still runs and is fully controllable — it just plays no sound (NullPlayer)
# unless you point audio_sink at a network sink (see lxc/README.md).

set -euo pipefail

# ------------------------------------------------------------ pretty output
if [[ -t 1 ]]; then
    C_GRN=$'\e[1;32m'; C_YLW=$'\e[1;33m'; C_RED=$'\e[1;31m'; C_CYN=$'\e[36m'; C_OFF=$'\e[0m'
else
    C_GRN=""; C_YLW=""; C_RED=""; C_CYN=""; C_OFF=""
fi
LOG="$(mktemp /tmp/noso-lxc.XXXXXX.log)"

log()  { echo -e "${C_GRN}==>${C_OFF} $*"; }
warn() { echo -e "${C_YLW}WARNING:${C_OFF} $*" >&2; }
die()  { echo -e "${C_RED}ERROR:${C_OFF} $*" >&2; exit 1; }
abort(){ echo -e "\n${C_YLW}Aborted by user.${C_OFF}"; exit 1; }

# run <description> <command...> — run a step quietly with a spinner and a
# ✔/✖ result line; full output goes to $LOG and is shown on failure.
FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
run() {
    local desc="$1"; shift
    echo "----- $desc -----" >>"$LOG"
    if [[ -t 1 ]]; then
        ("$@") >>"$LOG" 2>&1 &
        local pid=$! i=0
        while kill -0 "$pid" 2>/dev/null; do
            printf '\r %s%s%s %s' "$C_YLW" "${FRAMES[i++ % 10]}" "$C_OFF" "$desc"
            sleep 0.1
        done
        if wait "$pid"; then
            printf '\r %s✔%s %s \n' "$C_GRN" "$C_OFF" "$desc"
        else
            printf '\r %s✖%s %s \n' "$C_RED" "$C_OFF" "$desc"
            echo; tail -n 25 "$LOG" >&2
            die "step failed — full log: $LOG"
        fi
    else
        echo "==> $desc"
        "$@" >>"$LOG" 2>&1 || { tail -n 25 "$LOG" >&2; die "step failed — full log: $LOG"; }
    fi
}

header() {
    cat <<EOF
${C_CYN}    _   __
   / | / /___  _________
  /  |/ / __ \\/ ___/ __ \\
 / /|  / /_/ (__  ) /_/ /
/_/ |_/\\____/____/\\____/${C_OFF}
 Sonos ZonePlayer emulator — Proxmox LXC installer
EOF
}

# ---------------------------------------------------------------- defaults
CTID=""                    # empty -> next free ID from the cluster
HOSTNAME="noso"
ROOM="Noso"
STORAGE=""                 # empty -> auto-detect / wizard picker
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
    header
    cat <<EOF

Usage: bash lxc/create-noso-lxc.sh [options]

Run with NO options on a terminal to get the interactive wizard.

Options (any option switches to non-interactive mode):
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

# -------------------------------------------------------------------- args
INTERACTIVE=1
[[ $# -gt 0 ]] && INTERACTIVE=0
{ [[ -t 0 && -t 1 ]] && command -v whiptail >/dev/null; } || INTERACTIVE=0

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

# ------------------------------------------------------------------ checks
[[ $EUID -eq 0 ]] || die "run as root on the Proxmox host"
command -v pct   >/dev/null || die "'pct' not found — run this on a Proxmox VE host"
command -v pveam >/dev/null || die "'pveam' not found — run this on a Proxmox VE host"

# Locate the repo root relative to this script and sanity-check it.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$REPO_ROOT/pyproject.toml" && -d "$REPO_ROOT/noso" ]] \
    || die "cannot find the Noso source tree above $REPO_ROOT/lxc — run from a full checkout"

NEXTID="$(pvesh get /cluster/nextid 2>/dev/null)"

# Active storages that can hold container root disks: "name type" per line.
mapfile -t ROOTFS_STORAGES < <(pvesm status -content rootdir 2>/dev/null \
                               | awk 'NR>1 && $3=="active" {print $1, $2}')
[[ ${#ROOTFS_STORAGES[@]} -gt 0 ]] \
    || die "no active storage supports container disks (rootdir) — check 'pvesm status'"

# ------------------------------------------------------------------ wizard
WT="whiptail --backtitle Noso-LXC"

ask_room() {
    while :; do
        ROOM="$($WT --title "Room name" --inputbox \
            "Name shown as the room/zone in Sonos controllers:" 10 58 "$ROOM" \
            3>&1 1>&2 2>&3)" || abort
        [[ -n "$ROOM" ]] && break
    done
}

wizard() {
    header
    $WT --title "Noso LXC" --yesno \
"This will create a new LXC container running Noso
(a Sonos ZonePlayer emulator) on this Proxmox host.

Proceed?" 11 58 || abort

    local mode
    mode="$($WT --title "Settings" --menu "Choose an option:" 12 58 2 \
        "1" "Default Settings  (CT ${NEXTID}, 1 CPU, 512 MB, DHCP)" \
        "2" "Advanced Settings" \
        3>&1 1>&2 2>&3)" || abort

    ask_room
    [[ "$mode" == "1" ]] && { confirm_summary; return; }

    # ---- advanced ----
    while :; do
        CTID="$($WT --title "Container ID" --inputbox "Container ID:" 10 58 "$NEXTID" \
            3>&1 1>&2 2>&3)" || abort
        [[ "$CTID" =~ ^[0-9]+$ ]] || continue
        pct status "$CTID" &>/dev/null || break
        $WT --title "Container ID" --msgbox "CT $CTID already exists — pick another ID." 8 58
    done

    HOSTNAME="$($WT --title "Hostname" --inputbox "Container hostname:" 10 58 "$HOSTNAME" \
        3>&1 1>&2 2>&3)" || abort

    DISK_GB="$($WT --title "Disk" --inputbox "Root disk size (GB):" 10 58 "$DISK_GB" \
        3>&1 1>&2 2>&3)" || abort
    CORES="$($WT --title "CPU" --inputbox "CPU cores:" 10 58 "$CORES" \
        3>&1 1>&2 2>&3)" || abort
    MEMORY_MB="$($WT --title "Memory" --inputbox "RAM (MB):" 10 58 "$MEMORY_MB" \
        3>&1 1>&2 2>&3)" || abort

    if [[ ${#ROOTFS_STORAGES[@]} -eq 1 ]]; then
        STORAGE="${ROOTFS_STORAGES[0]%% *}"
    else
        local items=()
        local s
        for s in "${ROOTFS_STORAGES[@]}"; do
            items+=("${s%% *}" "${s#* }")
        done
        STORAGE="$($WT --title "Storage" --menu "Storage for the container disk:" \
            16 58 "${#ROOTFS_STORAGES[@]}" "${items[@]}" 3>&1 1>&2 2>&3)" || abort
    fi

    BRIDGE="$($WT --title "Network" --inputbox \
        "Bridge (must be on the same L2 network as your Sonos controllers — SSDP multicast):" \
        11 58 "$BRIDGE" 3>&1 1>&2 2>&3)" || abort

    local ipmode
    ipmode="$($WT --title "IP address" --menu "IP configuration:" 12 58 2 \
        "dhcp"   "Automatic (DHCP)" \
        "static" "Static IP" \
        3>&1 1>&2 2>&3)" || abort
    if [[ "$ipmode" == "static" ]]; then
        IP="$($WT --title "Static IP" --inputbox "IP address in CIDR form (e.g. 192.168.1.50/24):" \
            10 58 "" 3>&1 1>&2 2>&3)" || abort
        GW="$($WT --title "Gateway" --inputbox "Gateway IP:" 10 58 "" \
            3>&1 1>&2 2>&3)" || abort
    else
        IP="dhcp"; GW=""
    fi

    if $WT --title "Audio" --defaultno --yesno \
"Pass the host's sound card (/dev/snd) into the container?

Audio then plays out of this Proxmox host's own output
(speakers / HDMI / USB DAC). This makes the container
PRIVILEGED.

Choose 'No' to run silent/controllable, or to use a
network audio sink later." 14 58; then
        AUDIO=1; UNPRIVILEGED=0
    else
        AUDIO=0
        if $WT --title "Container type" --defaultno --yesno \
            "Make the container privileged anyway?\n(Default: unprivileged — recommended.)" 9 58; then
            UNPRIVILEGED=0
        fi
    fi

    if $WT --title "Autostart" --yesno "Start the container automatically when the Proxmox host boots?" 8 58; then
        START_ON_BOOT=1
    else
        START_ON_BOOT=0
    fi

    confirm_summary
}

confirm_summary() {
    [[ -z "$CTID" ]] && CTID="$NEXTID"
    [[ -z "$STORAGE" ]] && STORAGE="${ROOTFS_STORAGES[0]%% *}"
    $WT --title "Ready to build" --yesno \
"Create this container?

  CT ID      : ${CTID}
  Hostname   : ${HOSTNAME}
  Room name  : ${ROOM}
  Resources  : ${CORES} CPU / ${MEMORY_MB} MB RAM / ${DISK_GB} GB disk
  Storage    : ${STORAGE}
  Network    : ${BRIDGE}, ${IP}$( [[ -n "$GW" ]] && echo " gw ${GW}" )
  Audio      : $( [[ $AUDIO -eq 1 ]] && echo "host sound card (/dev/snd)" || echo "none (silent/NullPlayer)" )
  Type       : $( [[ $UNPRIVILEGED -eq 1 ]] && echo "unprivileged" || echo "privileged" )
  On boot    : $( [[ $START_ON_BOOT -eq 1 ]] && echo "yes" || echo "no" )" 21 62 || abort
}

if [[ $INTERACTIVE -eq 1 ]]; then
    wizard
else
    header
fi

# ------------------------------------------------------- resolve leftovers
if [[ "$IP" != "dhcp" && -z "$GW" ]]; then
    die "--ip $IP is static; a gateway is required (--gw)"
fi

if [[ -z "$STORAGE" ]]; then
    STORAGE="${ROOTFS_STORAGES[0]%% *}"
    log "Auto-selected rootfs storage: $STORAGE"
else
    printf '%s\n' "${ROOTFS_STORAGES[@]}" | awk '{print $1}' | grep -qx "$STORAGE" \
        || die "storage '$STORAGE' does not exist or cannot hold container disks (see 'pvesm status -content rootdir')"
fi

[[ -z "$CTID" ]] && CTID="$NEXTID"
pct status "$CTID" &>/dev/null && die "CT $CTID already exists"

if [[ $AUDIO -eq 1 && ! -d /dev/snd ]]; then
    warn "/dev/snd does not exist on this host (no sound card?)."
    warn "Proceeding, but the container will fall back to silent playback."
fi

# ---------------------------------------------------------------- template
TEMPLATE="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null \
            | awk '{print $1}' | grep -o 'debian-12-standard.*' | sort -V | tail -n1 || true)"
if [[ -z "$TEMPLATE" ]]; then
    run "Updating CT template catalogue" pveam update
    TEMPLATE="$(pveam available --section system 2>/dev/null \
                | awk '{print $2}' | grep '^debian-12-standard' | sort -V | tail -n1)"
    [[ -n "$TEMPLATE" ]] || die "no debian-12-standard template offered by pveam"
    run "Downloading template ${TEMPLATE}" pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi
TEMPLATE_REF="${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE##*/}"

# ------------------------------------------------------------------ create
NET0="name=eth0,bridge=${BRIDGE},firewall=0"
if [[ "$IP" == "dhcp" ]]; then
    NET0+=",ip=dhcp"
else
    NET0+=",ip=${IP},gw=${GW}"
fi

run "Creating CT ${CTID} (${HOSTNAME}, $( [[ $UNPRIVILEGED -eq 1 ]] && echo un )privileged)" \
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
    cat >> "/etc/pve/lxc/${CTID}.conf" <<'EOF'
# Noso: host sound card passthrough (ALSA). 116 = major of /dev/snd devices.
lxc.cgroup2.devices.allow: c 116:* rwm
lxc.mount.entry: /dev/snd dev/snd none bind,optional,create=dir
EOF
    log "Sound-card passthrough enabled (/dev/snd)"
fi

run "Starting CT ${CTID}" pct start "$CTID"

wait_for_boot() {
    local state _
    for _ in $(seq 1 30); do
        state="$(pct exec "$CTID" -- systemctl is-system-running 2>/dev/null || true)"
        [[ "$state" == "running" || "$state" == "degraded" ]] && return 0
        sleep 2
    done
    return 0   # proceed anyway; apt will fail loudly if it's truly broken
}
wait_for_net() {
    local _
    for _ in $(seq 1 30); do
        pct exec "$CTID" -- sh -c 'hostname -I 2>/dev/null | grep -q "[0-9]"' && return 0
        sleep 2
    done
    warn "container has no IP yet — continuing, but apt may fail"
    return 0
}
run "Waiting for the container to boot" wait_for_boot
run "Waiting for network (DHCP)" wait_for_net

# ------------------------------------------------------------- push source
push_source() {
    local tarball
    tarball="$(mktemp /tmp/noso-src.XXXXXX.tar.gz)"
    tar -C "$REPO_ROOT" -czf "$tarball" \
        --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.pytest_cache' --exclude='*.egg-info' \
        .
    pct push "$CTID" "$tarball" /tmp/noso-src.tar.gz
    rm -f "$tarball"
    pct exec "$CTID" -- bash -c "mkdir -p /opt/noso && tar -C /opt/noso -xzf /tmp/noso-src.tar.gz && rm /tmp/noso-src.tar.gz"
}
run "Copying Noso source to /opt/noso" push_source

# ----------------------------------------------------------------- install
run "Installing Debian packages + Noso (the slow part)" \
    pct exec "$CTID" -- bash -c "
        set -euo pipefail
        export DEBIAN_FRONTEND=noninteractive
        apt-get -qq update
        apt-get -qq install -y --no-install-recommends \
            python3 python3-pip python3-setuptools python3-gi \
            gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
            gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
            gir1.2-gstreamer-1.0 gstreamer1.0-alsa alsa-utils ca-certificates
        # --no-build-isolation: build with the system setuptools. The [mdns]
        # extra (zeroconf, from PyPI) is REQUIRED for the modern Sonos app to
        # discover Noso; fall back to a core install if PyPI is unreachable.
        if ! pip install --quiet --break-system-packages --no-build-isolation -e '/opt/noso[mdns]'; then
            echo 'WARNING: [mdns] extra failed (no PyPI access?) — installing without mDNS; the modern Sonos app will not see this speaker' >&2
            pip install --quiet --break-system-packages --no-build-isolation -e /opt/noso
        fi
    "

ROOM_SED="${ROOM//\//\\/}"; ROOM_SED="${ROOM_SED//&/\\&}"
run "Configuring the noso service (room: ${ROOM})" \
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

# ----------------------------------------------------------------- summary
sleep 2
CT_IP="$(pct exec "$CTID" -- hostname -I 2>/dev/null | awk '{print $1}' || true)"
STATUS="$(pct exec "$CTID" -- systemctl is-active noso 2>/dev/null || true)"

echo
log "Done. Container ${CTID} is up."
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

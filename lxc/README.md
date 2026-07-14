# Running Noso in a Proxmox LXC container

LXC is a good fit for Noso: unlike a default Docker bridge, an LXC container
gets its own bridged NIC directly on your LAN, which is exactly what SSDP
multicast discovery needs.

## Quick start

On the **Proxmox host**, as root:

```bash
git clone https://github.com/KevinThibaut89/Noso.git
cd Noso
bash lxc/create-noso-lxc.sh --room "Kitchen"
```

That single command:

1. downloads the Debian 12 standard CT template (if not cached),
2. creates an unprivileged container (1 core, 512 MB RAM, 4 GB disk, DHCP on
   `vmbr0`),
3. copies this checkout to `/opt/noso` inside the container and
   `pip install -e`'s it,
4. installs the GStreamer audio backend and ALSA utilities,
5. creates the `noso` service user, writes `/etc/noso/noso.toml` with your
   room name, and enables the systemd service.

When it finishes it prints the container's IP and a SoCo one-liner to verify
discovery from another machine.

## Options

```
--ctid N              container ID            (default: next free ID)
--hostname NAME       CT hostname             (default: noso)
--room NAME           Sonos room name         (default: Noso)
--storage NAME        rootfs storage          (default: auto-detect)
--template-storage N  CT template storage     (default: local)
--bridge NAME         network bridge          (default: vmbr0)
--ip CIDR|dhcp        e.g. 192.168.1.50/24    (default: dhcp)
--gw IP               gateway, required with a static --ip
--disk GB / --memory MB / --cores N
--audio               pass the host sound card through (see below)
--privileged          create a privileged container
--no-onboot           don't autostart the CT when the host boots
```

Example with a static IP and audio:

```bash
bash lxc/create-noso-lxc.sh --room "Office" \
    --ip 192.168.1.50/24 --gw 192.168.1.1 --audio
```

## Audio: three realistic setups

A container has no sound card of its own, so pick one:

1. **Host sound card (`--audio`)** — bind-mounts `/dev/snd` into the
   container so GStreamer plays through the Proxmox host's audio output
   (speakers/HDMI/USB DAC plugged into the server). This implies a
   *privileged* container, which is the standard homelab pattern for ALSA in
   LXC. If several ALSA devices exist, pin one in `/etc/noso/noso.toml`:

   ```toml
   audio_sink = "alsasink device=hw:1"
   ```

2. **Network audio sink** — keep the container unprivileged and send audio
   elsewhere, e.g. to a PulseAudio/PipeWire server on another machine:

   ```toml
   audio_sink = "pulsesink server=tcp:192.168.1.20:4713"
   ```

3. **No audio** — without `--audio` and with no sink configured, Noso runs
   with the silent `NullPlayer`: it is still discovered and fully
   controllable, which is enough for development and integration testing.

## Networking notes (important)

- Discovery is **SSDP multicast** (UDP 1900) plus a broadcast fallback;
  control is HTTP on TCP 1400. The script creates the NIC with
  `firewall=0` — if you enable the Proxmox firewall for this CT, allow
  those ports.
- The bridge you attach to (default `vmbr0`) must be on the **same L2
  network** as your Sonos controllers. VLAN hops, IGMP snooping without a
  querier, and Wi-Fi AP client isolation all silently break discovery.

## Day-2 operations

```bash
pct exec <ctid> -- journalctl -u noso -f      # follow logs
pct exec <ctid> -- systemctl restart noso     # after editing /etc/noso/noso.toml
pct enter <ctid>                              # shell inside the container
```

**Updating Noso** — from a fresh checkout on the Proxmox host:

```bash
cd Noso && git pull
tar -C . -czf /tmp/noso-src.tar.gz --exclude=.git .
pct push <ctid> /tmp/noso-src.tar.gz /tmp/noso-src.tar.gz
pct exec <ctid> -- bash -c 'tar -C /opt/noso -xzf /tmp/noso-src.tar.gz \
    && pip install -q --break-system-packages -e /opt/noso \
    && systemctl restart noso'
```

**Turning the CT into a reusable template** — once it's set up the way you
like, back it up and reuse it:

```bash
vzdump <ctid> --compress zstd --dumpdir /var/lib/vz/dump
pct restore <new-ctid> /var/lib/vz/dump/vzdump-lxc-<ctid>-*.tar.zst
```

(Then change `room_name` in the clone's `/etc/noso/noso.toml`. Each Noso
instance mints a stable RINCON identity on first start and persists it to
`/var/lib/noso/.local/share/noso/identity.json` — if you clone a CT that has
already run, delete that file in the clone so it generates a fresh identity
instead of colliding with the original.)

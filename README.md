# Noso

Noso turns a Linux box into something that looks and behaves like a **Sonos
speaker** (a "ZonePlayer") on your network: it shows up as a room in Sonos
controllers, and audio sent to it plays out of the machine's speakers.

It is pure Python standard library at the core — no pip dependencies — so it
runs on anything from a Raspberry Pi to a server. Audio playback uses whatever
backend you have (GStreamer, mpv, or ffmpeg).

---

## What actually works (read this first)

A Sonos speaker lives on two separate protocol "planes", and they are very
different in how open they are:

| Plane | Discovery | Control | Device auth | Noso? |
|---|---|---|---|---|
| **Legacy UPnP** | SSDP (UDP 1900) | SOAP + GENA (TCP 1400) | **none** | ✅ **emulated** |
| **Modern** (2024+ app) | mDNS + cloud household | TLS WebSocket (1443) | Sonos-signed X.509 device cert + secure registration | ❌ not possible in software |

Noso emulates the **legacy UPnP plane**. That plane has no device
authentication — topology is self-reported over plain HTTP — which is exactly
why it can be emulated.

**Confirmed working:** any legacy-plane controller —
[SoCo](https://github.com/SoCo/SoCo) (python), node-sonos, and Home Assistant's
Sonos integration — discovers Noso, lists it as a room, and drives playback,
volume, mute, grouping metadata, room renaming, and live events.

**The honest caveat about the official app:** the app Sonos shipped in May 2024
discovers over mDNS and, to *add* a product, requires a factory-provisioned,
Sonos-signed device certificate that lives behind the speaker's secure boot.
That cannot be reproduced in software, so a self-built speaker **cannot be
onboarded through "Add Product" in the current app.** Whether an *older* app
build (or an already-established household with UPnP enabled) surfaces a
legacy zone is firmware/app-version dependent and unproven — see
[Getting it into the Sonos app](#getting-it-into-the-sonos-app). If your goal is
"reliably stream audio to this Linux box", the SoCo/Home-Assistant path is the
one to count on.

---

## Install

Requires **Python 3.11+**. The core needs no pip packages.

```bash
git clone https://github.com/KevinThibaut89/Noso.git
cd Noso
pip install -e .          # installs the `noso` command (no runtime deps)
```

For real audio output, install one backend (any one is enough):

```bash
# Debian/Ubuntu/Raspberry Pi OS — GStreamer (recommended):
sudo apt install python3-gi gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
                 gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav

# ...or mpv:      sudo apt install mpv libmpv-dev && pip install python-mpv
# ...or ffmpeg:   sudo apt install ffmpeg
```

Without any of these, Noso still runs and is fully controllable — it just
produces no sound (`NullPlayer`).

## Run

```bash
noso --room "Kitchen"
# or: python -m noso --room "Kitchen"
```

Then open a controller (e.g. the SoCo one-liner below) and you should see the
room. Common flags:

```
--room NAME           room/zone name shown in the app
--model "Sonos One"   --model-number S13
--ip 192.168.1.50     advertise a specific LAN IP (else autodetected)
--audio auto|gstreamer|mpv|ffmpeg|null
--config noso.toml    load a TOML config file (see noso.example.toml)
--log-level DEBUG
```

> **Networking:** discovery needs SSDP multicast, so Noso must run on the host
> LAN — natively or with `docker run --network host`. A default Docker bridge,
> or a VLAN with IGMP snooping / AP client-isolation, will silently break
> discovery. Noso also broadcasts to `255.255.255.255` to survive many
> multicast-hostile networks, and you can pin the IP with `--ip`.

## Verify it works

With `pip install -e '.[dev]'` (installs SoCo) and Noso running:

```python
import soco
zp = soco.discover().pop()          # or soco.SoCo("<noso-ip>")
print(zp.player_name)               # -> your room name
zp.volume = 40
zp.play_uri("http://example.com/test.mp3")
print(zp.get_current_transport_info()["current_transport_state"])  # PLAYING
```

## Getting it into the Sonos app

Because the modern "Add Product" flow is gated by the device certificate,
target an environment where the **legacy UPnP path** is live:

1. In the Sonos app: **Settings → System → Network → check for a UPnP / "local
   control" toggle** and ensure it's on (older/S1 systems and some S2 builds).
2. Put Noso on the **same L2 network** as your existing speakers (no VLAN
   hop, multicast allowed).
3. **Capture your real speaker for fidelity** — the biggest lever you have:
   ```bash
   tools/capture_real_speaker.sh <your-speaker-ip> noso/assets/scpd
   ```
   This downloads that speaker's exact SCPDs so Noso serves them verbatim, and
   saves a `device_description.real.xml` to diff against. Set `--model` /
   `--model-number` to match, too.
4. The decisive early signal: run `tcpdump -n -A 'port 1400 or port 1900'` and
   watch whether the app ever HTTP-GETs Noso's `:1400/xml/device_description.xml`.
   If it never touches `:1400`, the app is mDNS-only and no amount of polish
   will surface Noso — and that's your definitive answer.

## How it works

```
noso/
  ssdp.py          SSDP: answers M-SEARCH, announces ssdp:alive/byebye
  httpd.py         minimal asyncio HTTP/1.1 server (UPnP control plane, :1400)
  soap.py          SOAP request parsing + response/fault building
  gena.py          GENA eventing: SUBSCRIBE/UNSUBSCRIBE + initial & change NOTIFY
  device.py        device_description.xml (root ZonePlayer + _MS/_MR devices)
  zonegroup.py     ZoneGroupState — the payload that makes it a "room"
  scpd.py          serves real SCPDs if present, else generates valid ones
  identity.py      stable RINCON_ UUID / MAC / serial (persisted)
  services/        one module per UPnP service (AVTransport, RenderingControl, …)
  audio/           AudioPlayer backends: gstreamer, mpv, ffmpeg, null
```

Playback is Sonos's **pull model**: a controller calls
`AVTransport.SetAVTransportURI(url)` then `Play`, and Noso's audio backend
HTTP-GETs the URL and decodes it (MP3/AAC/FLAC/ALAC/WAV/OGG, HLS/Shoutcast).

## Run as a service

```bash
sudo useradd --system --home /var/lib/noso noso && sudo usermod -aG audio noso
sudo cp systemd/noso.service /etc/systemd/system/
sudo mkdir -p /etc/noso && sudo cp noso.example.toml /etc/noso/noso.toml
sudo systemctl enable --now noso
```

## Run in a Proxmox LXC container

A one-command provisioner is included: on the Proxmox host,

```bash
git clone https://github.com/KevinThibaut89/Noso.git && cd Noso
bash lxc/create-noso-lxc.sh    # interactive wizard; or pass flags, e.g. --room "Kitchen" --audio
```

It creates a Debian 12 container on your LAN bridge (SSDP multicast works out
of the box, unlike a default Docker bridge), installs Noso + GStreamer, and
enables the service. See [`lxc/README.md`](lxc/README.md) for options, audio
setups, and updating.

## Limitations

- Not accepted by the modern app's setup flow (device-certificate wall).
- Single standalone zone: no real multi-room grouping/stereo-pair (grouping
  actions are accepted as no-ops so controllers don't error).
- Not affiliated with or endorsed by Sonos, Inc. "Sonos" is used only to
  describe interoperability. For personal/interoperability use on networks you
  control.

## License

MIT — see `pyproject.toml`.

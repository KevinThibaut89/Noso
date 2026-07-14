#!/usr/bin/env bash
#
# Capture a real Sonos speaker's UPnP descriptions so Noso can serve them
# verbatim. Serving byte-identical device_description.xml + SCPDs is the single
# highest-fidelity thing you can do to make a picky controller/app accept the
# emulator, so run this against a speaker you own and drop the results into
# noso/assets/scpd/ (filenames are matched automatically).
#
# Usage:
#   tools/capture_real_speaker.sh <speaker-ip> [scpd-outdir]
#
# Example:
#   tools/capture_real_speaker.sh 192.168.1.42 noso/assets/scpd
#
set -euo pipefail

IP="${1:?usage: capture_real_speaker.sh <speaker-ip> [scpd-outdir]}"
OUT="${2:-noso/assets/scpd}"
BASE="http://${IP}:1400"
REF_DIR="$(dirname "$OUT")"

mkdir -p "$OUT"
echo "==> Fetching device_description.xml from ${BASE}"
curl -fsS "${BASE}/xml/device_description.xml" -o "${REF_DIR}/device_description.real.xml"
echo "    saved ${REF_DIR}/device_description.real.xml (reference; compare against noso/device.py output)"

echo "==> Downloading every SCPD the device advertises"
python3 - "$IP" "$OUT" <<'PY'
import os, sys, urllib.request, xml.etree.ElementTree as ET

ip, out = sys.argv[1], sys.argv[2]
base = f"http://{ip}:1400"
desc = urllib.request.urlopen(f"{base}/xml/device_description.xml", timeout=10).read()
ns = "{urn:schemas-upnp-org:device-1-0}"
urls = sorted({e.text for e in ET.fromstring(desc).iter(f"{ns}SCPDURL") if e.text})
for url in urls:
    name = os.path.basename(url)
    try:
        data = urllib.request.urlopen(base + url, timeout=10).read()
    except Exception as exc:  # noqa: BLE001
        print(f"    !! {url}: {exc}")
        continue
    with open(os.path.join(out, name), "wb") as fh:
        fh.write(data)
    print(f"    saved {os.path.join(out, name)}  ({len(data)} bytes)")
PY

cat <<EOF

==> Done.
Restart Noso; any SCPD whose filename matches a service's scpd_asset is now
served verbatim instead of the generated fallback.

To capture live discovery/control traffic for a byte-level diff against Noso:
  sudo tcpdump -i <iface> -n -A 'port 1900 or port 1400'
EOF

"""Command-line entrypoint: ``python -m noso`` / the ``noso`` console script."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .app import NosoApp
from .config import Config

log = logging.getLogger("noso")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="noso",
        description="Emulate a Sonos ZonePlayer on the legacy UPnP plane.",
    )
    parser.add_argument("-c", "--config", help="path to a TOML config file")
    parser.add_argument("--room", dest="room_name", help="room/zone name shown in the app")
    parser.add_argument("--model", dest="model_name", help='e.g. "Sonos PLAY:3"')
    parser.add_argument("--model-number", dest="model_number", help='e.g. "S3"')
    parser.add_argument("--sw-version", dest="software_version", help="advertised firmware version")
    parser.add_argument("--ip", dest="interface_ip", help="LAN IP to advertise (autodetect if unset)")
    parser.add_argument("--bind", dest="bind_ip", help="bind address (default 0.0.0.0)")
    parser.add_argument("--http-port", dest="http_port", type=int, help="UPnP/SOAP port (default 1400)")
    parser.add_argument("--ssdp-port", dest="ssdp_port", type=int, help="SSDP port (default 1900)")
    parser.add_argument(
        "--audio",
        dest="audio_backend",
        choices=["auto", "gstreamer", "mpv", "ffmpeg", "null"],
        help="audio backend (default auto)",
    )
    parser.add_argument("--audio-sink", dest="audio_sink", help="GStreamer sink override")
    parser.add_argument(
        "--no-mdns", dest="mdns_enabled", action="store_const", const=False, default=None,
        help="disable mDNS advertisement (the modern app needs it to discover Noso)",
    )
    parser.add_argument(
        "--mdns-backend", dest="mdns_backend", choices=["auto", "zeroconf", "avahi", "none"],
        help="mDNS backend (default auto)",
    )
    parser.add_argument(
        "--household", dest="household",
        help="household id to advertise (paste your real hhid to look like a member)",
    )
    parser.add_argument("--icon", dest="icon", help="room icon, e.g. x-rincon-roomicon:living")
    parser.add_argument("--state-dir", dest="state_dir", help="where identity.json is stored")
    parser.add_argument(
        "--log-level",
        dest="log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging level (default INFO)",
    )
    return parser.parse_args(argv)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


async def _run(config: Config) -> None:
    app = NosoApp(config)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-Unix
            pass

    await app.start()
    print(f"Noso is up as room {config.room_name!r} — {app.ctx.description_url}", flush=True)
    try:
        await stop.wait()
    finally:
        await app.stop()


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    overrides = {k: v for k, v in vars(args).items() if k != "config"}
    config = Config.build(config_file=args.config, **overrides)
    _setup_logging(config.log_level)
    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:  # pragma: no cover
        pass


if __name__ == "__main__":
    main()

"""Noso — a Linux program that emulates a Sonos ZonePlayer.

Noso speaks the *legacy* Sonos UPnP plane: SSDP discovery on UDP 1900 and
UPnP/SOAP control on TCP 1400, with GENA eventing. That plane has no device
authentication, so legacy-plane controllers (SoCo, node-sonos, Home
Assistant, and older / UPnP-enabled Sonos apps) can discover it, list it as
a room, and drive playback. The modern Sonos app's mDNS + signed-certificate
onboarding is *not* emulated (it cannot be, in software) — see README.
"""

__version__ = "0.1.0"

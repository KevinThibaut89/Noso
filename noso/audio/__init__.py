"""Audio backends for the emulated speaker.

The core protocol stack talks to an :class:`~noso.audio.base.AudioPlayer`; the
concrete backend (GStreamer, mpv, ffmpeg, or a no-op) is chosen at runtime by
:func:`~noso.audio.factory.make_player`, so Noso runs even on a box with no
audio stack installed.
"""

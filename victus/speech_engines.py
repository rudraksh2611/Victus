"""Compatibility: import from ``victus.speech`` instead."""

from .speech import SpeakingStopped, print_installed_voices, speak_segments

__all__ = ["SpeakingStopped", "print_installed_voices", "speak_segments"]

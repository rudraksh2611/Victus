"""Text-to-speech: Edge (default), Windows SAPI fallback."""

from .engines import SpeakingStopped, print_installed_voices, speak_segments

__all__ = ["SpeakingStopped", "print_installed_voices", "speak_segments"]

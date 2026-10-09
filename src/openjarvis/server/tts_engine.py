"""Lightweight Windows TTS Engine for OpenJarvis.

Synthesizes speech to WAV audio using Windows System.Speech.Synthesis
with built-in caching for instant sub-millisecond audio streaming.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger("openjarvis.server.tts")

_AUDIO_CACHE: dict[str, bytes] = {}


def synthesize_wav(text: str) -> bytes | None:
    """Synthesize text to WAV audio bytes using native Windows SAPI."""
    clean = (
        re.sub(r"[*_#`~]", "", text)
        .replace("—", ", ")
        .replace("–", ", ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )
    if not clean:
        return None

    # Keep spoken answers articulate and under 240 chars for brisk, natural speech
    if len(clean) > 240:
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        trimmed = ""
        for s in sentences:
            if len(trimmed) + len(s) < 220:
                trimmed = (trimmed + " " + s).strip()
            else:
                break
        clean = trimmed or clean[:200].rsplit(" ", 1)[0] + "."

    if clean in _AUDIO_CACHE:
        return _AUDIO_CACHE[clean]

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name

    # Escape quotes for VBScript
    vbs_clean = clean.replace('"', '""')
    vbs_file = wav_path + ".vbs"

    # Primary Engine: Native Windows SAPI via cscript (zero external dependencies)
    try:
        with open(vbs_file, "w", encoding="utf-8") as f:
            f.write(f'''Set voice = CreateObject("SAPI.SpVoice")
Set stream = CreateObject("SAPI.SpFileStream")
stream.Open "{wav_path}", 3, False
Set voice.AudioOutputStream = stream
voice.Rate = 1
voice.Volume = 100
voice.Speak "{vbs_clean}"
stream.Close
''')
        subprocess.run(
            ["cscript", "//nologo", vbs_file],
            check=True,
            capture_output=True,
            timeout=8,
        )
        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
            with open(wav_path, "rb") as f:
                data = f.read()
            _AUDIO_CACHE[clean] = data
            return data
    except Exception as exc:
        logger.debug("cscript SAPI attempt failed: %s, falling back to powershell", exc)

    # Secondary Engine: PowerShell System.Speech fallback
    ps_file = wav_path + ".ps1"
    try:
        with open(ps_file, "w", encoding="utf-8") as f:
            f.write(f"""Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 1
$synth.Volume = 100
$synth.SetOutputToWaveFile('{wav_path}')
$synth.Speak(@'
{clean}
'@)
$synth.Dispose()
""")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps_file,
            ],
            check=True,
            capture_output=True,
            timeout=12,
        )
        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 1000:
            with open(wav_path, "rb") as f:
                data = f.read()
            _AUDIO_CACHE[clean] = data
            return data
    except Exception as exc:
        logger.warning("TTS generation failed for '%s': %s", clean[:30], exc)
        return None
    finally:
        for p in (wav_path, vbs_file, ps_file):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    return None

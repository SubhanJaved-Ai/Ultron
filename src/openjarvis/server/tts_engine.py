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


def synthesize_wav(text: str, voice_gender: str = "masculine") -> bytes | None:
    """Synthesize text to WAV audio bytes using native Windows SAPI.

    Args:
        text: Spoken text content.
        voice_gender: Voice timbre preference ('masculine', 'feminine', or 'neutral').
    """
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

    gender_key = str(voice_gender or "masculine").lower().strip()
    cache_key = f"{gender_key}:{clean}"
    if cache_key in _AUDIO_CACHE:
        return _AUDIO_CACHE[cache_key]

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = tf.name

    # Escape quotes for VBScript
    vbs_clean = clean.replace('"', '""')
    vbs_file = wav_path + ".vbs"

    is_female = gender_key == "feminine"
    vbs_voice_filter = (
        'InStr(LCase(v.GetDescription), "zira") > 0 Or InStr(LCase(v.GetDescription), "female") > 0'
        if is_female
        else 'InStr(LCase(v.GetDescription), "david") > 0 Or (InStr(LCase(v.GetDescription), "male") > 0 And InStr(LCase(v.GetDescription), "female") = 0)'
    )
    ps_gender_enum = (
        "[System.Speech.Synthesis.VoiceGender]::Female"
        if is_female
        else "[System.Speech.Synthesis.VoiceGender]::Male"
    )

    # Primary Engine: Native Windows SAPI via cscript (zero external dependencies)
    try:
        with open(vbs_file, "w", encoding="utf-8") as f:
            f.write(f'''Set voice = CreateObject("SAPI.SpVoice")
For Each v In voice.GetVoices
    If {vbs_voice_filter} Then
        Set voice.Voice = v
        Exit For
    End If
Next
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
            _AUDIO_CACHE[cache_key] = data
            return data
    except Exception as exc:
        logger.debug("cscript SAPI attempt failed: %s, falling back to powershell", exc)

    # Secondary Engine: PowerShell System.Speech fallback
    ps_file = wav_path + ".ps1"
    try:
        with open(ps_file, "w", encoding="utf-8") as f:
            f.write(f"""Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{ $synth.SelectVoiceByHints({ps_gender_enum}) }} catch {{}}
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
            _AUDIO_CACHE[cache_key] = data
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

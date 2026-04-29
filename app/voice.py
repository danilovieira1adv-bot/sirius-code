"""
voice.py — STT (Whisper local) + TTS (ElevenLabs ou gTTS)
"""
import os
import time
import hashlib
import asyncio


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

async def transcribe_audio(file_path: str) -> str:
    """Transcreve áudio usando faster-whisper (modelo 'base', CPU).

    Suporta .ogg, .mp3, .wav, .m4a e qualquer formato que o ffmpeg aceite.
    Retorna o texto transcrito (str).
    """
    loop = asyncio.get_event_loop()

    def _transcribe():
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(
            file_path,
            language="pt",
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    # Roda em executor para não bloquear o event-loop
    text = await loop.run_in_executor(None, _transcribe)
    return text


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

async def speak(text: str, voice_id: str = None) -> str:
    """Converte texto em áudio MP3.

    Usa ElevenLabs se ELEVENLABS_API_KEY estiver configurada.
    Senão, usa gTTS como fallback gratuito.

    Retorna o caminho do arquivo MP3 gerado.
    """
    os.makedirs("/app/data/files", exist_ok=True)
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    out_path = f"/app/data/files/tts_{h}_{int(time.time())}.mp3"

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    if api_key:
        await _speak_elevenlabs(text, out_path, api_key, voice_id)
    else:
        await _speak_gtts(text, out_path)

    return out_path


async def _speak_elevenlabs(text: str, out_path: str, api_key: str, voice_id: str = None):
    loop = asyncio.get_event_loop()

    def _generate():
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=api_key)
        # Adam (multilíngue) como padrão; qualquer voz pode ser passada via voice_id
        vid = voice_id or "pNInz6obpgDQGcFmaJgB"
        audio = client.text_to_speech.convert(
            voice_id=vid,
            text=text,
            model_id="eleven_multilingual_v2",
        )
        with open(out_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)

    await loop.run_in_executor(None, _generate)


async def _speak_gtts(text: str, out_path: str):
    loop = asyncio.get_event_loop()

    def _generate():
        from gtts import gTTS
        tts = gTTS(text=text, lang="pt")
        tts.save(out_path)

    await loop.run_in_executor(None, _generate)

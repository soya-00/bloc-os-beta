import sounddevice as sd
import numpy as np
import tempfile
import soundfile as sf
from faster_whisper import WhisperModel


class Transcriber:
    """
    BLOC voice transcription engine.
    Silent — no raw print() calls. All status goes through
    the optional status_callback(message: str) hook so the
    shell controls how output is displayed.

    device="cpu"   → faster-whisper on Pi 5 CPU (current)
    device="hailo" → Hailo-8L accelerated pipeline (on Pi, future)
    """

    def __init__(self, model_size="base", status_callback=None):
        self._cb = status_callback or (lambda msg, inline=False: None)
        self.sample_rate = 16000

        self._cb("ACQUIRING VOICE ENGINE")

        # ── device selection ──────────────────────────────
        # When Hailo drivers are available on the Pi, set
        # device="hailo" in bloc.config and swap this block
        # for the Hailo ASR pipeline initialisation.
        self.model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"
        )

        self._cb("VOICE ENGINE · ONLINE")

    # ─── recording ────────────────────────────────────────

    def record_until_silence(
        self,
        silence_threshold: float = 0.01,
        max_duration: int = 30,
    ) -> np.ndarray:
        """
        Record until silence is detected.
        Calls status_callback with live level bar each chunk.
        """
        self._cb("CHANNEL OPEN · LISTENING")

        chunk_duration  = 0.5
        chunk_samples   = int(self.sample_rate * chunk_duration)
        chunks          = []
        silent_chunks   = 0
        max_silent      = 3

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32"
        ) as stream:
            while len(chunks) < (max_duration / chunk_duration):
                chunk, _ = stream.read(chunk_samples)
                chunks.append(chunk.flatten())

                volume = np.abs(chunk).mean()
                bars   = int(volume * 400)
                bar    = "█" * min(bars, 20) + "░" * (20 - min(bars, 20))
                self._cb(f"LVL [{bar}]", inline=True)

                if volume < silence_threshold:
                    silent_chunks += 1
                    if silent_chunks >= max_silent and len(chunks) > 4:
                        break
                else:
                    silent_chunks = 0

        self._cb("SIGNAL LOST · PROCESSING")
        return np.concatenate(chunks)

    def record_fixed(self, duration: int = 5) -> np.ndarray:
        """Fixed-duration recording."""
        self._cb(f"RECORDING · {duration}s · SPEAK NOW")
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32"
        )
        sd.wait()
        self._cb("RECORDING STOPPED")
        return audio.flatten()

    # ─── transcription ────────────────────────────────────

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe audio array to text string."""
        self._cb("DECODING TRANSMISSION")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, audio, self.sample_rate)
            segments, _ = self.model.transcribe(tmp.name, language="en")
            text = " ".join(s.text.strip() for s in segments)
        return text.strip()

    # ─── main entry point ─────────────────────────────────

    def listen_and_transcribe(self, duration: int = None) -> str:
        """
        Full pipeline — record then transcribe.
        Returns transcript string. Empty string if nothing heard.
        """
        if duration:
            audio = self.record_fixed(duration)
        else:
            audio = self.record_until_silence()

        text = self.transcribe(audio)

        if text:
            self._cb(f"TRANSCRIPT · {text.upper()}")
        else:
            self._cb("NO SIGNAL · TRANSMISSION EMPTY")

        return text
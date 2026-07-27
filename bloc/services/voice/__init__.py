"""
Voice pipeline: wake word -> capture -> transcription -> intent -> action.

Transcription sits behind a backend Protocol so the CPU and NPU paths are
interchangeable:

    backend.py         Protocol
    whisper_cpu.py     faster-whisper on CPU
    whisper_hailo.py   Hailo-8L accelerated (verify model-zoo support first)
    wakeword.py        always-listening detector; the better first NPU target
    nlu.py             scored intent matcher, replacing ordered regex
"""

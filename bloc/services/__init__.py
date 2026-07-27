"""
Long-lived domain services.

Service state is persisted as atomic JSON under ~/bloc/state/, which is what
makes a background daemon optional rather than load-bearing: anything wanting to
observe state reads a file.

Planned modules:

    base.py      Service protocol: start / stop / status / probe
    registry.py  service table
    adsb.py      one OpenSky client with a TTL cache, shared by every consumer
    pulse.py     focus timer, derived from wall clock and persisted
    agenda.py    day time-blocks
    sync.py      vault backup
    voice/       transcription backends, wake word, intent parsing
"""

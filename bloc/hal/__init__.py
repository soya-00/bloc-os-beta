"""
Hardware abstraction layer.

Every hardware capability is a Protocol with a real implementation and a null
implementation. `detect.py` probes at boot and selects. Consequences:

  * the same code runs on a laptop (null printer, null controls, terminal
    display) and on the Pi (real everything) with no conditionals in app code
  * new hardware is a new file implementing a Protocol — nothing above changes
  * hardware not yet owned does not block development
  * the boot checklist becomes honest for free: each probe is exactly the
    [ OK ] / [ STANDBY ] line the sequence already prints

Planned modules:

    base.py             Protocols: Display, Audio, Printer, Controls, Power
    detect.py           probe and select implementations
    terminal.py         Display  -> ANSI terminal (laptop + Pi console)
    framebuffer.py      Display  -> pygame / DRM
    epaper.py           Display  -> SPI e-ink, for ambient mode
    audio_alsa.py       Audio    -> sounddevice
    printer_escpos.py   Printer  -> ESC/POS thermal
    controls_gpio.py    Controls -> gpiozero + lgpio (NOT RPi.GPIO on Pi 5)
    power_pi.py         Power    -> battery, RTC, shutdown
    null.py             no-op implementation of every Protocol
"""

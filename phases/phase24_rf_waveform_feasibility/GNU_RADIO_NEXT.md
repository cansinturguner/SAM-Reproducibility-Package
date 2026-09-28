# GNU Radio continuation plan

This file is a plan, not an implemented or measured experiment.

## Stage A: software loopback

1. Read the deterministic complex64 samples exported by the Phase 24 runner.
2. Apply controlled channel impairments: AWGN, frequency offset, sample-clock
   offset, and optional multipath.
3. Recover symbol timing and the PPM in-phase message.
4. Differentially demodulate the D8PSK overlay.
5. Compare recovered bits with the exported truth vector.

## Stage B: cabled SDR loopback

1. Use two SDR devices or a full-duplex device connected by coaxial cable.
2. Install appropriate fixed attenuation and verify levels before enabling TX.
3. Record device, sample-rate, gain, clock-source, attenuation, and firmware
   metadata in the report.
4. Repeat BER and packet-recovery measurements across received-power settings.

## Stage C: receiver compatibility

This requires qualified laboratory facilities and suitable receivers. It is not
authorized or implemented by this package. Any RF work must comply with local
spectrum rules and must not inject test signals into operational aviation bands.

# Source and implementation decisions

## Published CABBA elements represented

- D8PSK phase overlay associated with a 112-symbol 1090ES message;
- 336 overlay bits before allocation;
- 12 reference-phase bits;
- RS(54,34) accounting with 204 information bits and 120 parity bits;
- AWGN/Eb/N0 feasibility analysis as a software experiment.

## Independent implementation choices

The available CABBA paper is not a bit-exact executable specification. This
package therefore records, rather than conceals, the following choices:

- GF(64) primitive polynomial: `x^6 + x + 1` (`0x43`);
- RS generator roots: `alpha^1` through `alpha^20`;
- systematic 34-symbol payload followed by 20 parity symbols;
- each 6-bit RS symbol maps to two consecutive 3-bit D8PSK increments;
- natural-binary phase-increment labels from 0 through 7;
- differential phase starts at zero and uses hard decisions;
- perfect carrier and symbol timing;
- unit-energy complex symbols with independent complex Gaussian noise.

These choices permit a transparent and repeatable feasibility test. They are
not claimed to be the choices made by the CABBA authors, RTCA, or a certified
receiver implementation.

## RS interpretation and decoder

RS(54,34) has 20 parity symbols and a guaranteed bounded-distance correction
radius of 10 symbol errors. Version 2 retains this theoretical indicator and
also runs `reedsolo==1.7.0` with `c_exp=6`, `prim=0x43`, `fcr=1`, and 20 parity
symbols. A deterministic test confirms that its encoded codeword is identical
to the internal encoder and that a 10-symbol error vector is corrected. Decoder
success, declared failure, and miscorrection are reported separately beyond the
guaranteed correction radius.

## Safety boundary

No RF transmission is performed. Any later SDR test must begin with file or
cabled/attenuated loopback and must not radiate experimental traffic in the
operational 1090 MHz aviation band.

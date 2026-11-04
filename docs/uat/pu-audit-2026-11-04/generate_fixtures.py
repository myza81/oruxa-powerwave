"""Generate synthetic COMTRADE pairs for the PU DEV UAT checklist.

Standard library only. Output is explicitly selected by the engineer; these are
test signals, not owner event records. No application configuration is changed.
"""
from argparse import ArgumentParser
from math import pi, sin, sqrt
from pathlib import Path


def generate(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for label, marker, current_peak in (
        ("PRIMARY", "P", 4199.0),
        ("SECONDARY", "S", 4.199),
        ("UNKNOWN", "", 4199.0),
    ):
        station = "PU_UAT_" + label
        channels = []
        for phase, shift in zip("RYB", (0, -2 * pi / 3, 2 * pi / 3)):
            channels.append(("BUS V" + phase, "kV", 275 * sqrt(2 / 3), shift))
        for bay in ("HV", "LV"):
            for phase, shift in zip("RYB", (0, -2 * pi / 3, 2 * pi / 3)):
                channels.append(("IBT1 " + bay + " I" + phase, "A", current_peak, shift))
        cfg = [station + ",SYNTHETIC_UAT,1999", "9,9A,0D"]
        for index, (name, unit, peak, _shift) in enumerate(channels, 1):
            phase = "ABC"[(index - 1) % 3]
            cfg.append(f"{index},{name},{phase},,{unit},{peak / 30000:.17g},0,0,-32767,32767,1,1,{marker}")
        cfg += ["50", "1", "1000,201", "04/11/2026,10:00:00.000000",
                "04/11/2026,10:00:00.000000", "ASCII", "1"]
        dat = []
        for sample in range(201):
            values = [str(round(30000 * sin(2 * pi * 50 * sample / 1000 + shift)))
                      for _name, _unit, _peak, shift in channels]
            dat.append(",".join([str(sample + 1), str(sample * 1000), *values]))
        (destination / (station + ".cfg")).write_bytes(("\r\n".join(cfg) + "\r\n").encode("ascii"))
        (destination / (station + ".dat")).write_bytes(("\r\n".join(dat) + "\r\n").encode("ascii"))


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    generate(parser.parse_args().output_directory)

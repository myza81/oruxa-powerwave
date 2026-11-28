"""The COMTRADE scenario runner's path normalisation is platform-independent (test infrastructure only).

The frozen COMTRADE baselines (`fixtures/comtrade_frequency/comtrade_frequency_baseline.json`) were generated on Windows. A parser or upload error
message embeds the temporary path the file was read from, so the runner replaces it with placeholders (`<CFG>`, `<DIR>`, `<FILE>`). Before this module's
subject was corrected, only the Windows spelling of a path was recognised, so the same baseline failed on Linux CI (`<DIR>/e.dat`, `/tmp/...`).

These tests build the message exactly as each platform would write it (with `PureWindowsPath` / `PurePosixPath`, so they run identically everywhere)
and require BOTH to normalise to the byte-for-byte text frozen in the baseline, while meaningful content (file names, error wording, numbers, other
directories) is left untouched. The baseline file itself is never edited.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from tests import comtrade_frequency_scenarios as scn

FROZEN = json.loads(scn.BASELINE_PATH.read_text(encoding="utf-8"))["outcomes"]

WINDOWS_CFG = PureWindowsPath(r"C:\Users\someone\AppData\Local\Temp\oruxa-comtrade-freq-ab12cd\e.cfg")
POSIX_CFG = PurePosixPath("/tmp/oruxa-comtrade-freq-ab12cd/e.cfg")
PLATFORMS = [pytest.param(WINDOWS_CFG, id="windows"), pytest.param(POSIX_CFG, id="posix")]


def sep(path) -> str:
    return "\\" if isinstance(path, PureWindowsPath) else "/"


def repr_form(text: str) -> str:
    """How a path looks inside a `repr()` (the backslashes of a Windows path are doubled)."""
    return text.replace("\\", "\\\\")


class TestTheNormalisedTextEqualsTheFrozenBaselineOnEveryPlatform:
    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_a_message_naming_a_file_in_the_directory(self, cfg):
        frozen = FROZEN["parser"]["other_binary32_declared_60"]["message"]
        message = ("BINARY32 (COMTRADE 2013 float32) is not supported by this provider. "
                   f"Convert '{cfg.parent}{sep(cfg)}e.dat' to ASCII or BINARY format before loading.")
        assert scn._normalise_text(message, cfg) == frozen

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_the_cfg_path_and_two_directory_paths_in_one_message(self, cfg):
        frozen = FROZEN["fixtures"]["phasor_bare_three_phase.cfg"]["message"]
        d = f"{cfg.parent}{sep(cfg)}"
        message = f"DAT file not found for '{cfg}': tried '{d}phasor_bare_three_phase.dat' and '{d}phasor_bare_three_phase.DAT'"
        # the frozen fixture entry names a different CFG file but the same placeholders and tail
        assert scn._normalise_text(message, cfg) == frozen

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_a_warning_that_names_the_cfg(self, cfg):
        message = f"Cannot parse nominal frequency '50 Hz' in '{cfg}', defaulting to 50.0"
        assert scn._normalise_text(message, cfg) == "Cannot parse nominal frequency '50 Hz' in '<CFG>', defaulting to 50.0"

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_the_repr_spelling_of_the_path_is_recognised_too(self, cfg):
        message = f"Convert '{repr_form(str(cfg.parent))}{repr_form(sep(cfg))}e.dat' now"
        assert scn._normalise_text(message, cfg) == "Convert '<DIR>\\e.dat' now"

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_a_temporary_upload_path_becomes_file(self, cfg):
        frozen = FROZEN["api"]["missing_lf_file_truncated"]["error"]["message"]
        event = f"{cfg.parent}{sep(cfg)}event.cfg"
        text = f"Could not parse the COMTRADE record: CFG '{event}' is truncated: missing field 'nominal frequency (lf)'"
        assert scn._json_safe(text) == frozen

    def test_the_frozen_baseline_contains_the_canonical_spellings_this_relies_on(self):
        assert "<DIR>\\e.dat" in FROZEN["parser"]["other_binary32_declared_60"]["message"]
        assert "'<FILE>'" in FROZEN["api"]["missing_lf_file_truncated"]["error"]["message"]


class TestMeaningfulContentIsPreserved:
    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_a_different_file_name_is_kept(self, cfg):
        message = f"Convert '{cfg.parent}{sep(cfg)}other.dat' to ASCII"
        assert scn._normalise_text(message, cfg).endswith("'<DIR>\\other.dat' to ASCII")

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_another_directory_is_not_replaced(self, cfg):
        message = "Convert '/var/elsewhere/e.dat' and 'D:\\elsewhere\\e.dat' to ASCII"
        assert scn._normalise_text(message, cfg) == message

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_wording_numbers_and_ordinary_slashes_are_untouched(self, cfg):
        message = "COMTRADE 1999/2013 record: nrates 'x' at 4000.0,4 (50/60 Hz) is not supported"
        assert scn._normalise_text(message, cfg) == message

    @pytest.mark.parametrize("cfg", PLATFORMS)
    def test_normalising_twice_changes_nothing(self, cfg):
        once = scn._normalise_text(f"in '{cfg}' and '{cfg.parent}{sep(cfg)}e.dat'", cfg)
        assert scn._normalise_text(once, cfg) == once

    def test_a_posix_path_that_is_not_the_upload_event_file_is_left_alone(self):
        for text in ("CFG '/tmp/x/other.cfg' is truncated", "see '/usr/lib/python3/event_x.py'", "rate 50/60 Hz and 1999/2013",
                     "path '/tmp/oruxa-comtrade-ab/event.txt'"):
            assert scn._json_safe(text) == text

    def test_a_windows_event_path_and_a_posix_event_path_both_become_file_and_nothing_else_changes(self):
        for event in (r"C:\Users\u\AppData\Local\Temp\tmpab\event.cfg", "C:/Users/u/AppData/Local/Temp/tmpab/event.dat",
                      "/tmp/oruxa-comtrade-ab/event.cfg", "/var/folders/xy/T/oruxa-comtrade-ab/event.dat"):
            assert scn._json_safe(f"CFG '{event}' is truncated") == "CFG '<FILE>' is truncated", event
            assert scn._json_safe(f'in "{event}"') == 'in "<FILE>"', event


class TestARealPath:
    def test_every_spelling_of_a_real_temporary_path_is_recognised(self, tmp_path):
        cfg = tmp_path / "e.cfg"
        for spelling in (str(cfg), cfg.as_posix(), str(cfg).replace("\\", "\\\\"), str(cfg.resolve())):
            assert scn._normalise_text(f"in '{spelling}'", cfg) == "in '<CFG>'", spelling
        for spelling in (str(tmp_path), tmp_path.as_posix(), str(tmp_path.resolve())):
            assert scn._normalise_text(f"in '{spelling}{'/' if '/' in spelling else chr(92)}e.dat'", cfg) == "in '<DIR>\\e.dat'", spelling

    def test_the_resolved_spelling_of_a_symlinked_directory_is_recognised(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks are not available here")
        cfg = link / "e.cfg"
        assert Path(cfg).resolve().parent != cfg.parent
        assert scn._normalise_text(f"Convert '{cfg.resolve().parent}/e.dat'", cfg) == "Convert '<DIR>\\e.dat'"

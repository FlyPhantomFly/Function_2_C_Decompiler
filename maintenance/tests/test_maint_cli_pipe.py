"""A reader that goes away (`decomp backup --status | head`) is not an error and must not print a traceback.

Python raises BrokenPipeError when it writes to a pipe whose reader has exited, and a command-line tool that does not expect it prints a traceback for
something the user did on purpose. `main()` now treats it as the end of the conversation: quietly, and without a second error when the interpreter flushes at exit.
"""

from __future__ import annotations

import subprocess
import sys

from decompnet.app import cli


def test_a_command_whose_reader_has_gone_ends_quietly(monkeypatch, tmp_path):
    def vanished(args):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setenv("DECOMP_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "backup_cmd", vanished)
    assert cli.main(["backup"]) == 0


def test_other_errors_are_not_swallowed(monkeypatch, tmp_path):
    import pytest

    def broken(args):
        raise RuntimeError("a real bug")

    monkeypatch.setenv("DECOMP_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "backup_cmd", broken)
    with pytest.raises(RuntimeError, match="a real bug"):
        cli.main(["backup"])


def test_through_a_real_pipe_to_a_reader_that_has_already_exited_there_is_no_traceback(tmp_path):
    """`true` exits at once without reading: by the time Python writes, the read end is closed."""
    done = subprocess.run(f"{sys.executable} -m decompnet.app.cli backup --status | true", shell=True, capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "DECOMP_HOME": str(tmp_path), "HOME": str(tmp_path), "PYTHONPATH": ":".join(sys.path)})
    assert "Traceback" not in done.stderr and "BrokenPipe" not in done.stderr, done.stderr

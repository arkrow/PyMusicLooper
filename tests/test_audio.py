import os

import pytest

from pymusiclooper.audio import _suppress_stderr


def test_suppresses_fd2_preserves_stdout_and_restores_on_error(capfd, monkeypatch):
    monkeypatch.delenv("PML_DEBUG", raising=False)

    with pytest.raises(RuntimeError), _suppress_stderr():
        os.write(1, b"stdout-ok")
        os.write(2, b"stderr-hidden")
        raise RuntimeError("boom")
    os.write(2, b"stderr-restored")

    captured = capfd.readouterr()
    assert captured.out == "stdout-ok"
    assert captured.err == "stderr-restored"


def test_noop_in_debug_mode(capfd, monkeypatch):
    monkeypatch.setenv("PML_DEBUG", "1")

    with _suppress_stderr():
        os.write(2, b"stderr-visible")

    captured = capfd.readouterr()
    assert captured.err == "stderr-visible"


def test_noop_when_fd_invalid(monkeypatch):
    monkeypatch.delenv("PML_DEBUG", raising=False)

    def _raise_ebadf(_fd):
        raise OSError(9, "Bad file descriptor")

    monkeypatch.setattr("pymusiclooper.audio.os.dup", _raise_ebadf)
    ran = False
    with _suppress_stderr():
        ran = True
    assert ran

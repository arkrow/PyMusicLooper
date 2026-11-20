import ast
import importlib.util
import sys
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pymusiclooper


def test_sphinx_click_rich_markup_hook():
    conf_path = Path("docs/conf.py").resolve()
    assert conf_path.exists()
    spec = importlib.util.spec_from_file_location("pml_docs_conf", conf_path)
    conf_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf_mod)

    lines = [
        ".. option:: --path <path>",
        "",
        r"   Path to the audio file(s). [dim cyan]\[mutually exclusive with --url][/] [dim red]\[at least one required][/]",
        "   :options: WAV|FLAC|OGG|MP3",
    ]
    conf_mod._strip_rich_markup_from_lines(lines)
    assert lines[0] == ".. option:: --path <path>"
    assert (
        lines[2]
        == "   Path to the audio file(s). [mutually exclusive with --url] [at least one required]"
    )
    assert lines[3] == "   :options: WAV|FLAC|OGG|MP3"

    for rst in ("index.rst", "cli.rst", "api.rst"):
        assert (Path("docs") / rst).exists()


def test_version_fallback_on_package_not_found(monkeypatch):
    assert pymusiclooper.__version__

    def _missing(_name):
        raise PackageNotFoundError("pymusiclooper")

    monkeypatch.setitem(sys.modules, "pymusiclooper._version", None)
    monkeypatch.setattr("pymusiclooper.version", _missing)
    assert pymusiclooper._get_version() == "0.0.0+unknown"


def test_pyinstaller_spec_and_workflow_valid():
    spec_path = Path("pymusiclooper.spec").resolve()
    assert spec_path.exists()
    spec_src = spec_path.read_text(encoding="utf-8")
    ast.parse(spec_src)
    assert 'copy_metadata("pymusiclooper")' in spec_src

    wf_path = Path(".github/workflows/build-executables.yml").resolve()
    assert wf_path.exists()
    wf_src = wf_path.read_text(encoding="utf-8")
    assert "windows-latest" in wf_src
    assert "ubuntu-latest" in wf_src

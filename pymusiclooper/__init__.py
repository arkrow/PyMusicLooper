from importlib.metadata import PackageNotFoundError, version


def _get_version() -> str:
    try:
        return version("pymusiclooper")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _get_version()

from importlib.metadata import PackageNotFoundError, version


def _get_version() -> str:
    try:
        from pymusiclooper._version import __version__

        return __version__
    except ImportError:
        pass

    try:
        return version("pymusiclooper")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _get_version()

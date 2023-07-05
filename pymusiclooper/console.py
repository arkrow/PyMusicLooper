from rich.console import Console

# Module-level rich console instance
rich_console = Console()

# Creating groups for CLI --help styling
_basic_options = ["--path", "--url"]
_loop_options = [
    "--min-duration-multiplier",
    "--min-loop-duration",
    "--max-loop-duration",
    "--approx-loop-position",
    "--brute-force",
    "--disable-pruning",
]
_export_options = ["--output-dir", "--format"]
_batch_options = ["--recursive", "--flatten"]


def _option_groups(additional_basic_options=None):
    if additional_basic_options is not None:
        combined_basic_options = _basic_options + additional_basic_options
    else:
        combined_basic_options = _basic_options
    return [
        {
            "name": "Basic options",
            "options": combined_basic_options,
        },
        {
            "name": "Advanced loop options",
            "options": _loop_options,
        },
        {
            "name": "Export options",
            "options": _export_options,
        },
        {
            "name": "Batch options",
            "options": _batch_options,
        },
    ]


_common_option_groups = _option_groups()
OPTION_GROUPS = {
    "pymusiclooper play": _common_option_groups,
    "pymusiclooper split-audio": _common_option_groups,
    "pymusiclooper tag": _option_groups(["--tag-names"]),
    "pymusiclooper export-points": _option_groups(["--export-to"]),
}
COMMAND_GROUPS = {
    "pymusiclooper": [
        {
            "name": "Play Commands",
            "commands": [
                "play",
                "play-tagged"
            ],
        },
        {
            "name": "Export Commands",
            "commands": [
                "export-points",
                "split-audio",
                "tag"
            ],
        }
    ]
}

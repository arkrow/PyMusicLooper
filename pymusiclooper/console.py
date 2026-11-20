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
_read_tag_options = ["--read-tags", "--tag-names", "--tag-offset"]
_export_options = ["--output-dir", "--format"]
_batch_options = ["--recursive", "--flatten"]


def _option_groups(additional_basic_options=None, include_read_tag_options=True):
    if additional_basic_options is not None:
        combined_basic_options = _basic_options + additional_basic_options
    else:
        combined_basic_options = _basic_options
    groups = [
        {
            "name": "Basic options",
            "options": combined_basic_options,
        },
        {
            "name": "Advanced loop options",
            "options": _loop_options,
        },
    ]
    if include_read_tag_options:
        groups.append(
            {
                "name": "Tag reading options",
                "options": _read_tag_options,
            }
        )
    groups.extend(
        [
            {
                "name": "Export options",
                "options": _export_options,
            },
            {
                "name": "Batch options",
                "options": _batch_options,
            },
        ]
    )
    return groups


_common_option_groups = _option_groups()
_OPTION_GROUPS = {
    "pymusiclooper play": _option_groups(["--start-before-end"]),
    "pymusiclooper split-audio": _option_groups(["--loop-only"]),
    "pymusiclooper tag": _option_groups(
        ["--tag-names", "--tag-offset", "--smpl", "--in-place"],
        include_read_tag_options=False,
    ),
    "pymusiclooper export-points": _option_groups(["--export-to", "--alt-export-top", "--fmt"]),
    "pymusiclooper extend": _option_groups(["--extended-length", "--extended-count", "--fade-length", "--disable-fade-out"]),
}
_COMMAND_GROUPS = {
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
                "tag",
                "extend",
            ],
        }
    ]
}

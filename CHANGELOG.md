# Changelog

## [v3.0.0] - Unreleased

### Added

- New feature: `tag`. Export metadata tags of loop points to a copy of the input audio file(s) - (Credit: some of the implementation code was based on/inspired by RemedyTwo's fork)
- New options: added min loop duration and max loop duration (in seconds) as optional constraints to the CLI

### Changed

- Complete re-write of the CLI with much better interface and usability, use `pymuisclooper --help` for the new commands and options or consult the README
- Reimplemented playback using the python sounddevice library instead of mpg123 for better cross-platform compatibility
- Significant runtime improvement to the core loop search algorithm (now runs 10x faster).
- Much nicer formatting and interface in interactive mode thanks to the `rich` python package

## [v2.5.3] - 2023-01-13

- Completely removed defunct preserve tags function and its associated errors

## [v2.5.2] - 2023-01-12

- Hotfix for v2.5.1's redundant mpg123-related error message

## [v2.5.1] - 2023-01-12

- Added workaround for libsndfile mp3 loading issue
- Fixed error handling when no loop points were found, when audio has not been loaded or when mpg123 is unavailable.
- Moved the --recursive, --flatten and --n-jobs into their own "Batch Options" CLI arguments category for clarity

## [v2.5.0] - 2022-06-09

- Added option to print loop points to terminal STDOUT (contributed by Coolsonickirby).
- Project relicensed to MIT license as of v2.5+.

## [v2.4.0] - 2021-03-21

- Temporarily disabled preserve_tags features to resolve dependency installation issues; pending re-implementation.

## [v2.3.0] - 2021-03-11

- Partial code re-organization and improvement; better exception handling

## [v2.2.0] - 2021-03-08

- Merged the 'complete' installation option with the 'core' installation

## [v2.1.0] - 2021-03-08

- CLI can now be launched directly by calling `pymusiclooper` in the terminal

## [v2.0.0] - 2020-10-02

V2.0 Rationale: This release marks a milestone in stability over the v1.x versions, rather than a major update. Future major releases will be reserved for large changes in the code base (e.g. overhaul of the core algorithm), or breaking changes in API/shell commands.

- Removed --json export option in favor of the more versatile--txt option
- Performance improvements to beat comparisons as a result of using native numpy functions whenever possible
- Code refactoring and streamlining of internal functions

## [v1.7.0] - 2020-09-13

- Added a --txt option to export a loop.txt file compatible with LoopingAudioConverter
- Recursive batch export now replicates the source directory tree structure by default to avoid name conflicts
- Added a --flatten option for recursive batch export to output to a single folder without replicating the source directory structure (previous behaviour)
- Lowered note similarity threshold to improve loop point quality (from 10% to 8%)
- Renamed default output directory name from looper_output to Loops
- Fixed JSON export bug
- Fixed a bug with non-recursive batch export.

## [v1.6.0] - 2020-06-03

- Added -i/--interactive feature to CLI for manual loop previewing and selection
- Fixed an issue with the loop ranking algorithm triggering with lists having < 2 candidates

## [v1.5.0] - 2020-05-22

- Batch command option removed
- Batch mode is now enabled automatically if the given path is a directory

## [v1.4.0] - 2020-04-16

- Major improvements to the core loop finding algorithm.
- Added option to preserve/transfer the track's original tags

## [v1.3.1] - 2020-04-09

- Fixed batch processing mode selection

## [v1.3.0] - 2020-04-09

- Added multiprocessing support and progress bar for batch export

## [v1.2.1] - 2020-04-09

- Save export output to a "looper_output" folder in current directory by default

## [v1.2.0] - 2020-04-09

- Removed unreliable cache implementation

## [v1.1.0] - 2020-04-09

- Added support for batch processing and specifying a different output directory

## [v1.0.0] - 2020-04-08

Initial Release: PyMusicLooper - a script for repeating music seamlessly and endlessly.

Features:

- Find loop points within any music file (if they exist)
- Supports most audio formats (MP3, OGG, M4A, FLAC, WAV, etc.)
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports gapless playback
- Export loop points in samples for use in creating custom themes with looping audio

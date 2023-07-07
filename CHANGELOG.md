# Changelog

## [3.0.0] - 2023-07-07

### Added

- New functionality: `tag`. Export metadata tags of loop points to a copy of the input audio file(s) - (Credit: some of the implementation code was based on/inspired by RemedyTwo's fork)
- New functionality: `play-tagged`. Reads the metadata tags of loop points from an audio file and plays it looping
- New audio source option: `--url`. Can now load and process audio from a youtube link (or any stream supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp))
- New loop point search options
  - `--min-loop-duration` , `--max-loop-duration` : added min loop duration and max loop duration (in seconds) as optional constraints to the CLI
  - `--approx-loop-position` : specify the approximate desired loop start and loop end in seconds, searching around those points only +/- 2 seconds
  - `--brute-force` : enables an alternative loop discovery mode that checks the entire audio track instead of the detected beats; useful in case the main algorithm does not yield the desired results.
  - `--disable-pruning` : disables the internal filtering of potential loop points

- New export option for split-audio command: `--format`, to change the format of the exported split audio files (currently supported formats: WAV, FLAC, OGG, MP3)
- Official Python 3.10 and 3.11 support

### Changed

- Complete re-write of the CLI with much better interface and usability, use `pymuisclooper --help` for the new commands and options or consult the README
- Reimplemented playback using the python sounddevice library instead of mpg123 for better cross-platform compatibility
- Significant runtime improvement to the core loop search algorithm (now runs 10x faster).
- Better loop point alignment thanks to an internal implementation of Audacity's "At Zero Crossings" functionality (less cases of audio popping/clicking due to misaligned loop points)
- Much nicer formatting and interface in interactive mode thanks to the `rich` python package
- Increased the minimum Python requirement to Python 64-bit >=3.9

### Removed

- Multiprocessing option (`--n-jobs`). Batch mode operations are otherwise unaffected and work as if `--n-jobs` was fixed to 1.

## [2.5.3] - 2023-01-13

- Completely removed defunct preserve tags function and its associated errors

## [2.5.2] - 2023-01-12

- Hotfix for v2.5.1's redundant mpg123-related error message

## [2.5.1] - 2023-01-12

- Added workaround for libsndfile mp3 loading issue
- Fixed error handling when no loop points were found, when audio has not been loaded or when mpg123 is unavailable.
- Moved the --recursive, --flatten and --n-jobs into their own "Batch Options" CLI arguments category for clarity

## [2.5.0] - 2022-06-09

- Added option to print loop points to terminal STDOUT (contributed by Coolsonickirby).
- Project relicensed to MIT license as of v2.5+.

## [2.4.0] - 2021-03-21

- Temporarily disabled preserve_tags features to resolve dependency installation issues; pending re-implementation.

## [2.3.0] - 2021-03-11

- Partial code re-organization and improvement; better exception handling

## [2.2.0] - 2021-03-08

- Merged the 'complete' installation option with the 'core' installation

## [2.1.0] - 2021-03-08

- CLI can now be launched directly by calling `pymusiclooper` in the terminal

## [2.0.0] - 2020-10-02

V2.0 Rationale: This release marks a milestone in stability over the v1.x versions, rather than a major update. Future major releases will be reserved for large changes in the code base (e.g. overhaul of the core algorithm), or breaking changes in API/shell commands.

- Removed --json export option in favor of the more versatile--txt option
- Performance improvements to beat comparisons as a result of using native numpy functions whenever possible
- Code refactoring and streamlining of internal functions

## [1.7.0] - 2020-09-13

- Added a --txt option to export a loop.txt file compatible with LoopingAudioConverter
- Recursive batch export now replicates the source directory tree structure by default to avoid name conflicts
- Added a --flatten option for recursive batch export to output to a single folder without replicating the source directory structure (previous behaviour)
- Lowered note similarity threshold to improve loop point quality (from 10% to 8%)
- Renamed default output directory name from looper_output to Loops
- Fixed JSON export bug
- Fixed a bug with non-recursive batch export.

## [1.6.0] - 2020-06-03

- Added -i/--interactive feature to CLI for manual loop previewing and selection
- Fixed an issue with the loop ranking algorithm triggering with lists having < 2 candidates

## [1.5.0] - 2020-05-22

- Batch command option removed
- Batch mode is now enabled automatically if the given path is a directory

## [1.4.0] - 2020-04-16

- Major improvements to the core loop finding algorithm.
- Added option to preserve/transfer the track's original tags

## [1.3.1] - 2020-04-09

- Fixed batch processing mode selection

## [1.3.0] - 2020-04-09

- Added multiprocessing support and progress bar for batch export

## [1.2.1] - 2020-04-09

- Save export output to a "looper_output" folder in current directory by default

## [1.2.0] - 2020-04-09

- Removed unreliable cache implementation

## [1.1.0] - 2020-04-09

- Added support for batch processing and specifying a different output directory

## [1.0.0] - 2020-04-08

Initial Release: PyMusicLooper - a script for repeating music seamlessly and endlessly.

Features:

- Find loop points within any music file (if they exist)
- Supports most audio formats (MP3, OGG, M4A, FLAC, WAV, etc.)
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports gapless playback
- Export loop points in samples for use in creating custom themes with looping audio

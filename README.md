# PyMusicLooper

## Note for the current v3 development branch

Since PyMusicLooper v3.0 is still in development and carries several new features as well as many breaking changes especially to its CLI,
use the built-in `--help` option for up-to-date interface options.

A python script for repeating music seamlessly and endlessly, by automatically finding the best loop points.

Features:

- Find loop points within any music file (if they exist).
- Supports a large set of different audio formats, and all the popular ones (MP3, OGG, M4A, FLAC, WAV, etc).
- Play the music file endlessly and seamlessly with the best discovered loop.
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports [gapless playback](https://en.wikipedia.org/wiki/Gapless_playback).
- Export loop points in samples to a text file (e.g. for use in creating custom themes with seamlessly looping audio).

## Installation

### Pre-requisites

The following software must be installed for `pymusiclooper` to function correctly.

- [Python](https://www.python.org/downloads/) >= 3.8
- [ffmpeg](https://ffmpeg.org/download.html) (adds support for MP3 and many other audio formats)

### Option 1: Installing using pip

```sh
pip install pymusiclooper
```

### Option 2: Installing directly from source

Required python packages: `pip` and `poetry`.

Clone the git repository to a directory of your choice and `cd` to inside the repo.

(Optional): `git checkout` to the desired branch

Then, run:

```sh
poetry install
```

This will install all the project dependencies and the project itself.
Using a virtual environment is usually recommended to avoid version conflicts with other packages.

## Usage

```raw
Usage: pymusiclooper [OPTIONS] COMMAND [ARGS]...

  A program for repeating music seamlessly and endlessly, by automatically
  finding the best loop points.

Options:
  -v, --verbose      Enables verbose logging output.
  -i, --interactive  Enables interactive mode to manually preview/choose the
                     desired loop point.
  --version          Show the version and exit.
  --help             Show this message and exit.

Commands:
  export  Export the audio into intro, loop and outro files
  play    Play an audio file on repeat from the terminal
```

Note: further help can be found in each subcommand's help message (e.g. `pymusiclooper export --help`)

PyMusicLooper will find the best loop point it can detect, and will then, depending on your arguments:

(a) play the song on repeat using the best discovered loop point;

(b) export intro/loop/outro sections of the song (currently outputs as WAV-only; however you may convert them with [ffmpeg](https://ffmpeg.org/), [Audacity](https://www.audacityteam.org/), etc.);

(c) export the loop points (in samples) to the terminal directly or to a text file compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/), which you can use for audio loops in custom theme creation, game engine audio loops, etc.

**Note**: using the interactive `-i` option is highly recommended, since the algorithmically chosen "best" loop point may not be perceptually good, mainly due to some chosen loop points causing 'sound popping' when played.

## Example Usage

Side note: Most terminals support file drag-and-drop, which can be utilized instead of manual path navigation/selection.

### Play

Play the song on repeat with the best discovered loop point.

```sh
pymusiclooper play --path "TRACK_NAME.mp3"
```

If the automatically chosen loop is undesirable, you can use pymusiclooper in interactive mode, e.g.

```sh
pymusiclooper -i play --path "TRACK_NAME.mp3"
```

### Export

Export the song into intro, loop and outro files.

```sh
pymusiclooper export "TRACK_NAME.ogg"
```

Export the loop points (in samples) of all the songs in a particular directory to a single loop.txt file (compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/)).

```sh
pymusiclooper export --path "/path/to/dir/" --to-txt
```

Instead of exporting the file into loop segments, the discovered loop points can be output directly to the CLI as sample points

```sh
pymusiclooper export --path "/path/to/track.mp3" --to-stdout
```

Note: each line in loop.txt follows the following format: `{loop-start} {loop-end} {filename}`

### Miscellaneous

If the loop is very long (or very short), you may specify a different minimum duration for the algorithm to use, which is 0.35 (35%) by default.
If the most of the track is the loop section, specifying a higher multiplier will also speed the algorithm up.
Here `--min-duration-multiplier 0.85` means that, excluding trailing silence, the loop section is at least 85% of the music track.

```sh
pymusiclooper export --path "TRACK_NAME.flac" --min-duration-multiplier 0.85
```

Loop points can be chosen and previewed interactively before playback/export using the `-i` flag, e.g.

```sh
pymusiclooper -i export --path "TRACK_NAME.wav"
```

### Example of multiple functionalities in action

Export intro/loop/outro sections and loop points of all the songs in the current directory and its subdirectories, to a folder called "Music Loops", processing 4 tracks concurrently.
(Note: due to current limitations, concurrent processing is very memory intensive. Ten minute tracks can consume 3GBs of memory during processing, with typical shorter tracks (3-4 minutes) using 1-2 GBs each.)

```sh
pymusiclooper export --path "./" --recursive --output-dir "Music Loops" --n-jobs 4
```

## Acknowledgement

This project started out as a fork of [Nolan Nicholson](https://github.com/NolanNicholson)'s project [Looper](https://github.com/NolanNicholson/Looper/). Although at this point only a few lines of code remain from that project due to adopting a completely different approach and implementation; this project would not have been possible without their initial contribution.

## Version History

- v2.5.3 Completely removed defunct preserve tags function and its associated errors
- v2.5.2 Hotfix for v2.5.1's redundant mpg123-related error message
- v2.5.1 Added workaround for libsndfile mp3 loading issue; fixed error handling when no loop points were found, when audio has not been loaded or when mpg123 is unavailable.
- v2.5.0 Added option to print loop points to terminal STDOUT (contributed by Coolsonickirby). Project relicensed to MIT license as of v2.5+.
- v2.4.0 Temporarily disabled preserve_tags features to resolve dependency installation issues; pending re-implementation.
- v2.3.0 Partial code re-organization and improvement; better exception handling
- v2.2.0 Merged the 'complete' installation option with the 'core' installation
- v2.1.0 CLI can now be launched directly by calling `pymusiclooper` in the terminal
- v2.0.0 Rewrite of the core loop finding algorithm with performance optimizations and slightly better loop analysis
- v1.7.0 Added an option to export a `loop.txt` file compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/) and a flatten option if the new directory behavior introduced in v1.6.2 is not desired. Fixed a bug with non-recursive batch export.
- v1.6.2 Preserve source directory tree structure in batch output directory. Fixed json export bug.
- v1.6.1 Lowered note similarity threshold to improve loop point quality
- v1.6.0 Added interactive option for user loop selection
- v1.5.1 Fixed issues caused by previous release's refactoring
- v1.5.0 Batch mode now implicitly enabled based on given path
- v1.4.0 Major improvements to the loop detection algorithm; added option to preserve tags
- v1.3.2 Fixed fallback PLP method not working sometimes
- v1.3.1 Fixed batch processing mode selection
- v1.3.0 Added multiprocessing support and progress bar for batch export
- v1.2.1 Save export output to a "looper_output" folder in the current working directory by default
- v1.2.0 Removed unreliable cache implementation
- v1.1.0 Added support for batch processing
- v1.0.0 Initial Release

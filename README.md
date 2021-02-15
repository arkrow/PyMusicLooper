# PyMusicLooper

A python script for repeating music seamlessly and endlessly, by automatically finding the best loop points.

Features:

- Find loop points within any music file (if they exist).
- Supports a large set of different audio formats, and all the popular ones (MP3, OGG, M4A, FLAC, WAV, etc).
- Play the music file endlessly and seamlessly with the best discovered loop.
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports [gapless playback](https://en.wikipedia.org/wiki/Gapless_playback).
- Export loop points in samples to a text file (e.g. for use in creating custom themes with seamlessly looping audio).

## Installation

### Pre-requisites

- [Python](https://www.python.org/downloads/) >= 3.6
- [ffmpeg](https://ffmpeg.org/download.html) (adds support for MP3 and other proprietary audio formats)

### Installation Options

#### Base Install

Base installation (can export intro/loop/outro sections to WAV, or the loop points to a text file; easiest to install):

```sh
pip install pymusiclooper
```

#### Complete Install

Complete installation adds tag preservation and terminal playback support (requires additional setup):

```sh
pip install pymusiclooper[complete]
```

Additional requirements for "complete" feature set:

- [mpg123](https://www.mpg123.de/download.shtml) to play/preview music loops through the terminal.
- [pytaglib](https://github.com/supermihi/pytaglib) for tag preservation (see [pytaglib's installation notes](https://github.com/supermihi/pytaglib#installation-notes))

## Usage

```raw
usage: python -m pymusiclooper [-h] [-v] [-i] [-p] [-e] [--preserve-tags]
                               [-t] [-r] [-f] [-n N_JOBS] [-o OUTPUT_DIR]
                               [-m MIN_DURATION_MULTIPLIER]
                               path

A script for repeating music seamlessly and endlessly, by automatically
finding the best loop points.

positional arguments:
  path                  path to file or directory

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         enable verbose logging output
  -i, --interactive     manually preview/choose which loop to use out of the
                        discovered loop points

Play:
  -p, --play            play the song on repeat with the best discovered loop
                        point (default).

Export:
  -e, --export          export the song into intro, loop and outro files (WAV
                        format).
  --preserve-tags       export with the track's original tags.
  -t, --txt             export the loop points of a track in samples and
                        append to a loop.txt file (compatible with
                        LoopingAudioConverter).
  -r, --recursive       process directories and their contents recursively
                        (has an effect only if the given path is a
                        directory).
  -f, --flatten         flatten the output directory structure instead of
                        preserving it when using the --recursive flag.
  -n N_JOBS, --n-jobs N_JOBS
                        number of files to batch process at a time (default:
                        1). WARNING: greater values result in higher memory
                        consumption.

General Options:
  -o OUTPUT_DIR, --output-dir OUTPUT_DIR
                        specify a different output directory.
  -m MIN_DURATION_MULTIPLIER, --min-duration-multiplier MIN_DURATION_MULTIPLIER
                        specify minimum loop duration as a multiplier of song
                        duration (default: 0.35)

```

PyMusicLooper will find the best loop point it can detect, and will then, depending on your arguments:

(a) play the song on repeat using the best discovered loop point (default, requires [mpg123](https://www.mpg123.de/download.shtml));

(b) export intro/loop/outro sections of the song (currently outputs as WAV-only; however you may convert them with [ffmpeg](https://ffmpeg.org/) or [Audacity](https://www.audacityteam.org/));

(c) export the loop points (in samples) to a JSON or text file compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/), which you can use for audio loops in custom theme creation, game engine audio loops, etc.

**Note**: using the interactive `-i` option is highly recommended, since the algorithmically chosen "best" loop point may not be perceptually good, due to loudness difference, overall song beat, etc.

## Example Usage

Side note: Most terminals support file drag-and-drop, which can be utilized instead of manual path navigation/selection.

### Play

Play the song on repeat with the best discovered loop point.

```sh
python -m pymusiclooper "TRACK_NAME.mp3"
```

### Export

Export the song into intro, loop and outro files, and carry over the track's original tags.

```sh
python -m pymusiclooper -e "TRACK_NAME.ogg" --preserve-tags
```

Export the loop points of all the songs in a particular directory to a single loop.txt file (compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/)).

```sh
python -m pymusiclooper -t "/path/to/dir/"
```

Note: each line in loop.txt follows the following format: `{loop-start} {loop-end} {filename}`

### Miscellaneous

If the loop is very long (or very short), you may specify a different minimum duration for the algorithm to use, which is 0.35 (35%) by default.
If the most of the track is the loop section, specifying a higher multiplier will also speed the algorithm up.
Here `-m 0.85` means that, excluding silence, the loop section is at least 85% of the music track.

```sh
python -m pymusiclooper "TRACK_NAME.flac" -m 0.85
```

Loop points can be chosen and previewed interactively before playback/export using the `-i` flag, e.g.

```sh
python -m pymusiclooper "TRACK_NAME.wav" -e -i
```

### Example of multiple functionalities in action

Export intro/loop/outro sections and loop points of all the songs in the current directory and its subdirectories, to a folder called "Music Loops", processing 4 tracks concurrently, preserving the original tags.

```sh
python -m pymusiclooper -ret . -o "Music Loops" -n 4 --preserve-tags
```

## Building from source

Required python packages: `pip` and `setuptools`.

Clone the git repository to a directory of your choice and cd to inside the repo.

Run:

```sh
python setup.py build
```

Followed by:

```sh
python setup.py install
```

## Contribution

If there is a song that you think PyMusicLooper should be able to loop but doesn't, please feel free to open an issue with a link to that song and mention the approximate timestamp at which it loops. Forks and pull requests are of course welcome.

## Acknowledgement

This project started out as a fork of [Nolan Nicholson](https://github.com/NolanNicholson)'s project [Looper](https://github.com/NolanNicholson/Looper/). Although at this point only a few lines of code remain from that project due to adopting a completely different approach and implementation; this project would not have been possible without their initial contribution.

## Version History

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

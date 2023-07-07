# PyMusicLooper

[![Downloads](https://static.pepy.tech/badge/pymusiclooper)](https://pepy.tech/project/pymusiclooper)
[![Downloads](https://static.pepy.tech/badge/pymusiclooper/month)](https://pepy.tech/project/pymusiclooper)
[![PyPI pyversions](https://img.shields.io/pypi/v/pymusiclooper.svg)](https://pypi.python.org/pypi/pymusiclooper/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/pymusiclooper.svg)](https://pypi.python.org/pypi/pymusiclooper/)

A python-based program for repeating music seamlessly and endlessly, by automatically finding the best loop points.

Features:

- Find loop points within any audio file (if they exist).
- Supports loading the most common audio formats (MP3, OGG, FLAC, WAV), with additional codec support available through ffmpeg.
- Play the audio file endlessly and seamlessly with the best automatically discovered loop points, or using the loop metadata tags present in the audio file.
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports [gapless playback](https://en.wikipedia.org/wiki/Gapless_playback).
- Export loop points in samples directly to the terminal or to a text file (e.g. for use in creating custom themes with seamlessly looping audio).
- Export the loop points as metadata tags to a copy of the input audio file(s), for use with game engines, etc.

## Pre-requisites

The following software must be installed for `pymusiclooper` to function correctly.

- [Python (64-bit)](https://www.python.org/downloads/) >= 3.9
- [ffmpeg](https://ffmpeg.org/download.html): required for loading audio from youtube (or any stream supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp)) and adds support for loading additional audio formats and codecs such as M4A/AAC, Apple Lossless (ALAC), WMA, ATRAC (.at9), etc. A full list can be found at [ffmpeg's documentation](https://www.ffmpeg.org/general.html#Audio-Codecs). If the aforementioned features are not required, can be skipped.

Supported audio formats *without* ffmpeg include: WAV, FLAC, Ogg/Vorbis, Ogg/Opus, MP3.
A full list can be found at [libsndfile's supported formats page](https://libsndfile.github.io/libsndfile/formats.html)

## Installation

### Option 1: Installing using pipx [Recommended]

This method of installation is strongly recommended, as it isolates PyMusicLooper's dependencies from the rest of your environment,
making it the safest option and avoids dependency conflicts and breakage due to version upgrades.

Required python packages: [`pipx`](https://pypa.github.io/pipx/) (can be installed using `pip install pipx`).

```sh
pipx install pymusiclooper
```

### Option 2: Installing using pip

```sh
pip install pymusiclooper
```

### Option 3: Installing directly from source

Required python packages: `pip` and [`poetry`](https://python-poetry.org/).

Clone the git repository to a directory of your choice and `cd` to inside the repo.

Then, run:

```sh
poetry install
```

A virtual environment can be setup through poetry by invoking the `poetry shell` command before installing.

## Available Commands

```raw
 Usage: pymusiclooper [OPTIONS] COMMAND [ARGS]...

 A program for repeating music seamlessly and endlessly, by automatically
 finding the best loop points.

╭─ Options ────────────────────────────────────────────────────────────────╮
│ --verbose      -v    Enables verbose logging output.                     │
│ --interactive  -i    Enables interactive mode to manually preview/choose │
│                      the desired loop point.                             │
│ --samples      -s    Display all the loop points shown in interactive    │
│                      mode in sample points instead of the default        │
│                      mm:ss.sss format.                                   │
│ --version            Show the version and exit.                          │
│ --help               Show this message and exit.                         │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ Play Commands ──────────────────────────────────────────────────────────╮
│ play         Play an audio file on repeat from the terminal with the     │
│              best discovered loop points, or a chosen point if           │
│              interactive mode is active.                                 │
│ play-tagged  Skips loop analysis and reads the loop points directly from │
│              the tags present in the file.                               │
╰──────────────────────────────────────────────────────────────────────────╯
╭─ Export Commands ────────────────────────────────────────────────────────╮
│ export-points       Export the best discovered or chosen loop points to  │
│                     a text file or to the terminal (stdout)              │
│ split-audio         Split the input audio into intro, loop and outro     │
│                     sections                                             │
│ tag                 Adds metadata tags of loop points to a copy of the   │
│                     input audio file(s)                                  │
╰──────────────────────────────────────────────────────────────────────────╯
```

Note: further help can be found in each subcommand's help message (e.g. `pymusiclooper export-points --help`)

**Note**: using the interactive `-i` option is highly recommended, since the automatically chosen "best" loop point may not necessarily be the best one perceptually. As such, it is shown in all the examples. Can be disabled if the `-i` flag is omitted. Interactive mode is also available when batch processing.

## Example Usage

### Play

```sh
# Play the song on repeat with the best discovered loop point.
pymusiclooper -i play --path "TRACK_NAME.mp3"


# Audio can also be loaded from any stream supported by yt-dlp, e.g. youtube
# (also available for the `tag` and `split-audio` subcommands)
pymusiclooper -i play --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


# Reads the loop metadata tags from an audio file and play it with the loop active
# using the loop start and end specified in the file (must be stored as samples)
pymusiclooper play-tagged --path "TRACK_NAME.mp3" --tag-names LOOP_START LOOP_END
```

### Export

*Note: batch processing is available for all export subcommands. Simply specify a directory instead of a file as the path to be used.*

```sh
# Split the audio track into intro, loop and outro files.
pymusiclooper -i split-audio --path "TRACK_NAME.ogg"


# Export the discovered loop points directly to the terminal as sample points
pymusiclooper -i export-points --path "/path/to/track.wav" --export-to stdout


# Add metadata tags of the best discovered loop points to a copy of the input audio file
# (or all audio files in a directory, if a directory path is used instead)
pymusiclooper -i tag --path "TRACK_NAME.mp3" --tag-names LOOP_START LOOP_END


# Export the loop points (in samples) of all tracks in a particular directory to a loop.txt file
# (compatible with https://github.com/libertyernie/LoopingAudioConverter/)
# Note: each line in loop.txt follows the following format: {loop-start} {loop-end} {filename}
pymusiclooper -i export-points --path "/path/to/dir/" --export-to txt
```

### Miscellaneous

```sh
# If the loop is very long (or very short), a different minimum loop duration can be specified.
## --min-duration-multiplier 0.85 implies that the loop is at least 85% of the track,
## excluding trailing silence.
pymusiclooper -i split-audio --path "TRACK_NAME.flac" --min-duration-multiplier 0.85

# Alternatively, the loop length constraints can be specified in seconds
pymusiclooper -i split-audio --path "TRACK_NAME.flac" --min-loop-duration 120 --max-loop-duration 150


# If the detected loop points are unsatisfactory, the brute force option `--brute-force`
# may yield better results.
## NOTE: brute force mode checks the entire audio track instead of the detected beats.
## This leads to much longer runtime (may take several minutes).
## The program may appear frozen during this time while it is processing in the background.
pymusiclooper -i export-points --path "TRACK_NAME.wav" --brute-force


# By default, the program filters the loop points to the top 50% (according to
# internal criteria) of the discovered loops when there are many.
# If that is undesirable, it can be disabled using the `--disable-pruning` flag.
pymusiclooper -i export-points --path "TRACK_NAME.wav" --disable-pruning


# If a desired loop point is already known, and you would like to extract the best loop
# positions in samples, you can use the `--approx-loop-position` option,
# which searches with +/- 2 seconds of the point specified.
# Best used interactively. Example using the `export-points` subcommand:
pymusiclooper -i export-points --path "/path/to/track.mp3" --approx-loop-position 20 210
## `--approx-loop-position 20 210` means the desired loop point starts around 20 seconds
## and loops back at the 210 seconds mark.
```

## Acknowledgement

This project started out as a fork of [Nolan Nicholson](https://github.com/NolanNicholson)'s project [Looper](https://github.com/NolanNicholson/Looper/). Although at this point only a few lines of code remain from that project due to adopting a completely different approach and implementation; this project would not have been possible without their initial contribution.

## Version History

Available at [CHANGELOG.md](CHANGELOG.md)

# PyMusicLooper

[![Downloads](https://static.pepy.tech/badge/pymusiclooper)](https://pepy.tech/project/pymusiclooper)
[![Downloads](https://static.pepy.tech/badge/pymusiclooper/month)](https://pepy.tech/project/pymusiclooper)
[![PyPI pyversions](https://img.shields.io/pypi/v/pymusiclooper.svg)](https://pypi.python.org/pypi/pymusiclooper/)
[![PyPI pyversions](https://img.shields.io/pypi/pyversions/pymusiclooper.svg)](https://pypi.python.org/pypi/pymusiclooper/)

## Note for the current v3 development branch

Since PyMusicLooper v3.0 is still in development and carries several new features as well as many breaking changes especially to its CLI,
use the built-in `--help` option for up-to-date interface options.

---

A python script for repeating music seamlessly and endlessly, by automatically finding the best loop points.

Features:

- Find loop points within any audio file (if they exist).
- Supports a large set of different audio formats, including all the popular ones through ffmpeg (MP3, OGG, M4A, FLAC, WAV, etc).
- Play the audio file endlessly and seamlessly with the best discovered loop.
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports [gapless playback](https://en.wikipedia.org/wiki/Gapless_playback).
- Export loop points in samples to a text file (e.g. for use in creating custom themes with seamlessly looping audio).
- Export the loop points as metadata tags to a copy of the input audio file(s), for use with game engines, etc.

## Installation

### Pre-requisites

The following software must be installed for `pymusiclooper` to function correctly.

- [Python (64-bit)](https://www.python.org/downloads/) >= 3.9
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

 A program for repeating music seamlessly and endlessly, by automatically finding the best loop       
 points.

 Options
 --verbose      -v    Enables verbose logging output.
 --interactive  -i    Enables interactive mode to manually preview/choose the desired loop point.
 --in-samples   -s    Display all loop points in interactive mode in sample points instead of the
                      default mm:ss.sss format.
 --version            Show the version and exit.
 --help               Show this message and exit.

 Commands
 export-loop-points  Export the best discovered or chosen loop points to a text file or to the
                     terminal (stdout)
 play                Play an audio file on repeat from the terminal with the best discovered loop
                     points, or a chosen point if interactive mode is active
 split-audio         Split the input audio into intro, loop and outro sections (WAV format)
 tag                 Adds metadata tags of loop points to a copy of the input audio file(s)
```

Note: further help can be found in each subcommand's help message (e.g. `pymusiclooper export-loop-points --help`)

PyMusicLooper will find the best loop point it can detect, and will then, depending on the chosen command:

(a) play an audio track on repeat using the best discovered loop point;

(b) export an audio track into intro/loop/outro sections (currently outputs as WAV-only; however you may convert them with [ffmpeg](https://ffmpeg.org/), [Audacity](https://www.audacityteam.org/), etc.);

(c) export the loop points (in samples) to the terminal directly or to a text file compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/), which you can use for audio loops in custom theme creation, game engine audio loops, etc.

(d) Add the best/chosen loop points as metadata tags to a copy of the input audio file(s)

**Note**: using the interactive `-i` option is highly recommended, since the automatically chosen "best" loop point may not be the best one perceptually,
as that is difficult to calculate and score algorithmically

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

Split the audio track into intro, loop and outro files.

```sh
pymusiclooper split-audio "TRACK_NAME.ogg"
```

Export the discovered loop points directly to the terminal as sample points

```sh
pymusiclooper export-loop-points --path "/path/to/track.wav" --export-to stdout
```

 Add metadata tags of the best discovered loop points to a copy of the input audio file (or all audio files in a directory, if a directory path is used instead)

```sh
pymusiclooper tag --path "TRACK_NAME.mp3"
```

Export the loop points (in samples) of all the songs in a particular directory to a single loop.txt file (compatible with [LoopingAudioConverter](https://github.com/libertyernie/LoopingAudioConverter/)).

```sh
pymusiclooper export-loop-points --path "/path/to/dir/" --export-to txt
```

Note: each line in loop.txt follows the following format: `{loop-start} {loop-end} {filename}`

### Miscellaneous

If the loop is very long (or very short), you may specify a different minimum duration for the algorithm to use, which is 0.35 (35%) by default.
If the most of the track is the loop section, specifying a higher multiplier will also speed the algorithm up.
Here `--min-duration-multiplier 0.85` means that, excluding trailing silence, the loop section is at least 85% of the music track.

```sh
pymusiclooper split-audio --path "TRACK_NAME.flac" --min-duration-multiplier 0.85
```

Loop points can be chosen and previewed interactively before playback/export using the `-i` flag, e.g.

```sh
pymusiclooper -i export-loop-points --path "TRACK_NAME.wav"
```

If a desired loop point is already known, and you would like to extract the best loop positions in samples, you can use the `--approx-loop-position` option, which searches with +/- 2 seconds of the point specified. Best used interactively. Example using the `export-loop-points` subcommand:

```sh
pymusiclooper -i export-loop-points --path "/path/to/track.mp3" --export-to stdout --approx-loop-position 20 210
```

`--approx-loop-position 20 210` means the desired loop point starts around 20 seconds and loops back at the 210 seconds mark (i.e. 3:30).

### Batch processing example

Export intro/loop/outro sections and loop points of all the songs in the current directory and its subdirectories, to a folder called "Music Loops", processing 4 tracks concurrently.

```sh
pymusiclooper split-audio --path "./" --recursive --output-dir "Music Loops" --n-jobs 4
```

Generally, concurrent batch processing (i.e. when `--n-jobs` is set >1) is not encouraged as interactive mode cannot be used, however, it is relatively reliable with tracks that have clear and distinct repetition.

(Note: due to current limitations, concurrent processing is very memory intensive and scales multiplicatively with `--n-jobs`. Long tracks (~10 mins) can consume upwards of 3GBs of memory during processing, with typical shorter tracks (2-6 mins) using 1-2 GBs each.)

(Additional Note: when using parallel processing (i.e. n-jobs > 1), certain functionalities are disabled, namely: interactive mode, export to txt, export to stdout)

## Acknowledgement

This project started out as a fork of [Nolan Nicholson](https://github.com/NolanNicholson)'s project [Looper](https://github.com/NolanNicholson/Looper/). Although at this point only a few lines of code remain from that project due to adopting a completely different approach and implementation; this project would not have been possible without their initial contribution.

## Version History

Available at [CHANGELOG.md](CHANGELOG.md)

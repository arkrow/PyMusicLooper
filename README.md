# PyMusicLooper

A script for repeating music seamlessly and endlessly, by automatically finding the best loop points.

Features:

- Find loop points within any music file (if they exist).
- Supports a large set of different audio formats, and all the popular ones (MP3, OGG, M4A, FLAC, WAV, etc).
- Play the music file endlessly and seamlessly with the best discovered loop.
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports [gapless playback](https://en.wikipedia.org/wiki/Gapless_playback).
- Export loop points in samples (e.g. for use in creating custom themes with seamlessly looping audio).

## Installation

Requires Python >=3.6 to run.
This program depends on NumPy (for arrays and mathematical operations) and Librosa (for audio analysis and beat extraction).
If you don't have these dependencies installed, they'll be automatically downloaded:

```sh
pip install git+https://github.com/arkrow/PyMusicLooper.git
```

To play music endlessly through the terminal, the external library `mpg123` is required. Available through the following link: (https://www.mpg123.de/download.shtml).

## Usage

```
usage: python -m pymusiclooper [-h] [-p] [-e] [-j]
                               [-m MIN_DURATION_MULTIPLIER] [--skip-cache]
                               [--purge-cache]
                               [path]

Automatically find loop points in music files and play/export them.

positional arguments:
  path                  path to music file.

optional arguments:
  -h, --help            show this help message and exit
  -p, --play            play the song on repeat with the best discovered loop
                        point (default).
  -e, --export          export the song into intro, loop and outro files (WAV
                        format).
  -j, --json            export the loop points (in samples) to a JSON file in
                        the song's directory.
  -m MIN_DURATION_MULTIPLIER, --min-duration-multiplier MIN_DURATION_MULTIPLIER
                        specify minimum loop duration as a multiplier of song
                        duration (default: 0.35); use with --skip-cache.
  --skip-cache          skip loading cached loop points.
  --purge-cache         purges all cached loop points and exits.
```

PyMusicLooper will find the best loop point it can detect, and will then, depending on your arguments:

(a) play the song on repeat using the best discovered loop point (default, requires [mpg123](https://www.mpg123.de/download.shtml));

(b) export intro/loop/outro sections of the song (currently outputs as WAV-only, although you may convert with [ffmpeg](https://ffmpeg.org/) or [Audacity](https://www.audacityteam.org/));

(c) export the loop points (in samples) to a JSON text file, which you can use for audio loops in custom theme creation, etc.

## Example Usage

Note: If on Windows, you can Shift+Right-Click in an empty spot in the song's folder and choose command-line/powershell from the context menu. Otherwise, cd/dir to the folder.

Play the song on repeat with the best discovered loop point.

```sh
python -m pymusiclooper "Song I Could Listen To Forever.mp3"
```

Export the song into intro, loop and outro files, as well as the loop points used (outputs in the same directory/folder as the track).

```sh
python -m pymusiclooper -ej "some music track.ogg"
```

If the loop is very long (or very short), you may specify a different minimum duration for the algorithm to use, which is 0.35 (35%) by default.
If the most of the track is the loop section, specifying a higher multiplier will also speed the algorithm up.
Here `-m 0.85` means that, excluding silence, the loop section is at least 85% of the music track.
Note how the `--skip-cache` flag is set, which is needed otherwise the song will skip analysis and use the latest cached loop points instead.

```sh
python -m pymusiclooper -m "super long track.flac" -m 0.85 --skip-cache
```

## Building from source

Requried python packages: `pip` and `setuptools`.

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

This project started out as a fork of [Nolan Nicholson](https://github.com/NolanNicholson)'s project [Looper](https://github.com/NolanNicholson/Looper/). Although at this point only a few lines of code remain from that project due to adopting a completely different approach and implementation, without their contributions this project would not have been possible.

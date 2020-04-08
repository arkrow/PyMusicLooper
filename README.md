# PyMusicLooper

A script for repeating music seamlessly and endlessly.

Features:

- Find loop points within any music file (if they exist)
- Export to intro/loop/outro sections for editing or seamless playback within any music player that supports [gapless playback](https://en.wikipedia.org/wiki/Gapless_playback)
- Export loop points in samples for use in creating themes with looped audio

## Installation

Requires Python >=3.6 to run. This program depends on NumPy (arrays and mathematical operations) and Librosa (audio analysis and beat extraction). If you don't have these dependencies installed, you'll automatically download them (but keep in mind it might take a while depending on your internet connection):

```sh
pip install git+https://github.com/arkrow/PyMusicLooper.git
```

This program also requires the external library `mpg123` for music playback within the command-line. Available through the following link: https://www.mpg123.de/download.shtml

## Usage

```
usage: python -m pymusiclooper [-h] [-p] [-e] [-j] [--disable-cache] path

Automatically find loop points in music files and play/export them.

positional arguments:
  path        path to music file.

optional arguments:
  -h, --help       show this help message and exit
  -p, --play       play the song on repeat with the best discovered loop point
                   (default).
  -e, --export     export the song into intro, loop and outro files (WAV
                   format).
  -j, --json       export the loop points (in samples) to a JSON file in the
                   song's directory.
  --disable-cache  skip loading/using cached loop points.
```

PyMusicLooper will find the best loop point it can detect, and will then, depending on your arguments:

(a) play the song on repeat (by default);

(b) export to intro/loop/outro sections (currently outputs as WAV-only, although you may convert with [ffmpeg](https://ffmpeg.org/) or [Audacity](https://www.audacityteam.org/));

(c) export the loop points (in samples) to a JSON file, which you can use for audio loops in theme creation, etc..

## Example Usage

Note: If on Windows, you can Shift+Right-Click in an empty spot in the song's folder and choose command-line/powershell from the context menu. Otherwise, cd/dir to the folder.

Play the song on repeat with the best discovered loop point.

```sh
python -m pymusiclooper track.mp3
```

Export the song into intro, loop and outro files as well as the loop points used (outputs in the same directory/folder as the track).

```sh
python -m pymusiclooper -ej track.mp3
```

## Building from source

Requried python packages: pip and setuptools.

Clone the git repository somewhere and cd to inside the repo.

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

## Acknowledgements

This project started out as a fork of [Nolan Nicholson](https://github.com/NolanNicholson)'s project [Looper](https://github.com/NolanNicholson/Looper/). Although at this point only a few lines of code remain from that project due to adopting a completely different approach and implementation, without their contributions this project would not have been possible.

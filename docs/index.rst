PyMusicLooper Documentation
===========================

**PyMusicLooper** is a Python CLI tool and library for automatically finding
seamless loop points in audio tracks, with playback, splitting, extending,
and metadata tagging support.

Quickstart
----------

.. code-block:: sh

   # Play a track endlessly with automatic loop detection (or existing tags)
   pymusiclooper play --path "track.mp3"

   # Interactively preview and select loop points, starting 5s before loop end
   pymusiclooper -i play --path "track.mp3" --start-before-end 5

   # Export only the loop section as FLAC
   pymusiclooper split-audio --path "track.wav" --loop-only --format FLAC

   # Extend a track by 3 loop repetitions
   pymusiclooper extend --path "track.mp3" --extended-count 3

   # Tag a WAV file in-place (writes both text tags and a RIFF smpl chunk)
   pymusiclooper tag --path "track.wav" --tag-names LOOP_START LOOP_END --in-place

Building Documentation
----------------------

Install the ``docs`` dependency group and build HTML or Unix man pages with Sphinx:

.. code-block:: sh

   uv sync --group docs
   uv run sphinx-build -b html docs docs/_build/html
   uv run sphinx-build -b man docs docs/_build/man

.. toctree::
   :maxdepth: 2
   :caption: Contents

   cli
   api

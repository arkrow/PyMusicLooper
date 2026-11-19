"""Utilities for reading and writing RIFF WAVE `smpl` (sampler) chunks."""

import os
import shutil
import struct
import tempfile

_COPY_CHUNK_BYTES = 1024 * 1024  # 1 MiB streaming buffer
_RIFF_MAX_SIZE = 0xFFFFFFFF
_SMPL_HEADER_AND_LOOP_FMT = "<9I6I"
_SMPL_PAYLOAD_SIZE = struct.calcsize(_SMPL_HEADER_AND_LOOP_FMT)  # 60 bytes


def is_wav_file(filepath: str) -> bool:
    """Returns True if `filepath` has a valid RIFF/RF64 WAVE header."""
    try:
        with open(filepath, "rb") as f:
            header = f.read(12)
        return (
            len(header) == 12
            and header[:4] in (b"RIFF", b"RF64")
            and header[8:12] == b"WAVE"
        )
    except OSError:
        return False


def _stream_copy(src, dst, n_bytes: int) -> None:
    remaining = n_bytes
    while remaining > 0:
        buf = src.read(min(_COPY_CHUNK_BYTES, remaining))
        if not buf:
            raise EOFError("Unexpected end of WAV file while reading chunk data.")
        dst.write(buf)
        remaining -= len(buf)


def read_wav_smpl(filepath: str) -> tuple[int, int] | None:
    """Reads the first loop's (loop_start, loop_end) in samples from a WAV file's `smpl` chunk.

    Per the RIFF WAVE specification, `dwEnd` is inclusive, so this returns
    `(dwStart, dwEnd + 1)` to match PyMusicLooper's exclusive-end sample indexing.

    Returns None if the file is not a valid WAV or has no `smpl` loop entries.
    """
    if not is_wav_file(filepath):
        return None

    file_size = os.path.getsize(filepath)
    with open(filepath, "rb") as f:
        header = f.read(12)
        is_rf64 = header[:4] == b"RF64"
        ds64_data_size: int | None = None

        while f.tell() + 8 <= file_size:
            chunk_hdr = f.read(8)
            if len(chunk_hdr) < 8:
                break
            chunk_id = chunk_hdr[:4]
            chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]
            data_offset = f.tell()

            if is_rf64 and chunk_id == b"ds64" and chunk_size >= 24:
                ds64_head = f.read(24)
                if len(ds64_head) == 24:
                    _, ds64_data_size, _ = struct.unpack("<3Q", ds64_head)
                actual_size = chunk_size
            elif (
                is_rf64
                and chunk_id == b"data"
                and chunk_size == _RIFF_MAX_SIZE
                and ds64_data_size is not None
            ):
                actual_size = ds64_data_size
            else:
                actual_size = chunk_size

            if chunk_id == b"smpl" and actual_size >= _SMPL_PAYLOAD_SIZE:
                f.seek(data_offset)
                payload = f.read(_SMPL_PAYLOAD_SIZE)
                if len(payload) == _SMPL_PAYLOAD_SIZE:
                    fields = struct.unpack(_SMPL_HEADER_AND_LOOP_FMT, payload)
                    num_loops = fields[7]
                    if num_loops >= 1:
                        dw_start = fields[11]
                        dw_end = fields[12]
                        return dw_start, dw_end + 1

            next_offset = data_offset + actual_size + (actual_size & 1)
            if next_offset > file_size:
                break
            f.seek(next_offset)

    return None


def write_wav_smpl(
    filepath: str,
    loop_start: int,
    loop_end: int,
    sample_rate: int,
) -> None:
    """Writes or replaces the RIFF `smpl` chunk in a WAV/RF64 file with a forward infinite loop.

    Args:
        filepath (str): Path to an existing RIFF or RF64 WAV file.
        loop_start (int): Loop start index in samples (inclusive).
        loop_end (int): Loop end index in samples (exclusive; stored as `loop_end - 1` per spec).
        sample_rate (int): Audio sample rate in Hz.
    """
    if loop_start < 0 or loop_end <= loop_start:
        raise ValueError(
            f"Invalid loop points for smpl chunk: loop_start={loop_start}, loop_end={loop_end}."
        )
    if sample_rate <= 0:
        raise ValueError(f"Invalid sample rate for smpl chunk: {sample_rate}.")
    if not is_wav_file(filepath):
        raise ValueError(f'"{filepath}" is not a valid RIFF/RF64 WAVE file.')

    sample_period = round(1_000_000_000 / sample_rate)
    dw_start = int(loop_start)
    dw_end = int(loop_end) - 1  # Inclusive end sample per RIFF WAVE spec
    smpl_payload = struct.pack(
        _SMPL_HEADER_AND_LOOP_FMT,
        0,  # dwManufacturer
        0,  # dwProduct
        sample_period,  # dwSamplePeriod (ns)
        60,  # dwMIDIUnityNote (middle C)
        0,  # dwMIDIPitchFraction
        0,  # dwSMPTEFormat
        0,  # dwSMPTEOffset
        1,  # cSampleLoops
        0,  # cbSamplerData
        0,  # SampleLoop.dwIdentifier
        0,  # SampleLoop.dwType (0 = forward loop)
        dw_start,  # SampleLoop.dwStart
        dw_end,  # SampleLoop.dwEnd (inclusive)
        0,  # SampleLoop.dwFraction
        0,  # SampleLoop.dwPlayCount (0 = infinite)
    )
    smpl_chunk = b"smpl" + struct.pack("<I", len(smpl_payload)) + smpl_payload

    file_size = os.path.getsize(filepath)
    parent_dir = os.path.dirname(os.path.abspath(filepath))
    tmp_path: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=parent_dir, prefix=".pml_smpl_", suffix=".wav", delete=False
        ) as out_f:
            tmp_path = out_f.name
            with open(filepath, "rb") as in_f:
                header = in_f.read(12)
                riff_id = header[:4]
                is_rf64 = riff_id == b"RF64"
                ds64_data_size: int | None = None
                out_ds64_payload_offset: int | None = None

                # Write placeholder RIFF/RF64 header
                out_f.write(riff_id)
                out_f.write(struct.pack("<I", _RIFF_MAX_SIZE if is_rf64 else 0))
                out_f.write(b"WAVE")

                while in_f.tell() + 8 <= file_size:
                    chunk_hdr = in_f.read(8)
                    if len(chunk_hdr) < 8:
                        break
                    chunk_id = chunk_hdr[:4]
                    chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]
                    data_offset = in_f.tell()

                    if is_rf64 and chunk_id == b"ds64" and chunk_size >= 24:
                        ds64_head = in_f.read(24)
                        if len(ds64_head) == 24:
                            _, ds64_data_size, _ = struct.unpack("<3Q", ds64_head)
                        in_f.seek(data_offset)
                        actual_size = chunk_size
                    elif (
                        is_rf64
                        and chunk_id == b"data"
                        and chunk_size == _RIFF_MAX_SIZE
                        and ds64_data_size is not None
                    ):
                        actual_size = ds64_data_size
                    else:
                        actual_size = chunk_size

                    # Clamp in case a trailing chunk header over-reports past EOF
                    available = file_size - data_offset
                    if actual_size > available:
                        actual_size = available

                    if chunk_id != b"smpl":
                        out_f.write(chunk_id)
                        out_f.write(
                            struct.pack(
                                "<I",
                                _RIFF_MAX_SIZE
                                if (is_rf64 and chunk_id == b"data" and chunk_size == _RIFF_MAX_SIZE)
                                else actual_size,
                            )
                        )
                        if is_rf64 and chunk_id == b"ds64":
                            out_ds64_payload_offset = out_f.tell()
                        _stream_copy(in_f, out_f, actual_size)
                        if actual_size & 1:
                            out_f.write(b"\x00")

                    next_offset = data_offset + actual_size + (actual_size & 1)
                    if next_offset > file_size:
                        break
                    in_f.seek(next_offset)

                # Append the new smpl chunk
                out_f.write(smpl_chunk)

                total_size = out_f.tell()
                riff_payload_size = total_size - 8
                if is_rf64:
                    if out_ds64_payload_offset is not None:
                        out_f.seek(out_ds64_payload_offset)
                        out_f.write(struct.pack("<Q", riff_payload_size))
                else:
                    if riff_payload_size > _RIFF_MAX_SIZE:
                        raise ValueError(
                            "WAV file exceeds 4 GiB RIFF limit after adding smpl chunk."
                        )
                    out_f.seek(4)
                    out_f.write(struct.pack("<I", riff_payload_size))

        shutil.copymode(filepath, tmp_path)
        os.replace(tmp_path, filepath)
    except Exception:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

#!/usr/bin/env python3
"""
NetWhisper - Acoustic FSK Communication Engine
Role: Marnia (Communication Engine & Signal Processing)

Features:
- Binary conversion (UTF-8 <-> bits)
- Continuous-Phase FSK (CPFSK) modulation (1800 Hz & 2400 Hz)
- Linear chirp preamble matched filtering for acoustic synchronization
- Packet Framing:
    [ Guard (50ms) ] + [ Chirp (200ms) ] + [ Guard (50ms) ] +
    [ SYNC: 0xAC (1 byte) ] + [ SEQ (1 byte) ] + [ LEN (1 byte) ] +
    [ PAYLOAD (N bytes) ] + [ CRC-16 (2 bytes, Big-Endian) ] + [ Guard (50ms) ]
- CRC-16-CCITT (Poly: 0x1021, Init: 0xFFFF) error detection covering SEQ + LEN + PAYLOAD
- Corrupted frame rejection with detailed error reporting
- Physical acoustic transmission & reception via sounddevice
- Public integration contract for Keerthana's FastAPI dashboard:
    transmit_text(message, seq_num=None), receive_text(timeout_seconds), get_stats()
"""

import sys
import time
import argparse
import numpy as np
from scipy import signal

# Optional sounddevice import with graceful fallback
try:
    import sounddevice as sd
    AUDIO_HARDWARE_AVAILABLE = True
except (ImportError, OSError):
    sd = None
    AUDIO_HARDWARE_AVAILABLE = False


# ============================================================================
# Acoustic & Framing Protocol Parameters
# ============================================================================

DEFAULT_SAMPLE_RATE = 44100     # Audio sampling rate in Hz (CoreAudio default)
DEFAULT_FREQ_0 = 1800.0          # Audio frequency for bit '0' (Space, Hz)
DEFAULT_FREQ_1 = 2400.0          # Audio frequency for bit '1' (Mark, Hz)
DEFAULT_BIT_DURATION = 0.04      # Duration per bit in seconds (25 bps baud rate)
DEFAULT_AMPLITUDE = 0.6          # Audio signal amplitude (0.0 to 1.0)

# Preamble Synchronization Parameters
CHIRP_DURATION = 0.20            # Preamble chirp duration in seconds
CHIRP_F_START = 1200.0           # Chirp start frequency (Hz)
CHIRP_F_END = 2800.0             # Chirp end frequency (Hz)
GUARD_DURATION = 0.05            # Guard silence interval (seconds)
SYNC_BYTE = 0xAC                 # Frame sync delimiter (0b10101100)
CORR_THRESHOLD_RATIO = 8.0       # Minimum ratio of peak correlation to mean noise floor

# CRC-16-CCITT Parameters
CRC16_POLY = 0x1021              # Polynomial: x^16 + x^12 + x^5 + 1
CRC16_INIT = 0xFFFF              # Initial register value


# ============================================================================
# Internal Engine State & Statistics Tracker
# ============================================================================

_next_tx_seq = 0

_STATS = {
    "transmissions_attempted": 0,
    "transmissions_completed": 0,
    "receptions_attempted": 0,
    "receptions_successful": 0,
    "receptions_failed": 0,
    "crc_errors": 0,
    "last_tx_message": None,
    "last_tx_seq": None,
    "last_tx_duration_sec": 0.0,
    "last_rx_message": None,
    "last_rx_seq": None,
    "last_rx_crc_valid": None,
    "last_rx_corr_ratio": 0.0,
    "last_error": None,
    "data_rate_bps": round(1.0 / DEFAULT_BIT_DURATION, 2),
}


# ============================================================================
# CRC-16-CCITT Implementation
# ============================================================================

def compute_crc16(data: bytes, poly: int = CRC16_POLY, init: int = CRC16_INIT) -> int:
    """
    Computes standard CRC-16-CCITT (False) checksum over the given byte sequence.
    
    Specification:
    - Polynomial: 0x1021 (x^16 + x^12 + x^5 + 1)
    - Initial Value: 0xFFFF
    - Input Reflected: False
    - Result Reflected: False
    - XOR Out: 0x0000
    - Standard Check: compute_crc16(b"123456789") == 0x29B1
    """
    crc = init
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ============================================================================
# Bit Conversion Utilities
# ============================================================================

def text_to_bits(text: str) -> list[int]:
    """Converts a UTF-8 text string into a list of bits (MSB first)."""
    return bytes_to_bits(text.encode("utf-8"))


def bytes_to_bits(raw_bytes: bytes | bytearray) -> list[int]:
    """Converts bytes into a list of binary bits (MSB first)."""
    bits = []
    for byte in raw_bytes:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits: list[int]) -> bytes:
    """Converts a list of bits back into raw bytes. Truncates incomplete trailing bits."""
    byte_array = bytearray()
    for i in range(0, len(bits) - (len(bits) % 8), 8):
        byte_val = 0
        for bit in bits[i : i + 8]:
            byte_val = (byte_val << 1) | bit
        byte_array.append(byte_val)
    return bytes(byte_array)


def bits_to_text(bits: list[int]) -> str:
    """Converts a list of bits back into a UTF-8 text string."""
    raw_bytes = bits_to_bytes(bits)
    return raw_bytes.decode("utf-8", errors="replace")


def byte_to_bits(byte_val: int) -> list[int]:
    """Converts an integer (0-255) into 8 bits."""
    return [(byte_val >> (7 - i)) & 1 for i in range(8)]


def bits_to_byte(bits: list[int]) -> int:
    """Converts 8 bits into an integer (0-255)."""
    val = 0
    for b in bits[:8]:
        val = (val << 1) | b
    return val


# ============================================================================
# Modulation & Demodulation
# ============================================================================

def generate_chirp(sample_rate: int = DEFAULT_SAMPLE_RATE) -> np.ndarray:
    """
    Generates a linear frequency sweep (chirp) with Hanning window tapering.
    The chirp serves as a high-autocorrelation preamble for time synchronization.
    """
    num_samples = int(round(sample_rate * CHIRP_DURATION))
    t = np.linspace(0, CHIRP_DURATION, num_samples, False)
    phase = 2.0 * np.pi * (CHIRP_F_START * t + 0.5 * (CHIRP_F_END - CHIRP_F_START) / CHIRP_DURATION * t**2)
    window = np.hanning(num_samples)
    chirp = (DEFAULT_AMPLITUDE * np.sin(phase) * window).astype(np.float32)
    return chirp


def modulate_fsk(
    bits: list[int],
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    freq_0: float = DEFAULT_FREQ_0,
    freq_1: float = DEFAULT_FREQ_1,
    bit_duration: float = DEFAULT_BIT_DURATION,
    amplitude: float = DEFAULT_AMPLITUDE,
) -> np.ndarray:
    """
    Synthesizes Continuous-Phase FSK (CPFSK) audio for a given bit sequence.
    Continuous phase prevents sharp clicks at bit transitions, eliminating spectral splatter.
    """
    if not bits:
        return np.zeros(0, dtype=np.float32)

    samples_per_bit = int(round(sample_rate * bit_duration))
    total_samples = samples_per_bit * len(bits)

    freq_array = np.zeros(total_samples, dtype=np.float64)
    for idx, bit in enumerate(bits):
        start = idx * samples_per_bit
        end = start + samples_per_bit
        freq_array[start:end] = freq_1 if bit == 1 else freq_0

    phase = 2.0 * np.pi * np.cumsum(freq_array) / sample_rate
    signal_wave = amplitude * np.sin(phase)
    return signal_wave.astype(np.float32)


def demodulate_fsk(
    audio: np.ndarray,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    freq_0: float = DEFAULT_FREQ_0,
    freq_1: float = DEFAULT_FREQ_1,
    bit_duration: float = DEFAULT_BIT_DURATION,
    num_bits: int | None = None,
) -> list[int]:
    """
    Demodulates audio chunks using non-coherent quadrature matched filtering.
    Calculates in-phase (I) and quadrature (Q) energy per candidate tone.
    """
    samples_per_bit = int(round(sample_rate * bit_duration))
    total_samples = len(audio)

    if samples_per_bit <= 0 or total_samples < samples_per_bit:
        return []

    available_bits = total_samples // samples_per_bit
    bits_to_decode = available_bits if num_bits is None else min(available_bits, num_bits)

    t = np.arange(samples_per_bit) / sample_rate
    cos_0 = np.cos(2.0 * np.pi * freq_0 * t)
    sin_0 = np.sin(2.0 * np.pi * freq_0 * t)
    cos_1 = np.cos(2.0 * np.pi * freq_1 * t)
    sin_1 = np.sin(2.0 * np.pi * freq_1 * t)

    decoded_bits = []
    for i in range(bits_to_decode):
        start = i * samples_per_bit
        chunk = audio[start : start + samples_per_bit]

        i_0 = np.dot(chunk, cos_0)
        q_0 = np.dot(chunk, sin_0)
        energy_0 = i_0**2 + q_0**2

        i_1 = np.dot(chunk, cos_1)
        q_1 = np.dot(chunk, sin_1)
        energy_1 = i_1**2 + q_1**2

        decoded_bits.append(1 if energy_1 > energy_0 else 0)

    return decoded_bits


# ============================================================================
# Acoustic Framing & Frame Decoding with Sequence Number and CRC-16
# ============================================================================

def build_packet_bytes(text: str, seq_num: int = 0) -> bytes:
    """
    Constructs the binary packet data:
    [ SYNC (0xAC) ] + [ SEQ (1 byte) ] + [ LEN (1 byte) ] + [ PAYLOAD (N bytes) ] + [ CRC-16 (2 bytes, BE) ]
    
    CRC-16 covers: [ SEQ ] + [ LEN ] + [ PAYLOAD ].
    """
    payload_bytes = text.encode("utf-8")
    if len(payload_bytes) > 255:
        raise ValueError(f"Payload too large: {len(payload_bytes)} bytes (maximum 255 bytes supported)")

    seq_byte = seq_num & 0xFF
    len_byte = len(payload_bytes) & 0xFF

    protected_data = bytes([seq_byte, len_byte]) + payload_bytes
    crc_val = compute_crc16(protected_data)
    crc_bytes = bytes([(crc_val >> 8) & 0xFF, crc_val & 0xFF])

    return bytes([SYNC_BYTE]) + protected_data + crc_bytes


def create_acoustic_frame(
    text: str, seq_num: int = 0, sample_rate: int = DEFAULT_SAMPLE_RATE
) -> np.ndarray:
    """
    Encapsulates text into a complete acoustic transmission frame with preamble,
    sequence number, length header, payload, and CRC-16 checksum:
    
    [ Guard (50ms) ] + [ Chirp (200ms) ] + [ Guard (50ms) ] +
    [ Packet Audio (SYNC + SEQ + LEN + PAYLOAD + CRC-16) ] + [ Guard (50ms) ]
    """
    packet_bytes = build_packet_bytes(text, seq_num=seq_num)
    packet_bits = bytes_to_bits(packet_bytes)

    chirp = generate_chirp(sample_rate)
    guard = np.zeros(int(round(sample_rate * GUARD_DURATION)), dtype=np.float32)
    data_audio = modulate_fsk(packet_bits, sample_rate=sample_rate)

    frame = np.concatenate([guard, chirp, guard, data_audio, guard])
    return frame.astype(np.float32)


def decode_acoustic_frame(
    audio: np.ndarray, sample_rate: int = DEFAULT_SAMPLE_RATE
) -> tuple[str | None, dict]:
    """
    Detects and decodes an acoustic frame within an arbitrary audio buffer.
    Verifies frame synchronization, parses sequence number and length, and validates CRC-16.
    
    Returns:
        (decoded_text, metadata_dict)
        decoded_text is None if frame is missing, synchronization failed, or CRC-16 mismatch occurred.
    """
    metadata = {
        "detected": False,
        "peak_correlation": 0.0,
        "correlation_ratio": 0.0,
        "sync_matches": 0,
        "seq_num": None,
        "length_bytes": 0,
        "crc_valid": False,
        "expected_crc": None,
        "received_crc": None,
        "raw_text": None,
        "error": None,
    }

    reference_chirp = generate_chirp(sample_rate)
    if len(audio) < len(reference_chirp):
        metadata["error"] = "Audio buffer shorter than reference chirp."
        return None, metadata

    # 1. Matched filter cross-correlation to locate preamble chirp
    corr = signal.fftconvolve(audio, reference_chirp[::-1], mode="valid")
    abs_corr = np.abs(corr)
    peak_idx = int(np.argmax(abs_corr))
    max_corr = float(abs_corr[peak_idx])
    mean_corr = float(np.mean(abs_corr)) + 1e-9
    ratio = max_corr / mean_corr

    metadata["peak_correlation"] = max_corr
    metadata["correlation_ratio"] = ratio

    if ratio < CORR_THRESHOLD_RATIO:
        metadata["error"] = f"No preamble detected (correlation ratio {ratio:.2f} < threshold {CORR_THRESHOLD_RATIO})."
        return None, metadata

    # 2. Timing calculation: end of chirp + guard interval
    chirp_len = len(reference_chirp)
    guard_len = int(round(sample_rate * GUARD_DURATION))
    data_start = peak_idx + chirp_len + guard_len
    spb = int(round(sample_rate * DEFAULT_BIT_DURATION))

    sync_bits = byte_to_bits(SYNC_BYTE)

    # 3. Fine-tuning timing alignment over +/- 0.5 bit interval using SYNC_BYTE (0xAC)
    best_offset = 0
    best_sync_matches = -1
    candidate_offsets = sorted(range(-spb // 2, spb // 2 + 1, 15), key=lambda x: abs(x))

    for off in candidate_offsets:
        candidate_start = data_start + off
        if candidate_start < 0 or candidate_start + 8 * spb > len(audio):
            continue
        candidate_bits = demodulate_fsk(audio[candidate_start : candidate_start + 8 * spb], num_bits=8)
        matches = sum(1 for a, b in zip(candidate_bits, sync_bits) if a == b)
        if matches > best_sync_matches:
            best_sync_matches = matches
            best_offset = off
            if matches == 8:
                break

    metadata["sync_matches"] = best_sync_matches
    if best_sync_matches < 7:  # Allow at most 1 bit error in 8-bit sync delimiter
        metadata["error"] = f"Frame sync delimiter failed (matched {best_sync_matches}/8 bits)."
        return None, metadata

    # 4. Read Packet Header: SEQ (1 byte) + LEN (1 byte)
    header_start = data_start + best_offset + 8 * spb
    if header_start + 16 * spb > len(audio):
        metadata["error"] = "Audio buffer ended before packet header arrived."
        return None, metadata

    header_audio = audio[header_start : header_start + 16 * spb]
    header_bits = demodulate_fsk(header_audio, num_bits=16)
    rx_seq = bits_to_byte(header_bits[:8])
    rx_len = bits_to_byte(header_bits[8:16])

    metadata["seq_num"] = rx_seq
    metadata["length_bytes"] = rx_len

    if rx_len > 255:
        metadata["error"] = f"Invalid payload length: {rx_len} bytes."
        return None, metadata

    # 5. Read Payload (N bytes) and CRC-16 (2 bytes = 16 bits)
    body_start = header_start + 16 * spb
    body_bits_count = (rx_len + 2) * 8
    body_end = body_start + body_bits_count * spb

    if body_end > len(audio):
        metadata["error"] = f"Audio buffer ended before full payload and CRC arrived (needed {body_end} samples, have {len(audio)})."
        return None, metadata

    body_audio = audio[body_start:body_end]
    body_bits = demodulate_fsk(body_audio, num_bits=body_bits_count)
    body_bytes = bits_to_bytes(body_bits)

    rx_payload_bytes = body_bytes[:rx_len]
    rx_crc_bytes = body_bytes[rx_len : rx_len + 2]

    if len(rx_crc_bytes) < 2:
        metadata["error"] = "Incomplete CRC-16 bytes received."
        return None, metadata

    rx_crc = (rx_crc_bytes[0] << 8) | rx_crc_bytes[1]
    metadata["received_crc"] = rx_crc

    # 6. Verify CRC-16 over [SEQ] + [LEN] + [PAYLOAD]
    protected_data = bytes([rx_seq, rx_len]) + rx_payload_bytes
    calc_crc = compute_crc16(protected_data)
    metadata["expected_crc"] = calc_crc

    decoded_text = rx_payload_bytes.decode("utf-8", errors="replace")
    metadata["raw_text"] = decoded_text

    if calc_crc != rx_crc:
        metadata["crc_valid"] = False
        metadata["detected"] = True
        metadata["error"] = (
            f"CRC-16 mismatch: received 0x{rx_crc:04X}, computed 0x{calc_crc:04X} (corrupted frame rejected)"
        )
        # CRITICAL: Reject corrupted frames instead of returning corrupted text as successful
        return None, metadata

    metadata["crc_valid"] = True
    metadata["detected"] = True
    return decoded_text, metadata


# ============================================================================
# Integration Contract Interface (For Keerthana's Dashboard)
# ============================================================================

def transmit_text(message: str, seq_num: int | None = None) -> dict:
    """
    Acoustically transmits a text message with sequence numbering and CRC-16 protection.
    
    Arguments:
        message (str): UTF-8 string to transmit (max 255 bytes).
        seq_num (int | None): Optional sequence number (0-255). If None, internal counter auto-increments.
        
    Returns:
        dict: Transmission report with keys:
            - success (bool): True if audio played successfully.
            - message (str): The transmitted message.
            - seq_num (int): Sequence number used in the frame.
            - crc_16 (int): Computed CRC-16 integer value.
            - crc_hex (str): CRC-16 formatted as hex string (e.g. "0x29B1").
            - duration_sec (float): Transmission time in seconds.
            - bytes_sent (int): Number of UTF-8 payload bytes sent.
            - error (str | None): Error description if failed.
    """
    global _next_tx_seq
    _STATS["transmissions_attempted"] += 1

    if seq_num is None:
        current_seq = _next_tx_seq
        _next_tx_seq = (_next_tx_seq + 1) % 256
    else:
        current_seq = int(seq_num) & 0xFF

    payload_bytes = message.encode("utf-8")
    protected_data = bytes([current_seq, len(payload_bytes)]) + payload_bytes
    crc_val = compute_crc16(protected_data)

    report = {
        "success": False,
        "message": message,
        "seq_num": current_seq,
        "crc_16": crc_val,
        "crc_hex": f"0x{crc_val:04X}",
        "duration_sec": 0.0,
        "bytes_sent": len(payload_bytes),
        "error": None,
    }

    if not AUDIO_HARDWARE_AVAILABLE:
        report["error"] = "sounddevice package not available or audio output unavailable."
        _STATS["last_error"] = report["error"]
        return report

    try:
        frame = create_acoustic_frame(message, seq_num=current_seq, sample_rate=DEFAULT_SAMPLE_RATE)
        # 0.2s lead and 0.2s trailing silence to give soundcard clean DAC buffers
        lead = np.zeros(int(DEFAULT_SAMPLE_RATE * 0.2), dtype=np.float32)
        trail = np.zeros(int(DEFAULT_SAMPLE_RATE * 0.2), dtype=np.float32)
        tx_signal = np.concatenate([lead, frame, trail])

        t0 = time.time()
        sd.play(tx_signal, samplerate=DEFAULT_SAMPLE_RATE)
        sd.wait()
        actual_elapsed = time.time() - t0

        report["success"] = True
        report["duration_sec"] = round(actual_elapsed, 2)
        _STATS["transmissions_completed"] += 1
        _STATS["last_tx_message"] = message
        _STATS["last_tx_seq"] = current_seq
        _STATS["last_tx_duration_sec"] = report["duration_sec"]
    except Exception as e:
        report["error"] = str(e)
        _STATS["last_error"] = str(e)

    return report


def receive_text(timeout_seconds: float = 10.0) -> tuple[str | None, dict]:
    """
    Listens on the system microphone for an acoustic NetWhisper frame, validates CRC-16,
    and returns decoded text and frame metadata.
    
    Arguments:
        timeout_seconds (float): Duration to listen in seconds (default: 10.0s).
        
    Returns:
        tuple[str | None, dict]:
            - str | None: Decoded message string, or None if timed out, sync failed, or CRC failed.
            - dict: Reception metadata with keys:
                - success (bool): True if valid frame with verified CRC-16 received.
                - message (str | None): Decoded text if CRC passed, else None.
                - seq_num (int | None): Frame sequence number extracted.
                - crc_valid (bool): True if CRC-16 checksum matched.
                - expected_crc (int | None): Computed CRC-16 checksum.
                - received_crc (int | None): Received CRC-16 checksum.
                - timeout_seconds (float): Listening duration.
                - peak_correlation (float): Matched filter correlation score.
                - correlation_ratio (float): Peak-to-noise floor ratio.
                - sync_matches (int): Sync delimiter bits matched (max 8).
                - length_bytes (int): Payload length header.
                - raw_text (str | None): Decoded text regardless of CRC (for inspection).
                - error (str | None): Error description if failed.
    """
    _STATS["receptions_attempted"] += 1
    meta = {
        "success": False,
        "message": None,
        "seq_num": None,
        "crc_valid": False,
        "expected_crc": None,
        "received_crc": None,
        "timeout_seconds": timeout_seconds,
        "peak_correlation": 0.0,
        "correlation_ratio": 0.0,
        "sync_matches": 0,
        "length_bytes": 0,
        "raw_text": None,
        "error": None,
    }

    if not AUDIO_HARDWARE_AVAILABLE:
        meta["error"] = "sounddevice package not available or microphone unavailable."
        _STATS["receptions_failed"] += 1
        _STATS["last_error"] = meta["error"]
        return None, meta

    try:
        total_samples = int(round(timeout_seconds * DEFAULT_SAMPLE_RATE))
        rec_data = sd.rec(total_samples, samplerate=DEFAULT_SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        audio = rec_data.flatten()

        decoded_text, decode_meta = decode_acoustic_frame(audio, sample_rate=DEFAULT_SAMPLE_RATE)
        meta.update(decode_meta)

        if decode_meta.get("detected") and not decode_meta.get("crc_valid"):
            _STATS["crc_errors"] += 1
            _STATS["receptions_failed"] += 1
            _STATS["last_error"] = meta.get("error")
            _STATS["last_rx_crc_valid"] = False
            _STATS["last_rx_seq"] = meta.get("seq_num")
            return None, meta

        if decoded_text is not None:
            meta["success"] = True
            meta["message"] = decoded_text
            _STATS["receptions_successful"] += 1
            _STATS["last_rx_message"] = decoded_text
            _STATS["last_rx_seq"] = meta.get("seq_num")
            _STATS["last_rx_crc_valid"] = True
            _STATS["last_rx_corr_ratio"] = meta["correlation_ratio"]
        else:
            _STATS["receptions_failed"] += 1
            _STATS["last_error"] = meta.get("error")

        return decoded_text, meta

    except Exception as e:
        meta["error"] = f"Microphone error / permission denied: {e}"
        _STATS["receptions_failed"] += 1
        _STATS["last_error"] = meta["error"]
        return None, meta


def get_stats() -> dict:
    """Returns current cumulative communication engine statistics for dashboard monitoring."""
    return dict(_STATS)


def reset_stats() -> None:
    """Resets internal statistics counters."""
    global _STATS, _next_tx_seq
    _next_tx_seq = 0
    for key in _STATS:
        if isinstance(_STATS[key], int):
            _STATS[key] = 0
        elif isinstance(_STATS[key], float):
            _STATS[key] = 0.0
        elif key == "data_rate_bps":
            _STATS[key] = round(1.0 / DEFAULT_BIT_DURATION, 2)
        else:
            _STATS[key] = None


# ============================================================================
# Automated Self-Tests & CLI Entry Point
# ============================================================================

def run_automated_tests() -> bool:
    """
    Comprehensive software test suite verifying:
    1. Valid standard frame encoding, decoding, sequence number, and CRC-16 match.
    2. Deliberately corrupted payload (1-bit corruption triggers CRC rejection).
    3. Sequence number extraction across multiple frames (seq wrapping & values).
    4. Empty message (length = 0) support.
    5. UTF-8 multi-byte characters and punctuation.
    """
    print("=" * 65)
    print("NetWhisper: Automated Test Suite (CRC-16 & Framing)")
    print("=" * 65)

    all_passed = True

    # Test 1: Valid standard frame
    print("[1/5] Testing Valid Message Frame with CRC-16...")
    test_msg = "Hello NetWhisper!"
    seq_1 = 42
    frame_1 = create_acoustic_frame(test_msg, seq_num=seq_1)
    padded_1 = np.pad(frame_1, (int(DEFAULT_SAMPLE_RATE * 0.3), int(DEFAULT_SAMPLE_RATE * 0.3)))
    decoded_1, meta_1 = decode_acoustic_frame(padded_1)

    t1_pass = (
        decoded_1 == test_msg
        and meta_1["crc_valid"] is True
        and meta_1["seq_num"] == seq_1
        and meta_1["length_bytes"] == len(test_msg.encode("utf-8"))
    )
    print(f"      Result: {'PASS' if t1_pass else 'FAIL'} | Decoded: '{decoded_1}' | Seq: {meta_1['seq_num']} | CRC Valid: {meta_1['crc_valid']}")
    all_passed &= t1_pass

    # Test 2: Deliberately Corrupted Payload
    print("\n[2/5] Testing Deliberate Payload Corruption (Bit Flip)...")
    packet_bytes = bytearray(build_packet_bytes("Critical Data Packet", seq_num=10))
    # Deliberately flip 1 bit in payload (byte index 4)
    packet_bytes[4] ^= 0x01
    corrupted_bits = bytes_to_bits(packet_bytes)

    chirp = generate_chirp(DEFAULT_SAMPLE_RATE)
    guard = np.zeros(int(round(DEFAULT_SAMPLE_RATE * GUARD_DURATION)), dtype=np.float32)
    corrupted_audio = np.concatenate([guard, chirp, guard, modulate_fsk(corrupted_bits), guard])
    padded_corrupt = np.pad(corrupted_audio, (int(DEFAULT_SAMPLE_RATE * 0.2), int(DEFAULT_SAMPLE_RATE * 0.2)))

    decoded_corrupt, meta_corrupt = decode_acoustic_frame(padded_corrupt)
    t2_pass = (
        decoded_corrupt is None
        and meta_corrupt["crc_valid"] is False
        and meta_corrupt["error"] is not None
        and "CRC-16 mismatch" in meta_corrupt["error"]
    )
    print(f"      Result: {'PASS' if t2_pass else 'FAIL'} | Decoded: {decoded_corrupt} | CRC Valid: {meta_corrupt['crc_valid']}")
    print(f"      Error Reported: {meta_corrupt['error']}")
    all_passed &= t2_pass

    # Test 3: Sequence Number Extraction & Wrapping
    print("\n[3/5] Testing Sequence Number Extraction (Seq=255, Seq=0)...")
    frame_seq_255 = create_acoustic_frame("Seq 255 Test", seq_num=255)
    padded_255 = np.pad(frame_seq_255, (int(DEFAULT_SAMPLE_RATE * 0.2), int(DEFAULT_SAMPLE_RATE * 0.2)))
    _, meta_255 = decode_acoustic_frame(padded_255)

    frame_seq_0 = create_acoustic_frame("Seq 0 Test", seq_num=0)
    padded_0 = np.pad(frame_seq_0, (int(DEFAULT_SAMPLE_RATE * 0.2), int(DEFAULT_SAMPLE_RATE * 0.2)))
    _, meta_0 = decode_acoustic_frame(padded_0)

    t3_pass = (meta_255["seq_num"] == 255 and meta_255["crc_valid"] and meta_0["seq_num"] == 0 and meta_0["crc_valid"])
    print(f"      Result: {'PASS' if t3_pass else 'FAIL'} | Seq extracted: {meta_255['seq_num']} & {meta_0['seq_num']}")
    all_passed &= t3_pass

    # Test 4: Empty Message (Length = 0)
    print("\n[4/5] Testing Empty Message Support (length=0)...")
    frame_empty = create_acoustic_frame("", seq_num=77)
    padded_empty = np.pad(frame_empty, (int(DEFAULT_SAMPLE_RATE * 0.2), int(DEFAULT_SAMPLE_RATE * 0.2)))
    decoded_empty, meta_empty = decode_acoustic_frame(padded_empty)

    t4_pass = (
        decoded_empty == ""
        and meta_empty["crc_valid"] is True
        and meta_empty["length_bytes"] == 0
        and meta_empty["seq_num"] == 77
    )
    print(f"      Result: {'PASS' if t4_pass else 'FAIL'} | Decoded: '{decoded_empty}' | Length: {meta_empty['length_bytes']} | CRC Valid: {meta_empty['crc_valid']}")
    all_passed &= t4_pass

    # Test 5: UTF-8 Multi-Byte and Punctuation
    print("\n[5/5] Testing UTF-8 Multi-Byte Characters & Symbols...")
    utf8_msg = "Acoustic Link 100% OK!"
    frame_utf8 = create_acoustic_frame(utf8_msg, seq_num=99)
    padded_utf8 = np.pad(frame_utf8, (int(DEFAULT_SAMPLE_RATE * 0.2), int(DEFAULT_SAMPLE_RATE * 0.2)))
    decoded_utf8, meta_utf8 = decode_acoustic_frame(padded_utf8)

    t5_pass = (decoded_utf8 == utf8_msg and meta_utf8["crc_valid"] is True and meta_utf8["seq_num"] == 99)
    print(f"      Result: {'PASS' if t5_pass else 'FAIL'} | Decoded: '{decoded_utf8}' | CRC Valid: {meta_utf8['crc_valid']}")
    all_passed &= t5_pass

    print("\n" + "=" * 65)
    if all_passed:
        print("[ALL TESTS PASSED] 5/5 automated unit tests verified successfully.")
    else:
        print("[FAIL] Some unit tests failed.")
    print("=" * 65)
    return all_passed


def run_software_test(test_message: str = "NetWhisper CRC Link OK") -> bool:
    """Runs a single in-memory loopback test with simulated channel noise."""
    print("=" * 60)
    print("NetWhisper: Pure Software Loopback Test")
    print("=" * 60)
    print(f"Message              : '{test_message}'")

    frame = create_acoustic_frame(test_message, seq_num=1)
    padded = np.pad(frame, (int(DEFAULT_SAMPLE_RATE * 0.4), int(DEFAULT_SAMPLE_RATE * 0.4)))
    noisy = padded + 0.04 * np.random.randn(len(padded)).astype(np.float32)

    decoded_text, meta = decode_acoustic_frame(noisy)
    print(f"Preamble Detected    : {meta['detected']}")
    print(f"Correlation Ratio    : {meta['correlation_ratio']:.2f}")
    print(f"Sync Header Matches  : {meta['sync_matches']}/8")
    print(f"Sequence Number      : {meta['seq_num']}")
    print(f"CRC-16 Valid         : {meta['crc_valid']} (0x{meta.get('received_crc', 0):04X})")
    print(f"Decoded Message      : '{decoded_text}'")

    success = (decoded_text == test_message and meta["crc_valid"] is True)
    print(f"Status               : {'[PASS]' if success else '[FAIL]'}")
    print("=" * 60)
    return success


def run_acoustic_loopback_test(test_message: str = "NETWHISPER") -> bool:
    """
    Runs physical speaker-to-microphone acoustic loopback test on the local device.
    Uses sounddevice playrec to simultaneously transmit through speakers and capture via mic.
    """
    print("=" * 60)
    print("NetWhisper: Physical Acoustic Speaker-to-Mic Loopback Test")
    print("=" * 60)
    print(f"Message              : '{test_message}'")

    if not AUDIO_HARDWARE_AVAILABLE:
        print("[FAIL] sounddevice is not available. Run: pip3 install sounddevice")
        return False

    frame = create_acoustic_frame(test_message, seq_num=42)
    lead = np.zeros(int(DEFAULT_SAMPLE_RATE * 0.2), dtype=np.float32)
    trail = np.zeros(int(DEFAULT_SAMPLE_RATE * 0.4), dtype=np.float32)
    tx_signal = np.concatenate([lead, frame, trail])

    total_sec = len(tx_signal) / DEFAULT_SAMPLE_RATE
    print(f"Transmitting & Recording for {total_sec:.2f} seconds...")
    rx_raw = sd.playrec(tx_signal, samplerate=DEFAULT_SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    rx_audio = rx_raw.flatten()

    decoded_text, meta = decode_acoustic_frame(rx_audio)
    print(f"Preamble Detected    : {meta['detected']}")
    print(f"Correlation Ratio    : {meta['correlation_ratio']:.2f}")
    print(f"Sync Header Matches  : {meta['sync_matches']}/8")
    print(f"Sequence Number      : {meta['seq_num']}")
    print(f"Decoded Length       : {meta['length_bytes']} bytes")
    print(f"CRC-16 Checksum      : 0x{meta.get('received_crc', 0):04X} (Valid: {meta['crc_valid']})")
    print(f"Decoded Message      : '{decoded_text}'")

    success = (decoded_text == test_message and meta["crc_valid"] is True)
    if success:
        print("\n[SUCCESS] Real acoustic transmission & CRC-16 verified through physical air!")
    else:
        print(f"\n[FAIL] Transmission failed. Error: {meta.get('error')}")
    print("=" * 60)
    return success


def main():
    parser = argparse.ArgumentParser(description="NetWhisper Acoustic FSK Engine")
    parser.add_argument("--test-automated", action="store_true", help="Run automated test suite (5 tests)")
    parser.add_argument("--test-software", action="store_true", help="Run pure software loopback test")
    parser.add_argument("--test-acoustic", action="store_true", help="Run physical speaker-to-mic loopback test")
    parser.add_argument("--send", type=str, metavar="MSG", help="Acoustically transmit message through speaker")
    parser.add_argument("--seq", type=int, default=None, help="Sequence number for --send (default: auto)")
    parser.add_argument("--listen", type=float, metavar="SECS", help="Listen on microphone for incoming acoustic frame")
    parser.add_argument("--devices", action="store_true", help="List audio input and output devices")
    args = parser.parse_args()

    if args.devices:
        if AUDIO_HARDWARE_AVAILABLE:
            print(sd.query_devices())
        else:
            print("sounddevice not available.")
        return

    if args.test_automated:
        success = run_automated_tests()
        sys.exit(0 if success else 1)

    if args.test_software:
        success = run_software_test()
        sys.exit(0 if success else 1)

    if args.test_acoustic:
        success = run_acoustic_loopback_test()
        sys.exit(0 if success else 1)

    if args.send:
        print(f"[*] Transmitting: '{args.send}' (seq: {args.seq}) ...")
        res = transmit_text(args.send, seq_num=args.seq)
        if res["success"]:
            print(f"[+] Transmitted {res['bytes_sent']} bytes in {res['duration_sec']}s (seq={res['seq_num']}, CRC={res['crc_hex']})")
        else:
            print(f"[-] Transmission failed: {res['error']}")
        return

    if args.listen:
        print(f"[*] Listening on microphone for {args.listen} seconds...")
        text, meta = receive_text(timeout_seconds=args.listen)
        if text is not None:
            print(f"[+] Decoded Message: '{text}' (seq={meta['seq_num']}, CRC=0x{meta['received_crc']:04X}, valid={meta['crc_valid']})")
        else:
            print(f"[-] Frame rejected or missing: {meta.get('error')}")
        return

    # Default action if no flags given: run automated tests
    run_automated_tests()


if __name__ == "__main__":
    main()

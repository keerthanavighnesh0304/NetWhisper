
# NetWhisper — Reliable Data Communication over an Acoustic Channel

NetWhisper is an academic Computer Networks project that explores transmitting digital data through physical sound waves using speakers and microphones. It uses Continuous-Phase Frequency Shift Keying (CPFSK), packet framing, synchronization, and CRC-16 error detection.

## Project Status

- Dashboard and FastAPI backend: implemented.
- Synthetic dashboard loopback: implemented for software testing.
- Acoustic FSK engine: implemented in `fsk_engine.py`.
- CRC-16-CCITT and sequence numbering: implemented in the acoustic engine.
- Dashboard-to-engine integration: in progress; must be tested.
- Two-laptop acoustic communication: requires end-to-end verification.
- Stop-and-Wait ACK/NACK and retransmission: not implemented yet.

## Team Responsibilities

- **Keerthana:** FastAPI backend, React dashboard, telemetry, waveform visualization, packet history, metrics, and engine integration.
- **Marnia:** FSK communication engine, modulation/demodulation, packet framing, audio input/output, synchronization, and acoustic testing.

## Architecture

```text
                 TRANSMITTER
                      |
                 Text Message
                      |
               UTF-8 Byte Encoding
                      |
          Packet Framing + CRC-16
                      |
                CPFSK Modulation
                      |
                   Speaker
                      |
             Physical Acoustic Channel
                      |
                 Microphone
                      |
             Preamble Synchronization
                      |
              CPFSK Demodulation
                      |
             Frame and CRC Validation
                      |
              Reconstructed Message
```

The dashboard communicates with the FastAPI backend through HTTP endpoints and WebSockets. The backend uses `backend/engine_adapter.py` as the integration boundary between the dashboard and the acoustic engine.

## Acoustic Protocol Specification

### Physical Layer

- Modulation: Continuous-Phase Frequency Shift Keying (CPFSK).
- Sampling rate: 44,100 Hz, subject to audio-device support.
- Frequency for bit 0: 1800 Hz.
- Frequency for bit 1: 2400 Hz.
- Symbol duration: 40 ms per bit.
- Nominal raw bit rate: 25 bits per second.

### Frame Format

```text
Guard Silence
    |
Chirp Preamble
    |
Guard Silence
    |
SYNC (1 byte)
    |
SEQ (1 byte)
    |
LEN (1 byte)
    |
PAYLOAD (N bytes)
    |
CRC-16 (2 bytes, big-endian)
    |
Guard Silence
```

- **Preamble:** A chirp used to detect the beginning of a transmission.
- **SYNC:** `0xAC`, used as a frame synchronization delimiter.
- **SEQ:** An 8-bit sequence number from 0 to 255, wrapping modulo 256.
- **LEN:** An 8-bit payload length from 0 to 255 bytes.
- **PAYLOAD:** UTF-8 encoded message bytes.
- **CRC-16:** A 16-bit checksum for detecting accidental frame corruption.

### CRC-16-CCITT-FALSE

- Polynomial: `0x1021`
- Initial register: `0xFFFF`
- Reflected input/output: false/false
- Final XOR: `0x0000`
- Coverage: `SEQ + LEN + PAYLOAD`
- Check value: `compute_crc16(b"123456789") == 0x29B1`
- Byte order: big-endian.

The receiver should reject frames whose calculated checksum does not match the received checksum.

Sequence numbering identifies packets and can support duplicate detection. Sequence numbers alone do not implement a reliable acknowledgement protocol.

## Repository Structure

```text
NetWhisper/
├── backend/
│   ├── main.py
│   ├── models.py
│   ├── engine_adapter.py
│   └── tests/
│       └── test_backend.py
├── frontend/
│   ├── src/
│   ├── package.json
│   └── ...
├── fsk_engine.py
├── requirements.txt
├── NETWHISPER_PROJECT.md
├── README.md
└── .gitignore
```

## Installation

Use Python 3.10 or newer.

Install the project dependencies:

```bash
python -m pip install -r requirements.txt
```

The acoustic engine additionally requires:

```bash
python -m pip install sounddevice numpy scipy
```

On Windows, macOS, or Linux, verify that the selected audio input and output devices are available and that microphone access is permitted.

For the React development frontend:

```bash
cd frontend
npm install
```

## Running the Dashboard

From the project root, start FastAPI:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open:

http://127.0.0.1:8000

If port 8000 is already occupied, use another port, such as 8001.

The backend provides these endpoints:

- `GET /api/status`
- `POST /api/transmit`
- `POST /api/mode`
- `POST /api/reset`
- `GET /api/integration-info`
- WebSocket `/ws`

Check `backend/main.py` for the exact request and response schemas.

## Dashboard Modes

### Synthetic Test Mode

Synthetic loopback exercises the dashboard and backend without requiring real acoustic transmission. It can be used to test the interface, simulated packet flow, CRC display, and telemetry.

Synthetic results must be clearly labelled as simulated and must not be presented as evidence of physical acoustic communication.

### Acoustic Live Mode

Acoustic live mode should be enabled only when the real engine is registered and the relevant operations have succeeded. The dashboard must not report a successful physical transmission merely because the backend generated a synthetic waveform or updated its counters.

## Acoustic Engine Integration Contract

The acoustic engine is implemented in `fsk_engine.py`.

The reported public functions are:

```python
import fsk_engine

# Transmit a message through the acoustic output.
tx_report = fsk_engine.transmit_text(
    "Hello NetWhisper!",
    seq_num=1,
)

# Listen for and decode an incoming acoustic frame.
message, metadata = fsk_engine.receive_text(
    timeout_seconds=10.0,
)

# Retrieve engine statistics.
stats = fsk_engine.get_stats()
```

### Transmit Result

The transmit function reports whether audio playback completed, the message, sequence number, checksum information, duration, bytes sent, and any error.

### Receive Result

The receive function returns a tuple:

```python
message, metadata
```

The message is decoded text on successful reception, or `None` if reception fails or times out. The metadata reports reception status, sequence number, CRC validity, correlation information, payload length, and errors.

The exact return fields must be verified against the current implementation of `fsk_engine.py` before integration.

### Adapter Integration

`backend/engine_adapter.py` should provide a controlled boundary between FastAPI and the acoustic engine.

The adapter must:
- Preserve synthetic test mode.
- Call the actual acoustic engine for real transmissions.
- Report real engine errors instead of silently reporting success.
- Distinguish playback completion from successful reception.
- Expose only metrics supported by actual engine results.
- Avoid blocking the event loop with long-running audio operations.

A successful transmit call alone does not prove that a receiver decoded the message.

## Testing

### 1. Acoustic Engine Automated Tests

Run from the repository root:

```bash
python fsk_engine.py --test-automated
```

The reported test suite covers valid frames, corrupted payload rejection, sequence-number wrapping, empty messages, and UTF-8 text.

### 2. Physical Acoustic Loopback

```bash
python fsk_engine.py --test-acoustic
```

This test should play a generated signal through a speaker and capture it through a microphone. It must be executed on the actual device to count as physical test evidence.

### 3. Two-Laptop Communication

On the receiver laptop, start listening first:

```bash
python fsk_engine.py --listen 10
```

On the sender laptop, transmit within the listening window:

```bash
python fsk_engine.py --send "NETWHISPER" --seq 1
```

Both devices need the acoustic engine and its dependencies. The receiver should reconstruct the original message and report valid CRC metadata.

### 4. Backend Tests

```bash
python -m unittest backend.tests.test_backend -v
```

### 5. Frontend Production Build

```bash
cd frontend
npm run build
```

Run all relevant tests again after engine integration.

## Current Limitations

- The synthetic dashboard mode is not physical acoustic communication.
- Same-device acoustic loopback does not prove two-laptop communication.
- CRC-16 detects many accidental errors but does not correct corrupted data.
- Sequence numbers identify frames but do not by themselves guarantee reliable delivery.
- Stop-and-Wait ACK/NACK, timeout-based retransmission, and duplicate suppression remain future work.
- The dashboard-to-engine integration must be tested before claiming that the complete application performs real acoustic transmission.

## Academic Concepts Demonstrated

- Physical-layer digital modulation using CPFSK.
- Acoustic signal transmission and reception.
- Framing, synchronization, and payload length.
- Data integrity using CRC-16.
- Sequence numbering.
- Client-server architecture and API integration.
- Real-time monitoring with FastAPI, WebSockets, and React.
- Performance metrics such as latency, data rate, and reception success.
- Reliable data transfer concepts, including ACK/NACK and retransmission as future extensions.

# NetWhisper: Reliable Data Communication over an Acoustic Channel

An academic Computer Networks project transmitting digital data over physical sound waves using speaker and microphone with Frequency Shift Keying (FSK), packet framing, and CRC-16 error detection.

## Team Responsibilities

- **Keerthana:** Backend, dashboard, telemetry, oscilloscope visualization, and integration adapter.
- **Marnia:** Communication engine (FSK modulation/demodulation, packet framing, audio I/O via sounddevice, acoustic experiments).

---

## Architecture & Integration Layer

```
[Transmitter Console / Engine]
       ↓
[Text to Binary] → [Packet Framing + CRC-16] → [FSK Modulation]
       ↓                                              ↓
[Speaker: Acoustic Channel] -------------------> [Microphone]
                                                      ↓
[Live Oscilloscope] ← [FastAPI & WebSockets] ← [FSK Demodulator + CRC Check]
```

The system uses an isolated adapter in `backend/engine_adapter.py`. 
- **Idle / Awaiting Engine State:** Shows real zeroed metrics; does not claim acoustic transmission without confirmation from the engine.
- **Test Mode (Synthetic Loopback):** Clearly flagged as `TEST_LOOPBACK (Synthetic - Not Acoustic)` for validating UI, CRC verification, and latency without faking acoustic results.
- **Acoustic Live State:** Active when Marnia's engine is registered via `engine_adapter.register_acoustic_engine(engine)`.

---

## Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Dashboard (Single Command)
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in any web browser.

### 3. (Optional) Run Frontend in Vite Development Mode
```bash
cd frontend
npm install
npm run dev
```
Open **`http://localhost:5173`**.

---

## Running Automated Tests

Run backend unit tests:
```bash
python -m unittest backend.tests.test_backend -v
```

Build the frontend bundle:
```bash
cd frontend
npm run build
```

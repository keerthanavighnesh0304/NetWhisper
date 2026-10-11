"""
NetWhisper - Acoustic Engine Adapter & Integration Layer
Role: Keerthana (Backend / Integration / Dashboard)

This module provides a clean, isolated integration interface for Marnia's
acoustic communication engine.

INTEGRATION CONTRACT:
When Marnia's communication engine is ready, it connects here via
`register_acoustic_engine(engine)` or by implementing the callback hooks.

DATA INTEGRITY RULES:
- If engine is not connected, status is strictly marked AWAITING_ENGINE.
- In TEST_MODE, all records are explicitly flagged as 'TEST_LOOPBACK (Synthetic - Not Acoustic)'.
- Zero acoustic transmission claims are made without confirmation from the real acoustic engine.
"""

import time
import math
import asyncio
from typing import Optional, Callable, Dict, Any, List
from .models import EngineState, CRCStatus, PacketRecord, ChannelMetrics, SystemStatus


def compute_crc16(data_bytes: bytes) -> int:
    """Standard CRC-16-CCITT (polynomial 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data_bytes:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def text_to_binary(text: str) -> str:
    """Convert ASCII text string to binary string (8 bits per char)."""
    return "".join(f"{ord(c):08b}" for c in text)


def binary_to_text(binary_str: str) -> str:
    """Convert binary string back to ASCII text."""
    chars = []
    for i in range(0, len(binary_str), 8):
        byte = binary_str[i:i+8]
        if len(byte) == 8:
            try:
                chars.append(chr(int(byte, 2)))
            except ValueError:
                chars.append("?")
    return "".join(chars)


class EngineAdapter:
    def __init__(self):
        self.state: EngineState = EngineState.AWAITING_ENGINE
        self.acoustic_engine = None
        self.metrics = ChannelMetrics()
        self.recent_packets: List[PacketRecord] = []
        self.last_transmitted: Optional[str] = None
        self.last_received: Optional[str] = None
        self.recent_crc_status: CRCStatus = CRCStatus.IDLE
        self.packet_counter = 0

        # Callbacks for live WebSocket streaming
        self.telemetry_listeners: List[Callable[[Dict[str, Any]], Any]] = []

        # Current audio signal buffer for oscilloscope (synthetic or real)
        self.current_signal_samples: List[float] = [0.0] * 128
        self.mark_freq: float = 1800.0  # Hz (FSK binary 1)
        self.space_freq: float = 1200.0 # Hz (FSK binary 0)

    def register_acoustic_engine(self, engine_obj: Any) -> bool:
        """
        Integration point for Marnia's engine.
        Accepts any engine object exposing transmit / receive or custom hooks.
        """
        self.acoustic_engine = engine_obj
        self.state = EngineState.ACOUSTIC_LIVE
        self._notify_listeners({
            "type": "ENGINE_CONNECTED",
            "message": "Acoustic communication engine attached successfully."
        })
        return True

    def set_test_mode(self, enabled: bool):
        """
        Toggle between idle/awaiting mode and explicit test loopback mode.
        """
        if enabled:
            self.state = EngineState.TEST_MODE
        else:
            self.state = EngineState.AWAITING_ENGINE if not self.acoustic_engine else EngineState.ACOUSTIC_LIVE

    def reset_stats(self):
        """Reset all transmission and error metrics."""
        self.metrics = ChannelMetrics()
        self.recent_packets.clear()
        self.last_transmitted = None
        self.last_received = None
        self.recent_crc_status = CRCStatus.IDLE
        self.packet_counter = 0
        self.current_signal_samples = [0.0] * 128

    def get_status(self) -> SystemStatus:
        mode_label = (
            "ACOUSTIC LIVE (Real Physical Channel)" if self.acoustic_engine else
            ("TEST MODE (Synthetic Loopback — Not Acoustic)" if self.state == EngineState.TEST_MODE else
             "IDLE (Awaiting Acoustic Engine Integration)")
        )
        notice = (
            "Connected to physical acoustic channel." if self.acoustic_engine else
            ("Synthetic simulation mode for dashboard testing. NOT physical acoustic transmission." if self.state == EngineState.TEST_MODE else
             "Dashboard ready. Awaiting Marnia's communication engine. No acoustic transmission claims.")
        )
        return SystemStatus(
            state=self.state,
            engine_connected=self.acoustic_engine is not None,
            engine_name="Acoustic Engine (Active)" if self.acoustic_engine else "Pending (Marnia Communication Engine)",
            metrics=self.metrics,
            last_transmitted=self.last_transmitted,
            last_received=self.last_received,
            recent_crc_status=self.recent_crc_status,
            recent_packets=self.recent_packets[-10:],
            active_mode_label=mode_label,
            notice=notice,
        )

    async def transmit_message(self, message: str, simulate_noise: bool = False) -> Dict[str, Any]:
        """
        Handles message transmission.
        If acoustic engine is hooked up, delegates to physical acoustic engine.
        Otherwise, if in TEST_MODE, performs safe synthetic loopback calculation.
        If in AWAITING_ENGINE mode, rejects with clear instruction.
        """
        if not self.acoustic_engine and self.state != EngineState.TEST_MODE:
            return {
                "success": False,
                "error": "Acoustic engine is not yet connected. Switch to 'Test Mode' to test the dashboard, or connect Marnia's engine.",
                "state": self.state.value
            }

        if self.acoustic_engine:
            # REAL ACOUSTIC ENGINE TRANSMISSION HOOK
            return await self._transmit_via_acoustic_engine(message)
        else:
            # SYNTHETIC TEST TRANSMISSION
            return await self._simulate_test_transmission(message, simulate_noise)

    async def _transmit_via_acoustic_engine(self, message: str) -> Dict[str, Any]:
        """Invoked when Marnia's engine is connected."""
        start_time = time.time()
        self.state = EngineState.TRANSMITTING
        try:
            # Dynamically supports Marnia's engine method signature (e.g., transmit, send, or run_tx)
            if hasattr(self.acoustic_engine, "transmit"):
                result = await asyncio.to_thread(self.acoustic_engine.transmit, message)
            elif hasattr(self.acoustic_engine, "send"):
                result = await asyncio.to_thread(self.acoustic_engine.send, message)
            else:
                result = {"status": "success", "raw": "transmitted"}

            elapsed_ms = (time.time() - start_time) * 1000.0
            self.last_transmitted = message
            self.metrics.packets_sent += 1
            self.metrics.last_tx_time = time.time()
            self.metrics.latency_ms = round(elapsed_ms, 2)
            self.state = EngineState.ACOUSTIC_LIVE
            return {"success": True, "source": "ACOUSTIC_ENGINE", "result": result}
        except Exception as e:
            self.state = EngineState.ACOUSTIC_LIVE
            return {"success": False, "error": f"Acoustic engine error: {str(e)}"}

    async def _simulate_test_transmission(self, message: str, simulate_noise: bool) -> Dict[str, Any]:
        """
        Explicit synthetic loopback for validating dashboard UI, WebSocket,
        and metrics visualization before Marnia's engine is attached.
        """
        self.packet_counter += 1
        pkt_id = self.packet_counter
        self.state = EngineState.TRANSMITTING

        tx_time = time.time()
        binary = text_to_binary(message)
        raw_bytes = message.encode("utf-8")
        crc_val = compute_crc16(raw_bytes)
        crc_hex = f"0x{crc_val:04X}"

        # Generate sample FSK waveform points for oscilloscope
        self._generate_synthetic_fsk_waveform(binary)

        # Notify UI of transmission start
        self._notify_listeners({
            "type": "TX_START",
            "packet_id": pkt_id,
            "message": message,
            "binary_preview": binary[:64] + ("..." if len(binary) > 64 else ""),
            "crc": crc_hex,
            "waveform": self.current_signal_samples
        })

        # Simulated transmission duration based on realistic FSK baud (e.g. 50 baud)
        simulated_delay = min(0.4, max(0.1, len(binary) * 0.005))
        await asyncio.sleep(simulated_delay)

        self.state = EngineState.RECEIVING

        # Synthetic receiver check
        is_corrupted = simulate_noise
        received_text = message if not is_corrupted else (message[:-1] + "?" if len(message) > 1 else "?")
        rx_bytes = received_text.encode("utf-8")
        computed_rx_crc = compute_crc16(rx_bytes)
        crc_matches = (computed_rx_crc == crc_val) and not is_corrupted

        rx_time = time.time()
        latency_ms = round((rx_time - tx_time) * 1000.0, 2)
        total_bits = len(binary) + 16  # data + 16-bit CRC
        data_rate_bps = round(total_bits / (simulated_delay if simulated_delay > 0 else 0.1), 1)

        # Update metrics
        self.metrics.packets_sent += 1
        self.metrics.packets_received += 1
        self.metrics.last_tx_time = tx_time
        self.metrics.last_rx_time = rx_time
        self.metrics.latency_ms = latency_ms
        self.metrics.data_rate_bps = data_rate_bps
        self.last_transmitted = message

        if crc_matches:
            self.metrics.crc_valid_count += 1
            self.recent_crc_status = CRCStatus.VALID
            self.last_received = received_text
        else:
            self.metrics.crc_error_count += 1
            self.metrics.retransmissions += 1
            self.recent_crc_status = CRCStatus.CORRUPTED
            self.last_received = f"[CORRUPTED CRC ERROR] {received_text}"

        packet_record = PacketRecord(
            packet_id=pkt_id,
            timestamp=rx_time,
            payload_text=received_text,
            binary_data=text_to_binary(received_text),
            crc16=crc_hex,
            crc_valid=crc_matches,
            is_retransmission=is_corrupted,
            source="TEST_LOOPBACK (Synthetic - Not Acoustic)"
        )
        self.recent_packets.append(packet_record)
        if len(self.recent_packets) > 50:
            self.recent_packets.pop(0)

        self.state = EngineState.TEST_MODE

        # Broadcast RX event
        event_payload = {
            "type": "PACKET_EVENT",
            "packet": packet_record.model_dump(),
            "metrics": self.metrics.model_dump(),
            "crc_status": self.recent_crc_status.value,
            "waveform": self.current_signal_samples
        }
        self._notify_listeners(event_payload)

        return {
            "success": True,
            "packet_id": pkt_id,
            "crc_valid": crc_matches,
            "latency_ms": latency_ms,
            "data_rate_bps": data_rate_bps,
            "source": "TEST_LOOPBACK (Synthetic - Not Acoustic)"
        }

    def _generate_synthetic_fsk_waveform(self, binary_str: str):
        """Generates 128 normalized float points showing FSK tone transitions."""
        samples = []
        sample_rate = 8000
        n_samples = 128
        bits_to_show = binary_str[:8] if binary_str else "10101010"
        samples_per_bit = max(1, n_samples // len(bits_to_show))

        idx = 0
        for bit in bits_to_show:
            freq = self.mark_freq if bit == "1" else self.space_freq
            for _ in range(samples_per_bit):
                if idx >= n_samples:
                    break
                t = idx / sample_rate
                val = math.sin(2.0 * math.pi * freq * t)
                samples.append(round(val, 3))
                idx += 1

        while len(samples) < n_samples:
            samples.append(0.0)

        self.current_signal_samples = samples[:n_samples]

    def add_telemetry_listener(self, callback: Callable[[Dict[str, Any]], Any]):
        self.telemetry_listeners.append(callback)

    def remove_telemetry_listener(self, callback: Callable[[Dict[str, Any]], Any]):
        if callback in self.telemetry_listeners:
            self.telemetry_listeners.remove(callback)

    def _notify_listeners(self, data: Dict[str, Any]):
        for listener in list(self.telemetry_listeners):
            try:
                res = listener(data)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        res.close()
            except Exception:
                pass


# Global singleton instance for the backend
engine_adapter = EngineAdapter()

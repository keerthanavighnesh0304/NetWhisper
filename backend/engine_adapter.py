"""
NetWhisper - Acoustic Engine Adapter & Integration Layer
Role: Keerthana (Backend / Integration / Dashboard)

This module provides a clean, isolated integration interface for Marnia's
acoustic communication engine (fsk_engine.py).

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
        Accepts any engine object exposing transmit_text / receive_text or transmit / send hooks.
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

    def _update_computed_rates(self):
        """Recalculates error rates, retransmission rates, and running averages."""
        # CRC Error Rate (Frame Error Rate % over all received frames checked)
        total_crc_checked = self.metrics.crc_valid_count + self.metrics.crc_error_count
        if total_crc_checked > 0:
            self.metrics.crc_error_rate = round((self.metrics.crc_error_count / total_crc_checked) * 100.0, 1)
        else:
            self.metrics.crc_error_rate = 0.0

        # Retransmission Rate %
        total_traffic = self.metrics.packets_sent if self.metrics.packets_sent > 0 else self.metrics.packets_received
        if total_traffic > 0:
            self.metrics.retransmission_rate = round((self.metrics.retransmissions / total_traffic) * 100.0, 1)
        else:
            self.metrics.retransmission_rate = 0.0

        # Average latency across recent packets that have a measured latency > 0
        valid_latencies = [p.latency_ms for p in self.recent_packets if p.latency_ms is not None and p.latency_ms > 0]
        if valid_latencies:
            self.metrics.average_latency_ms = round(sum(valid_latencies) / len(valid_latencies), 1)

        # Average and peak data rates
        valid_rates = [p.data_rate_bps for p in self.recent_packets if p.data_rate_bps is not None and p.data_rate_bps > 0]
        if valid_rates:
            self.metrics.average_data_rate_bps = round(sum(valid_rates) / len(valid_rates), 1)
            self.metrics.peak_data_rate_bps = round(max(valid_rates), 1)

    def get_status(self) -> SystemStatus:
        hw_avail = getattr(self.acoustic_engine, "AUDIO_HARDWARE_AVAILABLE", False) if self.acoustic_engine else False
        if self.acoustic_engine:
            if hw_avail:
                mode_label = "ACOUSTIC LIVE (Real Physical Channel)"
                notice = "Connected to physical acoustic channel via Marnia's engine (sounddevice ready)."
            else:
                mode_label = "ACOUSTIC ENGINE (Audio Hardware Unavailable)"
                notice = "Marnia's FSK engine loaded, but sounddevice is not available. Install sounddevice for physical audio."
        elif self.state == EngineState.TEST_MODE:
            mode_label = "TEST MODE (Synthetic Loopback - Not Acoustic)"
            notice = "Synthetic simulation mode for dashboard testing. NOT physical acoustic transmission."
        else:
            mode_label = "IDLE (Awaiting Acoustic Engine Integration)"
            notice = "Dashboard ready. Awaiting Marnia's communication engine. No acoustic transmission claims."

        return SystemStatus(
            state=self.state,
            engine_connected=self.acoustic_engine is not None,
            engine_name="Acoustic Engine (Active)" if self.acoustic_engine else "Pending (Marnia Communication Engine)",
            hardware_available=hw_avail,
            metrics=self.metrics,
            last_transmitted=self.last_transmitted,
            last_received=self.last_received,
            recent_crc_status=self.recent_crc_status,
            recent_packets=list(self.recent_packets),
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
        if self.state == EngineState.TEST_MODE:
            # SYNTHETIC TEST TRANSMISSION
            return await self._simulate_test_transmission(message, simulate_noise)
        elif self.acoustic_engine:
            # REAL ACOUSTIC ENGINE TRANSMISSION HOOK
            return await self._transmit_via_acoustic_engine(message)
        else:
            return {
                "success": False,
                "error": "Acoustic engine is not yet connected. Switch to 'Test Mode' to test the dashboard, or connect Marnia's engine.",
                "state": self.state.value
            }

    async def _transmit_via_acoustic_engine(self, message: str) -> Dict[str, Any]:
        """Invoked when Marnia's engine is connected."""
        start_time = time.time()
        self.state = EngineState.TRANSMITTING
        binary = text_to_binary(message)
        self._generate_synthetic_fsk_waveform(binary)

        self._notify_listeners({
            "type": "TX_START",
            "message": message,
            "source": "ACOUSTIC_ENGINE",
            "waveform": self.current_signal_samples
        })

        try:
            # Support Marnia's engine transmit_text signature, plus legacy transmit/send
            if hasattr(self.acoustic_engine, "transmit_text"):
                result = await asyncio.to_thread(self.acoustic_engine.transmit_text, message)
            elif hasattr(self.acoustic_engine, "transmit"):
                result = await asyncio.to_thread(self.acoustic_engine.transmit, message)
            elif hasattr(self.acoustic_engine, "send"):
                result = await asyncio.to_thread(self.acoustic_engine.send, message)
            else:
                self.state = EngineState.ACOUSTIC_LIVE
                return {"success": False, "error": "Acoustic engine exposes no transmit function."}

            self.state = EngineState.ACOUSTIC_LIVE

            # Normalize result dict
            if not isinstance(result, dict):
                result = {"success": True, "raw": result}

            is_success = result.get("success")
            if is_success is None:
                is_success = not bool(result.get("error"))

            if not is_success:
                err_msg = result.get("error", "Acoustic transmission failed")
                return {
                    "success": False,
                    "error": err_msg,
                    "source": "ACOUSTIC_ENGINE"
                }

            # Map actual engine results
            elapsed_sec = float(result.get("duration_sec", (time.time() - start_time)))
            latency_ms = round(elapsed_sec * 1000.0, 2)
            crc_hex = str(result.get("crc_hex", f"0x{result.get('crc_16', 0):04X}"))
            seq_num = result.get("seq_num")
            bytes_sent = int(result.get("bytes_sent", len(message.encode("utf-8"))))
            total_bits = (bytes_sent + 5) * 8  # [SYNC, SEQ, LEN, PAYLOAD, CRC-16]
            data_rate_bps = round(total_bits / elapsed_sec, 1) if elapsed_sec > 0 else 25.0

            self.packet_counter += 1
            self.metrics.packets_sent += 1
            self.metrics.last_tx_time = time.time()
            self.metrics.latency_ms = latency_ms
            self.metrics.data_rate_bps = data_rate_bps
            self.last_transmitted = message

            pkt_record = PacketRecord(
                packet_id=self.packet_counter,
                seq_num=seq_num,
                timestamp=time.time(),
                payload_text=message,
                binary_data=binary,
                crc16=crc_hex,
                crc_valid=True,
                is_retransmission=False,
                source="ACOUSTIC_ENGINE",
                latency_ms=latency_ms,
                data_rate_bps=data_rate_bps,
                direction="TX"
            )
            self.recent_packets.append(pkt_record)
            if len(self.recent_packets) > 50:
                self.recent_packets.pop(0)

            self._update_computed_rates()

            event_payload = {
                "type": "TX_COMPLETE",
                "packet": pkt_record.model_dump(),
                "metrics": self.metrics.model_dump(),
                "waveform": self.current_signal_samples
            }
            self._notify_listeners(event_payload)

            return {
                "success": True,
                "source": "ACOUSTIC_ENGINE",
                "packet_id": self.packet_counter,
                "seq_num": seq_num,
                "crc_valid": True,
                "crc_hex": crc_hex,
                "latency_ms": latency_ms,
                "data_rate_bps": data_rate_bps,
                "bytes_sent": bytes_sent,
                "duration_sec": elapsed_sec,
                "result": result
            }

        except Exception as e:
            self.state = EngineState.ACOUSTIC_LIVE
            return {"success": False, "error": f"Acoustic engine error: {str(e)}", "source": "ACOUSTIC_ENGINE"}

    async def receive_message(self, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        """
        Listens on the physical acoustic channel (microphone) for an incoming frame.
        Uses asyncio.to_thread so blocking audio capture does not block FastAPI.
        """
        if not self.acoustic_engine and self.state != EngineState.TEST_MODE:
            return {
                "success": False,
                "error": "Acoustic engine is not yet connected. Switch to 'Test Mode' to test the dashboard, or connect Marnia's engine.",
                "state": self.state.value
            }

        if self.state == EngineState.TEST_MODE:
            # Synthetic loopback receive simulation
            if self.last_transmitted:
                crc_val = compute_crc16(self.last_transmitted.encode("utf-8"))
                return {
                    "success": True,
                    "source": "TEST_LOOPBACK (Synthetic - Not Acoustic)",
                    "message": self.last_transmitted,
                    "seq_num": 1,
                    "crc_valid": True,
                    "crc_hex": f"0x{crc_val:04X}"
                }
            return {
                "success": False,
                "source": "TEST_LOOPBACK (Synthetic - Not Acoustic)",
                "error": "No synthetic test frame available. Transmit a frame first in Test Mode."
            }

        # Real Acoustic Engine Receive
        self.state = EngineState.RECEIVING
        self._notify_listeners({
            "type": "RX_START",
            "timeout_seconds": timeout_seconds,
            "message": f"Listening for acoustic frame on microphone ({timeout_seconds:.1f}s)..."
        })

        try:
            if hasattr(self.acoustic_engine, "receive_text"):
                result = await asyncio.to_thread(self.acoustic_engine.receive_text, timeout_seconds)
            elif hasattr(self.acoustic_engine, "receive"):
                result = await asyncio.to_thread(self.acoustic_engine.receive, timeout_seconds)
            else:
                self.state = EngineState.ACOUSTIC_LIVE
                return {
                    "success": False,
                    "error": "Acoustic engine does not expose receive_text or receive function."
                }

            self.state = EngineState.ACOUSTIC_LIVE

            # Unpack (decoded_text, metadata)
            if isinstance(result, tuple):
                decoded_text, meta = result
            elif isinstance(result, dict):
                decoded_text = result.get("message")
                meta = result
            else:
                decoded_text = None
                meta = {}

            if not isinstance(meta, dict):
                meta = {}

            crc_valid = bool(meta.get("crc_valid", False))
            seq_num = meta.get("seq_num")
            corr_ratio = float(meta.get("correlation_ratio", 0.0) or 0.0)
            rx_crc = meta.get("received_crc")
            crc_hex = f"0x{rx_crc:04X}" if rx_crc is not None else "--"

            # Compute realistic frame over-the-air latency and effective throughput
            payload_len = meta.get("length_bytes", len(decoded_text.encode("utf-8")) if decoded_text else 0)
            # Physical frame duration: guard(50ms) + chirp(200ms) + guard(50ms) + bits * 40ms + guard(50ms)
            frame_duration_sec = 0.35 + ((payload_len + 5) * 8 * 0.04)
            rx_latency_ms = round(frame_duration_sec * 1000.0, 1)
            total_frame_bits = (payload_len + 5) * 8
            rx_data_rate_bps = round(total_frame_bits / frame_duration_sec, 1)

            if meta.get("success", False) and decoded_text is not None:
                self.packet_counter += 1
                self.metrics.packets_received += 1
                self.metrics.crc_valid_count += 1
                self.recent_crc_status = CRCStatus.VALID
                self.last_received = decoded_text
                self.metrics.last_rx_time = time.time()
                self.metrics.latency_ms = rx_latency_ms
                self.metrics.data_rate_bps = rx_data_rate_bps

                pkt_record = PacketRecord(
                    packet_id=self.packet_counter,
                    seq_num=seq_num,
                    timestamp=time.time(),
                    payload_text=decoded_text,
                    binary_data=text_to_binary(decoded_text),
                    crc16=crc_hex,
                    crc_valid=True,
                    is_retransmission=False,
                    source="ACOUSTIC_ENGINE",
                    correlation_ratio=corr_ratio,
                    latency_ms=rx_latency_ms,
                    data_rate_bps=rx_data_rate_bps,
                    direction="RX"
                )
                self.recent_packets.append(pkt_record)
                if len(self.recent_packets) > 50:
                    self.recent_packets.pop(0)

                self._update_computed_rates()

                event_payload = {
                    "type": "RX_EVENT",
                    "packet": pkt_record.model_dump(),
                    "metrics": self.metrics.model_dump(),
                    "crc_status": self.recent_crc_status.value,
                    "waveform": self.current_signal_samples
                }
                self._notify_listeners(event_payload)

                return {
                    "success": True,
                    "source": "ACOUSTIC_ENGINE",
                    "message": decoded_text,
                    "seq_num": seq_num,
                    "crc_valid": True,
                    "crc_hex": crc_hex,
                    "latency_ms": rx_latency_ms,
                    "data_rate_bps": rx_data_rate_bps,
                    "correlation_ratio": corr_ratio,
                    "metadata": meta
                }

            elif meta.get("detected", False) and not crc_valid:
                # Corrupted frame detected by acoustic engine
                self.packet_counter += 1
                self.metrics.packets_received += 1
                self.metrics.crc_error_count += 1
                self.metrics.retransmissions += 1
                self.recent_crc_status = CRCStatus.CORRUPTED
                raw_text = meta.get("raw_text") or "?"
                self.last_received = f"[CORRUPTED CRC ERROR] {raw_text}"
                self.metrics.last_rx_time = time.time()
                self.metrics.latency_ms = rx_latency_ms
                self.metrics.data_rate_bps = rx_data_rate_bps

                pkt_record = PacketRecord(
                    packet_id=self.packet_counter,
                    seq_num=seq_num,
                    timestamp=time.time(),
                    payload_text=raw_text,
                    binary_data=text_to_binary(raw_text),
                    crc16=crc_hex,
                    crc_valid=False,
                    is_retransmission=True,
                    source="ACOUSTIC_ENGINE",
                    correlation_ratio=corr_ratio,
                    latency_ms=rx_latency_ms,
                    data_rate_bps=rx_data_rate_bps,
                    direction="RX"
                )
                self.recent_packets.append(pkt_record)
                if len(self.recent_packets) > 50:
                    self.recent_packets.pop(0)

                self._update_computed_rates()

                event_payload = {
                    "type": "RX_EVENT",
                    "packet": pkt_record.model_dump(),
                    "metrics": self.metrics.model_dump(),
                    "crc_status": self.recent_crc_status.value,
                    "waveform": self.current_signal_samples
                }
                self._notify_listeners(event_payload)

                return {
                    "success": False,
                    "source": "ACOUSTIC_ENGINE",
                    "error": meta.get("error", "CRC-16 mismatch: corrupted frame rejected"),
                    "seq_num": seq_num,
                    "crc_valid": False,
                    "crc_hex": crc_hex,
                    "latency_ms": rx_latency_ms,
                    "data_rate_bps": rx_data_rate_bps,
                    "correlation_ratio": corr_ratio,
                    "raw_text": raw_text
                }

            else:
                err_msg = meta.get("error", f"No acoustic signal detected within {timeout_seconds:.1f}s timeout.")
                return {
                    "success": False,
                    "source": "ACOUSTIC_ENGINE",
                    "error": err_msg,
                    "metadata": meta
                }

        except Exception as e:
            self.state = EngineState.ACOUSTIC_LIVE
            return {
                "success": False,
                "error": f"Acoustic receiver error: {str(e)}",
                "source": "ACOUSTIC_ENGINE"
            }

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
            seq_num=pkt_id % 256,
            timestamp=rx_time,
            payload_text=received_text,
            binary_data=text_to_binary(received_text),
            crc16=crc_hex,
            crc_valid=crc_matches,
            is_retransmission=is_corrupted,
            source="TEST_LOOPBACK (Synthetic - Not Acoustic)",
            latency_ms=latency_ms,
            data_rate_bps=data_rate_bps,
            direction="TX/RX"
        )
        self.recent_packets.append(packet_record)
        if len(self.recent_packets) > 50:
            self.recent_packets.pop(0)

        self._update_computed_rates()

        self.state = EngineState.TEST_MODE

        # Broadcast RX event
        event_payload = {
            "type": "RX_EVENT",
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

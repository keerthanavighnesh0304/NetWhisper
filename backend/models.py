from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field
import time

class EngineState(str, Enum):
    AWAITING_ENGINE = "AWAITING_ENGINE"      # Idle, waiting for Marnia's acoustic engine
    TEST_MODE = "TEST_MODE"                  # Synthetic loopback test (explicitly marked: NOT acoustic)
    ACOUSTIC_LIVE = "ACOUSTIC_LIVE"          # Real acoustic transmission via sounddevice engine
    TRANSMITTING = "TRANSMITTING"
    RECEIVING = "RECEIVING"

class CRCStatus(str, Enum):
    IDLE = "IDLE"
    VALID = "VALID"
    CORRUPTED = "CORRUPTED"
    PENDING = "PENDING"

class PacketRecord(BaseModel):
    packet_id: int
    timestamp: float = Field(default_factory=time.time)
    payload_text: str
    binary_data: str
    crc16: str
    crc_valid: bool
    is_retransmission: bool = False
    source: str = "Awaiting Engine"          # "ACOUSTIC", "TEST_LOOPBACK (SIMULATED)", etc.
    rssi_db: Optional[float] = None          # Signal strength indicator (dB) when available from acoustic engine

class TransmissionRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="Text message to transmit")
    simulate_noise: bool = Field(default=False, description="Simulate noise corruption in test mode")

class ChannelMetrics(BaseModel):
    packets_sent: int = 0
    packets_received: int = 0
    crc_valid_count: int = 0
    crc_error_count: int = 0
    retransmissions: int = 0
    latency_ms: float = 0.0                  # Measured round-trip or transmit-decode latency
    data_rate_bps: float = 0.0               # Effective data rate in bits per second
    last_tx_time: Optional[float] = None
    last_rx_time: Optional[float] = None

class SystemStatus(BaseModel):
    project_name: str = "NetWhisper — Reliable Data Communication over an Acoustic Channel"
    state: EngineState = EngineState.AWAITING_ENGINE
    engine_connected: bool = False
    engine_name: Optional[str] = "Pending (Marnia Communication Engine)"
    metrics: ChannelMetrics = Field(default_factory=ChannelMetrics)
    last_transmitted: Optional[str] = None
    last_received: Optional[str] = None
    recent_crc_status: CRCStatus = CRCStatus.IDLE
    recent_packets: List[PacketRecord] = Field(default_factory=list)
    active_mode_label: str = "Idle — Awaiting Acoustic Engine"
    notice: str = "No acoustic transmission claims until Marnia's engine is linked."

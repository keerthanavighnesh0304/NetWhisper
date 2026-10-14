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
    seq_num: Optional[int] = None
    timestamp: float = Field(default_factory=time.time)
    payload_text: str
    binary_data: str
    crc16: str
    crc_valid: bool
    is_retransmission: bool = False
    source: str = "Awaiting Engine"          # "ACOUSTIC_ENGINE", "TEST_LOOPBACK (Synthetic - Not Acoustic)", etc.
    rssi_db: Optional[float] = None          # Signal strength indicator (dB) when available from acoustic engine
    correlation_ratio: Optional[float] = None # Preamble correlation ratio from acoustic receiver
    latency_ms: Optional[float] = None       # Measured transmission or decode latency (ms)
    data_rate_bps: Optional[float] = None    # Effective throughput (bps)
    direction: Optional[str] = "TX"          # "TX" (Outbound) or "RX" (Inbound)
    frame_type: Optional[str] = "DATA"       # "DATA", "ACK", "NACK"
    retry_count: Optional[int] = 0           # 0 for initial frame, 1, 2... for retransmissions
    is_duplicate: Optional[bool] = False     # True if received frame was suppressed as duplicate

class TransmissionRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="Text message to transmit")
    simulate_noise: bool = Field(default=False, description="Simulate noise corruption in test mode")
    enable_arq: bool = Field(default=False, description="Enable Stop-and-Wait ARQ automatic retransmission")
    max_retries: int = Field(default=2, ge=0, le=5, description="Maximum retransmission attempts")
    ack_timeout_seconds: float = Field(default=4.0, ge=0.1, le=15.0, description="Timeout waiting for ACK in seconds")
    is_retry: bool = Field(default=False, description="Explicit manual retry request")

class ReceiveRequest(BaseModel):
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=30.0, description="Duration to listen on microphone in seconds")

class ChannelMetrics(BaseModel):
    packets_sent: int = 0
    packets_received: int = 0
    crc_valid_count: int = 0
    crc_error_count: int = 0
    retransmissions: int = 0
    duplicate_packets_received: int = 0      # Duplicate frames suppressed by receiver
    successful_acks_received: int = 0        # ACKs successfully received by sender
    timeouts_count: int = 0                  # Sender timeouts waiting for ACK
    latency_ms: float = 0.0                  # Most recent measured latency
    data_rate_bps: float = 0.0               # Most recent measured throughput
    crc_error_rate: float = 0.0              # CRC Error Rate percentage (0.0 to 100.0%)
    retransmission_rate: float = 0.0         # Retransmission rate percentage (0.0 to 100.0%)
    average_latency_ms: float = 0.0          # Average latency across all recorded packets
    average_data_rate_bps: float = 0.0       # Average throughput across all recorded packets
    peak_data_rate_bps: float = 0.0          # Peak measured throughput
    last_tx_time: Optional[float] = None
    last_rx_time: Optional[float] = None

class SystemStatus(BaseModel):
    project_name: str = "NetWhisper — Reliable Data Communication over an Acoustic Channel"
    state: EngineState = EngineState.AWAITING_ENGINE
    engine_connected: bool = False
    engine_name: Optional[str] = "Pending (Marnia Communication Engine)"
    hardware_available: bool = False
    metrics: ChannelMetrics = Field(default_factory=ChannelMetrics)
    last_transmitted: Optional[str] = None
    last_received: Optional[str] = None
    recent_crc_status: CRCStatus = CRCStatus.IDLE
    recent_packets: List[PacketRecord] = Field(default_factory=list)
    active_mode_label: str = "Idle - Awaiting Acoustic Engine"
    notice: str = "No acoustic transmission claims until Marnia's engine is linked."
    last_arq_status: Optional[str] = "IDLE"

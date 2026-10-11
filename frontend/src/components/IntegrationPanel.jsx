import React from 'react';

export default function IntegrationPanel({ engineConnected, engineName, notice }) {
  return (
    <div className="card integration-card">
      <div className="card-header">
        <div className="card-title">
          <span className="dot pulse-purple"></span>
          Communication Engine Integration Contract
        </div>
        <span className={`integration-status-pill ${engineConnected ? 'connected' : 'waiting'}`}>
          {engineConnected ? 'ENGINE CONNECTED' : 'AWAITING ENGINE'}
        </span>
      </div>

      <div className="integration-content">
        <div className="roles-grid">
          <div className="role-box">
            <span className="role-tag keerthana">Keerthana</span>
            <strong>Backend, Dashboard & Telemetry</strong>
            <p>FastAPI API, WebSockets, Oscilloscope visualizer, metrics calculation, and integration adapter layer.</p>
          </div>
          <div className="role-box">
            <span className="role-tag marnia">Marnia</span>
            <strong>Acoustic Communication Engine</strong>
            <p>Binary encoding, FSK modulation/demodulation, speaker/mic audio I/O via sounddevice, and CRC error framing.</p>
          </div>
        </div>

        <div className="contract-box">
          <div className="contract-title">Integration Hook (backend/engine_adapter.py):</div>
          <pre className="code-snippet">
{`# In Marnia's acoustic engine entrypoint:
from backend.engine_adapter import engine_adapter

# Mount Marnia's engine to dashboard:
engine_adapter.register_acoustic_engine(acoustic_engine_instance)

# Interface:
# 1. acoustic_engine_instance.transmit(message: str)
# 2. engine_adapter.on_packet_received(packet_record) [optional hook]`}
          </pre>
        </div>

        <div className="integrity-notice">
          <strong>Data Integrity Note:</strong> {notice}
        </div>
      </div>
    </div>
  );
}

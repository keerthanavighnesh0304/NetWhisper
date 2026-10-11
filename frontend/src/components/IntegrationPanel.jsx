import React from 'react';

export default function IntegrationPanel({ engineConnected, engineName, notice, hardwareAvailable }) {
  return (
    <div className="card integration-card">
      <div className="card-header">
        <div className="card-title">
          <span className="dot pulse-purple"></span>
          Communication Engine Integration Contract (fsk_engine.py)
        </div>
        <span className={`integration-status-pill ${engineConnected ? 'connected' : 'waiting'}`}>
          {engineConnected ? (hardwareAvailable ? 'ACOUSTIC LIVE' : 'ENGINE CONNECTED') : 'AWAITING ENGINE'}
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
            <p>Binary encoding, Continuous-Phase FSK (1800/2400 Hz), Chirp preamble matched filtering, and CRC-16 framing.</p>
          </div>
        </div>

        <div className="contract-box">
          <div className="contract-title">Integration Hook (backend/engine_adapter.py):</div>
          <pre className="code-snippet">
{`# Mounted Marnia's engine module to dashboard adapter:
import fsk_engine
from backend.engine_adapter import engine_adapter

engine_adapter.register_acoustic_engine(fsk_engine)

# Active Function Signatures:
# 1. fsk_engine.transmit_text(message: str, seq_num=None) -> dict
# 2. fsk_engine.receive_text(timeout_seconds=10.0) -> (message, meta)
# 3. fsk_engine.get_stats() -> dict`}
          </pre>
        </div>

        <div className="integrity-notice">
          <strong>Data Integrity Note:</strong> {notice}
        </div>
      </div>
    </div>
  );
}

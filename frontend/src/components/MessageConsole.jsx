import React, { useState } from 'react';

export default function MessageConsole({
  lastTransmitted,
  lastReceived,
  recentCrcStatus,
  onTransmit,
  isTransmitting,
  isTestMode,
  engineConnected
}) {
  const [inputText, setInputText] = useState('NetWhisper Packet #1');
  const [simulateNoise, setSimulateNoise] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    onTransmit(inputText.trim(), simulateNoise);
  };

  const setPreset = (msg) => {
    setInputText(msg);
  };

  const canTransmit = isTestMode || engineConnected;

  return (
    <div className="console-grid">
      {/* Transmit Console */}
      <div className="card console-card">
        <div className="card-header">
          <div className="card-title">
            <span className="dot tx-dot"></span>
            Transmitter (TX)
          </div>
          <span className="channel-tag">FSK Modulator</span>
        </div>

        <form onSubmit={handleSubmit} className="tx-form">
          <div className="input-group">
            <label htmlFor="tx-message-input">Message to transmit:</label>
            <input
              id="tx-message-input"
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Enter message to transmit..."
              maxLength={200}
              className="text-input"
            />
          </div>

          <div className="presets-row">
            <span className="presets-label">Presets:</span>
            <button type="button" className="preset-btn" onClick={() => setPreset('HELLO NETWHISPER')}>HELLO</button>
            <button type="button" className="preset-btn" onClick={() => setPreset('SYNC 0xAA')}>SYNC</button>
            <button type="button" className="preset-btn" onClick={() => setPreset('ACK_SEQ_101')}>ACK_101</button>
            <button type="button" className="preset-btn" onClick={() => setPreset('CN_LAB_ACOUSTIC')}>CN_LAB</button>
          </div>

          {isTestMode && (
            <div className="noise-toggle-row">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  id="simulate-noise-checkbox"
                  checked={simulateNoise}
                  onChange={(e) => setSimulateNoise(e.target.checked)}
                />
                <span>Simulate Acoustic Noise / Bit Inversion (Triggers CRC Error)</span>
              </label>
            </div>
          )}

          <div className="tx-actions">
            <button
              type="submit"
              disabled={isTransmitting || !canTransmit || !inputText.trim()}
              className="btn btn-primary"
              id="transmit-submit-button"
            >
              {isTransmitting ? 'Transmitting Audio...' : 'Transmit Frame (TX)'}
            </button>
            {!canTransmit && (
              <span className="warning-hint">
                Switch to <strong>Test Mode</strong> or connect acoustic engine to transmit.
              </span>
            )}
          </div>
        </form>

        <div className="tx-display">
          <div className="display-header">Last Transmitted Message:</div>
          <div className="display-box font-mono" id="last-transmitted-display">
            {lastTransmitted || <span className="empty-text">No transmission recorded yet</span>}
          </div>
        </div>
      </div>

      {/* Receiver Console */}
      <div className="card console-card">
        <div className="card-header">
          <div className="card-title">
            <span className="dot rx-dot"></span>
            Receiver (RX)
          </div>
          <span className="channel-tag">FSK Demodulator + CRC</span>
        </div>

        <div className="rx-display-section">
          <div className="display-header">Reconstructed Message:</div>
          <div className={`display-box rx-box font-mono ${recentCrcStatus === 'CORRUPTED' ? 'corrupted' : ''}`} id="last-received-display">
            {lastReceived ? (
              <div>{lastReceived}</div>
            ) : (
              <span className="empty-text">Listening for incoming acoustic frames...</span>
            )}
          </div>
        </div>

        <div className="crc-verification-box">
          <div className="crc-header">
            <span>Frame Integrity Check</span>
            <span className={`crc-pill ${recentCrcStatus.toLowerCase()}`}>
              CRC-16: {recentCrcStatus}
            </span>
          </div>
          <p className="crc-explanation">
            {recentCrcStatus === 'VALID' && '✓ CRC-16 checksum matched payload. Frame accepted without error.'}
            {recentCrcStatus === 'CORRUPTED' && '✗ CRC-16 checksum mismatch detected! Frame discarded / Retransmission requested.'}
            {recentCrcStatus === 'IDLE' && 'No frame received yet. Waiting for acoustic or test carrier.'}
          </p>
        </div>
      </div>
    </div>
  );
}

import React, { useState } from 'react';

export default function MessageConsole({
  lastTransmitted,
  lastReceived,
  recentCrcStatus,
  onTransmit,
  onReceive,
  isTransmitting,
  isReceiving,
  isTestMode,
  engineConnected,
  hardwareAvailable
}) {
  const [inputText, setInputText] = useState('NetWhisper Packet #1');
  const [simulateNoise, setSimulateNoise] = useState(false);
  const [enableArq, setEnableArq] = useState(false);
  const [rxTimeout, setRxTimeout] = useState(10);

  const handleSubmitTx = (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    onTransmit(inputText.trim(), simulateNoise, enableArq);
  };

  const handleTriggerRx = () => {
    if (onReceive) {
      onReceive(rxTimeout);
    }
  };

  const setPreset = (msg) => {
    setInputText(msg);
  };

  const canTransmit = isTestMode || engineConnected;
  const canReceive = isTestMode || engineConnected;

  return (
    <div className="console-grid">
      {/* Transmit Console */}
      <div className="card console-card">
        <div className="card-header">
          <div className="card-title">
            <span className="dot tx-dot"></span>
            Transmitter (TX)
          </div>
          <span className="channel-tag">CPFSK Modulator</span>
        </div>

        <form onSubmit={handleSubmitTx} className="tx-form">
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
            <button type="button" className="preset-btn" onClick={() => setPreset('SYNC 0xAC')}>SYNC</button>
            <button type="button" className="preset-btn" onClick={() => setPreset('ACK:1')}>ACK:1</button>
            <button type="button" className="preset-btn" onClick={() => setPreset('NETWHISPER ACOUSTIC LINK')}>NETWHISPER</button>
          </div>

          <div className="arq-toggle-row">
            <label className="checkbox-label arq-label">
              <input
                type="checkbox"
                id="enable-arq-checkbox"
                checked={enableArq}
                onChange={(e) => setEnableArq(e.target.checked)}
              />
              <span>Stop-and-Wait ARQ (Auto-Retry on Timeout / Corrupt Frame)</span>
            </label>
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
          <span className="channel-tag">CPFSK Demodulator + Matched Filter</span>
        </div>

        <div className="rx-controls-row">
          <div className="timeout-selector">
            <label htmlFor="rx-timeout-select">Listen Timeout:</label>
            <select
              id="rx-timeout-select"
              value={rxTimeout}
              onChange={(e) => setRxTimeout(Number(e.target.value))}
              disabled={isReceiving}
              className="preset-btn"
            >
              <option value={5}>5 seconds</option>
              <option value={10}>10 seconds</option>
              <option value={15}>15 seconds</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleTriggerRx}
            disabled={isReceiving || !canReceive}
            className="btn btn-outline-cyan"
            id="receive-submit-button"
          >
            {isReceiving ? 'Listening on Microphone...' : 'Listen / Capture Frame (RX)'}
          </button>
        </div>

        <div className="rx-display-section">
          <div className="display-header">Reconstructed Message:</div>
          <div
            className={`display-box rx-box font-mono ${recentCrcStatus === 'CORRUPTED' ? 'corrupted' : ''}`}
            id="last-received-display"
          >
            {isReceiving ? (
              <span className="listening-pulse">Listening for acoustic chirp preamble ({rxTimeout}s)...</span>
            ) : lastReceived ? (
              <div>{lastReceived}</div>
            ) : (
              <span className="empty-text">Awaiting incoming acoustic frame...</span>
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

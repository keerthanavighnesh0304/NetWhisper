import React, { useState, useEffect, useRef } from 'react';
import WaveformCanvas from './components/WaveformCanvas';
import MetricsGrid from './components/MetricsGrid';
import MessageConsole from './components/MessageConsole';
import PacketHistoryTable from './components/PacketHistoryTable';
import IntegrationPanel from './components/IntegrationPanel';
import './App.css';

export default function App() {
  const [status, setStatus] = useState({
    project_name: 'NetWhisper — Reliable Data Communication over an Acoustic Channel',
    state: 'AWAITING_ENGINE',
    engine_connected: false,
    engine_name: 'Pending (Marnia Communication Engine)',
    hardware_available: false,
    metrics: {
      packets_sent: 0,
      packets_received: 0,
      crc_valid_count: 0,
      crc_error_count: 0,
      retransmissions: 0,
      latency_ms: 0.0,
      data_rate_bps: 0.0,
    },
    last_transmitted: null,
    last_received: null,
    recent_crc_status: 'IDLE',
    recent_packets: [],
    active_mode_label: 'Idle — Awaiting Acoustic Engine',
    notice: 'No acoustic transmission claims until Marnia engine is linked.',
  });

  const [waveformData, setWaveformData] = useState(new Array(128).fill(0));
  const [wsConnected, setWsConnected] = useState(false);
  const [isTransmitting, setIsTransmitting] = useState(false);
  const [isReceiving, setIsReceiving] = useState(false);
  const [notification, setNotification] = useState(null);

  const wsRef = useRef(null);
  const isTestMode = status.state === 'TEST_MODE';

  // Show temporary toast notification
  const notify = (msg, type = 'info') => {
    setNotification({ msg, type });
    setTimeout(() => setNotification(null), 4000);
  };

  // Fetch initial REST status
  const loadStatus = async () => {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (err) {
      console.warn('Initial REST status fetch error:', err);
    }
  };

  // Setup WebSocket connection
  useEffect(() => {
    loadStatus();

    let wsUrl = '';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    if (window.location.port === '5173') {
      wsUrl = `${protocol}//${window.location.hostname}:8000/ws`;
    } else {
      wsUrl = `${protocol}//${window.location.host}/ws`;
    }

    let socket;
    let reconnectTimer;

    const connectWs = () => {
      try {
        socket = new WebSocket(wsUrl);
        wsRef.current = socket;

        socket.onopen = () => {
          setWsConnected(true);
        };

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'INITIAL_STATE') {
              setStatus(data.status);
              if (data.waveform) setWaveformData(data.waveform);
            } else if (data.type === 'STATUS_UPDATE' || data.type === 'METRICS_RESET') {
              setStatus(data.status);
              if (data.waveform) setWaveformData(data.waveform);
            } else if (data.type === 'TX_START') {
              setIsTransmitting(true);
              if (data.waveform) setWaveformData(data.waveform);
            } else if (data.type === 'RX_START') {
              setIsReceiving(true);
            } else if (data.type === 'TX_COMPLETE') {
              setIsTransmitting(false);
              setStatus((prev) => ({
                ...prev,
                metrics: data.metrics,
                last_transmitted: data.packet ? data.packet.payload_text : prev.last_transmitted,
                recent_packets: data.packet
                  ? [...prev.recent_packets.slice(-49), data.packet]
                  : prev.recent_packets,
              }));
              if (data.waveform) setWaveformData(data.waveform);
            } else if (data.type === 'RX_EVENT' || data.type === 'PACKET_EVENT') {
              setIsTransmitting(false);
              setIsReceiving(false);
              setStatus((prev) => ({
                ...prev,
                metrics: data.metrics,
                recent_crc_status: data.crc_status ?? prev.recent_crc_status,
                last_received: data.packet ? data.packet.payload_text : prev.last_received,
                last_transmitted: data.packet?.source?.includes('Synthetic')
                  ? data.packet.payload_text
                  : prev.last_transmitted,
                recent_packets: data.packet
                  ? [...prev.recent_packets.slice(-49), data.packet]
                  : prev.recent_packets,
              }));
              if (data.waveform) setWaveformData(data.waveform);
            } else if (data.type === 'ENGINE_CONNECTED') {
              notify(data.message, 'success');
              loadStatus();
            }
          } catch (e) {
            console.error('Failed to parse WS message:', e);
          }
        };

        socket.onclose = () => {
          setWsConnected(false);
          reconnectTimer = setTimeout(connectWs, 2500);
        };

        socket.onerror = () => {
          setWsConnected(false);
        };
      } catch (err) {
        console.error('WS Connection error:', err);
        reconnectTimer = setTimeout(connectWs, 2500);
      }
    };

    connectWs();

    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) socket.close();
    };
  }, []);

  // Transmit action
  const handleTransmit = async (message, simulateNoise) => {
    setIsTransmitting(true);
    try {
      const res = await fetch('/api/transmit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, simulate_noise: simulateNoise }),
      });
      const data = await res.json();
      if (!res.ok) {
        notify(data.detail || 'Transmission failed', 'error');
        setIsTransmitting(false);
      } else {
        notify(
          `Packet #${data.packet_id} transmitted (${data.crc_valid ? 'CRC OK' : 'CRC Error Detected'})`,
          data.crc_valid ? 'success' : 'warning'
        );
      }
    } catch (err) {
      notify('Failed to reach backend API', 'error');
      setIsTransmitting(false);
    }
  };

  // Receive / Listen action
  const handleReceive = async (timeoutSeconds = 10) => {
    setIsReceiving(true);
    notify(`Listening on microphone for ${timeoutSeconds}s...`, 'info');
    try {
      const res = await fetch('/api/receive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeout_seconds: timeoutSeconds }),
      });
      const data = await res.json();
      setIsReceiving(false);
      if (data.success) {
        notify(`Frame received (Seq ${data.seq_num}): "${data.message}"`, 'success');
      } else {
        notify(data.error || 'No valid acoustic frame detected', 'warning');
      }
      loadStatus();
    } catch (err) {
      notify('Receive request failed', 'error');
      setIsReceiving(false);
    }
  };

  // Toggle Mode (Idle vs Test Mode)
  const handleToggleMode = async () => {
    try {
      const nextTestMode = !isTestMode;
      const res = await fetch('/api/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_mode: nextTestMode }),
      });
      if (res.ok) {
        notify(
          nextTestMode
            ? 'Test Mode Enabled: Synthetic loopback active (labeled explicitly as simulation).'
            : 'Idle Mode: Waiting for Marnia\'s acoustic engine.',
          'info'
        );
        loadStatus();
      }
    } catch (err) {
      notify('Failed to switch mode', 'error');
    }
  };

  // Reset Metrics
  const handleReset = async () => {
    try {
      const res = await fetch('/api/reset', { method: 'POST' });
      if (res.ok) {
        notify('Metrics and packet log cleared', 'info');
        loadStatus();
      }
    } catch (err) {
      notify('Failed to reset metrics', 'error');
    }
  };

  return (
    <div className="dashboard-container">
      {/* Toast Notification */}
      {notification && (
        <div className={`toast toast-${notification.type}`}>
          {notification.msg}
        </div>
      )}

      {/* Header */}
      <header className="dashboard-header">
        <div className="header-brand">
          <div className="badge-logo font-mono">NW-01</div>
          <div>
            <h1 className="project-title">
              NetWhisper — Reliable Data Communication over an Acoustic Channel
            </h1>
            <p className="project-subtitle">
              Computer Networks Academic Project | Real-Time Physical & Telemetry Monitor
            </p>
          </div>
        </div>

        <div className="header-controls">
          {/* WebSocket status */}
          <div className="ws-indicator" title={wsConnected ? 'WebSocket Live' : 'WebSocket Disconnected'}>
            <span className={`status-dot ${wsConnected ? 'live' : 'offline'}`}></span>
            <span className="ws-label">{wsConnected ? 'LIVE STREAM' : 'OFFLINE'}</span>
          </div>

          {/* Mode Badge */}
          <div className={`mode-badge ${isTestMode ? 'badge-test' : (status.engine_connected ? 'badge-live' : 'badge-idle')}`}>
            {status.active_mode_label}
          </div>

          {/* Mode Switch Button */}
          <button
            onClick={handleToggleMode}
            className={`btn ${isTestMode ? 'btn-outline-amber' : 'btn-outline-cyan'}`}
            id="toggle-mode-button"
          >
            {isTestMode ? 'Exit Test Mode (Go Idle)' : 'Enable Test Loopback Mode'}
          </button>

          {/* Reset Button */}
          <button onClick={handleReset} className="btn btn-outline" id="reset-button">
            Reset Stats
          </button>
        </div>
      </header>

      {/* Data Integrity Banner */}
      <div className={`integrity-banner ${isTestMode ? 'banner-test' : 'banner-idle'}`}>
        <span className="banner-icon">ℹ</span>
        <span>
          <strong>Academic Data Integrity: </strong>
          {status.notice}
        </span>
      </div>

      {/* Main Grid */}
      <main className="dashboard-body">
        {/* Metric Cards Row */}
        <MetricsGrid
          metrics={status.metrics}
          crcStatus={status.recent_crc_status}
          engineConnected={status.engine_connected}
          isTestMode={isTestMode}
        />

        {/* Oscilloscope Waveform Row */}
        <WaveformCanvas
          waveformData={waveformData}
          isTransmitting={isTransmitting}
          modeLabel={status.active_mode_label}
        />

        {/* Message TX & RX Console */}
        <MessageConsole
          lastTransmitted={status.last_transmitted}
          lastReceived={status.last_received}
          recentCrcStatus={status.recent_crc_status}
          onTransmit={handleTransmit}
          onReceive={handleReceive}
          isTransmitting={isTransmitting}
          isReceiving={isReceiving}
          isTestMode={isTestMode}
          engineConnected={status.engine_connected}
          hardwareAvailable={status.hardware_available}
        />

        {/* Packet Log & History */}
        <PacketHistoryTable packets={status.recent_packets} />

        {/* Teammate Integration Contract Box */}
        <IntegrationPanel
          engineConnected={status.engine_connected}
          engineName={status.engine_name}
          notice={status.notice}
          hardwareAvailable={status.hardware_available}
        />
      </main>

      {/* Footer */}
      <footer className="dashboard-footer">
        <div>
          <span>NetWhisper</span> • Department of Computer Networks • Acoustic Channel Physical Layer Protocol
        </div>
        <div>
          Team: Keerthana (Backend & Dashboard) & Marnia (Acoustic Communication Engine)
        </div>
      </footer>
    </div>
  );
}

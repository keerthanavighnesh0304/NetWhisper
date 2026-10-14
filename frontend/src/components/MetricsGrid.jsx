import React from 'react';

export default function MetricsGrid({ metrics = {}, crcStatus = 'IDLE', engineConnected = false, isTestMode = false }) {
  const getCrcBadgeClass = () => {
    switch (crcStatus) {
      case 'VALID':
        return 'badge-success';
      case 'CORRUPTED':
        return 'badge-error';
      case 'PENDING':
        return 'badge-warning';
      default:
        return 'badge-idle';
    }
  };

  const totalCrcChecked = (metrics.crc_valid_count || 0) + (metrics.crc_error_count || 0);
  const crcErrorRate = metrics.crc_error_rate !== undefined
    ? metrics.crc_error_rate
    : (totalCrcChecked > 0 ? ((metrics.crc_error_count || 0) / totalCrcChecked) * 100 : 0);

  const retransRate = metrics.retransmission_rate !== undefined
    ? metrics.retransmission_rate
    : (metrics.packets_sent > 0 ? ((metrics.retransmissions || 0) / metrics.packets_sent) * 100 : 0);

  return (
    <div className="metrics-grid">
      {/* 1. Packets Sent & Received */}
      <div className="metric-card">
        <div className="metric-header-row">
          <span className="metric-label">Packets (TX / RX)</span>
          <span className="metric-tag font-mono">L2 Framing</span>
        </div>
        <div className="metric-value font-mono">
          <span className="tx-count" title="Transmitted Packets">{metrics.packets_sent || 0}</span>
          <span className="separator">/</span>
          <span className="rx-count" title="Received Packets">{metrics.packets_received || 0}</span>
        </div>
        <div className="metric-subtext">
          <span>TX Sent: <strong className="text-cyan">{metrics.packets_sent || 0}</strong></span>
          <span className="bullet-sep">•</span>
          <span>RX Recv: <strong className="text-emerald">{metrics.packets_received || 0}</strong></span>
        </div>
      </div>

      {/* 2. CRC-16 Frame Integrity & Packet Loss */}
      <div className="metric-card">
        <div className="metric-header-row">
          <span className="metric-label">CRC-16 Integrity & Loss</span>
          <span className="metric-tag font-mono">CCITT-0x1021</span>
        </div>
        <div className="metric-value">
          <span className={`status-badge ${getCrcBadgeClass()}`}>
            {crcStatus || 'IDLE'}
          </span>
          <span className={`metric-rate-chip font-mono ${crcErrorRate > 0 ? 'chip-error' : 'chip-good'}`}>
            {totalCrcChecked > 0 ? `${crcErrorRate.toFixed(1)}% FER` : '0.0% FER'}
          </span>
        </div>
        <div className="metric-subtext font-mono">
          Valid: <span className="text-emerald">{metrics.crc_valid_count || 0}</span> | Corrupted (Dropped): <span className="text-rose">{metrics.crc_error_count || 0}</span>
        </div>
      </div>

      {/* 3. Retransmissions (Manual ARQ on Simplex Acoustic Link) */}
      <div className="metric-card">
        <div className="metric-header-row">
          <span className="metric-label">Retransmissions</span>
          <span className="metric-tag font-mono">Manual ARQ</span>
        </div>
        <div className="metric-value font-mono text-amber">
          {metrics.retransmissions || 0}
          <span className="metric-rate-chip chip-amber font-mono">
            {retransRate.toFixed(1)}%
          </span>
        </div>
        <div className="metric-subtext font-mono text-small">
          {isTestMode
            ? `Synthetic retry count: ${retransRate.toFixed(1)}%`
            : (engineConnected
                ? (metrics.retransmissions > 0
                    ? `Manual retries: ${metrics.retransmissions} (Simplex: no auto-ARQ)`
                    : 'Simplex physical link: No automated ARQ over air')
                : 'Awaiting acoustic engine')}
        </div>
      </div>

      {/* 4. Transmission Latency / Duration */}
      <div className="metric-card">
        <div className="metric-header-row">
          <span className="metric-label">Transmission Duration</span>
          <span className="metric-tag font-mono">Air / Playback</span>
        </div>
        <div className="metric-value font-mono text-cyan">
          {metrics.latency_ms > 0 ? `${metrics.latency_ms.toFixed(1)} ms` : '--'}
        </div>
        <div className="metric-subtext font-mono text-small">
          {metrics.average_latency_ms > 0 ? (
            <span>Avg: <strong className="text-main">{metrics.average_latency_ms.toFixed(1)} ms</strong> (TX playback / RX air-time)</span>
          ) : (
            <span>{isTestMode ? 'Loopback round-trip' : (engineConnected ? 'TX: Soundcard playback | RX: Acoustic air-time' : 'Awaiting engine')}</span>
          )}
        </div>
      </div>

      {/* 5. Effective Throughput */}
      <div className="metric-card">
        <div className="metric-header-row">
          <span className="metric-label">Effective Throughput</span>
          <span className="metric-tag font-mono">25 bps Baud</span>
        </div>
        <div className="metric-value font-mono text-emerald">
          {metrics.data_rate_bps > 0 ? `${metrics.data_rate_bps.toFixed(1)} bps` : '--'}
        </div>
        <div className="metric-subtext font-mono text-small">
          {metrics.peak_data_rate_bps > 0 ? (
            <span>Peak: <strong className="text-emerald">{metrics.peak_data_rate_bps.toFixed(1)} bps</strong> | Avg: <strong className="text-main">{(metrics.average_data_rate_bps || metrics.data_rate_bps).toFixed(1)} bps</strong></span>
          ) : (
            <span>FSK modulated channel throughput (25 bps baud)</span>
          )}
        </div>
      </div>
    </div>
  );
}

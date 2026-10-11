import React from 'react';

export default function MetricsGrid({ metrics, crcStatus, engineConnected, isTestMode }) {
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

  return (
    <div className="metrics-grid">
      {/* Packets */}
      <div className="metric-card">
        <div className="metric-label">Packets (TX / RX)</div>
        <div className="metric-value font-mono">
          <span className="tx-count">{metrics.packets_sent || 0}</span>
          <span className="separator">/</span>
          <span className="rx-count">{metrics.packets_received || 0}</span>
        </div>
        <div className="metric-subtext">
          Sent: {metrics.packets_sent || 0} | Received: {metrics.packets_received || 0}
        </div>
      </div>

      {/* CRC Error Detection */}
      <div className="metric-card">
        <div className="metric-label">CRC-16 Status</div>
        <div className="metric-value">
          <span className={`status-badge ${getCrcBadgeClass()}`}>
            {crcStatus || 'IDLE'}
          </span>
        </div>
        <div className="metric-subtext font-mono">
          Valid: <span className="text-emerald">{metrics.crc_valid_count || 0}</span> | Errors: <span className="text-rose">{metrics.crc_error_count || 0}</span>
        </div>
      </div>

      {/* Retransmissions & Errors */}
      <div className="metric-card">
        <div className="metric-label">Errors & Retransmissions</div>
        <div className="metric-value font-mono text-amber">
          {metrics.retransmissions || 0}
        </div>
        <div className="metric-subtext">
          Loss / Retransmit rate: {
            metrics.packets_sent > 0
              ? `${Math.round(((metrics.retransmissions || 0) / metrics.packets_sent) * 100)}%`
              : '0%'
          }
        </div>
      </div>

      {/* Measured Latency */}
      <div className="metric-card">
        <div className="metric-label">Channel Latency</div>
        <div className="metric-value font-mono text-cyan">
          {metrics.latency_ms > 0 ? `${metrics.latency_ms.toFixed(1)} ms` : '--'}
        </div>
        <div className="metric-subtext">
          {isTestMode ? 'Loopback round-trip' : (engineConnected ? 'Acoustic transit time' : 'Awaiting engine')}
        </div>
      </div>

      {/* Effective Data Rate */}
      <div className="metric-card">
        <div className="metric-label">Effective Data Rate</div>
        <div className="metric-value font-mono text-emerald">
          {metrics.data_rate_bps > 0 ? `${metrics.data_rate_bps.toFixed(0)} bps` : '--'}
        </div>
        <div className="metric-subtext">
          FSK physical channel throughput
        </div>
      </div>
    </div>
  );
}

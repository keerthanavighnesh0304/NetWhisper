import React, { useState } from 'react';

export default function PerformanceChart({ packets = [], metrics = {}, wsConnected = true }) {
  const [activeView, setActiveView] = useState('all'); // 'all', 'throughput', 'latency'
  const [hoveredPoint, setHoveredPoint] = useState(null);

  // Filter packets that have telemetry data
  const dataPoints = packets.filter(
    (p) => (p.data_rate_bps !== null && p.data_rate_bps !== undefined) ||
           (p.latency_ms !== null && p.latency_ms !== undefined)
  );

  // Chart Dimensions
  const svgWidth = 840;
  const svgHeight = 220;
  const padding = { top: 25, right: 60, bottom: 35, left: 60 };
  const innerWidth = svgWidth - padding.left - padding.right;
  const innerHeight = svgHeight - padding.top - padding.bottom;

  // Compute Scales
  const throughputValues = dataPoints.map((p) => p.data_rate_bps || 0);
  const latencyValues = dataPoints.map((p) => p.latency_ms || 0);

  const maxThroughput = Math.max(30, Math.ceil((Math.max(...throughputValues, 25) * 1.25) / 10) * 10);
  const maxLatency = Math.max(500, Math.ceil((Math.max(...latencyValues, 200) * 1.25) / 100) * 100);

  const getX = (index) => {
    if (dataPoints.length <= 1) return padding.left + innerWidth / 2;
    return padding.left + (index / (dataPoints.length - 1)) * innerWidth;
  };

  const getYThroughput = (val) => {
    return padding.top + innerHeight - (Math.min(val, maxThroughput) / maxThroughput) * innerHeight;
  };

  const getYLatency = (val) => {
    return padding.top + innerHeight - (Math.min(val, maxLatency) / maxLatency) * innerHeight;
  };

  // SVG Paths
  const buildPath = (values, getYFn) => {
    if (values.length === 0) return '';
    return values
      .map((val, idx) => `${idx === 0 ? 'M' : 'L'} ${getX(idx).toFixed(1)} ${getYFn(val).toFixed(1)}`)
      .join(' ');
  };

  const buildAreaPath = (values, getYFn) => {
    if (values.length === 0) return '';
    const linePath = buildPath(values, getYFn);
    const lastX = getX(values.length - 1).toFixed(1);
    const firstX = getX(0).toFixed(1);
    const bottomY = (padding.top + innerHeight).toFixed(1);
    return `${linePath} L ${lastX} ${bottomY} L ${firstX} ${bottomY} Z`;
  };

  const throughputLine = buildPath(throughputValues, getYThroughput);
  const throughputArea = buildAreaPath(throughputValues, getYThroughput);

  const latencyLine = buildPath(latencyValues, getYLatency);
  const latencyArea = buildAreaPath(latencyValues, getYLatency);

  return (
    <div className="card performance-analytics-card">
      <div className="card-header">
        <div className="card-title">
          <span className="dot pulse-emerald"></span>
          Network Performance Analytics
          <span className="analytics-subtitle font-mono">Real-time Throughput & Latency</span>
        </div>

        <div className="analytics-controls">
          <div className="chart-view-toggle">
            <button
              type="button"
              className={`toggle-btn ${activeView === 'all' ? 'active' : ''}`}
              onClick={() => setActiveView('all')}
            >
              Dual-Metric
            </button>
            <button
              type="button"
              className={`toggle-btn ${activeView === 'throughput' ? 'active' : ''}`}
              onClick={() => setActiveView('throughput')}
            >
              Throughput (bps)
            </button>
            <button
              type="button"
              className={`toggle-btn ${activeView === 'latency' ? 'active' : ''}`}
              onClick={() => setActiveView('latency')}
            >
              Latency (ms)
            </button>
          </div>
          {!wsConnected && (
            <span className="badge-offline-notice" title="WebSocket disconnected">
              Stream Paused
            </span>
          )}
        </div>
      </div>

      {/* KPI Summary Ribbon */}
      <div className="kpi-ribbon">
        <div className="kpi-item">
          <span className="kpi-label">Avg Throughput</span>
          <span className="kpi-value font-mono text-emerald">
            {metrics.average_data_rate_bps > 0 ? `${metrics.average_data_rate_bps.toFixed(1)} bps` : '--'}
          </span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">Peak Throughput</span>
          <span className="kpi-value font-mono text-emerald">
            {metrics.peak_data_rate_bps > 0 ? `${metrics.peak_data_rate_bps.toFixed(1)} bps` : '--'}
          </span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">Avg Latency</span>
          <span className="kpi-value font-mono text-cyan">
            {metrics.average_latency_ms > 0 ? `${metrics.average_latency_ms.toFixed(1)} ms` : '--'}
          </span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">CRC Frame Error Rate</span>
          <span className={`kpi-value font-mono ${metrics.crc_error_rate > 0 ? 'text-rose' : 'text-emerald'}`}>
            {metrics.crc_valid_count + metrics.crc_error_count > 0 ? `${metrics.crc_error_rate.toFixed(1)}%` : '0.0%'}
          </span>
        </div>
        <div className="kpi-item">
          <span className="kpi-label">Retransmissions</span>
          <span className="kpi-value font-mono text-amber">
            {metrics.retransmissions > 0 ? `${metrics.retransmissions} (Manual)` : '0 (Simplex link)'}
          </span>
        </div>
      </div>

      {/* SVG Chart or Empty State */}
      <div className="chart-wrapper">
        {dataPoints.length === 0 ? (
          <div className="chart-empty-state">
            <div className="empty-icon font-mono">~ ~ ~</div>
            <p className="empty-title">Awaiting Telemetry Samples</p>
            <p className="empty-desc">
              Transmit a frame or listen on microphone for incoming acoustic packets to render live throughput and latency curves.
            </p>
          </div>
        ) : (
          <div className="svg-container">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              className="performance-svg"
              onMouseLeave={() => setHoveredPoint(null)}
            >
              <defs>
                <linearGradient id="throughputGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
                </linearGradient>
                <linearGradient id="latencyGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.02" />
                </linearGradient>
              </defs>

              {/* Grid Lines */}
              {[0, 0.25, 0.5, 0.75, 1].map((pct, idx) => {
                const y = padding.top + innerHeight * (1 - pct);
                return (
                  <g key={`grid-${idx}`}>
                    <line
                      x1={padding.left}
                      y1={y}
                      x2={svgWidth - padding.right}
                      y2={y}
                      stroke="rgba(255, 255, 255, 0.07)"
                      strokeDasharray="4 4"
                    />
                    {/* Left Y-axis label: Throughput */}
                    {(activeView === 'all' || activeView === 'throughput') && (
                      <text
                        x={padding.left - 8}
                        y={y + 4}
                        fill="#10b981"
                        fontSize="10"
                        fontFamily="monospace"
                        textAnchor="end"
                      >
                        {Math.round(maxThroughput * pct)}
                      </text>
                    )}
                    {/* Right Y-axis label: Latency */}
                    {(activeView === 'all' || activeView === 'latency') && (
                      <text
                        x={svgWidth - padding.right + 8}
                        y={y + 4}
                        fill="#06b6d4"
                        fontSize="10"
                        fontFamily="monospace"
                        textAnchor="start"
                      >
                        {Math.round(maxLatency * pct)}
                      </text>
                    )}
                  </g>
                );
              })}

              {/* Y-Axis Units */}
              {(activeView === 'all' || activeView === 'throughput') && (
                <text
                  x={padding.left - 8}
                  y={padding.top - 8}
                  fill="#10b981"
                  fontSize="9"
                  fontFamily="sans-serif"
                  fontWeight="600"
                  textAnchor="end"
                >
                  bps (TX/RX)
                </text>
              )}
              {(activeView === 'all' || activeView === 'latency') && (
                <text
                  x={svgWidth - padding.right + 8}
                  y={padding.top - 8}
                  fill="#06b6d4"
                  fontSize="9"
                  fontFamily="sans-serif"
                  fontWeight="600"
                  textAnchor="start"
                >
                  ms (Latency)
                </text>
              )}

              {/* Areas & Lines */}
              {(activeView === 'all' || activeView === 'throughput') && throughputArea && (
                <path d={throughputArea} fill="url(#throughputGradient)" />
              )}
              {(activeView === 'all' || activeView === 'latency') && latencyArea && (
                <path d={latencyArea} fill="url(#latencyGradient)" />
              )}

              {(activeView === 'all' || activeView === 'throughput') && throughputLine && (
                <path
                  d={throughputLine}
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {(activeView === 'all' || activeView === 'latency') && latencyLine && (
                <path
                  d={latencyLine}
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth="2.2"
                  strokeDasharray={activeView === 'all' ? '5 3' : 'none'}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {/* Data Point Dots & Hover Targets */}
              {dataPoints.map((pkt, idx) => {
                const cx = getX(idx);
                const cyRate = getYThroughput(pkt.data_rate_bps || 0);
                const cyLat = getYLatency(pkt.latency_ms || 0);
                const isCorrupted = !pkt.crc_valid;

                return (
                  <g key={`point-group-${pkt.packet_id || idx}`}>
                    {/* X-axis labels */}
                    <text
                      x={cx}
                      y={svgHeight - padding.bottom + 16}
                      fill="#64748b"
                      fontSize="9"
                      fontFamily="monospace"
                      textAnchor="middle"
                    >
                      {pkt.seq_num !== null && pkt.seq_num !== undefined ? `Seq ${pkt.seq_num}` : `#${pkt.packet_id}`}
                    </text>

                    {/* Throughput Dot */}
                    {(activeView === 'all' || activeView === 'throughput') && (
                      <circle
                        cx={cx}
                        cy={cyRate}
                        r={isCorrupted ? 5 : 4}
                        fill={isCorrupted ? '#f43f5e' : '#10b981'}
                        stroke="#090d16"
                        strokeWidth="2"
                        className="chart-dot"
                      />
                    )}

                    {/* Latency Dot */}
                    {(activeView === 'all' || activeView === 'latency') && (
                      <circle
                        cx={cx}
                        cy={cyLat}
                        r="3.5"
                        fill="#06b6d4"
                        stroke="#090d16"
                        strokeWidth="1.5"
                        className="chart-dot"
                      />
                    )}

                    {/* Hover hotspot */}
                    <rect
                      x={cx - 15}
                      y={padding.top}
                      width="30"
                      height={innerHeight}
                      fill="transparent"
                      style={{ cursor: 'pointer' }}
                      onMouseEnter={() => setHoveredPoint({ x: cx, y: cyRate, packet: pkt, index: idx })}
                    />
                  </g>
                );
              })}

              {/* Hover Cursor Vertical Line */}
              {hoveredPoint && (
                <line
                  x1={hoveredPoint.x}
                  y1={padding.top}
                  x2={hoveredPoint.x}
                  y2={padding.top + innerHeight}
                  stroke="rgba(255, 255, 255, 0.4)"
                  strokeDasharray="3 3"
                />
              )}
            </svg>

            {/* Hover Tooltip Overlay */}
            {hoveredPoint && (
              <div
                className="chart-tooltip"
                style={{
                  left: `${Math.min(Math.max(hoveredPoint.x, 100), svgWidth - 140)}px`,
                  top: '15px',
                }}
              >
                <div className="tooltip-header font-mono">
                  <span>Packet #{hoveredPoint.packet.packet_id}</span>
                  <span className={`tooltip-tag ${hoveredPoint.packet.direction === 'RX' ? 'tag-rx' : 'tag-tx'}`}>
                    {hoveredPoint.packet.direction || 'TX'}
                  </span>
                </div>
                <div className="tooltip-row">
                  <span className="tooltip-lbl">Payload:</span>
                  <span className="tooltip-val font-mono">{hoveredPoint.packet.payload_text?.substring(0, 18)}</span>
                </div>
                <div className="tooltip-row">
                  <span className="tooltip-lbl">Throughput:</span>
                  <span className="tooltip-val font-mono text-emerald">
                    {hoveredPoint.packet.data_rate_bps ? `${hoveredPoint.packet.data_rate_bps.toFixed(1)} bps` : '--'}
                  </span>
                </div>
                <div className="tooltip-row">
                  <span className="tooltip-lbl">{hoveredPoint.packet.direction === 'RX' ? 'Air Duration:' : 'TX Playback:'}</span>
                  <span className="tooltip-val font-mono text-cyan">
                    {hoveredPoint.packet.latency_ms ? `${hoveredPoint.packet.latency_ms.toFixed(1)} ms` : '--'}
                  </span>
                </div>
                <div className="tooltip-row">
                  <span className="tooltip-lbl">CRC-16:</span>
                  <span className={`tooltip-val font-mono ${hoveredPoint.packet.crc_valid ? 'text-emerald' : 'text-rose'}`}>
                    {hoveredPoint.packet.crc16} ({hoveredPoint.packet.crc_valid ? 'VALID' : 'CORRUPTED'})
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="chart-legend">
        <div className="legend-item">
          <span className="legend-swatch swatch-emerald"></span>
          <span>Effective Throughput (bps)</span>
        </div>
        <div className="legend-item">
          <span className="legend-swatch swatch-cyan"></span>
          <span>Duration / Latency: TX Playback | RX Air-Time (ms)</span>
        </div>
        <div className="legend-item">
          <span className="legend-swatch swatch-rose"></span>
          <span>Corrupted Frame (CRC Mismatch)</span>
        </div>
      </div>
    </div>
  );
}

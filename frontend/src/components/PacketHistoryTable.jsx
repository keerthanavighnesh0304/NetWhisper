import React, { useState } from 'react';

export default function PacketHistoryTable({ packets = [] }) {
  const [filter, setFilter] = useState('all'); // 'all', 'valid', 'error', 'tx', 'rx'

  const filteredPackets = (packets || []).slice().reverse().filter((pkt) => {
    if (filter === 'valid') return pkt.crc_valid === true;
    if (filter === 'error') return pkt.crc_valid === false;
    if (filter === 'tx') return pkt.direction === 'TX';
    if (filter === 'rx') return pkt.direction === 'RX';
    return true;
  });

  return (
    <div className="card packets-card">
      <div className="card-header">
        <div className="card-title">
          <span className="dot pulse-blue"></span>
          Packet Transmission & Error Log
          <span className="analytics-subtitle font-mono">L2 Frame Inspection</span>
        </div>

        <div className="packets-header-controls">
          {/* Filter Pills */}
          <div className="table-filter-pills">
            <button
              type="button"
              className={`filter-pill ${filter === 'all' ? 'active' : ''}`}
              onClick={() => setFilter('all')}
            >
              All ({packets.length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'valid' ? 'active' : ''}`}
              onClick={() => setFilter('valid')}
            >
              Valid ({packets.filter((p) => p.crc_valid).length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'error' ? 'active' : ''}`}
              onClick={() => setFilter('error')}
            >
              Corrupted ({packets.filter((p) => !p.crc_valid).length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'tx' ? 'active' : ''}`}
              onClick={() => setFilter('tx')}
            >
              TX ({packets.filter((p) => p.direction === 'TX' || p.direction === 'TX/RX').length})
            </button>
            <button
              type="button"
              className={`filter-pill ${filter === 'rx' ? 'active' : ''}`}
              onClick={() => setFilter('rx')}
            >
              RX ({packets.filter((p) => p.direction === 'RX').length})
            </button>
          </div>

          <span className="log-counter font-mono">{packets.length} Frames Logged</span>
        </div>
      </div>

      <div className="table-responsive">
        <table className="packets-table">
          <thead>
            <tr>
              <th>Packet # / Seq</th>
              <th>Dir</th>
              <th>Time</th>
              <th>Payload</th>
              <th>Binary Preview</th>
              <th>CRC-16</th>
              <th title="TX: Measured soundcard playback duration | RX: Acoustic frame air-time">Duration / Latency</th>
              <th>Throughput</th>
              <th>Integrity</th>
              <th>Channel Source</th>
            </tr>
          </thead>
          <tbody>
            {filteredPackets.length > 0 ? (
              filteredPackets.map((pkt) => {
                const isCorrupted = !pkt.crc_valid;
                const isRx = pkt.direction === 'RX';
                const isTx = pkt.direction === 'TX' || pkt.direction === 'TX/RX';

                return (
                  <tr
                    key={`pkt-${pkt.packet_id}-${pkt.timestamp}`}
                    className={isCorrupted ? 'row-error' : 'row-valid'}
                  >
                    {/* Packet ID & Seq */}
                    <td className="font-mono">
                      <strong className="text-main">#{pkt.packet_id}</strong>
                      {pkt.seq_num !== undefined && pkt.seq_num !== null && (
                        <span className="pkt-seq-pill font-mono">
                          Seq {pkt.seq_num}
                        </span>
                      )}
                    </td>

                    {/* Direction: TX or RX */}
                    <td>
                      <span className={`direction-badge ${isRx ? 'dir-rx' : 'dir-tx'}`}>
                        {isRx ? 'RX (Inbound)' : 'TX (Outbound)'}
                      </span>
                    </td>

                    {/* Time */}
                    <td className="font-mono text-dim text-small">
                      {new Date(pkt.timestamp * 1000).toLocaleTimeString()}
                    </td>

                    {/* Payload Text */}
                    <td className="font-mono payload-cell">
                      {isCorrupted ? (
                        <span className="corrupted-payload-wrapper" title="Payload corrupted by acoustic noise or CRC mismatch">
                          <span className="payload-warn-icon">!</span>
                          <span className="text-rose font-bold">{pkt.payload_text}</span>
                        </span>
                      ) : (
                        <span className="text-main font-bold">{pkt.payload_text}</span>
                      )}
                    </td>

                    {/* Binary Preview */}
                    <td className="font-mono text-dim text-small binary-cell">
                      {pkt.binary_data ? `${pkt.binary_data.substring(0, 20)}...` : '--'}
                    </td>

                    {/* CRC-16 Checksum */}
                    <td className="font-mono">
                      <span className={isCorrupted ? 'text-rose' : 'text-cyan'}>
                        {pkt.crc16 || '--'}
                      </span>
                    </td>

                    {/* Latency (ms) */}
                    <td className="font-mono text-small">
                      {pkt.latency_ms !== null && pkt.latency_ms !== undefined ? (
                        <span className="text-cyan">
                          {Number(pkt.latency_ms).toFixed(1)} ms
                          <span className="text-dim text-small" style={{ marginLeft: '4px' }}>
                            {isRx ? '(air)' : '(tx)'}
                          </span>
                        </span>
                      ) : (
                        <span className="text-dim">--</span>
                      )}
                    </td>

                    {/* Throughput (bps) */}
                    <td className="font-mono text-small">
                      {pkt.data_rate_bps !== null && pkt.data_rate_bps !== undefined ? (
                        <span className="text-emerald">{Number(pkt.data_rate_bps).toFixed(1)} bps</span>
                      ) : (
                        <span className="text-dim">--</span>
                      )}
                    </td>

                    {/* Status badge with safe SVG icon and no encoding issues */}
                    <td>
                      <span className={`tag ${isCorrupted ? 'tag-error' : 'tag-valid'}`}>
                        {isCorrupted ? (
                          <span className="tag-inner">
                            <svg className="tag-icon" viewBox="0 0 16 16" fill="currentColor">
                              <path d="M3.72 3.72a.75.75 0 0 1 1.06 0L8 6.94l3.22-3.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734L9.06 8l3.22 3.22a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L8 9.06l-3.22 3.22a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L6.94 8 3.72 4.78a.75.75 0 0 1 0-1.06Z" />
                            </svg>
                            CORRUPTED
                          </span>
                        ) : (
                          <span className="tag-inner">
                            <svg className="tag-icon" viewBox="0 0 16 16" fill="currentColor">
                              <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z" />
                            </svg>
                            VALID
                          </span>
                        )}
                      </span>
                    </td>

                    {/* Channel Source */}
                    <td>
                      <span className={`source-tag ${pkt.source?.includes('Synthetic') ? 'source-synthetic' : 'source-acoustic'}`}>
                        {pkt.source?.includes('ACOUSTIC') ? 'Acoustic Channel' : 'Test Loopback'}
                      </span>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={10} className="empty-table-row">
                  {packets.length === 0
                    ? 'No frames recorded yet. Transmit or receive a frame over the acoustic link.'
                    : `No frames match the active filter "${filter}".`}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

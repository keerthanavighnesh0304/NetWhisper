import React from 'react';

export default function PacketHistoryTable({ packets }) {
  return (
    <div className="card packets-card">
      <div className="card-header">
        <div className="card-title">
          <span className="dot pulse-blue"></span>
          Packet Transmission & Error Log
        </div>
        <span className="log-counter">{packets.length} Frames Logged</span>
      </div>

      <div className="table-responsive">
        <table className="packets-table">
          <thead>
            <tr>
              <th>Packet / Seq</th>
              <th>Time</th>
              <th>Payload</th>
              <th>Binary Preview (First 24 bits)</th>
              <th>CRC-16</th>
              <th>Integrity</th>
              <th>Channel Source</th>
            </tr>
          </thead>
          <tbody>
            {packets && packets.length > 0 ? (
              packets.slice().reverse().map((pkt) => (
                <tr key={pkt.packet_id} className={pkt.crc_valid ? 'row-valid' : 'row-error'}>
                  <td className="font-mono">
                    #{pkt.packet_id}
                    {pkt.seq_num !== undefined && pkt.seq_num !== null && (
                      <span className="text-dim text-small" style={{ marginLeft: '4px' }}>
                        [Seq {pkt.seq_num}]
                      </span>
                    )}
                  </td>
                  <td className="font-mono text-dim">
                    {new Date(pkt.timestamp * 1000).toLocaleTimeString()}
                  </td>
                  <td className="font-mono font-bold">{pkt.payload_text}</td>
                  <td className="font-mono text-dim text-small">
                    {pkt.binary_data ? pkt.binary_data.substring(0, 24) + '...' : '--'}
                  </td>
                  <td className="font-mono text-cyan">{pkt.crc16}</td>
                  <td>
                    <span className={`tag ${pkt.crc_valid ? 'tag-valid' : 'tag-error'}`}>
                      {pkt.crc_valid ? 'VALID ✓' : 'CORRUPTED ✗'}
                    </span>
                  </td>
                  <td>
                    <span className={`source-tag ${pkt.source.includes('Synthetic') ? 'source-synthetic' : 'source-acoustic'}`}>
                      {pkt.source}
                    </span>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="empty-table-row">
                  No packets recorded yet. Transmit or receive a frame.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

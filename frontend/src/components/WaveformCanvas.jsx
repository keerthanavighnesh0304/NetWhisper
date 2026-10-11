import React, { useRef, useEffect } from 'react';

export default function WaveformCanvas({ waveformData, isTransmitting, modeLabel }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear background
    ctx.fillStyle = '#0a0f1d';
    ctx.fillRect(0, 0, width, height);

    // Draw oscilloscope grid lines
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
    ctx.lineWidth = 1;
    const stepX = width / 10;
    const stepY = height / 6;

    for (let x = 0; x <= width; x += stepX) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    for (let y = 0; y <= height; y += stepY) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // Center baseline
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.25)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw waveform trace
    const samples = waveformData && waveformData.length > 0 ? waveformData : new Array(128).fill(0);
    const hasSignal = samples.some(val => Math.abs(val) > 0.01);

    ctx.lineWidth = 2.5;
    ctx.strokeStyle = hasSignal ? '#06b6d4' : '#334155';
    ctx.shadowBlur = hasSignal ? 10 : 0;
    ctx.shadowColor = '#06b6d4';

    ctx.beginPath();
    const sliceWidth = width / (samples.length - 1);
    let x = 0;

    for (let i = 0; i < samples.length; i++) {
      // Map [-1.0, 1.0] to canvas height with padding
      const y = (height / 2) - (samples[i] * (height / 2) * 0.78);
      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      x += sliceWidth;
    }
    ctx.stroke();
    ctx.shadowBlur = 0; // reset
  }, [waveformData]);

  return (
    <div className="card waveform-card">
      <div className="card-header">
        <div className="card-title">
          <span className="dot pulse"></span>
          Acoustic FSK Oscilloscope & Signal Monitor
        </div>
        <div className="waveform-legend">
          <span className="legend-tag mark">Mark (1): 1800 Hz</span>
          <span className="legend-tag space">Space (0): 1200 Hz</span>
          <span className="legend-status">{isTransmitting ? 'TRANSMITTING...' : 'MONITORING'}</span>
        </div>
      </div>
      <div className="canvas-wrapper">
        <canvas
          ref={canvasRef}
          width={720}
          height={160}
          className="waveform-canvas"
        />
      </div>
      <div className="canvas-footer">
        <span className="source-caption">Signal View: {modeLabel}</span>
        <span className="fsk-rate">Modulation: Binary Frequency Shift Keying (2-FSK)</span>
      </div>
    </div>
  );
}

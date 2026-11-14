// frontend/src/components/HeatmapComponent.tsx
import React from 'react';

interface Props { parameter: string; time: string; north: number; south: number; east: number; west: number; }
export default function HeatmapComponent({ parameter, time, north, south, east, west }: Props) {
  // Construct URL for backend heatmap endpoint
  const url = `/api/heatmap?parameter=${parameter}&time=${encodeURIComponent(time)}&north=${north}&south=${south}&east=${east}&west=${west}`;
  return (
    <div>
      <h2>Spatial Heatmap</h2>
      <img src={url} alt="Heatmap" style={{ maxWidth: '100%' }} />
      <p>Map for {parameter} at {time} over the selected region.</p>
    </div>
  );
}

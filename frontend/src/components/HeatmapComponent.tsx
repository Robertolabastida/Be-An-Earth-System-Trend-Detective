// frontend/src/components/HeatmapComponent.tsx
import React from 'react';

interface Props { parameter: string; time: string; north: number; south: number; east: number; west: number; }
export default function HeatmapComponent({ parameter, time, north, south, east, west }: Props) {
  const query = new URLSearchParams({
    param: parameter,
    time,
    latN: String(north),
    lonW: String(west),
    latS: String(south),
    lonE: String(east),
  });
  const url = `/api/heatmap?${query}`;
  return (
    <div>
      <h2>Spatial Heatmap</h2>
      <img src={url} alt="Heatmap" style={{ maxWidth: '100%' }} />
      <p>Map for {parameter} at {time} over the selected region.</p>
    </div>
  );
}

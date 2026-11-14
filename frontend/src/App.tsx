// frontend/src/App.tsx
import React, { useState } from 'react';
import './App.css';
import ChartComponent from './components/ChartComponent';
import HeatmapComponent from './components/HeatmapComponent';
import { fetchTimeSeries, fetchTrend } from './api';

function App() {
  // State hooks for form inputs
  const [variable, setVariable] = useState('t_2m:C');
  const [lat, setLat] = useState(51.5);
  const [lon, setLon] = useState(0.0);
  const [start, setStart] = useState('2026-01-01T00:00:00Z');
  const [end, setEnd] = useState('2026-12-31T23:00:00Z');
  const [step, setStep] = useState('P1D');
  const [analysis, setAnalysis] = useState('time_series');
  const [region, setRegion] = useState<'point' | 'bbox'>('point');
  const [bbox, setBbox] = useState({ north: 55.0, south: 50.0, east: 5.0, west: -5.0 });

  // Data results
  const [seriesData, setSeriesData] = useState<any[]>([]);
  const [trendData, setTrendData] = useState<any>(null);
  const [error, setError] = useState<string>('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    try {
      if (analysis === 'time_series') {
        const res = await fetchTimeSeries(variable, lat, lon, start, end, step);
        setSeriesData(res.series);
        setTrendData(null);
      } else if (analysis === 'linear_trend') {
        const res = await fetchTrend(variable, lat, lon, start, end, step);
        setSeriesData(res.series);
        setTrendData(res);
      }
      // (Additional analysis types like anomaly/seasonal could be handled similarly.)
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="app">
      <h1>EarthTrend AI – Climate Trend Explorer</h1>
      <form onSubmit={handleSubmit} className="control-panel">
        {/* Variable selection */}
        <label>Variable:
          <select value={variable} onChange={e => setVariable(e.target.value)}>
            <option value="t_2m:C">Air Temp (2m, °C)</option>
            <option value="precip_1h:mm">Precipitation (hourly, mm)</option>
            <option value="relative_humidity_2m:p">Humidity (2m, %)</option>
            <option value="wind_speed_10m:ms">Wind Speed (10m, m/s)</option>
            {/* Add more parameter options as needed */}
          </select>
        </label>
        {/* Region: point vs bounding box */}
        <label>Region Type:
          <select value={region} onChange={e => setRegion(e.target.value as any)}>
            <option value="point">Point (lat/lon)</option>
            <option value="bbox">Bounding Box (for map)</option>
          </select>
        </label>
        {/* If point, show lat/lon inputs */}
        {region === 'point' && (
          <div className="coords">
            <label>Latitude: <input type="number" value={lat} onChange={e => setLat(Number(e.target.value))} /></label>
            <label>Longitude: <input type="number" value={lon} onChange={e => setLon(Number(e.target.value))} /></label>
          </div>
        )}
        {/* If bbox, show north/south/east/west inputs */}
        {region === 'bbox' && (
          <div className="bbox">
            <label>North: <input type="number" value={bbox.north} onChange={e => setBbox({ ...bbox, north: Number(e.target.value) })} /></label>
            <label>South: <input type="number" value={bbox.south} onChange={e => setBbox({ ...bbox, south: Number(e.target.value) })} /></label>
            <label>East: <input type="number" value={bbox.east} onChange={e => setBbox({ ...bbox, east: Number(e.target.value) })} /></label>
            <label>West: <input type="number" value={bbox.west} onChange={e => setBbox({ ...bbox, west: Number(e.target.value) })} /></label>
          </div>
        )}
        {/* Time range */}
        <label>Start (UTC):
          <input type="datetime-local" value={start.slice(0,-1)} onChange={e => setStart(new Date(e.target.value).toISOString())} />
        </label>
        <label>End (UTC):
          <input type="datetime-local" value={end.slice(0,-1)} onChange={e => setEnd(new Date(e.target.value).toISOString())} />
        </label>
        <label>Resolution:
          <select value={step} onChange={e => setStep(e.target.value)}>
            <option value="PT1H">Hourly</option>
            <option value="P1D">Daily</option>
            <option value="P1M">Monthly</option>
          </select>
        </label>
        {/* Analysis type */}
        <label>Analysis:
          <select value={analysis} onChange={e => setAnalysis(e.target.value)}>
            <option value="time_series">Time Series</option>
            <option value="linear_trend">Linear Trend</option>
            {/* Additional types could be added: anomaly, seasonal, spatial */}
          </select>
        </label>
        <button type="submit">Run Analysis</button>
      </form>

      {error && <div className="error">Error: {error}</div>}

      {/* Results */}
      {seriesData.length > 0 && (
        <ChartComponent data={seriesData} label={variable} title={analysis === 'linear_trend' ? "Trend Analysis" : "Time Series"} />
      )}
      {trendData && (
        <div className="trend-info">
          <p>Slope: {trendData.slope.toFixed(3)} units/day (R² = {trendData.r_squared.toFixed(2)})</p>
        </div>
      )}
      {/* For spatial map output (if region=bbox and analysis type = "map"), show image */}
      {region === 'bbox' && analysis === 'time_series' && (
        <HeatmapComponent
          parameter={variable}
          time={start}
          north={bbox.north}
          south={bbox.south}
          east={bbox.east}
          west={bbox.west}
        />
      )}
    </div>
  );
}

export default App;

import React, { useState } from 'react';
import axios from 'axios';
import { Line } from 'react-chartjs-2';
import 'chart.js/auto';  // Importa adaptadores para Chart.js

// Definición de opciones disponibles
const PARAMETERS = [
  { label: "Temperature (2m)", value: "t_2m:C" },
  { label: "Precipitation (1h)", value: "precip_1h:mm" },
  { label: "Wind Speed (10m)", value: "wind_speed_10m:ms" }
];
const ANALYSIS_TYPES = ["Chart", "Heatmap"];
const REGIONS = {
  "Ensenada, MX": {
    lat: 31.87, lon: -116.60,
    latN: 33, lonW: -118, latS: 30, lonE: -114
  },
  "Mexico": {
    lat: 23.0, lon: -102.0,
    latN: 32, lonW: -118, latS: 14, lonE: -86
  },
  "North America": {
    lat: 39.0, lon: -95.0,
    latN: 72, lonW: -170, latS: 8, lonE: -50
  },
  "Europe": {
    lat: 51.5, lon: 10.0,
    latN: 70, lonW: -25, latS: 30, lonE: 45
  },
  "World": {
    lat: 0, lon: 0,
    latN: 90, lonW: -180, latS: -90, lonE: 180
  }
};
const REGION_NAMES = Object.keys(REGIONS) as Array<keyof typeof REGIONS>;

const App: React.FC = () => {
  const today = new Date().toISOString().split('T')[0];
  const prevMonth = new Date();
  prevMonth.setDate(prevMonth.getDate() - 30);

  // Estados para parámetros del formulario
  const [param, setParam] = useState(PARAMETERS[0].value);
  const [analysisType, setAnalysisType] = useState(ANALYSIS_TYPES[0]);
  const [startDate, setStartDate] = useState(prevMonth.toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState(today);
  const [region, setRegion] = useState<keyof typeof REGIONS>("Ensenada, MX");
  const selectedRegion = REGIONS[region];

  // Estado para datos recibidos y para imagen de heatmap
  const [timeSeriesData, setTimeSeriesData] = useState<{ dates: string[]; values: number[]; slope: number | null; intercept: number | null; r2: number | null;} | null>(null);
  const [imageUrl, setImageUrl] = useState("");

  // Función para solicitar datos al backend
  const handleFetch = async () => {
    if (analysisType === "Chart") {
      // Datos de series de tiempo
      try {
        const res = await axios.get('/api/time-series', {
          params: {
            param: param,
            lat: selectedRegion.lat,
            lon: selectedRegion.lon,
            start: `${startDate}T00:00:00Z`,
            end: `${endDate}T00:00:00Z`
          }
        });
        setTimeSeriesData(res.data);
        setImageUrl("");
      } catch (error) {
        console.error(error);
        alert("Error fetching time series data.");
      }
    } else {
      // Mapa de calor
      setTimeSeriesData(null);
      const url = `/api/heatmap?param=${encodeURIComponent(param)}&time=${encodeURIComponent(endDate + "T00:00:00Z")}` +
                  `&latN=${selectedRegion.latN}&lonW=${selectedRegion.lonW}&latS=${selectedRegion.latS}&lonE=${selectedRegion.lonE}` +
                  `&_=${Date.now()}`;  // parametro anti-cache
      setImageUrl(url);
    }
  };

  return (
    <div className="container">
      <h1>EarthTrend AI - Data Explorer</h1>
      <div className="form-group">
        <label>Variable:&nbsp;
          <select value={param} onChange={e => setParam(e.target.value)}>
            {PARAMETERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </label>
      </div>
      <div className="form-group">
        <label>Analysis Type:&nbsp;
          <select value={analysisType} onChange={e => setAnalysisType(e.target.value)}>
            {ANALYSIS_TYPES.map(type => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
      </div>
      <div className="form-group">
        <label>Start Date:&nbsp;
          <input type="date" value={startDate} max={endDate} onChange={e => setStartDate(e.target.value)} />
        </label>
        <label style={{ marginLeft: "1rem" }}>End Date:&nbsp;
          <input type="date" value={endDate} min={startDate} onChange={e => setEndDate(e.target.value)} />
        </label>
      </div>
      <div className="form-group">
        <label>Region:&nbsp;
          <select value={region} onChange={e => setRegion(e.target.value as keyof typeof REGIONS)}>
            {REGION_NAMES.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </label>
      </div>
      <button onClick={handleFetch}>Get Data</button>

      <hr />

      {timeSeriesData && analysisType === "Chart" && (
        <div>
          <h2>Time Series for {param}</h2>
          <Line
            data={{
              labels: timeSeriesData.dates,
              datasets: [
                {
                  label: `${param} over time`,
                  data: timeSeriesData.values,
                  borderColor: 'rgba(53, 162, 235, 0.8)',
                  backgroundColor: 'rgba(53, 162, 235, 0.4)',
                  fill: false,
                }
              ]
            }}
            options={{
              scales: {
                x: { display: true, title: { display: true, text: 'Date' } },
                y: { display: true, title: { display: true, text: 'Value' } }
              }
            }}
          />
          <p>
            Slope: {timeSeriesData.slope !== null ? timeSeriesData.slope.toFixed(3) : 'N/A'}<br />
            R²: {timeSeriesData.r2 !== null ? timeSeriesData.r2.toFixed(3) : 'N/A'}
          </p>
        </div>
      )}

      {analysisType === "Heatmap" && imageUrl && (
        <div>
          <h2>Heatmap for {param}</h2>
          <img src={imageUrl} alt="Heatmap" style={{ maxWidth: '100%', border: '1px solid #ccc' }} />
        </div>
      )}
    </div>
  );
};

export default App;

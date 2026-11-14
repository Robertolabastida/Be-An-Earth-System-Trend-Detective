// frontend/src/api.ts
export async function fetchTimeSeries(variable: string, lat: number, lon: number, start: string, end: string, step: string) {
  const resp = await fetch(
    `/api/time_series?parameter=${encodeURIComponent(variable)}&lat=${lat}&lon=${lon}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&step=${step}`
  );
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}
export async function fetchTrend(variable: string, lat: number, lon: number, start: string, end: string, step: string) {
  const resp = await fetch(
    `/api/linear_trend?parameter=${encodeURIComponent(variable)}&lat=${lat}&lon=${lon}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&step=${step}`
  );
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

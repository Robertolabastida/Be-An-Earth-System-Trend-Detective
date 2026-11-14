export interface TimeSeriesResult {
  dates: string[];
  values: number[];
  slope: number | null;
  intercept: number | null;
  r2: number | null;
}

export async function fetchTimeSeries(
  param: string,
  lat: number,
  lon: number,
  start: string,
  end: string
): Promise<TimeSeriesResult> {
  const query = new URLSearchParams({
    param,
    lat: String(lat),
    lon: String(lon),
    start,
    end,
  });
  const resp = await fetch(`/api/time-series?${query}`);
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export const fetchTrend = fetchTimeSeries;

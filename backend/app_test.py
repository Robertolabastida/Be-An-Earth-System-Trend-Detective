from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_time_series_endpoint():
    # This is a placeholder test; real test would mock requests.get
    response = client.get("/api/time_series?parameter=t_2m:C&lat=51.5&lon=0.0&start=2026-01-01T00:00:00Z&end=2026-01-02T00:00:00Z")
    assert response.status_code in (200, 401)  # 401 if no creds set

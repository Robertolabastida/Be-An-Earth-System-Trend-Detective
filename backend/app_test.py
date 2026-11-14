from unittest.mock import Mock

from fastapi.testclient import TestClient
import main
import pytest

client = TestClient(main.app)


def test_time_series_endpoint_returns_values_and_trend(monkeypatch):
    monkeypatch.setattr(main, "METEO_USER", "test-user")
    monkeypatch.setattr(main, "METEO_PWD", "test-password")
    response_from_provider = Mock()
    response_from_provider.json.return_value = {
        "temperature": [
            {
                "coordinates": [
                    {
                        "dates": [
                            {"date": "2026-01-01T00:00:00Z", "value": 1},
                            {"date": "2026-01-02T00:00:00Z", "value": 3},
                            {"date": "2026-01-03T00:00:00Z", "value": 5},
                        ]
                    }
                ]
            }
        ]
    }
    monkeypatch.setattr(main.requests, "get", Mock(return_value=response_from_provider))

    response = client.get(
        "/api/time-series",
        params={
            "param": "t_2m:C",
            "lat": 51.5,
            "lon": 0.0,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-03T00:00:00Z",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["dates"] == [
        "2026-01-01T00:00:00Z",
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]
    assert data["values"] == [1, 3, 5]
    assert data["slope"] == pytest.approx(2)
    assert data["intercept"] == pytest.approx(1)
    assert data["r2"] == pytest.approx(1)
    assert main.requests.get.call_args.kwargs["auth"] == ("test-user", "test-password")


def test_time_series_requires_credentials(monkeypatch):
    monkeypatch.setattr(main, "METEO_USER", None)
    monkeypatch.setattr(main, "METEO_PWD", None)

    response = client.get(
        "/api/time-series",
        params={
            "param": "t_2m:C",
            "lat": 51.5,
            "lon": 0.0,
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-02T00:00:00Z",
        },
    )

    assert response.status_code == 503
    assert "METEOMATICS_USER" in response.json()["detail"]

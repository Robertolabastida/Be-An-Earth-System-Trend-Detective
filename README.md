# EarthTrend AI — Frontend and Backend

This repository's React frontend communicates with a FastAPI backend. The backend retrieves weather data from Meteomatics, calculates a linear trend for time series, and returns heatmap images. This guide covers only the setup required for that application.

## Requirements

- Python 3.10 or later and `pip`
- Node.js 18 or later and npm
- A Meteomatics account with API credentials
- Internet access to install dependencies and reach the Meteomatics API
- A modern web browser

The backend Python dependencies are listed in [`backend/requirements.txt`](backend/requirements.txt). They include FastAPI and Uvicorn to serve the API, Requests and NumPy for data retrieval and calculations, `python-dotenv` to load credentials, and pytest/httpx for the existing API test setup. The frontend dependencies are declared in [`frontend/package.json`](frontend/package.json) and locked in `frontend/package-lock.json`; use `npm ci` to install them.

## 1. Configure and install the backend

Run these commands from the repository root to create and activate a virtual environment:

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows PowerShell (use this instead of the command above)
.\.venv\Scripts\Activate.ps1
```

Install the backend packages:

```bash
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

Create `backend/.env` and add the credentials for your Meteomatics account:

```dotenv
METEOMATICS_USER=your_username
METEOMATICS_PASSWORD=your_password
```

The backend specifically loads `backend/.env` and will not start if either credential is missing. Keep this file private; do not commit or share your credentials.

## 2. Start the backend

In a terminal with the virtual environment activated:

```bash
cd backend
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal running. The API is available at <http://127.0.0.1:8000>; its interactive documentation is at <http://127.0.0.1:8000/docs>.

## 3. Install and start the frontend

Open a second terminal in the repository root:

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite, normally <http://localhost:5173>. Keep both development servers running. Vite forwards `/api` requests to the backend at `http://localhost:8000`.

## Using the application

Choose a variable, an analysis type (chart or heatmap), a date range, and a region, then select **Get Data**. Chart results show the returned time series and linear trend statistics; heatmap results show the requested map image. The Meteomatics account must have access to the selected parameters and date ranges.

## Production frontend build

To create the static frontend bundle, run from `frontend/`:

```bash
npm run build
```

The output is written to `frontend/dist/`. The Vite development proxy is for local development; production hosting must also route `/api` requests to the FastAPI backend.

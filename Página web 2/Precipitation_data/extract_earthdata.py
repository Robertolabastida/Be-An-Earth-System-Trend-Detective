from dotenv import load_dotenv
import earthaccess
import xarray as xr
import numpy as np

# 1. Authenticate (prompts once, then caches credentials in ~/.netrc)
load_dotenv(".env")
auth=earthaccess.login(strategy="environment")

# 2. Define your region (min_lon, min_lat, max_lon, max_lat) and period
bbox = (-116.9, 30.8, -114.6, 32.35)  # Ensenada, Baja California, México
time_range = ("2000-01-01", "2025-12-31")

# 3. Search for GPM_3IMERGM V07 granules
results = earthaccess.search_data(
    short_name="GPM_3IMERGM",
    version="07",
    temporal=time_range,
    bounding_box=bbox,
)
print(f"Found {len(results)} monthly granules.")

# 4. Access the data (choose Option A or Option B)

# Option A: Stream directly over HTTPS without saving full global files locally
# file_objs = earthaccess.open(results)

# Option B: Download granules locally first (recommended if re-running analyses often;
# each global monthly file is ~10–25 MB)
file_objs = earthaccess.download(results, local_path="./Precipitation_data/gpm_imergm_v07")
from dotenv import load_dotenv
import earthaccess
import xarray as xr
import numpy as np


load_dotenv(".env")
auth=earthaccess.login(strategy="environment")


bbox = (-116.9, 30.8, -114.6, 32.35)  # Ensenada, Baja California, México
time_range = ("2000-01-01", "2025-12-31")


results = earthaccess.search_data(
    short_name="GPM_3IMERGM",
    version="07",
    temporal=time_range,
    bounding_box=bbox,
)
print(f"Found {len(results)} monthly granules.")

file_objs = earthaccess.download(results, local_path="./Precipitation_data/gpm_imergm_v07")

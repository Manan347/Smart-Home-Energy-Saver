"""
prediction.py
--------------
Contains reusable functions for loading Prophet models
and forecasting next-day kWh for a specific appliance.
"""

from pathlib import Path
import json
import pickle
import pandas as pd
from datetime import datetime

ARTIFACT_DIR = Path("./artifacts")
REGISTRY_FILE = ARTIFACT_DIR / "prophet_registry.json"

# Load model registry on import
if not REGISTRY_FILE.exists():
    raise FileNotFoundError(f"Model registry file not found: {REGISTRY_FILE}")

with open(REGISTRY_FILE, "r") as f:
    MODEL_REGISTRY = json.load(f)


def predict_next_day_kwh(
    appliance: str,
    ds_next: str,
    avg_temp: float,
    hh_size: float,
    is_weekend: int
) -> dict:
    """Forecasts next-day kWh for given appliance using Prophet."""
    if appliance not in MODEL_REGISTRY:
        raise ValueError(f"No model found for appliance: {appliance}")

    # load model
    raw_path = MODEL_REGISTRY[appliance]["model_path"]
    model_path = Path(raw_path)
    if not model_path.is_absolute():
        model_path = ARTIFACT_DIR / model_path

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found at: {model_path}")

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    df = pd.DataFrame([{
        "ds": pd.to_datetime(ds_next),
        "avg_temp": float(avg_temp),
        "hh_size": float(hh_size),
        "is_weekend": int(is_weekend)
    }])

    pred = model.predict(df)
    return {
        "appliance": appliance,
        "date": ds_next,
        "predicted_kwh": float(pred.loc[0, "yhat"]),
        "ci_lower": float(pred.loc[0, "yhat_lower"]),
        "ci_upper": float(pred.loc[0, "yhat_upper"])
    }

# ----------------------------------------
# Local Test: Run prediction directly
# ----------------------------------------
if __name__ == "__main__":
    print("🔍 Testing Prophet prediction model locally...\n")

    # Sample test input
    appliance = "Air Conditioning"
    date = "2025-11-10"         # YYYY-MM-DD
    avg_temp = 30.5             # °C
    hh_size = 4                 # people in household
    is_weekend = 0              # weekday

    try:
        result = predict_next_day_kwh(
            appliance=appliance,
            ds_next=date,
            avg_temp=avg_temp,
            hh_size=hh_size,
            is_weekend=is_weekend
        )
        print("Prediction successful:")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print("Prediction failed:")
        print(e)

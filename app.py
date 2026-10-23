"""
app.py
-------
FastAPI backend that exposes:
- /optimize-energy → Agentic energy-saving optimization (via agent.py)
- /email-plan      → Format plan into email and send (via email_agent.py)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from datetime import datetime

from agent import run_agent, HomeProfile
from email_agent import generate_email_and_send_async  # Updated for async usage

# -------------------------------
# App Setup
# -------------------------------
app = FastAPI(title="Home Energy Saver API", version="2.4.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Update in production for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------
# Pydantic Models
# -------------------------------
class OptimizeEnergyRequest(BaseModel):
    hh_size: int
    appliances_present: list[str]
    latitude: float = 18.6298
    longitude: float = 73.7997
    timezone: str = "Asia/Kolkata"
    rate_peak: float = 12.0
    rate_offpeak: float = 7.5
    tariff_peak_start: str = "18:00"
    tariff_peak_end: str = "22:00"

    model_config = {
        "json_schema_extra": {
            "example": {
                "hh_size": 4,
                "appliances_present": ["Air Conditioning", "Microwave", "Computer"],
                "latitude": 18.6298,
                "longitude": 73.7997,
                "timezone": "Asia/Kolkata",
                "rate_peak": 12.0,
                "rate_offpeak": 7.5,
                "tariff_peak_start": "18:00",
                "tariff_peak_end": "22:00"
            }
        }
    }


class EmailPlanRequest(BaseModel):
    plan_json: dict
    email: EmailStr
    name: str = "User"

    model_config = {
        "json_schema_extra": {
            "example": {
                "plan_json": {
                    "summary": "⚠️ Tomorrow will be cooler than average with temperatures between 14.9°C and 26.9°C, providing an opportunity to optimize energy usage.",
                    "actions": [
                        {
                            "appliance": "Air Conditioning",
                            "recommendation": "Set to 24°C and use it only between 1PM–5PM.",
                            "estimated_kwh_saving": 1.7,
                            "estimated_cost_saving": 18.5,
                            "currency": "INR"
                        },
                        {
                            "appliance": "Washing Machine",
                            "recommendation": "Run during off-peak hours (8PM–10PM) to wash full loads.",
                            "estimated_kwh_saving": 0.2,
                            "estimated_cost_saving": 2.2,
                            "currency": "INR"
                        },
                        {
                            "appliance": "Dishwasher",
                            "recommendation": "Run on a shorter cycle during off-peak hours (8PM–10PM).",
                            "estimated_kwh_saving": 0.2,
                            "estimated_cost_saving": 2.2,
                            "currency": "INR"
                        },
                        {
                            "appliance": "Microwave",
                            "recommendation": "Limit use to essential cooking for a maximum of 10 minutes between 5PM–7PM.",
                            "estimated_kwh_saving": 0.1,
                            "estimated_cost_saving": 1.1,
                            "currency": "INR"
                        },
                        {
                            "appliance": "Computer",
                            "recommendation": "Schedule active use for only 3 hours (6PM–9PM).",
                            "estimated_kwh_saving": 0.4,
                            "estimated_cost_saving": 4.4,
                            "currency": "INR"
                        }
                    ]
                },
                "email": "your-email@example.com",
                "name": "User Name"
            }
        }
    }


# -------------------------------
# Routes
# -------------------------------
@app.get("/")
def index():
    return {
        "message": "Welcome to the Home Energy Saver API",
        "routes": ["/optimize-energy", "/email-plan"],
        "docs": "/docs"
    }

@app.post("/optimize-energy", summary="Generate energy optimization plan", tags=["Agentic AI"])
def optimize_energy(req: OptimizeEnergyRequest):
    """
    Orchestrates the entire agent workflow and returns structured results.
    """
    try:
        profile = HomeProfile(**req.dict())
        return run_agent(profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent Error: {e}")


@app.post("/email-plan", summary="Format and send plan via email", tags=["Email"])
async def email_plan(req: EmailPlanRequest):
    """
    Uses the email agent to format and send a plan over email.
    """
    try:
        return await generate_email_and_send_async(req.plan_json, req.email, req.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email Error: {e}")


# -------------------------------
# Local Run
# -------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

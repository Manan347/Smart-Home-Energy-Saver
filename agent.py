"""
agent.py
--------
Enhanced Home Energy Saver using Microsoft Agent Framework
and Microsoft Foundry.

Agents:
- UsageCollectorAgent:
    Collects latest appliance usage, tomorrow's weather,
    and next-day appliance energy forecasts.

- RecommendationAgent:
    Analyzes actual vs forecasted usage and generates
    practical energy-saving recommendations.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

from prediction import predict_next_day_kwh


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()


# ============================================================
# CONSTANTS & CONFIG
# ============================================================

CSV_PATH = "./data/appliance_usage.csv"
CURRENCY = "INR"


# ============================================================
# FOUNDRY CONFIGURATION
# ============================================================

def create_foundry_client() -> FoundryChatClient:
    """
    Create a Microsoft Foundry client.

    The Azure CLI credential is used for authentication.
    Make sure you are logged in using:

        az login
    """

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    model = os.getenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL")

    if not endpoint:
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT is missing from .env"
        )

    if not model:
        raise RuntimeError(
            "AZURE_OPENAI_CHAT_COMPLETION_MODEL is missing from .env"
        )

    # FoundryChatClient expects the project/resource endpoint,
    # so remove the OpenAI Responses path if it is present.
    endpoint = endpoint.rstrip("/")

    if endpoint.endswith("/openai/v1/responses"):
        endpoint = endpoint[:-len("/openai/v1/responses")]

    elif endpoint.endswith("/openai/v1"):
        endpoint = endpoint[:-len("/openai/v1")]

    elif endpoint.endswith("/openai"):
        endpoint = endpoint[:-len("/openai")]

    print("\nFoundry configuration:")
    print("Endpoint:", endpoint)
    print("Model:", model)

    try:
        credential = AzureCliCredential()

        client = FoundryChatClient(
            project_endpoint=endpoint,
            model=model,
            credential=credential,
        )

        return client

    except Exception as e:
        raise RuntimeError(
            f"Could not create Microsoft Foundry client: {e}"
        )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def iso_date(dt: datetime) -> str:
    """Format datetime to ISO date string."""
    return dt.strftime("%Y-%m-%d")


def safe_json_extract(response_text: str) -> Dict[str, Any]:
    """
    Extract valid JSON from an agent response.

    Handles responses where the model may accidentally place
    additional text before or after the JSON object.
    """

    if not response_text:
        raise ValueError("Agent returned an empty response.")

    response_text = response_text.strip()

    # Direct JSON
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # JSON enclosed in additional text
    start = response_text.find("{")
    end = response_text.rfind("}")

    if start != -1 and end != -1 and end > start:
        json_text = response_text[start:end + 1]

        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Could not parse JSON returned by agent: {e}\n\n"
                f"Response:\n{response_text}"
            )

    raise ValueError(
        "Could not extract JSON from agent response.\n\n"
        f"Response:\n{response_text}"
    )


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class HomeProfile:
    """Represents a household's energy usage profile."""

    hh_size: int

    appliances_present: List[str]

    rate_peak: float = 12.0

    rate_offpeak: float = 7.5

    tariff_peak_start: str = "18:00"

    tariff_peak_end: str = "22:00"

    latitude: float = 18.6298

    longitude: float = 73.7997

    timezone: str = "Asia/Kolkata"

    city: Optional[str] = None


# ============================================================
# GEOCODING
# ============================================================

def geocode_city(
    city: str,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    Return geocoding matches for a city using Nominatim.
    """

    try:
        url = "https://nominatim.openstreetmap.org/search"

        params = {
            "q": city,
            "format": "json",
            "limit": max_results
        }

        headers = {
            "User-Agent": "HomeEnergySaver/1.0"
        }

        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for item in data:

            results.append({
                "display_name": item.get(
                    "display_name",
                    ""
                ),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
                "type": item.get("type"),
                "class": item.get("class"),
            })

        return results

    except Exception:
        return []


# ============================================================
# TOOL 1
# ============================================================

@tool(
    name="get_last_usage_from_csv",
    description=(
        "Load appliance usage data for the most recent "
        "date available in the CSV file."
    ),
    approval_mode="never_require",
)
def get_last_usage_from_csv(
    csv_path: str = CSV_PATH
) -> dict:
    """
    Returns the latest appliance usage records.
    """

    try:

        df = pd.read_csv(
            csv_path,
            parse_dates=["date"]
        )

        if df.empty:
            raise RuntimeError(
                "The appliance usage CSV is empty."
            )

        latest_date = df["date"].max()

        latest_records = df[
            df["date"] == latest_date
        ].copy()

        # Make values JSON serializable
        latest_records["date"] = (
            latest_records["date"]
            .dt.strftime("%Y-%m-%d")
        )

        if "start_time" in latest_records.columns:
            latest_records["start_time"] = (
                latest_records["start_time"]
                .astype(str)
            )

        if "end_time" in latest_records.columns:
            latest_records["end_time"] = (
                latest_records["end_time"]
                .astype(str)
            )

        return {
            "date": latest_date.strftime(
                "%Y-%m-%d"
            ),
            "usage": latest_records.to_dict(
                orient="records"
            )
        }

    except Exception as e:

        raise RuntimeError(
            f"Error reading CSV: {str(e)}"
        )


# ============================================================
# TOOL 2
# ============================================================

@tool(
    name="get_tomorrow_weather",
    description=(
        "Gets tomorrow's weather including "
        "temperature high, temperature low, "
        "and weather condition using Open-Meteo."
    ),
    approval_mode="never_require",
)
def get_tomorrow_weather(
    latitude: float,
    longitude: float,
    timezone: str
) -> dict:
    """
    Returns tomorrow's weather forecast.
    """

    tomorrow = (
        datetime.now() + timedelta(days=1)
    ).date().isoformat()

    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "weathercode"
        ),
        "forecast_days": 2
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    temp_max = data["daily"][
        "temperature_2m_max"
    ][1]

    temp_min = data["daily"][
        "temperature_2m_min"
    ][1]

    weather_code = data["daily"][
        "weathercode"
    ][1]

    code_map = {
        0: "Clear",
        1: "Mainly Clear",
        2: "Partly Cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing Rime Fog",
        51: "Light Drizzle",
        53: "Moderate Drizzle",
        55: "Dense Drizzle",
        61: "Rain",
        63: "Moderate Rain",
        65: "Heavy Rain",
        71: "Snow",
        80: "Rain Showers",
        81: "Moderate Rain Showers",
        82: "Heavy Rain Showers",
        95: "Thunderstorm",
    }

    condition = code_map.get(
        weather_code,
        "Unknown"
    )

    return {
        "date": tomorrow,
        "temp_high": temp_max,
        "temp_low": temp_min,
        "condition": condition
    }


# ============================================================
# TOOL 3
# ============================================================

@tool(
    name="forecast_next_day_kwh",
    description=(
        "Predict appliance-level next-day "
        "electricity consumption in kWh using "
        "the project's ML prediction model."
    ),
    approval_mode="never_require",
)
def forecast_next_day_kwh(
    appliance: str,
    date: str,
    avg_temp: float,
    hh_size: int,
    is_weekend: int
) -> dict:
    """
    Returns predicted kWh usage for an appliance.
    """

    try:

        return predict_next_day_kwh(
            appliance=appliance,
            ds_next=date,
            avg_temp=avg_temp,
            hh_size=hh_size,
            is_weekend=is_weekend
        )

    except Exception as e:

        raise RuntimeError(
            f"Prediction error: {str(e)}"
        )


# ============================================================
# CREATE USAGE COLLECTOR AGENT
# ============================================================

def create_usage_collector_agent():

    instructions = """
You are the UsageCollectorAgent for a Smart Home
Energy Saver system.

Your job is to collect all information required for
the RecommendationAgent.

Follow these steps:

1. Load the latest appliance usage from the CSV.
2. Get tomorrow's weather forecast using the weather tool.
3. Use the household profile provided in the prompt.
4. For every appliance present in the household,
   gather the next-day kWh forecast using the ML
   prediction tool.
5. Use the actual values returned by the tools.
6. Do not invent missing measurements.
7. Do not create recommendations yourself.

The final response MUST contain JSON ONLY.

Required structure:

{
  "last_usage": {},
  "weather": {},
  "forecasts": []
}

The forecasts list should contain the predicted
next-day consumption for the relevant appliances.
"""

    client = create_foundry_client()

    return Agent(
        name="UsageCollectorAgent",
        instructions=instructions,
        client=client,
        tools=[
            get_last_usage_from_csv,
            get_tomorrow_weather,
            forecast_next_day_kwh
        ],
    )


# ============================================================
# CREATE RECOMMENDATION AGENT
# ============================================================

def create_recommendation_agent():

    instructions = """
You are the RecommendationAgent for a Smart Home
Energy Saver system.

You receive:

- The household profile
- Recent appliance usage
- Tomorrow's weather forecast
- Next-day appliance-level kWh forecasts

Your responsibility is to analyze the information and
generate practical energy-saving recommendations.

Important rules:

1. Consider ALL appliances present in the household.
2. Compare recent usage with forecasted usage.
3. Consider tomorrow's weather.
4. Consider household size.
5. Consider realistic household behavior.
6. Consider peak and off-peak electricity periods.
7. Recommendations must be practical and feasible.
8. Do not force a recommendation when there is no
   meaningful opportunity to save energy.
9. Do not invent energy savings without reasonable
   support from the supplied data.
10. Estimated savings should be conservative.
11. Recommendations should be understandable to a
    normal household user.
12. Do not recommend unsafe electrical practices.
13. If there is insufficient information for a specific
    recommendation, clearly state that.

Return JSON ONLY.

Use exactly this structure:

{
  "summary": "Short explanation of tomorrow's expected energy situation.",
  "actions": [
    {
      "appliance": "Air Conditioning",
      "recommendation": "Practical recommended action",
      "estimated_kwh_saving": 0.5,
      "estimated_cost_saving": 4.5,
      "currency": "INR"
    }
  ]
}

If there is no meaningful saving opportunity for an
appliance, you may include it with an explanation and
zero estimated savings.

Do not include Markdown.
Do not include ```json.
Return only valid JSON.
"""

    client = create_foundry_client()

    return Agent(
        name="RecommendationAgent",
        instructions=instructions,
        client=client,
    )


# ============================================================
# AGENT EXECUTION
# ============================================================

async def run_agents(
    profile: HomeProfile
) -> dict:

    # --------------------------------------------------------
    # Create agents
    # --------------------------------------------------------

    collector_agent = create_usage_collector_agent()

    recommender_agent = create_recommendation_agent()

    # --------------------------------------------------------
    # Resolve city to latitude/longitude
    # --------------------------------------------------------

    try:

        if getattr(profile, "city", None):

            geores = geocode_city(
                profile.city
            )

            if geores:

                selected = geores[0]

                try:

                    profile.latitude = float(
                        selected.get(
                            "lat",
                            profile.latitude
                        )
                    )

                    profile.longitude = float(
                        selected.get(
                            "lon",
                            profile.longitude
                        )
                    )

                except Exception:

                    pass

    except Exception:

        pass

    # --------------------------------------------------------
    # Prepare tomorrow information
    # --------------------------------------------------------

    tomorrow = (
        datetime.now() + timedelta(days=1)
    )

    tomorrow_iso = iso_date(tomorrow)

    is_weekend = (
        1
        if tomorrow.weekday() >= 5
        else 0
    )

    # --------------------------------------------------------
    # Build collector prompt
    # --------------------------------------------------------

    raw_prompt = json.dumps(
        {
            "csv_path": CSV_PATH,

            "profile": profile.__dict__,

            "tomorrow_iso": tomorrow_iso,

            "is_weekend": is_weekend,
        },
        indent=2
    )

    # --------------------------------------------------------
    # Run UsageCollectorAgent
    # --------------------------------------------------------

    print("\n========================================")
    print("RUNNING USAGE COLLECTOR AGENT")
    print("========================================\n")

    collector_result = await collector_agent.run(
        f"""
Collect all required information for tomorrow.

Household information:

{raw_prompt}

Use the available tools to obtain:
1. Latest appliance usage
2. Tomorrow's weather
3. Next-day kWh forecasts for the appliances

Return JSON ONLY.
"""
    )

    collector_text = collector_result.text

    print("Collector response:")
    print(collector_text)

    collector_data = safe_json_extract(
        collector_text
    )

    # --------------------------------------------------------
    # Run RecommendationAgent
    # --------------------------------------------------------

    print("\n========================================")
    print("RUNNING RECOMMENDATION AGENT")
    print("========================================\n")

    recommendation_input = json.dumps(
        {
            "home_profile": profile.__dict__,
            "collector_data": collector_data,
        },
        indent=2
    )

    recommender_result = await recommender_agent.run(
        f"""
Analyze the following Smart Home Energy Saver data
and generate practical recommendations.

DATA:

{recommendation_input}

Return JSON ONLY using the required format.
"""
    )

    recommendation_text = (
        recommender_result.text
    )

    print("Recommendation response:")
    print(recommendation_text)

    # --------------------------------------------------------
    # Parse final response
    # --------------------------------------------------------

    final_result = safe_json_extract(
        recommendation_text
    )

    return final_result


# ============================================================
# SYNCHRONOUS WRAPPER
# ============================================================

def run_agent(
    profile: HomeProfile
) -> dict:
    """
    Synchronous wrapper around the asynchronous
    agent workflow.
    """

    return asyncio.run(
        run_agents(profile)
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    profile = HomeProfile(
        hh_size=4,

        appliances_present=[
            "Air Conditioning",
            "Washing Machine",
            "Dishwasher",
            "Microwave",
            "Computer"
        ]
    )

    try:

        output = run_agent(
            profile
        )

        print("\n========================================")
        print("FINAL SMART HOME ENERGY RECOMMENDATIONS")
        print("========================================\n")

        print(
            json.dumps(
                output,
                indent=2,
                ensure_ascii=False
            )
        )

    except Exception as e:

        print("\n========================================")
        print("ERROR")
        print("========================================\n")

        print(str(e))
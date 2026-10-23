# streamlit_app.py
# -----------------------------------------
# Streamlit UI for Home Energy Saver (Agentic AI)
# Consumes FastAPI endpoints:
#   - POST /optimize-energy
#   - POST /email-plan
# -----------------------------------------

import os
import json
import requests
import streamlit as st
from datetime import datetime
import pytz

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except Exception:
    PLOTLY_OK = False

# -------------------------------
# Config + constants
# -------------------------------
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")

APPLIANCE_CHOICES = [
    "Air Conditioning", "Washing Machine", "Dishwasher", "Microwave",
    "Computer", "Refrigerator", "Oven", "Heater", "TV",
]

# Default set of five appliance categories used by the model (no user selection required)
DEFAULT_APPLIANCES = [
    "Air Conditioning",
    "Washing Machine",
    "Dishwasher",
    "Heater",
    "Computer",
]

TIMEZONES = [
    "Asia/Kolkata", "UTC", "Europe/London", "America/New_York",
    "Asia/Singapore", "Australia/Sydney", "Europe/Berlin"
]

# -------------------------------
# Helper functions
# -------------------------------
def post_optimize_energy(payload: dict) -> dict:
    url = f"{BACKEND_BASE_URL}/optimize-energy"
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()

def post_email_plan(plan: dict, email: str, name: str) -> dict:
    url = f"{BACKEND_BASE_URL}/email-plan"
    payload = {"plan_json": plan, "email": email, "name": name}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()

def kpi_from_plan(plan: dict):
    kwh = None
    cost = None
    total_kwh = 0.0
    total_cost = 0.0
    currency = "INR"
    if isinstance(plan, dict):
        if "plan" in plan and isinstance(plan["plan"], dict) and "summary" in plan["plan"]:
            s = plan["plan"]["summary"]
            kwh = s.get("kwh")
            cost = s.get("cost")
            currency = s.get("currency", currency)
        elif "summary" in plan and isinstance(plan["summary"], dict):
            s = plan["summary"]
            kwh = s.get("kwh")
            cost = s.get("cost")
            currency = s.get("currency", currency)

        actions = plan.get("plan", {}).get("actions", []) or plan.get("actions", [])
        for action in actions:
            total_kwh += action.get("expected_kwh_saving", 0) or action.get("estimated_kwh_saving", 0)
            total_cost += action.get("expected_cost_saving", 0) or action.get("estimated_cost_saving", 0)

    return kwh, cost, currency, total_kwh, total_cost

def render_gauge_kwh(value: float, title: str = "Estimated kWh Saved", unit: str = "kWh"):
    """Render a Plotly gauge with a number suffix showing the unit and a thin threshold line as an indicator.

    Args:
        value: numeric value to display
        title: gauge title
        unit: unit string to add as suffix to the number (e.g., 'kWh' or '₹')
    """
    if not PLOTLY_OK:
        return None
    try:
        val = float(value or 0)
    except Exception:
        val = 0.0

    # Determine a reasonable maximum range for the gauge (avoid zero max)
    max_range = max(1.0, round(val * 2, 1))

    # Threshold value must lie within axis range
    thr_val = max(0.0, min(val, max_range))

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=val,
            number={"font": {"size": 16}, "suffix": f" {unit}"},
            title={"text": title, "font": {"size": 14}},
            gauge={
                "axis": {"range": [0, max_range]},
                # visible bar keeps a filled feel; threshold line acts as a needle/arrow indicator
                "bar": {"color": "#16a34a", "thickness": 0.35},
                "threshold": {
                    "line": {"color": "#065f46", "width": 6},
                    "thickness": 0.8,
                    "value": thr_val,
                },
            },
        )
    )
    fig.update_layout(margin=dict(t=15, b=5, l=5, r=5), height=180)
    return fig

def nice_rupees(x):
    try:
        return f"₹{float(x):,.2f}"
    except Exception:
        return "₹—"


def geocode_city(query: str, max_results: int = 5) -> list:
    """Return a list of geocoding matches for the given query using Nominatim.

    Each item is a dict with keys: display_name, lat, lon.
    """
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": query, "format": "json", "limit": max_results}
        headers = {"User-Agent": "HomeEnergySaver/1.0 (+https://example.com)"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data:
            results.append({
                "display_name": item.get("display_name", ""),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
            })
        return results
    except Exception:
        return []

def show_action_cards(plan: dict):
    actions = []
    if "plan" in plan and isinstance(plan["plan"], dict) and "actions" in plan["plan"]:
        actions = plan["plan"]["actions"]
    elif "actions" in plan and isinstance(plan["actions"], list):
        actions = plan["actions"]

    if not actions:
        st.warning("No actions were returned by the optimizer.")
        return

    for a in actions:
        with st.container():
            st.markdown(
                """
                <div style="background: linear-gradient(90deg, #f7faff 0%, #eef2ff 100%);
                            border:1px solid #dee3f0; padding:12px; border-radius:12px; margin-bottom:10px;">
                """,
                unsafe_allow_html=True
            )
            cols = st.columns([0.85, 0.15])
            with cols[0]:
                st.markdown(
                    f"**🛠️ Appliance:** {a.get('appliance', '—')}\n\n"
                    f"**💡 Recommendation:** {a.get('action') or a.get('recommendation', '—')}"
                )
            with cols[1]:
                st.markdown("&nbsp;")
            s_kwh = a.get("expected_kwh_saving") or a.get("estimated_kwh_saving")
            s_cost = a.get("expected_cost_saving") or a.get("estimated_cost_saving")
            currency = a.get("currency", "INR")
            if s_kwh is not None or s_cost is not None:
                st.markdown(
                    f"**📉 Estimated Savings:** "
                    f"{(str(s_kwh)+' kWh') if s_kwh is not None else ''}"
                    f"{' • ' if (s_kwh is not None and s_cost is not None) else ''}"
                    f"{(nice_rupees(s_cost) if currency=='INR' else str(s_cost)) if s_cost is not None else ''}"
                )
            st.markdown("</div>", unsafe_allow_html=True)

def show_weather(plan: dict):
    w = plan.get("weather")
    if not w:
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Tomorrow High", f"{w.get('temp_high','—')} °C")
    c2.metric("Tomorrow Low", f"{w.get('temp_low','—')} °C")
    c3.metric("Condition", w.get("condition", "—"))

def show_forecasts(plan: dict):
    fcs = plan.get("forecasts") or []
    if not fcs:
        return
    st.markdown("### 📊 Appliance Forecasts")
    for fc in fcs:
        with st.expander(f"🔎 {fc.get('appliance', 'Appliance')} — details"):
            st.json(fc)

def decorate_header():
    st.markdown(
        """
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;margin-bottom:12px;">
          <div style="padding:8px 16px;border-radius:999px;background:linear-gradient(90deg, #cce5ff, #b3d9ff);border:1px solid #99ccff;color:#003366;font-weight:bold;">
            🌟 Agentic AI 🌟
          </div>
          <div style="color:#33475b;margin-top:10px;font-size:14px;text-align:center;max-width:720px;">
            Harness the power of <span style="color:#007acc;font-weight:bold;">Agentic AI</span> to predict tomorrow’s energy usage, optimize your settings, and automate daily reports effortlessly.
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# -------------------------------
# Streamlit layout
# -------------------------------
st.set_page_config(page_title="Home Energy Saver", page_icon="⚡", layout="wide")
decorate_header()

# Improved CSS
st.markdown(
    """
    <style>
    body {
        background: linear-gradient(180deg, #eaf3ff 0%, #f4fff8 100%);
        font-family: 'Segoe UI', Roboto, Arial, sans-serif;
        color: #2a2e35;
    }
    .stApp {
        padding: 16px;
    }
    h1 {
        font-size: 1.6rem !important;
        font-weight: 700;
    }
    .metric {
        font-size: 0.9rem !important;
    }
    .subtitle {
        color: #63748a;
        font-size: 0.95rem;
    }
    .gauge-container {
        max-width: 260px;
        margin: 0 auto;
    }
    .stPlotlyChart {
        padding: 6px !important;
    }
    /* Stylish green-gradient buttons for main actions */
    .stButton > button {
        background: linear-gradient(90deg, #16a34a 0%, #4ade80 100%);
        color: #ffffff;
        border: none;
        padding: 10px 18px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.98rem;
        box-shadow: 0 8px 20px rgba(16,185,129,0.14);
        transition: transform 0.12s ease, box-shadow 0.12s ease, opacity 0.12s ease;
        cursor: pointer;
        width: 100%;
    }
    .stButton > button:hover:not(:disabled) {
        transform: translateY(-3px);
        box-shadow: 0 14px 34px rgba(16,185,129,0.18);
        opacity: 0.98;
    }
    .stButton > button:active:not(:disabled) {
        transform: translateY(0);
        box-shadow: 0 6px 14px rgba(16,185,129,0.12);
    }
    .stButton > button[disabled], .stButton > button[aria-disabled="true"] {
        background: linear-gradient(90deg,#eef6ef 0%, #f7fbf7 100%);
        color: #9aa7a0;
        border: 1px solid #e6f3ea;
        box-shadow: none;
        cursor: default;
    }
    /* Inline spinner for button-level feedback */
    .inline-spinner {
        border: 3px solid rgba(0,0,0,0.06);
        border-top: 3px solid #16a34a;
        border-radius: 50%;
        width: 16px;
        height: 16px;
        display: inline-block;
        vertical-align: middle;
        animation: spin 1s linear infinite;
        margin-right: 6px;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    @media (max-width: 600px) {
        h1 { font-size: 1.2rem !important; }
        .gauge-container { max-width: 220px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Top-level header
st.markdown(
    """
    <div style="text-align: center; padding: 16px 0;">
        <div class="subtitle" style="font-size: 1.1rem; color: #33475b; margin-top: 8px;">
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if "plan" not in st.session_state:
    st.session_state.plan = None

# Sidebar
with st.sidebar:
    st.subheader("⚙️ Input Parameters")
    hh_size = st.number_input("Household size", min_value=1, max_value=20, value=4, step=1)
    # Appliance selection is intentionally omitted: the model computes recommendations
    # for the default five appliance categories. Display an informational note so users
    # know which categories will be used.
    st.markdown("**Appliances:** Using default categories (no selection required)")
    st.caption("Default categories: " + ", ".join(DEFAULT_APPLIANCES))
    # Use the fixed default appliance list when building requests
    appliances = list(DEFAULT_APPLIANCES)
    st.markdown("---")
    st.caption("📍 Location")
    # Simplified UI: user provides only a city name. We resolve coords silently
    # and pick the closest match on Generate (no coordinate selection shown).
    city_query = st.text_input("City", value="Pune, India", key="city_query")

    # Default coordinates (used if geocoding fails)
    latitude = 18.6298
    longitude = 73.7997
    timezone = st.selectbox("Timezone", TIMEZONES, index=TIMEZONES.index("Asia/Kolkata"))
    st.markdown("---")
    st.caption("💵 Tariff")
    rate_peak = st.slider("Peak rate (INR/kWh)", min_value=0.0, max_value=20.0, value=12.0, step=0.1)
    rate_offpeak = st.slider("Off-peak rate (INR/kWh)", min_value=0.0, max_value=20.0, value=7.5, step=0.1)

    # Ensure tariff_peak_start and tariff_peak_end persist across reruns
    if "tariff_peak_start" not in st.session_state:
        st.session_state.tariff_peak_start = datetime.now().replace(hour=18, minute=0, second=0).time()
    if "tariff_peak_end" not in st.session_state:
        st.session_state.tariff_peak_end = datetime.now().replace(hour=22, minute=0, second=0).time()

    tariff_peak_start = st.time_input(
        "Peak start",
        value=st.session_state.tariff_peak_start,
        key="tariff_peak_start_input",
    )
    st.session_state.tariff_peak_start = tariff_peak_start

    tariff_peak_end = st.time_input(
        "Peak end",
        value=st.session_state.tariff_peak_end,
        key="tariff_peak_end_input",
    )
    st.session_state.tariff_peak_end = tariff_peak_end

    st.markdown("---")
    email_to = st.text_input("Email to send plan (optional)")
    sender_name = st.text_input("Recipient name for email salutation", value="User")
    auto_hint = st.checkbox("Show daily automation hint", value=True)

# Main actions
# Button state: we will use a session flag to control sending so we can show
# an inline status next to the button while the network call is in progress.
if "send_email_requested" not in st.session_state:
    st.session_state.send_email_requested = False
if "email_sending" not in st.session_state:
    st.session_state.email_sending = False

def _request_send_email():
    st.session_state.send_email_requested = True


controls_row = st.container()
with controls_row:
    c_run, c_email = st.columns([0.5, 0.5])
    with c_run:
        run_btn = st.button("Generate Optimization Plan", use_container_width=True, type="primary", key="generate_plan_btn")
    with c_email:
        btn_col, status_col = st.columns([0.78, 0.22])
        with btn_col:
            # Use on_click so we set a session flag and handle the send flow below
            st.button("✉️ Send Plan by Email", use_container_width=True, key="email_plan_btn", on_click=_request_send_email)
        # small placeholder column to render inline spinner / text
        email_status_placeholder = status_col.empty()
        if not st.session_state.get("plan"):
            # guidance text shown beside the button
            email_status_placeholder.caption("Generate plan first")

# Generate plan
if run_btn:
    # Resolve city -> lat/lon automatically (pick the first/closest match)
    selected_city_display = None
    try:
        if city_query and city_query.strip():
            geores = geocode_city(city_query.strip(), max_results=3)
            if geores:
                sel = geores[0]
                try:
                    latitude = float(sel.get("lat", latitude))
                    longitude = float(sel.get("lon", longitude))
                    selected_city_display = sel.get("display_name")
                except Exception:
                    # keep defaults if conversion fails
                    pass
    except Exception:
        # If geocoding fails for any reason, fall back to defaults
        latitude = latitude
        longitude = longitude

    req = {
        "hh_size": int(hh_size),
        "appliances_present": appliances,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "timezone": timezone,
        "rate_peak": float(rate_peak),
        "rate_offpeak": float(rate_offpeak),
        "tariff_peak_start": tariff_peak_start.strftime("%H:%M"),
        "tariff_peak_end": tariff_peak_end.strftime("%H:%M"),
    }
    if selected_city_display:
        # show friendly location confirmation (no coordinates shown)
        st.caption(f"Using location: {selected_city_display}")
    try:
        with st.spinner("Calling optimizer…"):
            plan = post_optimize_energy(req)
        st.session_state.plan = plan
        st.success("Optimization complete.")
    except requests.HTTPError as e:
        st.error(f"API error: {e.response.text if e.response is not None else e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")

# Display results
if st.session_state.plan:
    st.markdown("### Your Optimized Energy Plan")

    # Weather
    show_weather(st.session_state.plan)

    # KPI
    _, _, currency, total_kwh, total_cost = kpi_from_plan(st.session_state.plan)

    # Gauges
    if PLOTLY_OK:
        st.markdown("##### 📟 Savings Overview")
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(render_gauge_kwh(total_kwh, "kWh Saved", unit="kWh"), use_container_width=True)
        with col2:
            # Use currency symbol as unit for the cost gauge
            st.plotly_chart(render_gauge_kwh(total_cost, "₹ Saved", unit="₹"), use_container_width=True)

    # Recommendations
    st.markdown("#### Recommendations")
    show_action_cards(st.session_state.plan)

    # Forecast details
    show_forecasts(st.session_state.plan)

# Send email flow triggered via on_click -> session flag
if st.session_state.get("send_email_requested"):
    # Use the small status placeholder beside the button to show progress
    try:
        if not email_to:
            email_status_placeholder.warning("Please provide an email address.")
            st.session_state.send_email_requested = False
        elif not st.session_state.plan:
            email_status_placeholder.warning("Generate the plan first.")
            st.session_state.send_email_requested = False
        else:
            st.session_state.email_sending = True
            # Render a compact inline spinner next to the button
            email_status_placeholder.markdown('<div class="inline-spinner"></div> Sending...', unsafe_allow_html=True)
            try:
                with st.spinner("Sending email..."):
                    res = post_email_plan(st.session_state.plan, email_to, sender_name)
                email_status_placeholder.success("Sent")
                st.success(f"Email sent to {email_to}")
                st.json(res)
            except requests.HTTPError as e:
                email_status_placeholder.error("Send failed")
                st.error(f"Email API error: {e.response.text if e.response is not None else e}")
            except Exception as e:
                email_status_placeholder.error("Send failed")
                st.error(f"Unexpected error: {e}")
            finally:
                st.session_state.email_sending = False
                st.session_state.send_email_requested = False
    except NameError:
        # If placeholder isn't available for any reason, fallback to original flow
        if not email_to:
            st.warning("Please provide an email address.")
        elif not st.session_state.plan:
            st.warning("Generate the plan first.")
        else:
            try:
                with st.spinner("Sending email..."):
                    res = post_email_plan(st.session_state.plan, email_to, sender_name)
                st.success(f"Email sent to {email_to}")
                st.json(res)
            except requests.HTTPError as e:
                st.error(f"Email API error: {e.response.text if e.response is not None else e}")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

# Footer
st.markdown(
    """
    <div style="text-align:center;color:#94a3b8;margin-top:30px;font-size:0.85rem;">
      Built with ❤️ using FastAPI · Microsoft Agent Framework · Streamlit
    </div>
    """,
    unsafe_allow_html=True
)

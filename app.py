import streamlit as st # type: ignore # Import Streamlit for the UI dashboard
import time # Import time to handle the refresh delay
import random # Import random to deterministically assign map coordinates
import json # Import json for our fallback
import os # Import os for file checking
from typing import Any, Dict, List # Import robust typing for Pyre
import pandas as pd # type: ignore # Import pandas to format data for the line chart
import pydeck as pdk # type: ignore # Import pydeck for 3D mapping
import firebase_admin # type: ignore # Import firebase_admin to connect to Firestore
from firebase_admin import credentials, firestore # type: ignore # Import credentials and firestore

# Configure the Streamlit page layout and title
st.set_page_config(page_title="Smart Grid Dashboard", page_icon="⚡", layout="wide")

# Custom CSS for a professional utility dashboard look
st.markdown("""
<style>
    /* Dark utility theme */
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    
    /* Style the big metric text */
    [data-testid="stMetricValue"] {
        font-size: 4rem;
        font-family: monospace;
        color: #58a6ff;
        text-shadow: 0 0 10px rgba(88, 166, 255, 0.3);
    }
    
    /* Make expanders and containers look like dashboard panels */
    [data-testid="stExpander"] {
        background-color: #161b22;
        border-radius: 8px;
        border: 1px solid #30363d;
    }
    
    /* Style headers */
    h1, h2, h3 {
        font-family: 'Segoe UI', sans-serif;
        font-weight: 300;
        letter-spacing: 1px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize the Firebase connection (checking if it's already initialized to prevent errors on refresh)
if not firebase_admin._apps:
    # Check if we are running on Streamlit Cloud (where secrets are defined)
    if "firebase" in st.secrets:
        # Load credentials from Streamlit secrets
        firebase_credentials = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_credentials)
    else:
        # Fallback to local JSON file
        cred = credentials.Certificate("e-smart-grid-firebase-adminsdk-fbsvc-1d2f3b9c69.json")
    firebase_admin.initialize_app(cred)

db = firestore.client() # Create the database client

st.title("⚡ Smart Grid Command Center")
st.markdown("Real-time monitoring of regional grid load and individual node distribution.")

# Fetch data from Firebase Firestore
houses: List[Dict[str, Any]] = []
total_load = 0

try:
    docs = db.collection('simulations').stream()
    # Loop through the database documents and extract their data
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        houses.append(data)
        total_load += data.get('watts', 0)
except Exception as e:
    # Firebase Quota Exceeded Fallback
    st.sidebar.warning("⚠️ Firebase Free Tier Quota Exceeded. Streaming via Local Telemetry Fallback.")
    if os.path.exists("simulations_fallback.json"):
        with open("simulations_fallback.json", "r") as f:
            import typing
            loaded_data = json.load(f)
            houses = typing.cast(List[Dict[str, Any]], loaded_data)
            total_load = sum(int(h.get('watts', 0)) for h in houses)

# Initialize a blink toggle variable in session_state for our blinking red dots
if 'blink_state' not in st.session_state:
    st.session_state.blink_state = True
else:
    st.session_state.blink_state = not st.session_state.blink_state



# Curated list of exact coordinates mapped directly to residential house footprints in Cypress, TX
cypress_houses = [
    (29.9678, -95.7001), (29.9682, -95.7005), (29.9691, -95.7012),
    (29.9723, -95.6945), (29.9734, -95.6952), (29.9741, -95.6961),
    (29.9801, -95.7112), (29.9812, -95.7121), (29.9823, -95.7130),
    (29.9912, -95.7253), (29.9918, -95.7262), (29.9925, -95.7271),
    (29.9955, -95.7301), (29.9951, -95.7312), (29.9967, -95.7323),
    (30.0011, -95.7421), (30.0022, -95.7432), (30.0033, -95.7443),
    (30.0051, -95.7481), (30.0062, -95.7492)
]

for i, house_data in enumerate(houses):
    house_id = str(house_data.get('id', ''))
    watts = int(house_data.get('watts', 0))
    status = str(house_data.get('status', 'ON'))
    
    # Map the house to an exact physical footprint based on its ID
    coord_index = i % len(cypress_houses)
    house_data['lat'] = float(cypress_houses[coord_index][0])
    house_data['lon'] = float(cypress_houses[coord_index][1])
    
    # Set Pydeck color based on status and load
    if status == 'OFF':
        # Blinking Red if TRIPPED
        if st.session_state.blink_state:
            house_data['color'] = [255, 50, 50, 255] # Bright Red
        else:
            house_data['color'] = [100, 0, 0, 200] # Dark Red / off-state
    elif watts > 5000:
        # Yellow for High Load (> 5kW)
        house_data['color'] = [255, 200, 50, 255] # Bright Yellow
    else:
        # Green for Normal Load
        house_data['color'] = [50, 255, 50, 200] # Bright Green

# Sort houses numerically by the number in their ID (e.g. House_1, House_2)
houses = sorted(houses, key=lambda x: int(x['id'].split('_')[1]))

# 1. THE BIG METER (Total Grid Load)
meter_col1, meter_col2 = st.columns([1, 2])

with meter_col1:
    # Display the big numbered metric in kW
    st.metric(label="Current Draw", value=f"{float(total_load) / 1000.0:,.1f} kW")

with meter_col2:
    # Logic to show the Red/Green Box and Progress Bar
    if total_load > 50000:
        st.error("🚨 TRANSFORMER OVERLOAD! (> 50 kW Limit Reached)")
    else:
        st.success("✅ Transformer Operating Normally (Capacity < 50 kW)")
        
    # Calculate progress for a visual capacity meter (Max 50,000W for visual scale)
    progress_value = min(float(total_load) / 50000.0, 1.0)
    st.progress(progress_value, text="Transformer Capacity Meter")

st.divider() # Draw a horizontal line separating the sections



# 2. PYDECK 3D MAP
st.subheader("🗺️ Regional Power Map (Cypress, TX)")

# Streamlit Toggle for 2D vs 3D Map View
is_3d = st.toggle("Enable 3D Pillar View", value=True)
map_pitch = 50 if is_3d else 0
map_elevation_scale = 0.5 if is_3d else 0

# Create a TileLayer using standard Google Maps Satellite imagery
satellite_layer = pdk.Layer(
    "TileLayer",
    data="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    max_zoom=19,
    min_zoom=0,
    get_image="url",
)

layer = pdk.Layer(
    'ColumnLayer',
    data=pd.DataFrame(houses),
    get_position=['lon', 'lat'],
    get_elevation='watts',
    elevation_scale=map_elevation_scale, # Dynamically collapse pillars to flat circles if 2D
    radius=12, # Scale down to the exact footprint of a single physical house!
    get_fill_color='color',
    pickable=True,
    auto_highlight=True,
)

view_state = pdk.ViewState(
    latitude=29.993589,
    longitude=-95.725313,
    zoom=14, # Zoom in significantly closer so we can see the exact rooftops
    pitch=map_pitch, # Switch from overhead map to 3D angled
    bearing=0
)

st.pydeck_chart(pdk.Deck(
    map_style=None, # Disable mapbox to use our own Google Satellite tiles
    initial_view_state=view_state,
    layers=[satellite_layer, layer],
    tooltip={"text": "Household: {id}\nCurrent Draw: {watts} W\nBreaker Status: {status}"}
))

st.divider() # Draw another horizontal line

# 2. LIST OF ALL HOUSES DATA GRID
st.subheader(f"🏢 Monitored Nodes ({len(houses)} Active Connections)")

# Format the data for a clean dataframe view instead of 100 individual columns, which looks messy
df_houses = pd.DataFrame(houses)
if not df_houses.empty:
    # Reorder and format columns
    df_houses = df_houses[['id', 'watts', 'status']]
    df_houses.columns = ['Node ID', 'Current Load (W)', 'Breaker Status']
    
    # Display as a dataframe that takes up the width of the page
    st.dataframe(
        df_houses,
        use_container_width=True,
        hide_index=True,
        height=400 # Allow scrolling through the 100 houses
    )

# 3. REAL-TIME REFRESH
# Pause for 2 seconds, then tell Streamlit to rerun the entire script to fetch fresh data
time.sleep(2)
st.rerun()

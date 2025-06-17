import streamlit as st
import pandas as pd
import folium
from folium import LinearColormap
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import numpy as np
from scipy.spatial import cKDTree

st.set_page_config(layout="centered", page_title="Savills EV Charger Site Analyser", page_icon="🏢")

# --- CSS Styling for Savills look ---
st.markdown(
    """
    <style>
    /* Use Savills red and clean font */
    @import url('https://fonts.googleapis.com/css2?family=Open+Sans&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Open Sans', sans-serif;
        background-color: #fafafa;
        color: #333333;
    }

    .css-1d391kg {  /* Streamlit main block - optional tweak */
        max-width: 900px;
        margin-left: auto;
        margin-right: auto;
    }

    /* Header with red accent */
    .stTitle {
        font-weight: 700 !important;
        color: #E10600 !important;
        letter-spacing: 1.2px;
        margin-bottom: 0.1rem;
    }

    /* Logo + title container */
    .logo-title-row {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1rem;
    }

    /* Site table styling */
    .dataframe tbody tr:hover {
        background-color: #ffe6e6 !important;
    }

    /* Info box with Savills red border and lighter red background */
    .stAlert > div:first-child {
        border-left: 5px solid #E10600 !important;
        background-color: #fff0f0 !important;
        color: #a30000 !important;
        font-weight: 600 !important;
    }

    /* Checkbox styling */
    .stCheckbox > div {
        color: #E10600 !important;
        font-weight: 600 !important;
    }

    /* Map caption */
    .map-caption {
        font-style: italic;
        color: #666666;
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Layout: logo and title side by side with styled container ---
col1, col2 = st.columns([1, 7])
with col1:
    st.image("logo.png", width=80)
with col2:
    st.markdown('<h1 class="stTitle">EV Charger Site Analyser</h1>', unsafe_allow_html=True)

# --- Helper functions and rest of your logic here ---

# --- Upload Section ---
uploaded_file = st.file_uploader("Upload your ranked sites CSV", type=["csv"])
sites = None

if uploaded_file is not None:
    sites = pd.read_csv(uploaded_file)
    required_cols = {
        "site_name", "latitude", "longitude", "use",
        "opening_hours", "land_accessibility"
    }
    if not required_cols.issubset(sites.columns):
        st.error(f"❌ Uploaded CSV is missing required columns: {required_cols - set(sites.columns)}")
        st.stop()

    st.write("Preview of your uploaded sites:")
    st.dataframe(sites.head())
else:
    st.info("Please upload a CSV with columns: site_name, latitude, longitude, use, opening_hours, land_accessibility.")
    st.stop()

# Load and process data as in your code
chargers, cleaned_dft, headroom = load_data()
sites = process_sites(sites, chargers, cleaned_dft, headroom)
sites = calculate_scores(sites)

# --- Table Display ---
display_df = sites[[
    "site_name", "composite_score", "traffic_level", "nearby_chargers", "headroom_mva", "use",
    "opening_hours", "land_accessibility"
]].copy()

display_df.rename(columns={
    "site_name": "Site Name",
    "composite_score": "Score",
    "traffic_level": "Traffic Level",
    "nearby_chargers": "Nearby Chargers",
    "headroom_mva": "Headroom (MVA)",
    "use": "Site Use",
    "opening_hours": "Opening Hours",
    "land_accessibility": "Land Accessibility"
}, inplace=True)

display_df["Score"] = display_df["Score"].round(2)
display_df["Headroom (MVA)"] = display_df["Headroom (MVA)"].round(0).astype(int)

st.header("📊 Ranked Sites Table")
st.dataframe(display_df, use_container_width=True)

# --- Map Display ---
st.header("🗺️ Sites Map with Rankings")
st.write("Additional points to include in the map:")
st.info("Based on the location, the following settings might take a few minutes to load")

show_chargers = st.checkbox("EV chargers", value=False)
show_substations = st.checkbox("Substations", value=False)

m = create_map(sites, chargers, headroom, show_chargers=show_chargers, show_substations=show_substations)

st.markdown('<div class="map-caption">Map showing site rankings: green = best, red = worst</div>', unsafe_allow_html=True)
st_folium(m, width=900, height=600, returned_objects=[])

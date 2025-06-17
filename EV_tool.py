import streamlit as st
import pandas as pd
import folium
from folium import LinearColormap
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import numpy as np
from scipy.spatial import cKDTree

st.set_page_config(layout="wide")

# Sidebar Navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Input", "Map", "Output"])


# Load static data once
@st.cache_data
def load_data():
    cleaned_dft = pd.read_csv("cleaned_dft.zip", compression='zip')
    chargers = pd.read_csv("chargers.csv")
    headroom = pd.read_csv("headroom.csv")
    cleaned_dft = cleaned_dft.sort_values("year").drop_duplicates(subset=["count_point_id"], keep="last")
    return chargers, cleaned_dft, headroom


chargers, cleaned_dft, headroom = load_data()


# Helper Functions (same as in your original script)
def latlon_to_xyz(lat, lon):
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    R = 6371
    x = R * np.cos(lat_rad) * np.cos(lon_rad)
    y = R * np.cos(lat_rad) * np.sin(lon_rad)
    z = R * np.sin(lat_rad)
    return np.vstack((x, y, z)).T


def process_sites(sites, chargers, cleaned_dft, headroom):
    # Same as in original
    ...
    return sites


def calculate_scores(sites):
    # Same as in original
    ...
    return sites


def create_map(sites, chargers, substations, show_chargers=True, show_substations=True):
    # Same as in original
    ...
    return folium_map


# --- Page: Input ---
if page == "Input":
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image("logo.png", width=80)
    with col2:
        st.title("EV Charger Site Analyser")

    st.header("📤 Upload Site Data")
    uploaded_file = st.file_uploader("Upload your ranked sites CSV", type=["csv"])

    if uploaded_file:
        sites = pd.read_csv(uploaded_file)
        required_cols = {"site_name", "latitude", "longitude", "use", "opening_hours", "land_accessibility"}
        if not required_cols.issubset(sites.columns):
            st.error(f"❌ Uploaded CSV is missing required columns: {required_cols - set(sites.columns)}")
            st.stop()

        st.session_state["sites_raw"] = sites
        st.success("✅ File uploaded successfully. Go to the Output tab to process it.")
        st.dataframe(sites.head())
    else:
        st.info("Upload a CSV with: site_name, latitude, longitude, use, opening_hours, land_accessibility.")

# --- Page: Output ---
elif page == "Output":
    st.title("📊 Ranked Sites Output")

    if "sites_raw" not in st.session_state:
        st.warning("Please upload a file on the Input page first.")
        st.stop()

    sites = process_sites(st.session_state["sites_raw"], chargers, cleaned_dft, headroom)
    sites = calculate_scores(sites)
    st.session_state["sites_scored"] = sites  # Store for map use

    display_df = sites[[
        "site_name", "composite_score", "traffic_level", "nearby_chargers",
        "headroom_mva", "use", "opening_hours", "land_accessibility"
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

    display_df["Headroom (MVA)"] = display_df["Headroom (MVA)"].round(0).astype(int)

    st.dataframe(display_df)

# --- Page: Map ---
elif page == "Map":
    st.title("🗺️ Site Rankings Map")

    if "sites_scored" not in st.session_state:
        st.warning("Please process your site data on the Output page first.")
        st.stop()

    show_chargers = st.checkbox("Show EV Chargers", value=True)
    show_substations = st.checkbox("Show Substations", value=True)

    m = create_map(
        st.session_state["sites_scored"],
        chargers,
        headroom,
        show_chargers=show_chargers,
        show_substations=show_substations
    )


    st.caption("Green = best sites, Red = lower ranked")
    st_folium(m, width=1000, height=600, returned_objects=[])

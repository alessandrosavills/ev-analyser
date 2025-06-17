import streamlit as st
import pandas as pd
import folium
from folium import LinearColormap
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import numpy as np
from scipy.spatial import cKDTree

st.set_page_config(layout="centered")

# Layout
col1, col2 = st.columns([1, 8])
with col1:
    st.image("logo.png", width=80)
with col2:
    st.title("EV Charger Site Analyser")

# --- Helper Functions ---
def latlon_to_xyz(lat, lon):
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    R = 6371
    x = R * np.cos(lat_rad) * np.cos(lon_rad)
    y = R * np.cos(lat_rad) * np.sin(lon_rad)
    z = R * np.sin(lat_rad)
    return np.vstack((x, y, z)).T

def load_data():
    cleaned_dft = pd.read_csv("cleaned_dft.csv.gz", compression='gzip')
    chargers = pd.read_csv(
        r"chargers.csv")
    headroom = pd.read_csv(
        r"headroom.csv")
    cleaned_dft = cleaned_dft.sort_values("year").drop_duplicates(subset=["count_point_id"], keep="last")
    return chargers, cleaned_dft, headroom

def process_sites(sites, chargers, cleaned_dft, headroom):
    dft_xyz = latlon_to_xyz(cleaned_dft["latitude"].values, cleaned_dft["longitude"].values)
    dft_tree = cKDTree(dft_xyz)
    sites_xyz = latlon_to_xyz(sites["latitude"].values, sites["longitude"].values)

    # Traffic count within 1 km radius
    radius_km = 1.0
    indices_within_radius = dft_tree.query_ball_point(sites_xyz, r=radius_km)
    traffic_counts = [
        cleaned_dft.iloc[idx]["cars_and_taxis"].sum() if idx else 0
        for idx in indices_within_radius
    ]
    sites["traffic_count"] = traffic_counts

    # Categorise traffic level
    bins = [0, 3503, 16210, 41627, 96626, 1_233_284]
    labels = ["Very Low", "Low", "Medium", "High", "Very High"]
    sites["traffic_level"] = pd.cut(
        sites["traffic_count"],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=False  # to keep intervals left-closed, right-open (optional)
    )

    # Nearby chargers
    chargers = chargers.dropna(subset=["latitude", "longitude"])
    chargers_xyz = latlon_to_xyz(chargers["latitude"].values, chargers["longitude"].values)
    chargers_tree = cKDTree(chargers_xyz)
    nearby_indices = chargers_tree.query_ball_point(sites_xyz, r=1.0)
    sites["nearby_chargers"] = [len(idx_list) for idx_list in nearby_indices]

    # Use score
    use_map = {
        "residential": 4,
        "public": 3,
        "retail": 2,
        "office": 1
    }
    sites["use_score"] = sites["use"].str.lower().map(use_map).fillna(1)

    # Grid headroom
    sub_xyz = latlon_to_xyz(headroom["latitude"].values, headroom["longitude"].values)
    sub_tree = cKDTree(sub_xyz)
    _, nearest_sub_indices = sub_tree.query(sites_xyz, k=1)
    sites["headroom_mva"] = headroom.iloc[nearest_sub_indices]["headroom_mva"].values

    # Normalisation
    sites["traffic_norm"] = (sites["traffic_count"] - sites["traffic_count"].min()) / (
        sites["traffic_count"].max() - sites["traffic_count"].min() + 1e-6)
    sites["grid_score"] = (sites["headroom_mva"] - sites["headroom_mva"].min()) / (
        sites["headroom_mva"].max() - sites["headroom_mva"].min() + 1e-6)

    return sites

def calculate_scores(sites):
    w_hours = 0.2
    w_land = 0.2
    w_grid = 0.2
    w_use = 0.1
    w_traffic = 0.3

    sites["total_score"] = (
        (sites["opening_hours"] / 24) * w_hours +
        sites["land_availability_score"] * w_land +
        sites["grid_score"] * w_grid +
        sites["use_score"] * w_use +
        sites["traffic_norm"] * w_traffic
    )

    penalty_per_charger = 0.05
    sites["composite_score"] = sites["total_score"] - penalty_per_charger * sites["nearby_chargers"]
    sites = sites.sort_values(by="composite_score", ascending=False).reset_index(drop=True)
    sites["final_rank"] = sites.index + 1
    return sites

def create_map(sites, chargers, substations, show_chargers=True, show_substations=True):
    map_center = [sites["latitude"].mean(), sites["longitude"].mean()]
    m = folium.Map(location=map_center, zoom_start=11, tiles="CartoDB positron")

    colormap = LinearColormap(colors=["green", "yellow", "red"],
                              vmin=sites["final_rank"].min(),
                              vmax=sites["final_rank"].max())

    for _, row in sites.iterrows():
        popup = folium.Popup(f"""
            <b>{row["site_name"]}</b><br>
            Traffic Level: {row["traffic_level"]}<br>
            Traffic Count: {int(row["traffic_count"])}<br>
            Headroom (MVA): {int(round(row["headroom_mva"]))}<br>
            Use: {row["use"]}<br>
            Opening Hours: {row["opening_hours"]}<br>
            Land Availability Score: {row["land_availability_score"]}
        """, max_width=300)

        color = colormap(row["final_rank"])
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=8,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=popup
        ).add_to(m)

    if show_chargers:
        charger_cluster = MarkerCluster(name="EV Chargers").add_to(m)
        for _, c in chargers.iterrows():
            folium.Marker(
                location=[c["latitude"], c["longitude"]],
                icon=folium.Icon(color="blue", icon="charging-station", prefix='fa'),
                popup=folium.Popup(f"Charger: {c.get('name', 'N/A')}", max_width=200)
            ).add_to(charger_cluster)

    if show_substations:
        substation_cluster = MarkerCluster(name="Substations").add_to(m)
        for _, s in substations.iterrows():
            popup_html = f"""
                <b>Substation</b><br>
                Name: {s.get('name', 'N/A')}<br>
                Headroom (MVA): {int(round(s.get('headroom_mva', 0)))}
            """
            folium.Marker(
                location=[s["latitude"], s["longitude"]],
                icon=folium.Icon(color="red", icon="bolt", prefix='fa'),
                popup=folium.Popup(popup_html, max_width=200)
            ).add_to(substation_cluster)

    folium.LayerControl().add_to(m)
    return m

# --- Upload Section ---
uploaded_file = st.file_uploader("Upload your ranked sites CSV", type=["csv"])
sites = None

if uploaded_file is not None:
    from chargers import get_chargers
    with st.spinner("Fetching latest charger data..."):
        get_chargers()

    sites = pd.read_csv(uploaded_file)
    required_cols = {
        "site_name", "latitude", "longitude", "use",
        "opening_hours", "land_availability_score"
    }
    if not required_cols.issubset(sites.columns):
        st.error(f"❌ Uploaded CSV is missing required columns: {required_cols - set(sites.columns)}")
        st.stop()

    st.write("Preview of your uploaded sites:")
    st.dataframe(sites.head())
else:
    st.info("Please upload a CSV with columns: site_name, latitude, longitude, use, opening_hours, land_availability_score.")
    st.stop()

chargers, cleaned_dft, headroom = load_data()
sites = process_sites(sites, chargers, cleaned_dft, headroom)
sites = calculate_scores(sites)

# --- Map Display ---
st.header("🗺️ Sites Map with Rankings")

st.caption("Based on the location, the following settingS might take a few minutes to load")
show_chargers = st.checkbox("EV chargers", value=False)
show_substations = st.checkbox("Substations", value=False)

m = create_map(sites, chargers, headroom, show_chargers=show_chargers, show_substations=show_substations)

st.caption("Map showing site rankings: green = best, red = worst")
st_folium(m, width=800, height=600, returned_objects=[])



# --- Table Display ---
display_df = sites[[
    "site_name", "traffic_level", "traffic_count", "headroom_mva", "use",
    "opening_hours", "land_availability_score"
]].copy()

display_df.rename(columns={
    "site_name": "Site Name",
    "traffic_level": "Traffic Level",
    "headroom_mva": "Headroom (MVA)",
    "use": "Site Use",
    "opening_hours": "Opening Hours",
    "land_availability_score": "Land Availability Score"
}, inplace=True)

display_df["Headroom (MVA)"] = display_df["Headroom (MVA)"].round(0).astype(int)

st.header("📊 Ranked Sites Table")
st.dataframe(display_df)

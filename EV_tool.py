import streamlit as st
import pandas as pd
import folium
from folium import LinearColormap
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import numpy as np
from scipy.spatial import cKDTree, distance_matrix

st.set_page_config(layout="centered")

# Layout: logo and title
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
    cleaned_dft = pd.read_csv("cleaned_dft.zip", compression='zip')
    chargers = pd.read_csv("chargers.csv")
    headroom = pd.read_csv("headroom.csv")
    cleaned_dft = cleaned_dft.sort_values("year").drop_duplicates(subset=["count_point_id"], keep="last")
    return chargers, cleaned_dft, headroom

def process_sites(sites, chargers, cleaned_dft, headroom):
    # Prepare DfT traffic points
    dft_xyz = latlon_to_xyz(cleaned_dft["latitude"].values, cleaned_dft["longitude"].values)
    sites_xyz = latlon_to_xyz(sites["latitude"].values, sites["longitude"].values)

    # --- Weighted Traffic Analysis (improved) ---
    distances = distance_matrix(sites_xyz, dft_xyz)  # shape: (n_sites, n_dft)
    weights = 1 / (distances + 0.1)  # Avoid division by zero

    # Optional: boost traffic weights by road category
    category_weight = {
        "Motorway": 1.5,
        "A Road": 1.2,
        "B Road": 1.0,
        "Minor Road": 0.5
    }
    cleaned_dft["category_boost"] = cleaned_dft["road_category"].map(category_weight).fillna(1)
    weighted_traffic = weights @ (cleaned_dft["cars_and_taxis"].values * cleaned_dft["category_boost"].values)
    sites["traffic_count"] = weighted_traffic

    # Categorise traffic level
    bins = [0, 3503, 16210, 41627, 96626, 1_233_284]
    labels = ["Very Low", "Low", "Medium", "High", "Very High"]
    sites["traffic_level"] = pd.cut(
        sites["traffic_count"],
        bins=bins,
        labels=labels,
        include_lowest=True,
        right=False
    )

    # --- Nearby EV chargers ---
    chargers = chargers.dropna(subset=["latitude", "longitude"])
    chargers_xyz = latlon_to_xyz(chargers["latitude"].values, chargers["longitude"].values)
    chargers_tree = cKDTree(chargers_xyz)
    nearby_indices = chargers_tree.query_ball_point(sites_xyz, r=1.0)
    sites["nearby_chargers"] = [len(idx_list) for idx_list in nearby_indices]

    # --- Use score ---
    use_map = {
        "residential": 95,
        "public": 60,
        "retail": 75,
        "office": 85
    }
    sites["use_score"] = sites["use"].str.lower().map(use_map).fillna(1)

    # --- Grid headroom ---
    sub_xyz = latlon_to_xyz(headroom["latitude"].values, headroom["longitude"].values)
    sub_tree = cKDTree(sub_xyz)
    _, nearest_sub_indices = sub_tree.query(sites_xyz, k=1)
    sites["headroom_mva"] = headroom.iloc[nearest_sub_indices]["headroom_mva"].values

    # --- Normalisation ---
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
        (sites["opening_hours"] / 24) * 100 * w_hours +
        sites["land_accessibility"] * w_land +
        sites["grid_score"] * 100 * w_grid +
        sites["use_score"] * w_use +
        sites["traffic_norm"] * 100 * w_traffic
    )

    penalty_per_charger = 0.05
    sites["composite_score"] = sites["total_score"] - penalty_per_charger * sites["nearby_chargers"]
    sites.loc[sites["headroom_mva"] <= 0, ["composite_score", "total_score"]] = 0

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
            Nearby EV Chargers: {row["nearby_chargers"]}<br>
            Headroom (MVA): {int(round(row["headroom_mva"]))}<br>
            Use: {row["use"]}<br>
            Opening Hours: {row["opening_hours"]}<br>
            Land Accessibility: {row["land_accessibility"]}
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
            headroom_val = s["headroom_mva"] if "headroom_mva" in s and pd.notna(s["headroom_mva"]) else 0
            popup_html = f"""
                <b>Substation</b><br>
                Name: {s.get('name', 'N/A')}<br>
                Headroom (MVA): {int(round(headroom_val))}
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
    st.warning("Please upload a CSV with columns: site_name, latitude, longitude, use, opening_hours, land_accessibility.")
    st.stop()

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
st.dataframe(display_df)

# --- Map Display ---
st.header("🗺️ Sites Map with Rankings")

st.write("Additional points to include in the map:")
st.info("Depending on the location, loading the full map may take a moment.")
show_chargers = st.checkbox("EV chargers", value=False)
show_substations = st.checkbox("Substations", value=False)

m = create_map(sites, chargers, headroom, show_chargers=show_chargers, show_substations=show_substations)
st.caption("Map showing site rankings: green = best, red = worst")
st_folium(m, width=800, height=600, returned_objects=[])

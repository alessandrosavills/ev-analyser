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


@st.cache_data(show_spinner=False)
def load_data():
    cleaned_dft = pd.read_csv("cleaned_dft.zip", compression='zip')
    chargers = pd.read_csv("chargers.csv")
    headroom = pd.read_csv("headroom.csv")
    cleaned_dft = cleaned_dft.sort_values("year").drop_duplicates(subset=["count_point_id"], keep="last")
    return chargers, cleaned_dft, headroom


def process_sites(sites, chargers, cleaned_dft, headroom):
    dft_xyz = latlon_to_xyz(cleaned_dft["latitude"].values, cleaned_dft["longitude"].values)
    sites_xyz = latlon_to_xyz(sites["latitude"].values, sites["longitude"].values)

    distances = distance_matrix(sites_xyz, dft_xyz)
    weights = 1 / (distances + 0.1)

    category_weight = {
        "Motorway": 1.5,
        "A Road": 1.2,
        "B Road": 1.0,
        "Minor Road": 0.5
    }
    cleaned_dft["category_boost"] = cleaned_dft["road_type"].map(category_weight).fillna(1)
    weighted_traffic = weights @ (cleaned_dft["cars_and_taxis"].values * cleaned_dft["category_boost"].values)
    sites["traffic_count"] = weighted_traffic

    labels = ["Very Low", "Low", "Medium", "High", "Very High"]
    try:
        sites["traffic_level"] = pd.qcut(sites["traffic_count"], q=5, labels=labels)
    except ValueError:
        sites["traffic_level"] = pd.cut(sites["traffic_count"], bins=5, labels=labels)

    chargers = chargers.dropna(subset=["latitude", "longitude"])
    chargers_xyz = latlon_to_xyz(chargers["latitude"].values, chargers["longitude"].values)
    chargers_tree = cKDTree(chargers_xyz)
    nearby_indices = chargers_tree.query_ball_point(sites_xyz, r=1.0)
    sites["nearby_chargers"] = [len(idx_list) for idx_list in nearby_indices]

    sub_xyz = latlon_to_xyz(headroom["latitude"].values, headroom["longitude"].values)
    sub_tree = cKDTree(sub_xyz)
    _, nearest_sub_indices = sub_tree.query(sites_xyz, k=1)
    sites["headroom_mva"] = headroom.iloc[nearest_sub_indices]["headroom_mva"].values

    sites["traffic_norm"] = (sites["traffic_count"] - sites["traffic_count"].min()) / (
            sites["traffic_count"].max() - sites["traffic_count"].min() + 1e-6)
    sites["grid_score"] = (sites["headroom_mva"] - sites["headroom_mva"].min()) / (
            sites["headroom_mva"].max() - sites["headroom_mva"].min() + 1e-6)

    return sites


def calculate_scores(sites, w_hours, w_land, w_grid, w_use, w_traffic):
    sites["total_score"] = (
            (sites["opening_hours"] / 24) * 100 * w_hours +
            sites["land_accessibility"] * w_land +
            sites["grid_score"] * 100 * w_grid +
            sites["use_score"] * w_use +
            sites["traffic_norm"] * 100 * w_traffic
    )
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
        st.error(f"\u274c Uploaded CSV is missing required columns: {required_cols - set(sites.columns)}")
        st.stop()
else:
    st.warning("Please upload a CSV with columns: site_name, latitude, longitude, use, opening_hours, land_accessibility.")
    st.stop()

# Load all other data
chargers, cleaned_dft, headroom = load_data()

# --- Sidebar Controls ---

st.markdown("Configuration Settings")

with st.expander("Use Class Suitability Configuration", expanded=False):
    unique_uses = sorted(sites["use"].dropna().str.lower().unique())
    use_map = {}

    cols = st.columns(2)
    for i, use_type in enumerate(unique_uses):
        default = 75 if "retail" in use_type else 85 if "office" in use_type else 95 if "residential" in use_type else 60
        col = cols[i % 2]
        use_map[use_type] = col.slider(
            label=f"{use_type.title()} suitability",
            min_value=0, max_value=100, value=default, step=5,
            help=f"Set suitability score for {use_type.title()} sites (0 = least suitable, 100 = most suitable)"
        )

with st.expander("Ranking Weights Configuration", expanded=False):
    col1, col2 = st.columns(2)
    w_hours = col1.slider("Opening Hours Weight", 0.0, 1.0, 0.2, 0.05,
                          help="Weight given to site's daily opening hours in ranking")
    w_land = col2.slider("Land Accessibility Weight", 0.0, 1.0, 0.2, 0.05,
                         help="Weight given to how easy the land is to access")
    w_grid = col1.slider("Grid Headroom Weight", 0.0, 1.0, 0.2, 0.05,
                         help="Weight given to electrical grid capacity near the site")
    w_use = col2.slider("Use Suitability Weight", 0.0, 1.0, 0.1, 0.05,
                        help="Weight given to the suitability score of the site’s use")
    w_traffic = col1.slider("Traffic Flow Weight", 0.0, 1.0, 0.3, 0.05,
                            help="Weight given to local traffic volume around the site")

with st.expander("EV Chargers Configuration", expanded=False):
    penalty_choice = st.selectbox(
        "Penalty per Nearby Charger",
        options=["None", "Low", "Medium", "High"],
        index=2,
        help="How much to penalize sites with nearby EV chargers to avoid oversaturation"
    )

penalty_map = {
    "None": 0.0,
    "Low": 0.01,
    "Medium": 0.05,
    "High": 0.1
}
penalty_per_charger = penalty_map[penalty_choice]

# Normalize weights to sum 1
total_weight = w_hours + w_land + w_grid + w_use + w_traffic
if total_weight > 0:
    w_hours /= total_weight
    w_land /= total_weight
    w_grid /= total_weight
    w_use /= total_weight
    w_traffic /= total_weight
else:
    # Avoid division by zero
    w_hours = w_land = w_grid = w_use = w_traffic = 0.2

# --- Processing and Calculations ---

# Map 'use' to 'use_score'
sites["use_score"] = sites["use"].str.lower().map(use_map).fillna(1)

# Process sites with traffic, chargers nearby, headroom, etc.
sites = process_sites(sites, chargers, cleaned_dft, headroom)

# Calculate total weighted score
sites = calculate_scores(sites, w_hours, w_land, w_grid, w_use, w_traffic)

# Apply penalty per nearby charger
sites["composite_score"] = sites["total_score"] - penalty_per_charger * sites["nearby_chargers"]

# Remove sites with no headroom
sites.loc[sites["headroom_mva"] <= 0, ["composite_score", "total_score"]] = 0

# Sort and rank
sites = sites.sort_values(by="composite_score", ascending=False).reset_index(drop=True)
sites["final_rank"] = sites.index + 1

# --- Table Display ---
display_df = sites[[
    "final_rank", "site_name", "composite_score", "traffic_level", "nearby_chargers", "headroom_mva", "use",
    "opening_hours", "land_accessibility"
]].copy()

display_df.rename(columns={
    "final_rank": "Rank",
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

st.header("Ranked Sites Table")
st.dataframe(display_df)

# --- Map Display ---
st.write("Additional points to include in the map:")
st.info("Depending on the location, loading the additional points may take a moment.")
show_chargers = st.checkbox("EV chargers", value=False)
show_substations = st.checkbox("Substations", value=False)

ev_map = create_map(sites, chargers, headroom, show_chargers=show_chargers, show_substations=show_substations)
st.caption("Map showing site rankings: green = best, red = worst")
st_folium(ev_map, width=1000, height=700)

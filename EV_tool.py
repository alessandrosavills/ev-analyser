import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from folium import LinearColormap
from streamlit_folium import st_folium

# Sample placeholder loading – replace these with your actual CSVs or DataFrames
@st.cache_data
def load_data():
    sites = pd.read_csv("data/sites.csv")  # Must contain: latitude, longitude, final_rank, etc.
    chargers = pd.read_csv("data/ev_chargers.csv")  # Must contain: latitude, longitude, name (optional)
    substations = pd.read_csv("data/substations.csv")  # Must contain: latitude, longitude, headroom_mva
    return sites, chargers, substations

def create_map(sites, chargers, substations, show_chargers=True, show_substations=True):
    map_center = [sites["latitude"].mean(), sites["longitude"].mean()]
    m = folium.Map(location=map_center, zoom_start=11, tiles="CartoDB positron")

    colormap = LinearColormap(colors=["green", "yellow", "red"],
                              vmin=sites["final_rank"].min(),
                              vmax=sites["final_rank"].max())

    # Add site markers
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

    # Add EV Chargers
    if show_chargers:
        charger_group = folium.FeatureGroup(name="EV Chargers")
        charger_cluster = MarkerCluster().add_to(charger_group)
        for _, c in chargers.iterrows():
            folium.Marker(
                location=[c["latitude"], c["longitude"]],
                icon=folium.Icon(color="blue", icon="charging-station", prefix='fa'),
                popup=folium.Popup(f"Charger: {c.get('name', 'N/A')}", max_width=200)
            ).add_to(charger_cluster)
        charger_group.add_to(m)

    # Add Substations
    if show_substations:
        substation_group = folium.FeatureGroup(name="Substations")
        substation_cluster = MarkerCluster().add_to(substation_group)
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
        substation_group.add_to(m)

    folium.LayerControl().add_to(m)
    return m

# Streamlit UI
st.set_page_config(page_title="EV Site Ranking Map", layout="wide")
st.title("EV Site Ranking Map")

# Load data
sites, chargers, substations = load_data()

# Sidebar options
with st.sidebar:
    st.header("Map Options")
    show_chargers = st.checkbox("Show EV Chargers", value=True)
    show_substations = st.checkbox("Show Substations", value=True)

# Create and display map
folium_map = create_map(sites, chargers, substations, show_chargers, show_substations)
st_folium(folium_map, width=1200, height=700)

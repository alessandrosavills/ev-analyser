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
                popup=folium.Popup(f"Charger: {c['name'] if 'name' in c else 'N/A'}", max_width=200)
            ).add_to(charger_cluster)

    if show_substations:
        substation_cluster = MarkerCluster(name="Substations").add_to(m)
        for _, s in substations.iterrows():
            # Use indexing with fallback instead of .get()
            name = s['name'] if 'name' in s else 'N/A'
            headroom_val = int(round(s['headroom_mva'])) if 'headroom_mva' in s else 0
            popup_html = f"""
                <b>Substation</b><br>
                Name: {name}<br>
                Headroom (MVA): {headroom_val}
            """
            folium.Marker(
                location=[s["latitude"], s["longitude"]],
                icon=folium.Icon(color="red", icon="bolt", prefix='fa'),
                popup=folium.Popup(popup_html, max_width=200)
            ).add_to(substation_cluster)

    folium.LayerControl().add_to(m)
    return m

import streamlit as st
import pandas as pd
import folium
import leafmap.foliumap as leafmap
from folium.plugins import MarkerCluster
import random

# Load dataset (replace with actual file path)
@st.cache_data
def load_data():
    df = pd.read_csv("place_names_historical.csv")  # Modify file path as needed
    
    # Ensure only rows with valid latitude & longitude are kept
    df = df.dropna(subset=["Latitude", "Longitude"])

    return df

# Load full data
df = load_data()

# Streamlit UI
st.title("🌍 Historical Place Name Viewer")
st.markdown("This interactive map displays geocoded historical place names.")

# Button to resample
if st.button("🔄 Resample Data"):
    sampled_df = df.sample(500, random_state=random.randint(1, 10000))  # New random seed for each resample
    st.experimental_rerun()
else:
    sampled_df = df.sample(500)  # Default sample

# Define color mapping for different location types
color_map = {'Coastal Feature':"blue", 'Town/Village':"red", 'Other':"black", 'River/Watercourse':"green",
       'Mountain':"grey", 'Bridge':"pink", 'Administrative Region':"navy", 'Fortress':"brown",
       'Island':"magenta", 'Mythological Place':"yellow", 'Lake':"blue", 'Country':"brown",
       'Nature Reserve':"green", 'Valley':"blue", 'Geographic Region':"black", 'Religious Site':"red",
       'Historical Landmark':"brown", 'Sea/Ocean':"blue", 'Unknown':"blue", 'Fictional Place':"green",
       'Historical Kingdom':"blue"}

# Create a Folium map
m = leafmap.Map(center=[10, 20], zoom=1)  # Default center near Scandinavia

# Create a Layer Control for toggling categories
layer_control = folium.LayerControl()

# Dictionary to store feature groups for each location type
feature_groups = {}

# Create a FeatureGroup for each location type
for loc_type in df["Category"].unique():
    feature_groups[loc_type] = folium.FeatureGroup(name=loc_type)
    m.add_child(feature_groups[loc_type])

# Add markers using folium with clustering
marker_cluster = MarkerCluster()

for _, row in sampled_df.iterrows():
    location_type = row["Category"]
    color = color_map.get(location_type, "black")  # Default to black if unknown type

    popup_text = f"""
    <b>{row['Input']}</b><br>
    Modern: {row['Modern Variant']}<br>
    Type: {row['Location Type']}<br>
    Area: {row['Larger Area']}<br>
    Lat: {row['Latitude']}, Lon: {row['Longitude']}
    """

    marker = folium.CircleMarker(
        location=[row["Latitude"], row["Longitude"]],
        radius=6,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.3,
        popup=folium.Popup(popup_text, max_width=300),
    )

    # Add marker to corresponding feature group
    feature_groups[location_type].add_child(marker)

# Add feature groups to the map
for feature_group in feature_groups.values():
    m.add_child(feature_group)

# Add layer control to allow toggling
m.add_child(folium.LayerControl(collapsed=False))

# Display the map in Streamlit
m.to_streamlit(height=600)

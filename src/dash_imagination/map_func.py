import importlib.resources as pkg_resources
import tempfile
from dataclasses import dataclass
from urllib.parse import quote

import folium
from folium.plugins import MarkerCluster
import leafmap.foliumap as leafmap
import numpy as np
import pandas as pd


# configure map constants
BASEMAP_OPTIONS = [
    "OpenStreetMap.Mapnik",
    "CartoDB.Positron",
    "CartoDB.DarkMatter",
]
WORLD_VIEW = {"center": [20, 0], "zoom": 2}
EUROPE_VIEW = {"center": [55, 15], "zoom": 4}


# Use global caching
_cached_data = {"corpus": None, "places": None, "lists": None}
_map_cache = {}


def get_data_path(filename):
    with pkg_resources.path("dash_imagination.data", filename) as path:
        return path


def load_corpus() -> pd.DataFrame:
    """Load the ImagiNation corpus as a DataFrame."""
    excel_path = get_data_path("imag_korpus.xlsx")
    corpus = pd.read_excel(excel_path, index_col=0)
    corpus["author"] = (
        corpus["author"].fillna("").apply(lambda x: x.replace("/", " "))
    )
    corpus["Verk"] = corpus.apply(
        lambda x: f"{x['title'] or 'Uten tittel'} av {x['author'] or 'Ingen'} ({x['year'] or 'n.d.'})",
        axis=1,
    )
    return corpus


# Cache functions
def get_cached_data():
    global _cached_data
    if _cached_data["corpus"] is None:
        # Load data once
        corpus = load_corpus()

        pkl_path = get_data_path("unique_places.pkl")
        places = pd.read_pickle(pkl_path)

        _cached_data["corpus"] = corpus
        _cached_data["places"] = places
        _cached_data["lists"] = {
            "authors": list(set(corpus.author)),
            "titles": list(set(corpus.Verk)),
            "categories": list(set(corpus.category)),
        }
    return _cached_data


def get_cached_map_html(cache_key, create_map_func):
    global _map_cache
    if cache_key not in _map_cache:
        _map_cache[cache_key] = create_map_func()
    return _map_cache[cache_key]


def clean_map_cache():
    global _map_cache
    if len(_map_cache) > 10:  # Only keep 10 most recent maps
        _map_cache.clear()


@dataclass
class feature_info:
    name: str
    description: str
    color: str
    icon: str


# Dict that replaced feature_colors, feature_descriptions, and color_emojis
features = {
    "P": feature_info("Populated place", "Befolkede steder", "red", "🔴"),
    "H": feature_info("Hydrographic", "Vann og vassdrag", "blue", "🔵"),
    "T": feature_info("Hypsographic", "Fjell og høyder", "green", "🟢"), 
    "L": feature_info("Area", "Parker og områder", "orange", "🟠"),
    "A": feature_info("Administrative", "Administrative steder", "purple", "🟣"), 
    "R": feature_info("Road", "Veier og jernbane", "darkred", "🟥"),
    "S": feature_info("Spot", "Bygninger og gårder", "darkblue", "🟦"),
    "V": feature_info("Vegetation", "Skog og mark", "darkgreen", "🟩"),    
}


# Helper function to convert Folium map to HTML string
def folium_to_html(m):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
        m.save(tmp.name)
        with open(tmp.name, "r", encoding="utf-8") as f:
            html_str = f.read()
    return html_str


def create_popup_html(place: dict, place_books: pd.DataFrame) -> str:
    """Display information about a place and its books in a popup HTML element."""
    html = f"""
    <div style='width:500px'>
        <h4>{place["token"]}</h4>
        <p><strong>Moderne navn:</strong> {place["name"]}</p>
        <p><strong>{place["frekv"]} forekomster i {len(place_books)} bøker</strong></p>
        <div style='max-height: 400px; overflow-y: auto;'>
            <table style='width: 100%; border-collapse: collapse;'>
                <thead style='position: sticky; top: 0; background: white;'>
                    <tr>
                        <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Title</th>
                        <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Author</th>
                        <th style='border: 1px solid #ddd; padding: 8px; text-align: left;'>Year</th>
                    </tr>
                </thead>
                <tbody>
    """

    for _, book in place_books.iterrows():
        book_url = (
            f'https://nb.no/items/{book.urn}?searchText="{quote(place["token"])}"'
        )
        html += f"""
            <tr>
                <td style='border: 1px solid #ddd; padding: 8px;'>
                    <a href='{book_url}' target='_blank'>{book.title}</a>
                </td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{book.author}</td>
                <td style='border: 1px solid #ddd; padding: 8px;'>{book.year}</td>
            </tr>
        """

    html += """
                </tbody>
            </table>
        </div>
    </div>
    """
    return html


# JavaScript function with blue colors for clusters
CLUSTER_JS = """
function(cluster) {
var childCount = cluster.getChildCount();
var total_freq = 0;

cluster.getAllChildMarkers().forEach(function(marker) {
    var popupContent = marker.getPopup().getContent();  // Access the popup content
    var freqMatch = popupContent.match(/data-frequency="(\d+(\.\d+)?)"/);  // Regex to extract frequency
    var freq = freqMatch ? parseFloat(freqMatch[1]) : 0;  // Parse frequency
    console.log('Extracted Frequency:', freq);  // Debugging
    total_freq += freq;
});

console.log('Total Frequency for Cluster:', total_freq);  // Debugging

var size = Math.max(Math.sqrt(total_freq) * 3, 30);  // Adjust size multiplier
size = Math.min(size, 200);  // Cap maximum size

return L.divIcon({
    html: '<div style="display: flex; align-items: center; justify-content: center;">' +
          '<div style="width: ' + size + 'px; height: ' + size + 'px; ' +
          'background-color: rgba(0, 0, 255, 0.3); ' +
          'border: 2px solid rgba(0, 0, 255, 0.8); ' +
          'display: flex; align-items: center; justify-content: center;">' +
          '<span style="color: white; font-weight: bold;">' + childCount + '</span>' +
          '</div></div>',
    className: 'marker-cluster-custom',
    iconSize: L.point(size, size),
    iconAnchor: L.point(size / 2, size / 2)
});
}

"""


# Currently used by the app 
def make_map(
    significant_places, corpus_df, basemap, marker_size, center=None, zoom=None
):
    """Create a map of significant places with markers clustered by feature class."""
    cache_key = f"{significant_places.shape[0]}_{basemap}_{marker_size}_{center}_{zoom}"

    def create_map():
        """Create the map with the specified parameters"""
        significant_places_clean = significant_places.dropna(
            subset=["latitude", "longitude"]
        )
        center_lat = (
            significant_places_clean["latitude"].median()
            if center is None
            else center[0]
        )
        center_lon = (
            significant_places_clean["longitude"].median()
            if center is None
            else center[1]
        )
        current_zoom = EUROPE_VIEW["zoom"] if zoom is None else zoom

        # Create the map with the specified center and zoom
        m = leafmap.Map(
            center=[center_lat, center_lon], zoom=current_zoom, basemap=basemap
        )

        ## Aggregate place name frequencies by feature class
        feature_frequencies = {}
        for feature_class in features.keys():
            feature_frequencies[feature_class] = significant_places[
                significant_places["feature_class"] == feature_class
            ]["frekv"].sum()

        ## Create MarkerClusters for each feature class
        feature_groups = {}
        for feature_class, details in features.items():
            # Add the frequency to the layer name
            freq = feature_frequencies.get(feature_class, 0)
            layer_name = f"{details.description} ({int(freq)} forekomster) {details.icon}"

            # Create a MarkerCluster for each feature group with your custom cluster_js
            marker_cluster = MarkerCluster(
                name=layer_name,
                icon_create_function=CLUSTER_JS, 
            ).add_to(m)

            feature_groups[feature_class] = marker_cluster

        # Create cluster groups for each feature class 
        # cluster_groups = {}
        # for feature_class, feature_info in features.items():
        #     cluster_groups[feature_class] = MarkerCluster(
        #         name=f"{feature_info.description} {feature_info.icon}",
        #         options={
        #             "spiderfyOnMaxZoom": True,
        #             "showCoverageOnHover": True,
        #             "zoomToBoundsOnClick": True,
        #             "maxClusterRadius": 40,
        #         },
    #             icon_create_function=f"""
    # function(cluster) {{
    # var childCount = cluster.getChildCount();
    # var size = Math.min(40 + Math.log(childCount) * 10, 80);  // Logarithmic scaling with upper limit
    # return L.divIcon({{
    #     html: '<div style="background-color: rgba(128, 128, 128, 0.4); width: ' + size + 'px; height: ' + size + 'px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid {features[feature_class].color};">' + childCount + '</div>',
    #     className: 'marker-cluster marker-cluster-{feature_class}',
    #     iconSize: L.point(size, size)
    # }});
    # }}
    # """,
    #         ).add_to(m)

        # Process places in batches for better memory management
        batch_size = 50
        for i in range(0, len(significant_places), batch_size):
            batch = significant_places.iloc[i : i + batch_size]

            # Individual markers remain red
            # Add markers to their respective feature clusters
            for _, place in batch.iterrows():
                place_books = corpus_df[corpus_df.dhlabid.isin(place["dhlabid"])]
                book_count = len(place_books)
                feature_class = place["feature_class"]
                feature_details = features.get(feature_class)

                popup_html = create_popup_html(place, place_books)

                radius = min(6 + np.log(place["frekv"]) * marker_size, 60)
                
                # Create a regular marker instead of CircleMarker (for clustering)
                #marker = folium.CircleMarker(
                marker = folium.Marker(
                    radius=radius,
                    location=[place["latitude"], place["longitude"]],
                    popup=folium.Popup(popup_html, max_width=500),
                    tooltip=f"{place['token']}: {place['frekv']} forekomster i {book_count} bøker",
                    color=feature_details.color,
                    fill=True,
                    fill_color=feature_details.color,
                    fill_opacity=0.4,
                    weight=2,
                    frequency=float(place["frekv"]),
                )
                marker.add_to(feature_groups[feature_class])

        folium.LayerControl(collapsed=False, position="topright").add_to(m)
        return folium_to_html(m)
    return get_cached_map_html(cache_key, create_map)


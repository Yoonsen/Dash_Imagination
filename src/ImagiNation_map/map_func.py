import pandas as pd
import numpy as np
import leafmap.foliumap as leafmap
import folium
from urllib.parse import quote



def make_map(significant_places, corpus_df, basemap, marker_size, center=None, zoom=None):
    # If center and zoom aren't provided, use defaults
    significant_places_clean = significant_places.dropna(subset=['latitude', 'longitude'])
    center_lat = significant_places_clean['latitude'].median()
    center_lon = significant_places_clean['longitude'].median()
    if center is None:
        center = [center_lat, 
                 center_lon]
    if zoom is None:
        zoom = 4
        
    # Create the map with the specified center and zoom
    m = leafmap.Map(
        center=center,
        zoom=zoom,
        basemap=basemap
    )
    

    
 
    

        
    
    # Updated JavaScript function with blue colors for clusters
    cluster_js = """
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
    


    # First, create a mapping for feature classes and their colors
    feature_colors = {
        'P': 'red',      # Populated places
        'H': 'blue',     # Hydrographic
        'T': 'green',    # Mountain,hill
        'L': 'orange',   # Parks,areas
        'A': 'purple',   # Administrative
        'R': 'darkred',  # Roads,railroads
        'S': 'darkblue', # Spots,buildings,farms
        'V': 'darkgreen' # Forest,heath
    }
    
    # Add feature descriptions
    feature_descriptions = {
        'P': 'Befolkede steder',     
        'H': 'Vann og vassdrag',     
        'T': 'Fjell og høyder',      
        'L': 'Parker og områder',    
        'A': 'Administrative',       
        'R': 'Veier og jernbane',    
        'S': 'Bygninger og gårder',  
        'V': 'Skog og mark'          
    }
    
    feature_groups = {}
    for feature_class, description in feature_descriptions.items():
        feature_groups[feature_class] = folium.FeatureGroup(name=description).add_to(m)
        
        
    # Individual markers remain red
    # Add markers to their respective feature clusters
    for _, place in significant_places.iterrows():
        place_books = corpus_df[corpus_df.dhlabid.isin(place['dhlabid'])]
        book_count = len(place_books)
        
        html = f"""
        <div style='width:500px'>
            <h4>{place['name']}</h4>
            <p><strong>Historisk navn:</strong> {place['token']}</p>
            <p><strong>{place['frekv']} forekomster i {book_count} bøker</strong></p>
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
            book_url = f"https://nb.no/items/{book.urn}?searchText=\"{quote(place['token'])}\""
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




        radius = min(8 + np.log(place['frekv']) * marker_size, 60)
        marker = folium.CircleMarker(
            radius=radius,
            location=[place['latitude'], place['longitude']],
            popup=folium.Popup(html, max_width=500),
            tooltip=f"{place['name']}: {place['frekv']} forekomster i {book_count} bøker",
            color=feature_colors[place['feature_class']],
            fill=True,
            fill_color=feature_colors[place['feature_class']],
            fill_opacity=0.4,
            weight=2
        )
        marker.add_to(feature_groups[place['feature_class']])
    folium.LayerControl().add_to(m)
    return m

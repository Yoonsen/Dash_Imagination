import dash
from dash import dcc, html, Input, Output, State, callback, dash_table
import pandas as pd
import numpy as np
import folium
import leafmap.foliumap as leafmap
from folium.plugins import MarkerCluster, HeatMap
import tools_imag as ti
from urllib.parse import quote
import json
from dash.exceptions import PreventUpdate
import tempfile
import sqlite3
import base64

class DataLayer:
    def __init__(self, corpus_db="corpus.db", places_db="place_exploded.db"):
        """
        Initialize DataLayer with database paths and cache
        """
        self.corpus_db = corpus_db
        self.places_db = places_db
        self._cached_lists = {}
        self._corpus_stats = None
        
        # Initialize cache on startup
        with sqlite3.connect(self.corpus_db) as con:
            self._initialize_cache(con)
    
    def _initialize_cache(self, con):
        """Initialize cached values for dropdowns and corpus stats"""
        # First get basic stats from metadata
        for column in ['category', 'year']:
            self._cached_lists[column] = pd.read_sql_query(
                f"SELECT DISTINCT {column} FROM metadata WHERE {column} IS NOT NULL ORDER BY {column}",
                con
            )[column].tolist()
        
        # Initialize corpus stats from metadata
        self._corpus_stats = {
            'total_books': pd.read_sql_query(
                "SELECT COUNT(DISTINCT dhlabid) as count FROM metadata", 
                con
            ).iloc[0]['count'],
            'year_range': pd.read_sql_query(
                "SELECT MIN(year) as min_year, MAX(year) as max_year FROM metadata", 
                con
            ).iloc[0].to_dict()
        }
        
        # Get dhlabids that have places
        with sqlite3.connect(self.places_db) as places_con:
            place_dhlabids = pd.read_sql_query(
                "SELECT DISTINCT dhlabid FROM places",
                places_con
            )['dhlabid'].tolist()
            
            # Get total places count
            self._corpus_stats['total_places'] = pd.read_sql_query(
                "SELECT COUNT(DISTINCT token) as count FROM places",
                places_con
            ).iloc[0]['count']
        
        # Now get authors and titles that have place mentions
        place_ids_str = ','.join('?' * len(place_dhlabids))
        self._cached_lists['author'] = pd.read_sql_query(
            f"""
            SELECT DISTINCT author 
            FROM metadata 
            WHERE dhlabid IN ({place_ids_str})
            AND author IS NOT NULL
            ORDER BY author
            """,
            con,
            params=place_dhlabids
        )['author'].tolist()
        
        self._cached_lists['title'] = pd.read_sql_query(
            f"""
            SELECT DISTINCT title 
            FROM metadata 
            WHERE dhlabid IN ({place_ids_str})
            AND title IS NOT NULL
            ORDER BY title
            """,
            con,
            params=place_dhlabids
        )['title'].tolist()
            
        # Initialize corpus stats
        self._corpus_stats = {
            'total_books': pd.read_sql_query(
                "SELECT COUNT(DISTINCT dhlabid) as count FROM metadata", 
                con
            ).iloc[0]['count'],
            'year_range': pd.read_sql_query(
                "SELECT MIN(year) as min_year, MAX(year) as max_year FROM metadata", 
                con
            ).iloc[0].to_dict()
        }
        
        # Get total places count from places database
        with sqlite3.connect(self.places_db) as places_con:
            self._corpus_stats['total_places'] = pd.read_sql_query(
                "SELECT COUNT(DISTINCT token) as count FROM places", 
                places_con
            ).iloc[0]['count']
    
    def get_corpus_stats(self):
        """Return basic statistics about the entire corpus"""
        return self._corpus_stats
    
    def _execute_batched_query(self, base_query, id_list, db_path, extra_params=None, batch_size=499):
        """Execute a query in batches to avoid SQLite parameter limits"""
        all_results = []
        extra_params = extra_params or []
        
        # Process in batches
        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            
            # Create the IN clause for this batch
            placeholders = ','.join('?' * len(batch))
            query = base_query.format(placeholders)
            
            # Combine batch IDs with any extra parameters
            params = batch + extra_params
            
            with sqlite3.connect(db_path) as con:
                batch_df = pd.read_sql_query(query, con, params=params)
                all_results.append(batch_df)
        
        # Combine all results
        if all_results:
            return pd.concat(all_results, ignore_index=True)
        return pd.DataFrame()

    def get_filtered_corpus_ids(self, years=None, categories=None, authors=None, titles=None, sample_size=None):
        """Get dhlabids for filtered corpus with optional sampling"""
        query_parts = ["SELECT dhlabid FROM metadata WHERE 1=1"]
        params = []
        
        if years:
            query_parts.append("AND year BETWEEN ? AND ?")
            params.extend(years)
            
        if categories and len(categories) > 0:
            query_parts.append(
                f"AND category IN ({','.join('?' for _ in categories)})"
            )
            params.extend(categories)
            
        if authors and len(authors) > 0:
            query_parts.append(
                f"AND author IN ({','.join('?' for _ in authors)})"
            )
            params.extend(authors)
            
        if titles and len(titles) > 0:
            query_parts.append(
                f"AND title IN ({','.join('?' for _ in titles)})"
            )
            params.extend(titles)
            
        # Add sampling if requested
        if sample_size:
            query_parts.append("ORDER BY RANDOM() LIMIT ?")
            params.append(sample_size)
            
        query = " ".join(query_parts)
        
        with sqlite3.connect(self.corpus_db) as con:
            df = pd.read_sql_query(query, con, params=params)
            return df['dhlabid'].tolist()
            
        # Add sampling if requested
        if sample_size:
            query_parts.append("ORDER BY RANDOM() LIMIT ?")
            params.append(sample_size)
            
        query = " ".join(query_parts)
        
        with sqlite3.connect(self.corpus_db) as con:
            df = pd.read_sql_query(query, con, params=params)
            return df['dhlabid'].tolist()

    def get_unique_values(self, column):
        """Get cached unique values for dropdowns"""
        return self._cached_lists.get(column, [])
    
    def get_unique_places(self):
        """Get list of unique place names for dropdown"""
        query = """
        SELECT DISTINCT token 
        FROM places 
        WHERE token IS NOT NULL 
        ORDER BY token
        """
        with sqlite3.connect(self.places_db) as con:
            df = pd.read_sql_query(query, con)
            return df['token'].tolist()
            
    def filter_by_places(self, dhlabids, place_tokens=None):
        """Filter corpus by specific place mentions"""
        if not place_tokens:
            return dhlabids
            
        base_query = """
        SELECT DISTINCT dhlabid 
        FROM places 
        WHERE token IN ({}) 
        AND dhlabid IN ({})
        """
        
        return self._execute_batched_query(
            base_query=base_query,
            id_list=dhlabids,
            db_path=self.places_db,
            extra_params=place_tokens
        )['dhlabid'].tolist()
        
    def get_places_for_dhlabids(self, dhlabids, max_places=200):
        """Get place data for a set of dhlabids"""
        if dhlabids is None or (isinstance(dhlabids, np.ndarray) and dhlabids.size == 0) or len(dhlabids) == 0:
            return pd.DataFrame()
            
        if isinstance(dhlabids, np.ndarray):
            dhlabids = dhlabids.tolist()
            
        base_query = """
        SELECT
            dhlabid,
            token,
            name as modern_name,
            freq,
            lat,
            lon,
            feature_class
        FROM places
        WHERE dhlabid IN ({})
        """
        
        return self._execute_batched_query(
            base_query=base_query,
            id_list=dhlabids,
            db_path=self.places_db
        )
    
    def get_metadata_for_dhlabids(self, dhlabids):
        """Get corpus metadata for a set of documents"""
        if dhlabids is None or (isinstance(dhlabids, np.ndarray) and dhlabids.size == 0) or len(dhlabids) == 0:
            return pd.DataFrame()
            
        if isinstance(dhlabids, np.ndarray):
            dhlabids = dhlabids.tolist()
            
        base_query = """
        SELECT dhlabid, title, author, year, urn
        FROM metadata
        WHERE dhlabid IN ({})
        """
        
        return self._execute_batched_query(
            base_query=base_query,
            id_list=dhlabids,
            db_path=self.corpus_db
        )


BASEMAP_OPTIONS = [
    "OpenStreetMap.Mapnik",
    "CartoDB.Positron",
    "CartoDB.DarkMatter",
]

WORLD_VIEW = {
    'center': [20, 0],
    'zoom': 2
}

EUROPE_VIEW = {
    'center': [55, 15],
    'zoom': 4
}

feature_colors = {
    'P': 'red', 'H': 'blue', 'T': 'green', 'L': 'orange',
    'A': 'purple', 'R': 'darkred', 'S': 'darkblue', 'V': 'darkgreen'
}

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

color_emojis = {
    'P': '🔴',  # Red for Befolkede steder
    'H': '🔵',  # Blue for Vann og vassdrag
    'T': '🟢',  # Green for Fjell og høyder
    'L': '🟠',  # Orange for Parker og områder
    'A': '🟣',  # Purple for Administrative
    'R': '🟥',  # Dark Red for Veier og jernbane
    'S': '🟦',  # Dark Blue for Bygninger og gårder
    'V': '🟩'   # Dark Green for Skog og mark
}




def create_popup_html(place, place_books):
    html = f"""
    <div style='width:500px'>
        <h4>{place['token']}</h4>
        <p><strong>Moderne navn:</strong> {place['modern_name']}</p>
        <p><strong>{place['freq']} forekomster</strong></p>
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
    
    # Now place_books should just be the single matching book
    book = place_books.iloc[0] if not place_books.empty else None
    if book is not None:
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
    return html

def make_map(significant_places, corpus_df, basemap, marker_size, center=None, zoom=None):
    cache_key = f"{significant_places.shape[0]}_{basemap}_{marker_size}_{center}_{zoom}"
    
    def create_map():
        significant_places_clean = significant_places.dropna(subset=['lat', 'lon'])
        center_lat = significant_places_clean['lat'].median() if center is None else center[0]
        center_lon = significant_places_clean['lon'].median() if center is None else center[1]
        current_zoom = EUROPE_VIEW['zoom'] if zoom is None else zoom
    
        m = leafmap.Map(center=[center_lat, center_lon], zoom=current_zoom, basemap=basemap)
    
        # Create cluster groups for each feature class
        cluster_groups = {}
        for feature_class, description in feature_descriptions.items():
            cluster_groups[feature_class] = MarkerCluster(
                name=f"{description} {color_emojis.get(feature_class, '🔲')}",
                options={
                    'spiderfyOnMaxZoom': True,
                    'showCoverageOnHover': True,
                    'zoomToBoundsOnClick': True,
                    'maxClusterRadius': 40,
                },
                icon_create_function=f"""
function(cluster) {{
    var childCount = cluster.getChildCount();
    var size = Math.min(40 + Math.log(childCount) * 10, 80);
    return L.divIcon({{
        html: '<div style="background-color: rgba(128, 128, 128, 0.4); width: ' + size + 'px; height: ' + size + 'px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid {feature_colors[feature_class]};">' + childCount + '</div>',
        className: 'marker-cluster marker-cluster-{feature_class}',
        iconSize: L.point(size, size)
    }});
}}
"""
            ).add_to(m)

        # Process places in batches
        batch_size = 50
        for i in range(0, len(significant_places), batch_size):
            batch = significant_places.iloc[i:i+batch_size]
            
            for _, place in batch.iterrows():
                # Get the book info for this specific place mention
                place_books = corpus_df[corpus_df.dhlabid == place['dhlabid']]
                
                popup_html = create_popup_html(place, place_books)
                
                radius = min(6 + np.log(place['freq']) * marker_size, 60)
                marker = folium.CircleMarker(
                    radius=radius,
                    location=[place['lat'], place['lon']],
                    popup=folium.Popup(popup_html, max_width=500),
                    tooltip=f"{place['token']}: {place['freq']} forekomster",
                    color=feature_colors[place['feature_class']],
                    fill=True,
                    fill_color=feature_colors[place['feature_class']],
                    fill_opacity=0.4,
                    weight=2,
                    frequency=float(place['freq'])
                )
                marker.add_to(cluster_groups[place['feature_class']])

        folium.LayerControl(collapsed=False, position='topright').add_to(m)
        return folium_to_html(m)

    return get_cached_map_html(cache_key, create_map)

def create_heatmap(places_df, intensity=3, radius=15, blur=10, basemap="OpenStreetMap.Mapnik"):
    """Create a heatmap from places data"""
    if places_df.empty:
        return ""
        
    # Calculate weight based on frequency and intensity
    places_df['weight'] = places_df['freq'] * intensity
    
    # Create base map centered on data
    center_lat = places_df['lat'].median()
    center_lon = places_df['lon'].median()
    
    m = folium.Map(location=[center_lat, center_lon],
                   zoom_start=4,
                   tiles=basemap)
    
    # Prepare data for heatmap
    heat_data = places_df[['lat', 'lon', 'weight']].values.tolist()
    
    # Add heatmap layer
    HeatMap(heat_data,
            radius=radius,
            blur=blur,
            max_zoom=1,
            gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(m)
    
    return folium_to_html(m)

# Cache for map HTML
_map_cache = {}

def get_cached_map_html(cache_key, create_map_func):
    """Cache map HTML to avoid regeneration"""
    global _map_cache
    if cache_key not in _map_cache:
        _map_cache[cache_key] = create_map_func()
    return _map_cache[cache_key]

def folium_to_html(m):
    """Convert Folium map to HTML string"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp:
        m.save(tmp.name)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            html_str = f.read()
    return html_str

def create_layout(dl):
    """Create the complete Dash app layout with improved organization"""
    return html.Div([
        # Left Sidebar - Core Controls
        html.Div([
            html.H1("ImagiNation", style={'marginBottom': '20px'}),
            
            # Corpus Overview Panel
            html.Div([
                html.H3("Corpus Overview", style={'marginBottom': '15px'}),
                html.Div(id='corpus-stats-panel')
            ], style={'padding': '20px', 'backgroundColor': 'white', 'marginBottom': '20px'}),
            
            # Core Filters Panel
            html.Div([
                html.H3("Filters", style={'marginBottom': '15px'}),
                
                html.Label("Year Range"),
                dcc.RangeSlider(
                    id='year-slider',
                    min=1814,
                    max=1905,
                    value=[1850, 1880],
                    marks={i: str(i) for i in range(1814, 1906, 20)}
                ),
                
                html.Label("Category", style={'marginTop': '15px'}),
                dcc.Dropdown(
                    id='category-dropdown',
                    options=[{'label': c, 'value': c} for c in dl.get_unique_values('category')],
                    multi=True
                ),
                
                html.Label("Author", style={'marginTop': '15px'}),
                dcc.Dropdown(
                    id='author-dropdown',
                    options=[{'label': a, 'value': a} for a in dl.get_unique_values('author')],
                    multi=True
                ),
                
                html.Label("Title", style={'marginTop': '15px'}),
                dcc.Dropdown(
                    id='title-dropdown',
                    options=[{'label': t, 'value': t} for t in dl.get_unique_values('title')],
                    multi=True
                ),
                
                html.Label("Places", style={'marginTop': '15px'}),
                dcc.Dropdown(
                    id='places-dropdown',
                    options=[],  # Dynamically populated
                    multi=True
                ),
            ], style={'padding': '20px', 'backgroundColor': 'white', 'marginBottom': '20px'}),
            
            # Current Selection Stats
            html.Div(id='selection-stats-panel', 
                    style={'padding': '20px', 'backgroundColor': 'white'})
            
        ], style={'width': '300px', 'position': 'fixed', 'left': 0, 'top': 0, 
                  'bottom': 0, 'padding': '20px', 'background': '#f0f0f0', 
                  'overflowY': 'auto'}),
        
        # Main Content Area
        html.Div([
            dcc.Tabs([
                # Sampled Place Map Tab
                dcc.Tab(label='Sampled Places Map', children=[
                    html.Div([
                        # Left side - Map Controls
                        html.Div([
                            # Sampling Controls
                            html.Div([
                                html.H3("Sampling Controls", style={'marginBottom': '15px'}),
                                
                                html.Label("Sample Size"),
                                dcc.Slider(
                                    id='sample-size-slider',
                                    min=100,
                                    max=1000,
                                    value=400,
                                    step=100,
                                    marks={i: str(i) for i in [100, 250, 500, 750, 1000]}
                                ),
                                
                                html.Label("Max Places per Sample", style={'marginTop': '15px'}),
                                dcc.Slider(
                                    id='max-places-slider',
                                    min=50,
                                    max=500,
                                    value=200,
                                    step=50,
                                    marks={i: str(i) for i in [50, 100, 200, 350, 500]}
                                ),
                            ], style={'marginBottom': '20px'}),
                            
                            # Map Controls
                            html.Div([
                                html.H3("Map Controls", style={'marginBottom': '15px'}),
                                
                                html.Label("Base Map"),
                                dcc.Dropdown(
                                    id='basemap-dropdown',
                                    options=[{'label': bm, 'value': bm} for bm in [
                                        "OpenStreetMap.Mapnik",
                                        "CartoDB.Positron",
                                        "CartoDB.DarkMatter",
                                    ]],
                                    value="OpenStreetMap.Mapnik"
                                ),
                                
                                html.Label("Marker Size", style={'marginTop': '15px'}),
                                dcc.Slider(
                                    id='marker-size-slider',
                                    min=1,
                                    max=6,
                                    value=3,
                                    marks={i: str(i) for i in range(1, 7)}
                                ),
                            ], style={'marginBottom': '20px'}),
                            
                            # Place Summary
                            html.Div([
                                html.H3("Place Summary"),
                                html.Div(id='place-summary')
                            ])
                        ], style={
                            'width': '300px',
                            'padding': '20px',
                            'backgroundColor': 'white',
                            'height': '100%',
                            'overflowY': 'auto'
                        }),
                        
                        # Right side - Map Display
                        html.Div([
                            html.Iframe(
                                id='map-iframe',
                                srcDoc='',
                                style={
                                    'width': '100%', 
                                    'height': '800px', 
                                    'border': 'none'
                                }
                            )
                        ], style={
                            'flex': '1',
                            'marginLeft': '20px',
                            'backgroundColor': 'white',
                            'padding': '10px'
                        })
                    ], style={'display': 'flex', 'height': '800px'})
                ]),
                
                # Full Corpus Heatmap Tab
                dcc.Tab(label='Corpus Heatmap', children=[
                    html.Div([
                        # Left side - Heatmap Controls
                        html.Div([
                            html.H3("Heatmap Controls", style={'marginBottom': '15px'}),
                            
                            html.Label("Intensity"),
                            dcc.Slider(
                                id='heatmap-intensity-slider',
                                min=1,
                                max=10,
                                value=3,
                                marks={i: str(i) for i in range(1, 11, 2)}
                            ),
                            
                            html.Label("Radius", style={'marginTop': '15px'}),
                            dcc.Slider(
                                id='heatmap-radius-slider',
                                min=5,
                                max=30,
                                value=15,
                                step=5,
                                marks={i: str(i) for i in [5, 10, 15, 20, 25, 30]}
                            ),
                            
                            html.Label("Blur", style={'marginTop': '15px'}),
                            dcc.Slider(
                                id='heatmap-blur-slider',
                                min=5,
                                max=20,
                                value=10,
                                step=5,
                                marks={i: str(i) for i in [5, 10, 15, 20]}
                            )
                        ], style={
                            'width': '300px',
                            'padding': '20px',
                            'backgroundColor': 'white',
                            'height': '100%'
                        }),
                        
                        # Right side - Heatmap Display
                        html.Div([
                            html.Iframe(
                                id='heatmap-iframe',
                                srcDoc='',
                                style={
                                    'width': '100%', 
                                    'height': '800px', 
                                    'border': 'none'
                                }
                            )
                        ], style={
                            'flex': '1',
                            'marginLeft': '20px',
                            'backgroundColor': 'white',
                            'padding': '10px'
                        })
                    ], style={'display': 'flex', 'height': '800px'})
                ]),

                # Add to the tabs section of create_layout:
                
                dcc.Tab(label='Timeline Map', children=[
                    html.Div([
                        # Left side - Timeline Controls
                        html.Div([
                            html.H3("Timeline Controls", style={'marginBottom': '15px'}),
                            
                            # Animation Controls
                            html.Div([
                                html.Label("Visualization Type"),
                                dcc.RadioItems(
                                    id='timeline-type',
                                    options=[
                                        {'label': 'Cumulative (showing all places up to selected year)', 'value': 'cumulative'},
                                        {'label': 'Time Slice (showing only places from selected year)', 'value': 'slice'}
                                    ],
                                    value='cumulative',
                                    style={'marginBottom': '15px'}
                                ),
                                
                                html.Label("Time Control"),
                                dcc.Slider(
                                    id='year-timeline-slider',
                                    min=1814,
                                    max=1905,
                                    value=1850,
                                    marks={i: str(i) for i in range(1814, 1906, 10)},
                                    included=False
                                ),
                                
                                html.Div([
                                    html.Button('◀', id='prev-year', n_clicks=0),
                                    html.Button('▶', id='next-year', n_clicks=0),
                                    html.Button('Play', id='play-button', n_clicks=0),
                                ], style={'marginTop': '10px'}),
                                
                                # Animation Speed Control
                                html.Label("Animation Speed (years/second)", style={'marginTop': '15px'}),
                                dcc.Slider(
                                    id='animation-speed',
                                    min=1,
                                    max=10,
                                    value=2,
                                    marks={i: str(i) for i in range(1, 11)},
                                ),
                                
                                # Display Options
                                html.H4("Display Options", style={'marginTop': '20px'}),
                                
                                html.Label("Place Persistence"),
                                dcc.Slider(
                                    id='place-persistence',
                                    min=1,
                                    max=10,
                                    value=5,
                                    marks={
                                        1: '1 yr',
                                        5: '5 yrs',
                                        10: '10 yrs'
                                    },
                                    tooltip={'placement': 'bottom'}
                                ),
                                
                                html.Label("Base Map", style={'marginTop': '15px'}),
                                dcc.Dropdown(
                                    id='timeline-basemap',
                                    options=[{'label': bm, 'value': bm} for bm in [
                                        "OpenStreetMap.Mapnik",
                                        "CartoDB.Positron",
                                        "CartoDB.DarkMatter",
                                    ]],
                                    value="OpenStreetMap.Mapnik"
                                ),
                            ], style={'marginBottom': '20px'}),
                            
                            # Timeline Statistics
                            html.Div([
                                html.H4("Timeline Statistics"),
                                html.Div(id='timeline-stats')
                            ])
                        ], style={
                            'width': '300px',
                            'padding': '20px',
                            'backgroundColor': 'white',
                            'height': '100%',
                            'overflowY': 'auto'
                        }),
                        
                        # Right side - Map and Timeline Display
                        html.Div([
                            # Current Year Display
                            html.Div(
                                id='current-year-display',
                                style={
                                    'fontSize': '24px',
                                    'textAlign': 'center',
                                    'marginBottom': '10px'
                                }
                            ),
                            
                            # Map Display
                            html.Iframe(
                                id='timeline-map-iframe',
                                srcDoc='',
                                style={
                                    'width': '100%',
                                    'height': '700px',
                                    'border': 'none'
                                }
                            ),
                            
                            # Timeline Graph below map
                            dcc.Graph(
                                id='timeline-graph',
                                style={'height': '150px'}
                            )
                        ], style={
                            'flex': '1',
                            'marginLeft': '20px',
                            'backgroundColor': 'white',
                            'padding': '10px'
                        })
                    ], style={'display': 'flex', 'height': '900px'})
                ])
                # Future tabs can be added here...
                
            ], style={'marginBottom': '20px'})
        ], style={'marginLeft': '320px', 'padding': '20px'}),
        
        # Stores for state management
        dcc.Store(id='filtered-data'),
        dcc.Store(id='filtered-agg-data')
    ])


### new callbacks 

def register_callbacks(app, dl):
    """Register all callbacks for the app"""
    
    @app.callback(
        Output('corpus-stats-panel', 'children'),
        Input('year-slider', 'value')  # We can use any input as trigger
    )
    def update_corpus_stats(_):
        """Update the corpus-wide statistics"""
        stats = dl.get_corpus_stats()
        return html.Div([
            html.P(f"Total Books: {stats['total_books']:,}"),
            html.P(f"Total Places: {stats['total_places']:,}"),
            html.P(f"Years: {stats['year_range']['min_year']} - {stats['year_range']['max_year']}")
        ])
    
    @app.callback(
        [Output('filtered-data', 'data'),
         Output('filtered-agg-data', 'data'),
         Output('selection-stats-panel', 'children')],  # Updated ID
        [Input('year-slider', 'value'),
         Input('category-dropdown', 'value'),
         Input('author-dropdown', 'value'),
         Input('title-dropdown', 'value'),
         Input('places-dropdown', 'value'),
         Input('sample-size-slider', 'value')]
    )
    def update_filtered_data(years, categories, authors, titles, places, sample_size):
        # Get filtered document IDs with sampling
        filtered_ids = dl.get_filtered_corpus_ids(
            years=years,
            categories=categories,
            authors=authors,
            titles=titles,
            sample_size=sample_size
        )
        
        if not filtered_ids:
            return None, None, html.Div([
                html.H3("Current Selection"),
                html.P("No documents match the criteria")
            ])
        
        # Apply place filters if selected
        if places:
            filtered_ids = dl.filter_by_places(filtered_ids, places)
            
        if not filtered_ids:
            return None, None, html.Div([
                html.H3("Current Selection"),
                html.P("No documents match the place filters")
            ])
        
        # Get places data
        raw_places = dl.get_places_for_dhlabids(filtered_ids)
        
        if raw_places.empty:
            return None, None, html.Div([
                html.H3("Current Selection"),
                html.P("No place data found for selected documents")
            ])
        
        # Aggregate the data
        aggregated = (raw_places.groupby(['token', 'modern_name', 'feature_class'])
                     .agg({
                         'freq': 'sum',
                         'dhlabid': 'nunique'
                     })
                     .reset_index()
                     .rename(columns={
                         'freq': 'total_mentions',
                         'dhlabid': 'doc_count'
                     }))
        
        # Sort by total mentions
        aggregated = aggregated.sort_values('total_mentions', ascending=False)
        
        # Create selection stats
        stats = html.Div([
            html.H3("Current Selection"),
            html.P(f"Documents: {len(filtered_ids)}"),
            html.P(f"Unique places: {len(aggregated)}"),
            html.P(f"Total mentions: {aggregated['total_mentions'].sum():,}")
        ])
        
        return (raw_places.to_json(date_format='iso', orient='split'),
                aggregated.to_json(date_format='iso', orient='split'),
                stats)
        
    @app.callback(
        Output('map-iframe', 'srcDoc'),
        [Input('filtered-data', 'data'),
         Input('basemap-dropdown', 'value'),
         Input('marker-size-slider', 'value'),
         Input('max-places-slider', 'value')]  # Add this input
    )
    def update_map(raw_json, basemap, marker_size, max_places):
        if not raw_json:
            return ""
        
        # Deserialize JSON into a DataFrame
        raw_places = pd.read_json(raw_json, orient='split')
        
        # Aggregate and limit before mapping
        place_counts = (raw_places.groupby(['token', 'modern_name', 'lat', 'lon', 'feature_class'])
                       .agg({'freq': 'sum', 'dhlabid': 'first'})
                       .reset_index()
                       .nlargest(max_places, 'freq'))
        
        # Get metadata for these documents
        all_dhlabids = place_counts['dhlabid'].unique()
        corpus_df = dl.get_metadata_for_dhlabids(all_dhlabids)
        
        # Generate the map
        return make_map(place_counts, corpus_df, basemap, marker_size)
    
    @app.callback(
        Output('place-summary', 'children'),
        [Input('filtered-agg-data', 'data')]
    )
    def update_place_summary(aggregated_json):
        """Update place summary based on pre-aggregated data"""
        if not aggregated_json:
            return "No places to display"
        
        # Deserialize JSON into a DataFrame
        aggregated = pd.read_json(aggregated_json, orient='split')
        
        # Sort and get the top 10 places by mentions
        top_places = aggregated.nlargest(10, 'total_mentions')
        
        # Create summary table
        summary = html.Table(
            # Header
            [html.Tr([html.Th("Place"), html.Th("Mentions"), html.Th("Documents")])] +
            # Rows
            [html.Tr([
                html.Td(row['token']),
                html.Td(f"{row['total_mentions']:,}"),
                html.Td(row['doc_count'])
            ]) for _, row in top_places.iterrows()]
        )
        
        return html.Div([
            html.H3("Most Mentioned Places"),
            summary
        ])

def register_heatmap_callbacks(app, dl):
    """Register callbacks specific to the heatmap functionality"""
    
    @app.callback(
        Output('heatmap-iframe', 'srcDoc'),
        [Input('filtered-data', 'data'),
         Input('heatmap-intensity-slider', 'value'),
         Input('heatmap-radius-slider', 'value'),
         Input('heatmap-blur-slider', 'value'),
         Input('basemap-dropdown', 'value')]
    )
    def update_heatmap(places_json, intensity, radius, blur, basemap):
        if not places_json:
            return ""
            
        # Convert JSON to DataFrame
        places_df = pd.read_json(places_json, orient='split')
        
        # Create base map centered on data
        center_lat = places_df['lat'].median()
        center_lon = places_df['lon'].median()
        
        m = folium.Map(location=[center_lat, center_lon],
                      zoom_start=4,
                      tiles=basemap)
        
        # Calculate weight based on frequency and intensity
        places_df['weight'] = places_df['freq'] * intensity
        
        # Prepare data for heatmap
        heat_data = places_df[['lat', 'lon', 'weight']].values.tolist()
        
        # Add heatmap layer
        HeatMap(heat_data,
               radius=radius,
               blur=blur,
               max_zoom=1,
               gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'}).add_to(m)
        
        # Convert to HTML
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp:
            m.save(tmp.name)
            with open(tmp.name, 'r', encoding='utf-8') as f:
                html_str = f.read()
                
        return html_str


def register_timeline_callbacks(app, dl):
    """Register callbacks for timeline map functionality"""
        
    @app.callback(
        [Output('year-timeline-slider', 'value'),
         Output('current-year-display', 'children'),
         Output('play-button', 'children')],
        [Input('play-button', 'n_clicks'),
         Input('prev-year', 'n_clicks'),
         Input('next-year', 'n_clicks')],
        [State('year-timeline-slider', 'value'),
         State('animation-speed', 'value'),
         State('play-button', 'children')]
    )
    def update_year(play_clicks, prev_clicks, next_clicks, current_year, speed, play_state):
        ctx = dash.callback_context
        if not ctx.triggered:
            return current_year, f"Year: {current_year}", "▶ Play"
        
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        
        if trigger_id == 'prev-year':
            new_year = max(1814, current_year - 1)
        elif trigger_id == 'next-year':
            new_year = min(1905, current_year + 1)
        elif trigger_id == 'play-button':
            # Toggle play/pause
            if play_state == "▶ Play":
                # Start animation logic would go here
                # You might want to use dcc.Interval for actual animation
                return current_year, f"Year: {current_year}", "❚❚ Pause"
            else:
                return current_year, f"Year: {current_year}", "▶ Play"
        
        return new_year, f"Year: {new_year}", play_state    
    @app.callback(
        Output('timeline-map-iframe', 'srcDoc'),
        [Input('filtered-data', 'data'),
         Input('timeline-type', 'value'),
         Input('year-timeline-slider', 'value'),
         Input('place-persistence', 'value'),
         Input('timeline-basemap', 'value')]
    )
    def update_timeline_map(places_json, viz_type, current_year, persistence, basemap):
        print("Timeline map callback triggered")  # Debug print
        if not places_json:
            return ""
            
        # Convert JSON to DataFrame
        places_df = pd.read_json(places_json, orient='split')
        
        # Get metadata for the places
        all_dhlabids = places_df['dhlabid'].unique()
        corpus_df = dl.get_metadata_for_dhlabids(all_dhlabids)
        
        # Merge place data with year information
        merged_df = places_df.merge(corpus_df[['dhlabid', 'year']], on='dhlabid')
        
        # Filter based on visualization type
        if viz_type == 'cumulative':
            # Show all places up to current year
            filtered_df = merged_df[merged_df['year'] <= current_year]
        else:  # time slice
            # Show places within persistence window
            year_start = current_year - persistence + 1
            filtered_df = merged_df[
                (merged_df['year'] >= year_start) & 
                (merged_df['year'] <= current_year)
            ]
        
        if filtered_df.empty:
            return ""
        
        # Create the map
        center_lat = filtered_df['lat'].median()
        center_lon = filtered_df['lon'].median()
        
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=4,
            tiles=basemap or "OpenStreetMap.Mapnik"
        )
        
        # Add the markers - no clustering
        for _, place in filtered_df.iterrows():
            # Calculate opacity based on recency
            years_old = current_year - place['year']
            opacity = 1.0 if viz_type == 'cumulative' else max(0.3, 1 - (years_old / persistence))
            
            # Calculate radius based on frequency
            radius = min(6 + np.log(place['freq']) * 3, 30)
            
            # Create popup
            place_books = corpus_df[corpus_df.dhlabid == place['dhlabid']]
            popup_html = create_popup_html(place, place_books)
            
            # Add marker
            folium.CircleMarker(
                location=[place['lat'], place['lon']],
                radius=radius,
                popup=folium.Popup(popup_html, max_width=500),
                tooltip=f"{place['token']} ({place['year']}): {place['freq']} mentions",
                color=feature_colors[place['feature_class']],
                fill=True,
                fill_color=feature_colors[place['feature_class']],
                fill_opacity=opacity,
                weight=2
            ).add_to(m)
        
        # Add legend
        feature_legend = {}
        for _, place in filtered_df.iterrows():
            feature_class = place['feature_class']
            if feature_class not in feature_legend:
                feature_legend[feature_class] = feature_descriptions[feature_class]
        
        if feature_legend:
            legend_html = """
            <div style="position: fixed; 
                        bottom: 50px; right: 50px; 
                        border:2px solid grey; z-index:9999; font-size:14px;
                        background-color:white;
                        padding: 10px;
                        opacity: 0.8;">
            """
            
            for feature_class, description in feature_legend.items():
                color = feature_colors[feature_class]
                legend_html += f"""
                <div>
                    <i class="fa fa-circle fa-1x" style="color:{color}"></i>
                    {description}
                </div>"""
            
            legend_html += "</div>"
            m.get_root().html.add_child(folium.Element(legend_html))
        
        # Convert to HTML
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp:
            m.save(tmp.name)
            with open(tmp.name, 'r', encoding='utf-8') as f:
                html_str = f.read()
                
        return html_str
    @app.callback(
        Output('timeline-graph', 'figure'),
        [Input('filtered-data', 'data'),
         Input('year-timeline-slider', 'value'),
         Input('timeline-type', 'value')]
    )
    def update_timeline_graph(places_json, current_year, viz_type):
        if not places_json:
            return {}
        
        # Convert JSON to DataFrame
        places_df = pd.read_json(places_json, orient='split')
        
        # Get metadata for the places
        all_dhlabids = places_df['dhlabid'].unique()
        corpus_df = dl.get_metadata_for_dhlabids(all_dhlabids)
        
        # Merge place data with year information
        merged_df = places_df.merge(corpus_df[['dhlabid', 'year']], on='dhlabid')
        
        # Filter based on visualization type
        if viz_type == 'cumulative':
            filtered_df = merged_df[merged_df['year'] <= current_year]
        else:  # time slice
            year_start = current_year - 5 + 1  # using a fixed 5-year window for graph
            filtered_df = merged_df[
                (merged_df['year'] >= year_start) & 
                (merged_df['year'] <= current_year)
            ]
        
        # Aggregate places by year
        yearly_places = filtered_df.groupby('year').size().reset_index(name='place_count')
        
        # Create the figure
        import plotly.graph_objs as go
        
        return go.Figure(
            data=[go.Bar(
                x=yearly_places['year'], 
                y=yearly_places['place_count'],
                marker_color='rgba(50, 171, 96, 0.6)',
                marker_line_color='rgba(50, 171, 96, 1.0)',
                marker_line_width=1.5
            )],
            layout=go.Layout(
                title='Places Mentioned per Year',
                xaxis=dict(title='Year'),
                yaxis=dict(title='Number of Places'),
                bargap=0.2
            )
        )
# Update the main() function to include new callbacks
def main():
    dl = DataLayer()
    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    app.layout = create_layout(dl)
    register_callbacks(app, dl)
    print("About to register timeline callbacks...")  # Debug print
    register_timeline_callbacks(app, dl)
    print("Timeline callbacks registered")  # Debug print
    app.run_server(debug=True, host='0.0.0.0')

if __name__ == '__main__':
    main()
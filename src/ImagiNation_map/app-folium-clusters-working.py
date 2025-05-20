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

import base64

import logging
logging.basicConfig(level=logging.INFO)


# Better approach - use global caching
_cached_data = {
    'corpus': None,
    'places': None,
    'lists': None
}

def get_cached_data():
    global _cached_data
    if _cached_data['corpus'] is None:
        # Load data once
        corpus = pd.read_excel("imag_korpus.xlsx", index_col=0)
        corpus['author'] = corpus['author'].fillna('').apply(lambda x: x.replace('/', ' '))
        corpus['Verk'] = corpus.apply(lambda x: f"{x['title'] or 'Uten tittel'} av {x['author'] or 'Ingen'} ({x['year'] or 'n.d.'})", axis=1)
        
        _cached_data['corpus'] = corpus
        _cached_data['places'] = pd.read_pickle('exploded_places.pkl')
        _cached_data['lists'] = {
            'authors': list(set(corpus.author)),
            'titles': list(set(corpus.Verk)),
            'categories': list(set(corpus.category))
        }
    return _cached_data


_map_cache = {}

def get_cached_map_html(cache_key, create_map_func):
    global _map_cache
    if cache_key not in _map_cache:
        _map_cache[cache_key] = create_map_func()
    return _map_cache[cache_key]

def clean_map_cache():
    global _map_cache
    if len(_map_cache) > 10:  # Only keep 10 most recent maps
        _map_cache.clear()

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




def make_map(significant_places, corpus_df, basemap, marker_size, center=None, zoom=None):

    cache_key = f"{significant_places.shape[0]}_{basemap}_{marker_size}_{center}_{zoom}"
    
    def create_popup_html(place, place_books):
        html = f"""
        <div style='width:500px'>
            <h4>{place['token']}</h4>
            <p><strong>Moderne navn:</strong> {place['name']}</p>
            <p><strong>{place['frekv']} forekomster i {len(place_books)} bøker</strong></p>
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
        return html

    def create_map():
        significant_places_clean = significant_places.dropna(subset=['latitude', 'longitude'])
        center_lat = significant_places_clean['latitude'].median() if center is None else center[0]
        center_lon = significant_places_clean['longitude'].median() if center is None else center[1]
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
    var size = Math.min(40 + Math.log(childCount) * 10, 80);  // Logarithmic scaling with upper limit
    return L.divIcon({{
        html: '<div style="background-color: rgba(128, 128, 128, 0.7); width: ' + size + 'px; height: ' + size + 'px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; border: 2px solid {feature_colors[feature_class]};">' + childCount + '</div>',
        className: 'marker-cluster marker-cluster-{feature_class}',
        iconSize: L.point(size, size)
    }});
}}
"""
            ).add_to(m)

        # Process places in batches for better memory management
        batch_size = 50
        for i in range(0, len(significant_places), batch_size):
            batch = significant_places.iloc[i:i+batch_size]
            
            for _, place in batch.iterrows():
                place_books = corpus_df[corpus_df.dhlabid.isin(place['dhlabid'])]
                book_count = len(place_books)
                
                popup_html = create_popup_html(place, place_books)
                
                radius = min(6 + np.log(place['frekv']) * marker_size, 60)
                marker = folium.CircleMarker(
                    radius=radius,
                    location=[place['latitude'], place['longitude']],
                    popup=folium.Popup(popup_html, max_width=500),
                    tooltip=f"{place['token']}: {place['frekv']} forekomster i {book_count} bøker",
                    color=feature_colors[place['feature_class']],
                    fill=True,
                    fill_color=feature_colors[place['feature_class']],
                    fill_opacity=0.4,
                    weight=2,
                    frequency=float(place['frekv'])
                )
                marker.add_to(cluster_groups[place['feature_class']])


     
        folium.LayerControl(
            collapsed=False,
            position='topright'
        ).add_to(m)
        return folium_to_html(m)

    return get_cached_map_html(cache_key, create_map)

app = dash.Dash(__name__, suppress_callback_exceptions=True)
# Constants


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

# Helper function to convert Folium map to HTML string
def folium_to_html(m):
    with tempfile.NamedTemporaryFile(delete=False, suffix='.html') as tmp:
        m.save(tmp.name)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            html_str = f.read()
    return html_str

# Cache functions
def load_corpus():
    korpus_file = "imag_korpus.xlsx"
    corpus = pd.read_excel(korpus_file, index_col=0)
    corpus['author'] = corpus['author'].fillna('').apply(lambda x: x.replace('/', ' '))
    corpus['Verk'] = corpus.apply(lambda x: f"{x['title'] or 'Uten tittel'} av {x['author'] or 'Ingen'} ({x['year'] or 'n.d.'})", axis=1)
    authors = list(set(corpus.author))
    titles = list(set(corpus.Verk))
    categories = list(set(corpus.category))
    return corpus, authors, titles, categories

def load_exploded_places():
    return pd.read_pickle('exploded_places.pkl')

# Load initial data
# corpus_df, authorlist, titlelist, categorylist = load_corpus()
# preprocessed_places = load_exploded_places()


cached_data = get_cached_data()
corpus_df = cached_data['corpus']
preprocessed_places = cached_data['places']
authorlist = cached_data['lists']['authors']
titlelist = cached_data['lists']['titles']
categorylist = cached_data['lists']['categories']



# Then in your layout, update the components like this:
# Layout
# Define some CSS styles
styles = {
    'panel': {
        'padding': '20px',
        'backgroundColor': 'white',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
        'marginBottom': '20px',
        'borderRadius': '4px',
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif'
    },
    'controlPanel': {
        'width': '300px',
        'height': '100vh',
        'position': 'fixed',
        'left': 0,
        'top': 0,
        'padding': '20px',
        'backgroundColor': 'white',
        'boxShadow': '2px 0 4px rgba(0,0,0,0.1)',
        'overflowY': 'auto',
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif'
    },
    'mainContent': {
        'marginLeft': '320px',
        'padding': '20px',
        'width': 'calc(100% - 340px)',
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif'
    },
    'mapContainer': {
        'height': '700px',
        'marginBottom': '20px',
        'width': '100%'
    },
    'placesTable': {
        'height': '400px',
        'overflowY': 'auto',
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif'
    },
    'dropdownStyle': {
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif',
        'fontSize': '14px'
    },
    'headerStyle': {
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif',
        'fontWeight': '500',
        'fontSize': '24px',
        'marginBottom': '20px'
    },
    'labelStyle': {
        'fontFamily': '"Helvetica Neue", Helvetica, Arial, sans-serif',
        'fontSize': '14px',
        'fontWeight': '500',
        'marginBottom': '5px'
    }
}

# Layout with Tabs
# Layout with Tabs
app.layout = html.Div([
    # Left Control Panel
    html.Div([
        html.H1("ImagiNation", style=styles['headerStyle']),
        
        # Metadata Controls
        html.Div([
            html.H3("Filters", style={**styles['headerStyle'], 'fontSize': '18px'}),
            
            html.Label("Period", style=styles['labelStyle']),
            html.Div([
                dcc.RangeSlider(
                    id='year-slider',
                    min=1814,
                    max=1905,
                    value=[1850, 1880],
                    marks={i: str(i) for i in range(1814, 1906, 20)}
                )
            ], style={'marginBottom': '20px'}),
            
            html.Label("Category", style=styles['labelStyle']),
            dcc.Dropdown(
                id='category-dropdown',
                options=[{'label': cat, 'value': cat} for cat in categorylist],
                multi=True,
                style={**styles['dropdownStyle'], 'marginBottom': '15px'}
            ),
            
            html.Label("Author", style=styles['labelStyle']),
            dcc.Dropdown(
                id='author-dropdown',
                options=[{'label': author, 'value': author} for author in authorlist],
                multi=True,
                style={**styles['dropdownStyle'], 'marginBottom': '15px'}
            ),
            
            html.Label("Work", style=styles['labelStyle']),
            dcc.Dropdown(
                id='title-dropdown',
                options=[{'label': title, 'value': title} for title in titlelist],
                multi=True,
                style={**styles['dropdownStyle'], 'marginBottom': '15px'}
            ),
            
            html.Label("Places", style=styles['labelStyle']),
            dcc.Dropdown(
                id='places-dropdown',
                options=[{'label': place, 'value': place} 
                        for place in sorted(preprocessed_places['name'].unique())],
                multi=True,
                style={'marginBottom': '20px'}
            ),
        ], style=styles['panel']),
        
        # Map Controls
        html.Div([
            html.H3("Map Controls", style={'marginBottom': '15px'}),
            
            html.Label("Max Books", style=styles['labelStyle']),
            dcc.Slider(
                id='max-books-slider',
                min=100,
                max=5000,
                value=400,
                step=100,
                marks={i: str(i) for i in [100, 1000, 2500, 5000]}
            ),
            
            html.Label("Max Places", style=styles['labelStyle']),
            dcc.Slider(
                id='max-places-slider',
                min=1,
                max=500,
                value=200,
                step=10,
                marks={i: str(i) for i in [1, 100, 250, 500]}
            ),
            
            html.Label("Marker Size", style=styles['labelStyle']),
            dcc.Slider(
                id='marker-size-slider',
                min=1,
                max=6,
                value=3,
                step=1,
                marks={i: str(i) for i in range(1, 7)}
            ),
            
            html.Label("Base Map", style=styles['labelStyle']),
            dcc.Dropdown(
                id='basemap-dropdown',
                options=[{'label': bm, 'value': bm} for bm in BASEMAP_OPTIONS],
                value=BASEMAP_OPTIONS[0],
                style={'marginBottom': '15px'}
            ),
        ], style=styles['panel']),
        
        # Corpus Stats
        html.Div(id='corpus-stats', style=styles['panel']),
    ], style=styles['controlPanel']),
    
    # Main Content Area
    html.Div([
        dcc.Tabs([
            # Map View Tab
            dcc.Tab(label='Map View', children=[
                html.Div([
                    # Map Container
                    html.Div([
                        html.Iframe(
                            id='map-iframe',
                            srcDoc='',
                            style={'width': '100%', 'height': '100%', 'border': 'none'}
                        )
                    ], style=styles['mapContainer']),
                    
                    # Place Summary
                    html.Div([
                        html.H3("Place Summary", style={'marginBottom': '15px'}),
                        html.Div(id='place-summary', style=styles['panel'])
                    ], style={**styles['panel'], 'width': '600px'})
                ])
            ]),
            
            # Heatmap Tab
            dcc.Tab(label='Heatmap', children=[
                html.Div([
                    # Heatmap Controls
                    html.Div([
                        html.Div([
                            html.Label("Heatmap Intensity", style=styles['labelStyle']),
                            dcc.Slider(
                                id='heatmap-intensity-slider',
                                min=1,
                                max=10,
                                value=3,
                                marks={i: str(i) for i in range(1, 11, 2)}
                            )
                        ], style={'marginBottom': '15px'}),
                        
                        html.Div([
                            html.Label("Point Radius", style=styles['labelStyle']),
                            dcc.Slider(
                                id='heatmap-radius-slider',
                                min=5,
                                max=30,
                                value=15,
                                step=5,
                                marks={i: str(i) for i in [5, 10, 15, 20, 25, 30]}
                            )
                        ], style={'marginBottom': '15px'}),
                        
                        html.Div([
                            html.Label("Blur Amount", style=styles['labelStyle']),
                            dcc.Slider(
                                id='heatmap-blur-slider',
                                min=5,
                                max=20,
                                value=10,
                                step=5,
                                marks={i: str(i) for i in [5, 10, 15, 20]}
                            )
                        ], style={'marginBottom': '15px'}),
                        
                        html.Div([
                            html.Label("Color Scale", style=styles['labelStyle']),
                            dcc.Dropdown(
                                id='heatmap-color-scheme',
                                options=[
                                    {'label': 'Blue-Lime-Red', 'value': 'blue-lime-red'},
                                    {'label': 'Yellow-Red', 'value': 'yellow-red'},
                                    {'label': 'Blue-Purple', 'value': 'blue-purple'}
                                ],
                                value='blue-lime-red',
                                clearable=False
                            )
                        ])
                    ], style={**styles['panel'], 'marginBottom': '15px'}),
                    
                    # Heatmap Display
                    html.Div([
                        html.Iframe(
                            id='heatmap-iframe',
                            srcDoc='',
                            style={'width': '100%', 'height': '700px', 'border': 'none'}
                        )
                    ])
                ])
            ])
        ])
    ], style=styles['mainContent']),
    
    # Store Components
    dcc.Store(id='filtered-corpus'),
    dcc.Store(id='map-view-state', data=EUROPE_VIEW),
    dcc.Store(id='places-data'),
    dcc.Store(id='store-selected-row')
])


app.clientside_callback(
    """
    function(active_cell, data) {
        // If no active cell, hide context menu
        if (!active_cell) {
            return [
                {'display': 'none'},
                null
            ];
        }
        
        // Get the table element
        const table = document.getElementById('places-table');
        
        // Check if row exists
        const row = table.querySelector(`[data-rk="${active_cell.row}"]`);
        if (!row) {
            return [
                {'display': 'none'},
                null
            ];
        }
        
        // Calculate position
        const rect = row.getBoundingClientRect();
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
        
        return [
            {
                'display': 'block',
                'left': (rect.left + scrollLeft + rect.width) + 'px',
                'top': (rect.top + scrollTop) + 'px'
            },
            active_cell.row
        ];
    }
    """,
    [Output('context-menu', 'style'),
     Output('store-selected-row', 'data')],
    [Input('places-table', 'active_cell'),
     State('places-table', 'data')],
    prevent_initial_call=True
)


@callback(
    [Output('corpus-stats', 'children'),
     Output('filtered-corpus', 'data'),
     Output('category-dropdown', 'options'),
     Output('author-dropdown', 'options'),
     Output('title-dropdown', 'options')],
    [Input('year-slider', 'value'),
     Input('category-dropdown', 'value'),
     Input('author-dropdown', 'value'),
     Input('title-dropdown', 'value'),
     Input('places-dropdown', 'value')]
)
def interdependent_filters(years, categories, authors, titles, places):
    # Start with the full dataset
    filtered_corpus = corpus_df.copy()

    # Apply Year Filter
    if years:
        filtered_corpus = filtered_corpus[
            (filtered_corpus['year'] >= years[0]) &
            (filtered_corpus['year'] <= years[1])
        ]

    # Generate Category Options (before applying Category Filter)
    category_options = [{'label': cat, 'value': cat} for cat in sorted(filtered_corpus['category'].unique())]

    # Apply Category Filter
    if categories:
        filtered_corpus = filtered_corpus[filtered_corpus['category'].isin(categories)]

    # Generate Author Options (before applying Author Filter)
    author_options = [{'label': author, 'value': author} for author in sorted(filtered_corpus['author'].unique())]

    # Apply Author Filter
    if authors:
        filtered_corpus = filtered_corpus[filtered_corpus['author'].isin(authors)]

    # Generate Title Options (before applying Title Filter)
    title_options = [{'label': title, 'value': title} for title in sorted(filtered_corpus['Verk'].unique())]

    # Apply Title Filter
    if titles:
        filtered_corpus = filtered_corpus[filtered_corpus['Verk'].isin(titles)]

    # Apply Places Filter
    if places:
        place_books = preprocessed_places[
            preprocessed_places['name'].isin(places)
        ]['docs'].unique()
        filtered_corpus = filtered_corpus[filtered_corpus['dhlabid'].isin(place_books)]

    # Safeguard: Handle empty datasets
    if filtered_corpus.empty:
        return "No data available", [], category_options, author_options, title_options

    # Update stats
    stats = f"Filtered Corpus: {len(filtered_corpus)} records, {len(filtered_corpus['author'].unique())} authors."

    # Convert filtered data to JSON
    filtered_data = filtered_corpus.to_json(date_format='iso', orient='split')

    return stats, filtered_data, category_options, author_options, title_options



# Callback to update map view state


def update_map_view(world_clicks, europe_clicks, current_state):
    ctx = dash.callback_context
    if not ctx.triggered:
        return EUROPE_VIEW
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'world-view-btn':
        return WORLD_VIEW
    elif button_id == 'europe-view-btn':
        return EUROPE_VIEW
    
    return current_state or EUROPE_VIEW

@callback(
    Output('map-iframe', 'srcDoc'),
    [Input('filtered-corpus', 'data'),
     Input('map-view-state', 'data'),
     Input('max-books-slider', 'value'),
     Input('max-places-slider', 'value'),
     Input('basemap-dropdown', 'value'),
     Input('marker-size-slider', 'value')]
)
def update_map(filtered_corpus_json, view_state, max_books, max_places, basemap, marker_size):
    if not filtered_corpus_json:
        raise PreventUpdate
    
    # Get cached data
    cached_data = get_cached_data()
    corpus_df = cached_data['corpus']
    
    # Process data efficiently
    subkorpus = pd.read_json(filtered_corpus_json, orient='split')
    selected_dhlabids = subkorpus.sample(min(len(subkorpus), max_books)).dhlabid
    
    # Use more efficient groupby operations
    places = ti.geo_locations_corpus(selected_dhlabids)
    places = places[places['rank']==1]
    
    all_places = (places.groupby('name', as_index=False)
        .agg({
            'token': 'first',
            'frekv': 'sum',
            'latitude': 'first',
            'longitude': 'first',
            'feature_class': 'first',
            'dhlabid': lambda x: list(x)
        })
    )
    
    # Efficient calculations
    all_places['dispersion'] = all_places['dhlabid'].apply(len) / len(selected_dhlabids)
    all_places['score'] = all_places['frekv']
    significant_places = all_places.nlargest(max_places, 'score')
    
    result = make_map(significant_places, corpus_df, basemap, marker_size, 
                     center=view_state['center'], zoom=view_state['zoom'])
    clean_map_cache()  # Clean cache after generating new map
    return result



@callback(
    Output('place-summary', 'children'),
    [Input('filtered-corpus', 'data'),
     Input('max-books-slider', 'value')]
)
def update_place_summary(filtered_corpus_json, max_books):
    try:
        if not filtered_corpus_json:
            return "No places found"
        
        # Convert filtered corpus back to DataFrame
        subkorpus = pd.read_json(filtered_corpus_json, orient='split')
        logging.info(f"Corpus size: {len(subkorpus)}")
        
        # Sample books if needed
        if len(subkorpus) > max_books:
            selected_dhlabids = subkorpus.sample(max_books).dhlabid
        else:
            selected_dhlabids = subkorpus.dhlabid
        
        logging.info(f"Selected DhLabIDs: {len(selected_dhlabids)}")
        
        # Get and process places
        places = ti.geo_locations_corpus(selected_dhlabids)
        places = places[places['rank']==1]
        
        logging.info(f"Places found: {len(places)}")
        
        # Calculate summary statistics
        total_places = len(places)
        total_frequency = places['frekv'].sum()
        unique_places = places['name'].nunique()
        
        # Group by feature class and count
        feature_class_counts = places['feature_class'].value_counts()
        
        # Create a more detailed summary
        return html.Div([
            html.H4("Place Distribution Summary"),
            html.P(f"Total Unique Places: {unique_places}"),
            html.P(f"Total Place Mentions: {total_frequency:,}"),
            html.Div([
                html.H5("Place Types"),
                html.Ul([
                    html.Li(f"{feature_descriptions.get(fc, fc)}: {count}")
                    for fc, count in feature_class_counts.items()
                ])
            ])
        ])
    except Exception as e:
        logging.error(f"Error in place summary: {e}")
        return html.Div(f"Error generating place summary: {str(e)}")

@callback(
    Output('heatmap-iframe', 'srcDoc'),
    [Input('filtered-corpus', 'data'),
     Input('heatmap-intensity-slider', 'value'),
     Input('heatmap-radius-slider', 'value'),
     Input('heatmap-blur-slider', 'value'),
     Input('heatmap-color-scheme', 'value')]
)
def generate_heatmap(filtered_corpus_json, intensity, radius, blur, color_scheme):
    try:
        if not filtered_corpus_json:
            raise PreventUpdate
        
        # Convert filtered corpus back to DataFrame
        subkorpus = pd.read_json(filtered_corpus_json, orient='split')
        
        # Convert dhlabid to standard Python int
        subkorpus['dhlabid'] = subkorpus['dhlabid'].astype(int)
        dhlabids = subkorpus['dhlabid'].tolist()  # Convert to regular Python list
        
        # Get all places for the corpus
        places = ti.geo_locations_corpus(dhlabids)
        places = places[places['rank']==1]
        
        # Force conversion of numeric columns to float
        places['latitude'] = places['latitude'].astype(float)
        places['longitude'] = places['longitude'].astype(float)
        places['frekv'] = places['frekv'].astype(float)
        
        # Create heatmap data directly without using apply
        heatmap_data = []
        for _, row in places.iterrows():
            freq = float(row['frekv'])
            if freq > 0:  # Only add points with frequency
                heatmap_data.append([
                    float(row['latitude']),
                    float(row['longitude']),
                    float(np.log1p(freq)) * float(intensity)
                ])
        
        # Define color schemes
        color_schemes = {
            'blue-lime-red': {0.4: 'blue', 0.65: 'lime', 1: 'red'},
            'yellow-red': {0.4: '#ffffb2', 0.65: '#fd8d3c', 1: '#bd0026'},
            'blue-purple': {0.4: '#7fcdbb', 0.65: '#2c7fb8', 1: '#253494'}
        }
        
        # Create map
        m = folium.Map(
            location=[55, 15],
            zoom_start=4,
            tiles='CartoDB.Positron'
        )
        
        # Add heatmap layer
        HeatMap(
            heatmap_data,
            radius=int(radius),
            blur=int(blur),
            gradient=color_schemes[color_scheme],
            min_opacity=0.3
        ).add_to(m)
        
        return folium_to_html(m)
        
    except Exception as e:
        logging.error(f"Error generating heatmap: {e}")
        return f"Error generating heatmap: {str(e)}"

if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8055)
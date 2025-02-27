import logging
import os

import dash
import folium
import numpy as np
import pandas as pd
from dash import Dash, Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate
from folium.plugins import HeatMap

from dash_imagination import map_func
from dash_imagination import tools_imag as ti

logging.basicConfig(level=logging.INFO)



# Check if running in production or local
is_production = os.environ.get('ENVIRONMENT') == 'production'

if is_production:
    app = Dash(__name__,  
        routes_pathname_prefix='/imagination_map/', 
        requests_pathname_prefix="/run/imagination_map/")
else:
    # For local development
    app = Dash(__name__)


# Load initial data
cached_data = map_func.get_cached_data()
preprocessed_places = cached_data["places"]
corpus_df = cached_data["corpus"]
authorlist = cached_data["lists"]["authors"]
titlelist = cached_data["lists"]["titles"]
categorylist = cached_data["lists"]["categories"]


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
                options=[{'label': bm, 'value': bm} for bm in map_func.BASEMAP_OPTIONS],
                value=map_func.BASEMAP_OPTIONS[0],
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
    dcc.Store(id='map-view-state', data=map_func.EUROPE_VIEW),
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
        return map_func.EUROPE_VIEW

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if button_id == "world-view-btn":
        return map_func.WORLD_VIEW
    elif button_id == "europe-view-btn":
        return map_func.EUROPE_VIEW

    return current_state or map_func.EUROPE_VIEW


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
    cached_data = map_func.get_cached_data()
    corpus_df = cached_data["corpus"]

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
    
    result = map_func.make_map(significant_places, corpus_df, basemap, marker_size, 
                     center=view_state['center'], zoom=view_state['zoom'])
    map_func.clean_map_cache()  # Clean cache after generating new map
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
        return html.Div(
            [
                html.H4("Place Distribution Summary"),
                html.P(f"Total Unique Places: {unique_places}"),
                html.P(f"Total Place Mentions: {total_frequency:,}"),
                html.Div(
                    [
                        html.H5("Place Types"),
                        html.Ul(
                            [
                                html.Li(f"{map_func.features.get(fc).description}: {count}")
                                for fc, count in feature_class_counts.items()
                            ]
                        ),
                    ]
                ),
            ]
        )
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
        
        return map_func.folium_to_html(m)
        
    except Exception as e:
        logging.error(f"Error generating heatmap: {e}")
        return f"Error generating heatmap: {str(e)}"

if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8055)
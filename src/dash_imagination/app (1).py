import dash
from dash import dcc, html, Input, Output, State, callback
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
import sqlite3
import os
from scipy.stats import gaussian_kde  # Add this import

#=== initialize

# Determine environment
is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
app_name = os.getenv('APP_NAME', 'imagination_map')  # Default to 'imagination_map' if not set

# Initialize Dash App
if is_production:
    server = dash.Dash(
        __name__,
        routes_pathname_prefix=f'/{app_name}/',
        requests_pathname_prefix=f"/run/{app_name}/",
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ]
    )
else:
    server = dash.Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ]
    )

app = server  # Alias for compatibility with existing code





# ============== Database Connection & Queries ==============
def get_db_connection():
    """Create a connection to the SQLite database"""
    db_path = "/mnt/disk1/Github/Dash_Imagination/src/dash_imagination/data/imagination.db"
    
    print(f"Connecting to database at: {db_path}")
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def pdquery(conn, query, params=()):
    """Execute a query and return results as DataFrame"""
    return pd.read_sql_query(query, conn, params=params)

def get_authors():
    """Get list of authors from the database"""
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT author FROM corpus WHERE author IS NOT NULL ORDER BY author")
    conn.close()
    # Convert to plain Python list and filter out None values
    authors = [str(author) for author in df['author'].tolist() if author is not None]
    return authors

def get_categories():
    """Get list of categories from the database"""
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT category FROM corpus WHERE category IS NOT NULL ORDER BY category")
    conn.close()
    # Convert to plain Python list and filter out None values
    categories = [str(category) for category in df['category'].tolist() if category is not None]
    return categories

def get_titles():
    """Get list of book titles from the database"""
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT title, year FROM corpus WHERE title IS NOT NULL ORDER BY title")
    
    # Create title_year safely
    title_year_list = []
    for _, row in df.iterrows():
        title = row['title']
        year = row['year']
        if title is not None:
            year_str = f"({year})" if year is not None else "(n.d.)"
            title_year_list.append(f"{title} {year_str}")
    
    conn.close()
    return title_year_list

def get_places_for_map(filters=None):
    """Get sampled places data from Epikk or uploaded corpus"""
    conn = get_db_connection()
    
    sample_size = filters.get('sample_size', 50) if filters else 50
    
    if filters and 'uploaded_corpus' in filters and filters['uploaded_corpus']:
        dhlabids = filters['uploaded_corpus']
        print(f"Using uploaded corpus with {len(dhlabids)} dhlabids")  # Debug
        book_sample_query = f"""
        SELECT dhlabid
        FROM (SELECT DISTINCT dhlabid FROM book_places WHERE dhlabid IN ({','.join(['?'] * len(dhlabids))}))
        ORDER BY RANDOM()
        LIMIT ?
        """
        sampled_books = pd.read_sql_query(book_sample_query, conn, params=tuple(dhlabids) + (sample_size,))
    else:
        print("Falling back to Epikk sample")  # Debug
        book_sample_query = """
        SELECT dhlabid
        FROM corpus
        WHERE category = 'Diktning: Epikk'
        ORDER BY RANDOM()
        LIMIT ?
        """
        sampled_books = pd.read_sql_query(book_sample_query, conn, params=(sample_size,))
    
    if sampled_books.empty:
        print("No books sampled")
        conn.close()
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
    
    sampled_dhlabids = sampled_books['dhlabid'].tolist()
    print(f"Sampled dhlabids: {len(sampled_dhlabids)} - {sampled_dhlabids[:5]}...")  # Debug
    
    base_query = """
    SELECT 
        p.token, 
        p.modern as name,
        p.latitude, 
        p.longitude, 
        SUM(bp.frequency) as frequency,
        COUNT(DISTINCT bp.dhlabid) as book_count
    FROM 
        places p
    JOIN 
        book_places bp ON p.token = bp.token
    WHERE 
        bp.dhlabid IN ({})
    GROUP BY p.token, p.modern, p.latitude, p.longitude
    ORDER BY frequency DESC
    LIMIT 500
    """.format(','.join(['?'] * len(sampled_dhlabids)))
    
    try:
        df = pd.read_sql_query(base_query, conn, params=tuple(sampled_dhlabids))
        print(f"Sampled {len(sampled_dhlabids)} books, got {len(df)} places")
        conn.close()
        return df
    except Exception as e:
        print(f"Error querying database: {e}")
        conn.close()
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])

def get_place_details(token):
    """Get details for a specific place including books where it appears"""
    conn = get_db_connection()
    
    # Query to get books containing this place
    query = """
    SELECT DISTINCT c.title, c.author, c.year, c.urn, bp.frequency
    FROM corpus c
    JOIN book_places bp ON c.dhlabid = bp.dhlabid
    WHERE bp.token = ?
    ORDER BY bp.frequency DESC
    LIMIT 20
    """
    
    books = pdquery(conn, query, (token,))
    conn.close()
    
    return books

# ============== Initialize Dash App ==============
# Check if running in production or local
is_production = os.environ.get('ENVIRONMENT') == 'production'

default_filters = {
    'year_range': [1850, 1880],
    'categories': [],
    'authors': [],
    'titles': [],
    'max_places': 500,
    'sample_size': 50
}


# Try to get filter options from database
try:
    authors_list = get_authors()
    categories_list = get_categories()
    titles_list = get_titles()
except Exception as e:
    print(f"Error loading filter options: {e}")
    # Fallback sample options
    authors_list = ["Ibsen", "Bjørnson", "Collett", "Lie", "Kielland"]
    categories_list = ["Fiksjon", "Sakprosa", "Poesi", "Drama"]
    titles_list = ["Et dukkehjem (1879)", "Synnøve Solbakken (1857)", "Amtmandens Døttre (1854)"]

# ============== App Layout ==============
app.layout = html.Div([
    # Main map container (takes entire screen)
    html.Div([
        # Map view
        dcc.Graph(
            id='main-map',
            style={'height': '100vh'},
            config={
                'displayModeBar': False,
                'scrollZoom': True
            }
        ),
    ], style={
        'position': 'absolute',
        'top': 0,
        'left': 0,
        'width': '100%',
        'height': '100vh'
    }),
    
     # Map/Heatmap toggle - floating rounded buttons
    html.Div([
        dbc.RadioItems(
            id='view-toggle',
            options=[
                {'label': 'Map', 'value': 'map'},
                {'label': 'Heatmap', 'value': 'heatmap'}
            ],
            value='map',
            inline=True,
            inputClassName='btn-check',
            labelClassName='btn btn-outline-primary rounded-pill mx-1',
            labelCheckedClassName='active',
        )
    ], style={
        'position': 'absolute', 
        'top': '20px', 
        'right': '20px',
        'zIndex': 1000
    }),
    
    # Sidebar toggle button (hamburger menu)
    html.Div([
        html.Button(
            html.I(className="fa fa-bars"),
            id='sidebar-toggle',
            style={
                'background': 'white',
                'border': 'none',
                'borderRadius': '50%',  # Make it circular
                'width': '40px',
                'height': '40px',
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'center',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.2)',
                'cursor': 'pointer'
            }
        )
    ], style={
        'position': 'absolute',
        'top': '20px',
        'left': '20px',
        'zIndex': 1000
    }),
    
    # ImagiNation title - moved to bottom left
    html.Div([
        html.H3("ImagiNation", style={
            'margin': '0',
            'fontWeight': '400',
            'color': '#333',
            'fontSize': '20px'
        })
    ], style={
        'position': 'absolute', 
        'bottom': '20px', 
        'left': '20px',
        'backgroundColor': 'white',
        'padding': '8px 12px',
        'borderRadius': '4px',
        'boxShadow': '0 2px 4px rgba(0,0,0,0.2)',
        'zIndex': 800
    }),
        
    # Sidebar
    html.Div([
        # Sidebar header
        html.Div([
            html.H3("Layers & Filters", style={'margin': '0', 'fontWeight': '400'})
        ], style={'padding': '15px', 'borderBottom': '1px solid #eee', 'marginTop': '50px'}),  # Added marginTop
                
            # Accordion sections for filters
        dbc.Accordion([
                    
            # Add this as a new dbc.AccordionItem in your sidebar accordion
            dbc.AccordionItem([
                # Upload component
                html.Div([
                    html.Label("Upload Custom Corpus", style={'marginBottom': '8px'}),
                    dcc.Upload(
                        id='upload-corpus',
                        children=html.Div([
                            html.I(className="fas fa-file-upload", style={'marginRight': '10px'}),
                            'Drag and Drop or ',
                            html.A('Select File', style={'color': '#4285F4', 'cursor': 'pointer'})
                        ]),
                        style={
                            'width': '100%',
                            'height': '60px',
                            'lineHeight': '60px',
                            'borderWidth': '1px',
                            'borderStyle': 'dashed',
                            'borderRadius': '5px',
                            'textAlign': 'center',
                            'margin': '0 0 15px 0',
                            'background': 'rgba(66, 133, 244, 0.05)'
                        },
                        multiple=False
                    ),
                    
                    # Upload status indicator
                    html.Div(id='upload-status', style={'fontSize': '13px', 'marginBottom': '15px'}),
                    
                    # Reset button
                    html.Div([
                        html.Button([
                            html.I(className="fas fa-trash-alt", style={'marginRight': '5px'}),
                            "Reset to Default Corpus"
                        ], 
                        id='reset-corpus',
                        style={
                            'background': 'none',
                            'border': 'none',
                            'color': '#555',
                            'textDecoration': 'underline',
                            'cursor': 'pointer',
                            'fontSize': '13px',
                            'padding': '0',
                            'display': 'inline-block',
                            'marginTop': '5px'
                        })
                    ], style={'textAlign': 'right'})
                ])
            ], title="Upload Corpus", className="sidebar-section"),
            # Base Maps
            dbc.AccordionItem([
                dbc.RadioItems(
                    id='map-style',
                    options=[
                        {'label': 'Street', 'value': 'open-street-map'},
                        {'label': 'Light', 'value': 'carto-positron'},
                        {'label': 'Dark', 'value': 'carto-darkmatter'},
                        {'label': 'Satellite', 'value': 'white-bg'}
                    ],
                    value='carto-positron',
                    inline=False,
                    labelStyle={'display': 'block', 'margin': '8px 0'}
                ),
            ], title="Base Map", className="sidebar-section"),
            
            # Display Settings
            dbc.AccordionItem([

                html.Label("Sample Size"),
                dcc.Dropdown(
                    id='sample-size',
                    options=[{'label': f"{n} Books", 'value': n} for n in [10, 50, 100, 500]],
                    value=50,
                    className='mb-3'
                ),

                html.Label("Marker Size"),
                dcc.Slider(
                    id='marker-size-slider',
                    min=1,
                    max=6,
                    value=3,
                    step=1,
                    marks={i: str(i) for i in range(1, 7)},
                    className='mb-4'
                ),
                
                html.Label("Max Places"),
                dcc.Slider(
                    id='max-places-slider',
                    min=50,
                    max=500,
                    value=200,
                    step=50,
                    marks={i: str(i) for i in [50, 200, 350, 500, 1000]},
                    className='mb-4'
                ),
                
                # Heatmap settings
                html.Div([
                    html.H5("Heatmap Settings", className='mt-3 mb-2'),
                    
                    html.Label("Intensity"),
                    dcc.Slider(
                        id='heatmap-intensity',
                        min=1,
                        max=10,
                        value=3,
                        marks={i: str(i) for i in range(1, 11, 2)},
                        className='mb-3'
                    ),
                    
                    html.Label("Radius"),
                    dcc.Slider(
                        id='heatmap-radius',
                        min=5,
                        max=30,
                        value=15,
                        step=5,
                        marks={i: str(i) for i in [5, 15, 30]},
                        className='mb-3'
                    ),
                ], id='heatmap-settings', style={'display': 'none'}),
            ], title="Display Settings", className="sidebar-section"),
            
            # Corpus Filters
            dbc.AccordionItem([
                html.Label("Period"),
                dcc.RangeSlider(
                    id='year-slider',
                    min=1814,
                    max=1905,
                    value=[1850, 1880],
                    marks={i: str(i) for i in range(1814, 1906, 20)},
                    className='mb-4'
                ),
                
                html.Label("Category"),
                dcc.Dropdown(
                    id='category-dropdown',
                    options=[{'label': cat, 'value': cat} for cat in categories_list],
                    multi=True,
                    placeholder="Select categories...",
                    className='mb-3'
                ),
                
                html.Label("Author"),
                dcc.Dropdown(
                    id='author-dropdown',
                    options=[{'label': author, 'value': author} for author in authors_list],
                    multi=True,
                    placeholder="Select authors...",
                    className='mb-3'
                ),
                
                html.Label("Work"),
                dcc.Dropdown(
                    id='title-dropdown',
                    options=[{'label': title, 'value': title} for title in titles_list],
                    multi=True,
                    placeholder="Select works...",
                    className='mb-3'
                ),
            ], title="Corpus Filters", className="sidebar-section"),
        ], id="sidebar-accordion", start_collapsed=True),
        
        # Corpus stats
        html.Div(id='corpus-stats', style={'padding': '15px', 'borderTop': '1px solid #eee', 'fontSize': '14px'})
    ], id='sidebar', style={
        'position': 'absolute',
        'top': 0,
        'left': 0,
        'width': '0',  # Initially collapsed
        'height': '100vh',
        'backgroundColor': 'white',
        'boxShadow': '2px 0 4px rgba(0,0,0,0.2)',
        'zIndex': 900,
        'overflowY': 'auto',
        'overflowX': 'hidden',
        'transition': 'width 0.3s ease'
    }),
    
    # Update the place summary container to be draggable
    html.Div([
        html.Div([
            # Header with close button and draggable handle
            html.Div([
                # Add draggable handle
                html.Div(
                    html.I(className="fa fa-grip-horizontal"), 
                    id='drag-handle',
                    style={
                        'cursor': 'grab',
                        'paddingRight': '10px',
                        'color': '#666'
                    }
                ),
                
                html.H4("Place Details", style={'marginBottom': '0', 'fontWeight': '400', 'flex': '1'}),
                
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-summary',
                    style={
                        'background': 'none',
                        'border': 'none',
                        'cursor': 'pointer',
                        'fontSize': '16px'
                    }
                )
            ], style={
                'display': 'flex',
                'justifyContent': 'space-between',
                'alignItems': 'center',
                'marginBottom': '10px',
                'cursor': 'move'  # Indicate it's draggable
            }, id='summary-header'),
            
            # Summary content
            html.Div(id='place-summary')
        ], style={
            'padding': '15px',
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',  # Enhanced shadow
            'border': '1px solid rgba(0,0,0,0.05)'  # Subtle border
        })
    ], id='place-summary-container', style={
        'position': 'absolute',
        'bottom': '80px',
        'left': '20px',
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',  # Initially hidden
        'cursor': 'auto'
    }),
    html.Div(id='reset-status', style={'display': 'none'}),
    # Add a hidden div to store the current position
    html.Div(id='summary-position', style={'display': 'none'}),
    
    dcc.Store(id='filtered-data'),
    dcc.Store(id='selected-place'),
    dcc.Store(id='map-view-state'),
    dcc.Store(id='current-filters', data=default_filters),
    dcc.Store(id='upload-state', data=None),
])

# Add custom CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
        <link rel="stylesheet" href="https://code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://code.jquery.com/ui/1.12.1/jquery-ui.min.js"></script>
        <style>

        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>

    </body>
</html>
'''

# ============== Callbacks ==============

import base64
import io
import pandas as pd
import sqlite3
from dash.exceptions import PreventUpdate

@callback(
    [Output('upload-status', 'children'),
     Output('upload-state', 'data'),
     Output('current-filters', 'data')],
    [Input('upload-corpus', 'contents')],
    [State('upload-corpus', 'filename'),
     State('upload-corpus', 'last_modified'),
     State('current-filters', 'data')]
)
def process_uploaded_corpus(contents, filename, date, current_filters):
    print("process_uploaded_corpus triggered")  # Debug
    if contents is None:
        print("No contents provided")
        return html.Div("Upload a corpus file to begin"), None, default_filters
    
    try:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        
        if filename.endswith('.csv'):
            uploaded_df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
        elif filename.endswith('.xlsx'):
            uploaded_df = pd.read_excel(io.BytesIO(decoded))
        else:
            print(f"Unsupported file type: {filename}")
            return html.Div(['Unsupported file type. Please upload CSV or Excel files.'], style={'color': 'red'}), None, default_filters
        
        id_column = 'dhlabid' if 'dhlabid' in uploaded_df.columns else 'urn'
        if id_column == 'urn':
            conn = get_db_connection()
            urns = uploaded_df['urn'].tolist()
            urn_query = f"SELECT dhlabid, urn FROM corpus WHERE urn IN ({','.join(['?'] * len(urns))})"
            urn_mapping = pd.read_sql_query(urn_query, conn, params=tuple(urns))
            conn.close()
            uploaded_df = uploaded_df.merge(urn_mapping, on='urn', how='inner')
        
        if uploaded_df.empty or 'dhlabid' not in uploaded_df.columns:
            print("No valid dhlabids found")
            return html.Div(['No valid dhlabids found in uploaded file.'], style={'color': 'red'}), None, default_filters
        
        dhlabids = uploaded_df['dhlabid'].tolist()
        updated_filters = current_filters.copy() if current_filters else default_filters.copy()
        updated_filters['uploaded_corpus'] = dhlabids
        
        filtered_corpus_json = uploaded_df.to_json(date_format='iso', orient='split')
        
        print(f"Uploaded {len(dhlabids)} dhlabids: {dhlabids[:5]}...")  # Debug
        print(f"Updated filters: {updated_filters}")  # Debug
        
        return (
            html.Div([html.I(className="fas fa-check-circle", style={'color': 'green', 'marginRight': '8px'}),
                      f'Uploaded {filename} with {len(dhlabids)} books. Showing a sample of {min(updated_filters["sample_size"], len(dhlabids))} books.']),
            filtered_corpus_json,
            updated_filters
        )
    except Exception as e:
        print(f"Upload error: {e}")
        return html.Div(['Error processing the file: ', html.Pre(str(e))], style={'color': 'red'}), None, default_filters


@callback(
    Output('filtered-data', 'data'),  # No allow_duplicate needed here
    [Input('upload-state', 'data'),
     Input('reset-corpus', 'n_clicks')],
    [State('upload-corpus', 'filename')]
)
def update_data_from_upload(upload_data, reset_clicks, filename):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
        
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'upload-state' and upload_data is not None:
        return upload_data
    elif trigger_id == 'reset-corpus' and reset_clicks:
        # Get default corpus
        conn = get_db_connection()
        default_corpus = pd.read_sql_query("SELECT * FROM corpus", conn)
        conn.close()
        
        # Add Verk column
        default_corpus['Verk'] = default_corpus.apply(
            lambda x: f"{x['title'] or 'Uten tittel'} av {x['author'] or 'Ingen'} ({x['year'] or 'n.d.'})", 
            axis=1
        )
        
        return default_corpus.to_json(date_format='iso', orient='split')
    
    raise PreventUpdate

@callback(
    Output('upload-status', 'children', allow_duplicate=True),
    [Input('reset-corpus', 'n_clicks')],
    prevent_initial_call=True
)
def update_reset_status(n_clicks):
    if n_clicks is None:
        raise PreventUpdate
    
    return html.Div([
        html.I(className="fas fa-info-circle", style={'color': 'blue', 'marginRight': '8px'}),
        'Reset to default corpus.'
    ])



# Callback to toggle sidebar
app.clientside_callback(
    """
    function(n_clicks, currentStyle) {
        const newStyle = {...currentStyle};
        
        if (newStyle.width === '0px' || newStyle.width === '0') {
            newStyle.width = '300px';
        } else {
            newStyle.width = '0px';
        }
        
        return newStyle;
    }
    """,
    Output('sidebar', 'style'),
    [Input('sidebar-toggle', 'n_clicks')],
    [State('sidebar', 'style')],
    prevent_initial_call=True
)

# Callback to toggle between map and heatmap views
@callback(
    Output('heatmap-settings', 'style'),
    [Input('view-toggle', 'value')]
)
def toggle_heatmap_settings(view):
    if view == 'heatmap':
        return {'display': 'block'}
    return {'display': 'none'}

# Callback to update current filters
@callback(
    Output('current-filters', 'data'),
    [Input('year-slider', 'value'),
     Input('category-dropdown', 'value'),
     Input('author-dropdown', 'value'),
     Input('title-dropdown', 'value'),
     Input('max-places-slider', 'value'),
     Input('sample-size', 'value')],  # Add this
    [State('current-filters', 'data')]  # Add this to preserve uploaded_corpus
)
def update_filters(years, categories, authors, titles, max_places, sample_size, current_filters):
    updated = current_filters.copy() if current_filters else default_filters.copy()
    updated.update({
        'year_range': years,
        'categories': categories or [],
        'authors': authors or [],
        'titles': titles or [],
        'max_places': max_places,
        'sample_size': sample_size
    })
    print(f"Updated filters: {updated}")  # Debug
    return updated

    
# Callback to update the map with filtered data
@callback(
    Output('main-map', 'figure'),
    [Input('filtered-data', 'data'),
     Input('current-filters', 'data'),
     Input('map-style', 'value'),
     Input('marker-size-slider', 'value'),
     Input('view-toggle', 'value'),
     Input('heatmap-intensity', 'value'),
     Input('heatmap-radius', 'value')]
)
def update_map(filtered_data_json, filters, map_style, marker_size, view_type, heatmap_intensity, heatmap_radius):
    print("update_map triggered")
    if not filters:
        filters = default_filters  # Fallback if None
    
    if filtered_data_json:
        try:
            from io import StringIO
            places_df = pd.read_json(StringIO(filtered_data_json), orient='split')
        except Exception as e:
            print(f"Error reading filtered data: {e}")
            places_df = get_places_for_map(filters)  # Fallback to sampling
    else:
        places_df = get_places_for_map(filters)
    
    print(f"Number of places: {len(places_df)}")
    
    fig = go.Figure()
    if places_df.empty:
        print("Returning empty figure")
        fig.update_layout(mapbox=dict(style=map_style, center=dict(lat=60.5, lon=9.0), zoom=5), margin=dict(l=0, r=0, t=0, b=0), showlegend=False)
        return fig
    
    # Scatter layer (map view)
    sizes = places_df['frequency'].copy()
    min_freq, max_freq = sizes.min(), sizes.max()
    if min_freq != max_freq:
        normalized_sizes = 10 + (sizes - min_freq) / (max_freq - min_freq) * 50
        sizes = normalized_sizes * marker_size
    else:
        sizes = [30 * marker_size] * len(sizes)
    
    fig.add_trace(go.Scattermapbox(
        lat=places_df['latitude'],
        lon=places_df['longitude'],
        mode='markers',
        marker=dict(size=sizes, color='#4285F4', opacity=0.7, sizemode='diameter'),
        text=places_df.apply(lambda row: f"{row['token']} ({row['name']})<br>{int(row['frequency'])} mentions in {int(row['book_count'])} books", axis=1),
        hoverinfo='text',
        customdata=places_df['token'],
        visible=(view_type == 'map'),
        name='Places'
    ))
    
    # Precomputed Heatmap layer
    if len(places_df) > 0:
        try:
            x = places_df['longitude'].values
            y = places_df['latitude'].values
            z = places_df['frequency'].values
            x_grid, y_grid = np.mgrid[x.min():x.max():50j, y.min():y.max():50j]
            positions = np.vstack([x_grid.ravel(), y_grid.ravel()])
            values = np.vstack([x, y])
            kernel = gaussian_kde(values, weights=z, bw_method=heatmap_radius / 100.0)
            density = kernel(positions).T * (heatmap_intensity / 3)
            density = density.reshape(50, 50)
            
            fig.add_trace(go.Heatmap(
                z=density,
                x=x_grid[:, 0],
                y=y_grid[0, :],
                colorscale='Viridis',
                opacity=0.8,
                visible=(view_type == 'heatmap'),
                showscale=False,
                name='Heatmap'
            ))
        except Exception as e:
            print(f"Error computing heatmap: {e}")
            fig.add_trace(go.Heatmap(visible=(view_type == 'heatmap'), name='Heatmap'))
    
    fig.update_layout(mapbox=dict(style=map_style, center=dict(lat=60.5, lon=9.0), zoom=5), margin=dict(l=0, r=0, t=0, b=0), showlegend=False, uirevision='constant')
    print("Returning figure")
    return fig
    
# Callback to update corpus stats
@callback(
    Output('corpus-stats', 'children'),
    [Input('filtered-data', 'data'),
     Input('current-filters', 'data')]
)
def update_corpus_stats(filtered_data_json, filters):
    if not filtered_data_json:
        return "No data available"
    
    try:
        # Convert JSON back to DataFrame
        places_df = pd.read_json(filtered_data_json, orient='split')
        
        if places_df.empty:
            return "No places match the current filters"
        
        # Calculate basic stats
        total_places = len(places_df)
        total_mentions = int(places_df['frequency'].sum())
        total_books = int(places_df['book_count'].sum())
        
        # Format year range
        year_range = f"{filters['year_range'][0]}–{filters['year_range'][1]}" if filters['year_range'] else "All years"
        
        # Format filter counts
        category_count = len(filters['categories']) if filters['categories'] else 0
        author_count = len(filters['authors']) if filters['authors'] else 0
        title_count = len(filters['titles']) if filters['titles'] else 0
        
        # Create stats text
        return html.Div([
            html.P(f"Period: {year_range}"),
            html.P(f"Filters: {category_count} categories, {author_count} authors, {title_count} works"),
            html.P(f"Places shown: {total_places}"),
            html.P(f"Total mentions: {total_mentions:,}"),
        ])
    except Exception as e:
        print(f"Error updating corpus stats: {e}")
        return "Error loading statistics"

# Callback to update place summary when a place is clicked
@callback(
    [Output('place-summary-container', 'style'),
     Output('place-summary', 'children')],
    [Input('main-map', 'clickData')],
    [State('place-summary-container', 'style')]
)
def update_place_summary(click_data, current_style):
    print("Place summary callback triggered")
    
    if click_data is None:
        print("No click data")
        return dash.no_update, dash.no_update
    
    try:
        # Get the clicked point's data
        point = click_data['points'][0]
        
        # For scatter mapbox, we can access the custom data
        if 'customdata' in point:
            token = point['customdata']
            
            # Get place name and frequency from the point data directly
            text = point.get('text', '')
            parts = text.split('<br>')
            place_info = parts[0]
            
            # Get modern name in parentheses if available
            if '(' in place_info and ')' in place_info:
                token_part = place_info.split('(')[0].strip()
                modern_part = place_info.split('(')[1].split(')')[0].strip()
            else:
                token_part = place_info
                modern_part = ""
            
            # Extract frequency from text if available
            frequency = 0
            book_count = 0
            if len(parts) > 1 and 'mentions in' in parts[1]:
                mentions_part = parts[1].split('mentions in')
                try:
                    frequency = int(mentions_part[0].strip())
                    book_count = int(mentions_part[1].split('books')[0].strip())
                except ValueError:
                    print("Could not parse frequency/book count")
            
            # Get books related to this place
            try:
                books_df = get_place_details(token)
            except Exception as e:
                print(f"Error getting place details: {e}")
                books_df = pd.DataFrame(columns=['title', 'author', 'year', 'urn', 'frequency'])
            
            # Create the place summary
            summary = html.Div([
                # Place info
                html.Div([
                    html.H5(token_part, style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                    html.P(f"Appears in {book_count} books with {frequency} total mentions", 
                           style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                
                # Books section - ensure no duplicates by using unique URNs
                html.Div([
                    html.H6(f"Books mentioning this place:", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            # Title and year
                            html.Div(f"{row['title']} ({row['year']})", style={'fontWeight': '500'}),
                            
                            # Author and frequency
                            html.Div([
                                html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                                html.Span(f" • {int(row['frequency'])} mentions", 
                                          style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between'}),
                            
                            # Link to National Library 
                            html.Div([
                                html.A(
                                    "View at National Library", 
                                    href=f"https://nb.no/items/{row['urn']}?searchText=\"{token}\"",
                                    target="_blank",
                                    style={'fontSize': '13px', 'color': '#4285F4'}
                                ) if pd.notna(row['urn']) else ""
                            ])
                        ], style={'marginBottom': '10px', 'paddingBottom': '8px', 
                                   'borderBottom': '1px solid #eee'})
                        for i, row in books_df.iterrows() if pd.notna(row['title'])
                    ]) if not books_df.empty else html.Div("No book details available")
                ])
            ])
            
        else:
            # If it's a densitymapbox (heatmap), we can't get the exact point
            summary = html.Div([
                html.P("Click on individual markers in map view to see place details.")
            ])
        
        # Update the style to make visible
        new_style = dict(current_style)
        new_style['display'] = 'block'
        
        return new_style, summary
    except Exception as e:
        print(f"Error updating place summary: {e}")
        return dash.no_update, dash.no_update

@callback(
    [Output('sample-size', 'value'),
     Output('year-slider', 'value'),
     Output('category-dropdown', 'value'),
     Output('author-dropdown', 'value'),
     Output('title-dropdown', 'value'),
     Output('max-places-slider', 'value')],
    [Input('current-filters', 'data')],
    prevent_initial_call=False
)
def sync_accordion_on_load(filters):
    if not filters:
        filters = default_filters
    print(f"Syncing accordion with filters: {filters}")  # Debug
    return (
        filters['sample_size'],
        filters['year_range'],
        filters['categories'],
        filters['authors'],
        filters['titles'],
        filters['max_places']
    )

app.clientside_callback(
    """
    function(view_type) {
        return {
            'data': [
                {'visible': view_type === 'map'},    // Scattermapbox
                {'visible': view_type === 'heatmap'} // Densitymapbox
            ],
            'layout': {'datarevision': Date.now()}  // Force re-render
        };
    }
    """,
    Output('main-map', 'figure'),
    Input('view-toggle', 'value'),
    prevent_initial_call=True
)
        
# Callback for the close button on place summary
app.clientside_callback(
    """
    function(n_clicks, currentStyle) {
        if (!n_clicks) return dash_clientside.no_update;
        
        const newStyle = {...currentStyle};
        newStyle.display = 'none';
        return newStyle;
    }
    """,
    Output('place-summary-container', 'style', allow_duplicate=True),
    [Input('close-summary', 'n_clicks')],
    [State('place-summary-container', 'style')],
    prevent_initial_call=True
)

# ============== Run Server ==============
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8050, dev_tools_hot_reload=False)
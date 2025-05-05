import dash
from dash import dcc, html, Input, Output, State, callback, callback_context
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
import sqlite3
import os
import base64
import io
from dash.exceptions import PreventUpdate
from components.map import create_map_controls
from components.corpus import create_corpus_controls

#=== initialize

# Determine environment
is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
is_chromebook = os.getenv('ENVIRONMENT', 'development') == 'chromebook'
app_name = os.getenv('APP_NAME', 'imagination-map')  # Default to 'imagination_map' if not set

if is_production:
    db_path = "/app/src/dash_imagination/data/imagination.db"
elif is_chromebook:
    db_path = "/home/yoonsen/Dash_Imagination/src/dash_imagination/data/imagination.db"
else:
    # Development environment - use relative path from current directory
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "imagination.db")
    if not os.path.exists(db_path):
        print(f"Warning: Database not found at {db_path}")
        # Try alternative paths
        alt_paths = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "imagination.db"),
            "/mnt/disk1/Github/Dash_Imagination/src/dash_imagination/data/imagination.db"
        ]
        for path in alt_paths:
            if os.path.exists(path):
                db_path = path
                print(f"Found database at alternative path: {db_path}")
                break

print(f"Using database at: {db_path}")

# Initialize Dash App
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
    ],
    suppress_callback_exceptions=True
)

server = app.server

# Database Connection & Queries
def get_db_connection():
    print(f"Connecting to database at: {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        # You could return a dummy connection or raise the error
        raise

def pdquery(conn, query, params=()):
    return pd.read_sql_query(query, conn, params=params)

def get_authors():
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT author FROM corpus WHERE author IS NOT NULL ORDER BY author")
    conn.close()
    authors = [str(author) for author in df['author'].tolist() if author is not None]
    return authors

def get_categories():
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT category FROM corpus WHERE category IS NOT NULL ORDER BY category")
    conn.close()
    categories = [str(category) for category in df['category'].tolist() if category is not None]
    return categories

def get_titles():
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT title, year FROM corpus WHERE title IS NOT NULL ORDER BY title")
    title_year_list = []
    for _, row in df.iterrows():
        title = row['title']
        year = row['year']
        if title is not None:
            year_str = f"({year})" if year is not None else "(n.d.)"
            title_year_list.append(f"{title} {year_str}")
    conn.close()
    return title_year_list

def get_places_for_map(filters=None, return_total=False):
    conn = get_db_connection()
    sample_size = filters.get('sample_size', 50) if filters else 50
    max_places = filters.get('max_places', 1500) if filters else 1500

    dhlabids=[]
    if filters and 'uploaded_corpus' in filters and filters['uploaded_corpus']:
        dhlabids = filters['uploaded_corpus']
        print(f"Using uploaded corpus with {len(dhlabids)} dhlabids")
        book_sample_query = f"""
        SELECT dhlabid
        FROM (SELECT DISTINCT dhlabid FROM books WHERE dhlabid IN ({','.join(['?'] * len(dhlabids))}))
        ORDER BY RANDOM()
        LIMIT ?
        """
        sampled_books = pd.read_sql_query(book_sample_query, conn, params=tuple(dhlabids) + (sample_size,))
    else:
        print("Falling back to Epikk sample")
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
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'global_counts', 'book_count'])

    sampled_dhlabids = sampled_books['dhlabid'].tolist()
    print(f"Sampled dhlabids: {len(sampled_dhlabids)} - {sampled_dhlabids[:5]}...")

    # Total places query without LIMIT
    if filters and 'uploaded_corpus' in filters:
        total_query = """
        SELECT COUNT(DISTINCT p.token) as total_places
        FROM places p
        JOIN books bp ON p.token = bp.token
        WHERE bp.dhlabid IN ({})
        """.format(','.join(['?'] * len(dhlabids)))
        total_places_df = pd.read_sql_query(total_query, conn, params=tuple(dhlabids))
        total_places = total_places_df['total_places'].iloc[0] if not total_places_df.empty else 0
    else:
        total_places = 0  # Default for non-uploaded corpus

    # Limited places query
    base_query = """
    SELECT p.token, p.modern as name, p.latitude, p.longitude, SUM(bp.book_count) as frequency,
           COUNT(DISTINCT bp.dhlabid) as book_count
    FROM places p
    JOIN books bp ON p.token = bp.token
    WHERE bp.dhlabid IN ({})
    GROUP BY p.token, p.modern, p.latitude, p.longitude
    ORDER BY frequency DESC
    LIMIT ?
    """.format(','.join(['?'] * len(sampled_dhlabids)))
    df = pd.read_sql_query(base_query, conn, params=tuple(sampled_dhlabids) + (max_places,))
    print(f"Sampled {len(sampled_dhlabids)} books, got {len(df)} places")
    conn.close()
    
    if return_total:
        return df, total_places
    return df

def get_place_details(token, filters=None):
    conn = get_db_connection()
    query = """
    SELECT DISTINCT c.title, c.author, c.year, c.urn, bp.book_count
    FROM corpus c
    JOIN books bp ON c.dhlabid = bp.dhlabid
    WHERE bp.token = ?
    """
    params = [token]
    conditions = []
    
    if filters:
        if 'uploaded_corpus' in filters and filters['uploaded_corpus']:
            dhlabids = filters['uploaded_corpus']
            conditions.append(f"c.dhlabid IN ({','.join(['?'] * len(dhlabids))})")
            params.extend(dhlabids)
        if 'categories' in filters and filters['categories']:
            categories = filters['categories']
            conditions.append(f"c.category IN ({','.join(['?'] * len(categories))})")
            params.extend(categories)
        if 'titles' in filters and filters['titles']:
            titles = [title.split(' (')[0] for title in filters['titles']]
            conditions.append(f"c.title IN ({','.join(['?'] * len(titles))})")
            params.extend(titles)
    
    if conditions:
        query += " AND " + " AND ".join(conditions)
    query += " ORDER BY bp.book_count DESC LIMIT 20"
    print(query, params)
    books = pdquery(conn, query, tuple(params))
    conn.close()
    return books


# Initialize variables before layout
default_filters = {
    'year_range': [1850, 1880],
    'categories': [],
    'authors': [],
    'titles': [],
    'max_places': 1500,
    'sample_size': 50
}

# Initialize lists with defaults
authors_list = ["Ibsen", "Bjørnson", "Collett", "Lie", "Kielland"]
categories_list = ["Fiksjon", "Sakprosa", "Poesi", "Drama"]
titles_list = ["Et dukkehjem (1879)", "Synnøve Solbakken (1857)", "Amtmandens Døttre (1854)"]

try:
    authors_list = get_authors()
    categories_list = get_categories()
    titles_list = get_titles()
except Exception as e:
    print(f"Error loading filter options: {e}")

# App Layout
app.layout = html.Div([
    # Main map area (bottom layer)
    html.Div([
        dcc.Graph(
            id='main-map',
            style={'height': '100vh'},
            config={'displayModeBar': False}
        )
    ], style={'position': 'absolute', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0}),
    
    # Top bar (top layer with translucent background)
    html.Div([
        # Database buttons (left)
        html.Div([
            html.Button("Corpus", id='corpus-button', style={
                'padding': '8px 16px',
                'backgroundColor': '#475569',  # Lighter slate
                'color': 'white',
                'border': 'none',
                'borderRadius': '20px',
                'cursor': 'pointer',
                'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                'transition': 'background-color 0.2s'
            }),
            html.Button("Places", id='place-names-toggle', style={
                'padding': '8px 16px',
                'backgroundColor': '#475569',  # Lighter slate
                'color': 'white',
                'border': 'none',
                'borderRadius': '20px',
                'cursor': 'pointer',
                'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                'transition': 'background-color 0.2s',
                'marginLeft': '8px'
            }),
        ], style={'position': 'absolute', 'left': '20px', 'top': '20px', 'pointerEvents': 'auto'}),
        # Display options (right)
        html.Div([
            html.Div([
                html.Div([
                    html.Button("Map", id='map-button', style={
                        'padding': '8px 16px',
                        'backgroundColor': '#3b82f6',  # Lighter blue
                        'color': 'white',
                        'border': 'none',
                        'borderRadius': '20px',
                        'cursor': 'pointer',
                        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                        'transition': 'background-color 0.2s'
                    }),
                    html.Button("Heatmap", id='heatmap-button', style={
                        'padding': '8px 16px',
                        'backgroundColor': '#3b82f6',  # Lighter blue
                        'color': 'white',
                        'border': 'none',
                        'borderRadius': '20px',
                        'cursor': 'pointer',
                        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                        'transition': 'background-color 0.2s',
                        'marginLeft': '8px'
                    }),
                ], style={'display': 'flex', 'alignItems': 'flex-start'}),
                html.Div([
                    html.Label([
                        dcc.Checklist(
                            id='top-cluster-toggle',
                            options=[{'label': 'Cluster', 'value': 'cluster'}],
                            value=['cluster'],
                            style={'marginLeft': '10px', 'display': 'inline-block'}
                        )
                    ], style={'fontSize': '12px', 'color': '#666', 'marginTop': '4px'})
                ])
            ], style={'display': 'inline-block'}),
        ], style={'position': 'absolute', 'right': '20px', 'top': '20px', 'pointerEvents': 'auto'}),
    ], style={
        'position': 'fixed',
        'top': 0,
        'left': 0,
        'right': 0,
        'height': '80px',
        'backgroundColor': 'rgba(255, 255, 255, 0)',
        'zIndex': 1000,
        'pointerEvents': 'none'
    }),
    
    # Rest of the components...
    html.Div(id='cached-data', style={'display': 'none'}),

    # Map controls in a modal
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Corpus Controls")),
        dbc.ModalBody([
            create_map_controls(),
            html.Hr(),
            html.Div([
                html.H5("Corpus Information", style={'marginBottom': '10px'}),
                html.Div(id='corpus-stats')
            ])
        ]),
        dbc.ModalFooter(
            dbc.Button("Close", id="close-corpus-modal", className="ml-auto")
        )
    ], id="corpus-modal", size="lg"),

    # ImagiNation info button and modal
    html.Div([
        html.Button([
            html.H3("ImagiNation", style={
                'margin': '0',
                'fontWeight': '400',
                'color': '#333',
                'fontSize': '20px'
            }),
            html.Span("Click for info", style={
                'fontSize': '11px',
                'color': '#666',
                'display': 'block',
                'marginTop': '2px'
            })
        ], 
        id='info-button',
        style={
            'background': 'white',
            'border': 'none',
            'borderRadius': '4px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.2)',
            'padding': '8px 12px',
            'cursor': 'pointer',
            'textAlign': 'left',
            'width': '100%'
        }),
        
        # Modal for project information
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("About the ImagiNation Project")),
            dbc.ModalBody([
                html.H5("Project Overview"),
                html.P("The ImagiNation project maps places mentioned in Norwegian literature, visualizing the geography of our literary imagination."),
                
                html.H5("Tools & Resources"),
                html.P([
                    "Build your own corpus with our ",
                    html.A("Corpus App", 
                           href="https://korpus.imagination.it.ntnu.no/", 
                           target="_blank",
                           style={'fontWeight': 'bold'})
                ]),
                
                html.H5("How to Use This Map"),
                html.P("Use the controls to toggle between map and heatmap views. Enable clustering for a clearer overview of dense areas. Click on places to see details about their mentions in literature."),
                
                html.H5("About the Data"),
                html.P("This visualization uses a database of literary works from the National Library of Norway, with place names extracted using natural language processing techniques."),
                
                html.Hr(),
                html.P("A research project by the Norwegian University of Science and Technology (NTNU)", style={'fontSize': '0.9rem', 'color': '#666'}),
            ]),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-info-modal", className="ml-auto")
            ),
        ], id="info-modal", is_open=False, size="lg"),
    ], style={
        'position': 'absolute',
        'bottom': '20px',
        'left': '20px',
        'zIndex': 800,
        'width': 'auto'
    }),
    
    # Place summary container
    html.Div([
        html.Div([
            html.Div([
                html.I(className="fa fa-grip-horizontal"),
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
                'cursor': 'move'
            }, id='summary-header'),
            html.Div(id='place-summary')
        ], style={
            'padding': '15px',
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',
            'border': '1px solid rgba(0,0,0,0.05)'
        })
    ], id='place-summary-container', style={
        'position': 'absolute',
        'bottom': '80px',
        'left': '20px',
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',
        'cursor': 'auto'
    }),

    # Place names container
    html.Div([
        html.Div([
            html.Div([
                html.I(className="fa fa-list", style={'marginRight': '8px'}),
                html.H4("Place Names", style={'marginBottom': '0', 'fontWeight': '400', 'flex': '1'}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-places',
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
                'cursor': 'grab'
            }, id='places-header'),
            html.Div([
                dcc.Dropdown(
                    id='places-limit-dropdown',
                    options=[
                        {'label': 'Top 100', 'value': 100},
                        {'label': 'Top 250', 'value': 250},
                        {'label': 'Top 500', 'value': 500},
                        {'label': 'Top 1000', 'value': 1000}
                    ],
                    value=250,
                    clearable=False,
                    className='mb-2'
                ),
                dcc.Input(
                    id='place-search',
                    type='text',
                    placeholder='Search places...',
                    className='form-control mb-2'
                ),
                html.Div(id='place-list', style={'maxHeight': '300px', 'overflowY': 'auto'})
            ])
        ], style={
            'padding': '15px',
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',
            'border': '1px solid rgba(0,0,0,0.05)'
        })
    ], id='place-names-container', style={
        'position': 'absolute',
        'top': '80px',
        'right': '20px',
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',
        'cursor': 'auto'
    }),

    # Hidden divs and stores
    html.Div(id='reset-status', style={'display': 'none'}),
    dcc.Store(id='filtered-data'),
    dcc.Store(id='selected-place'),
    dcc.Store(id='map-view-state'),
    dcc.Store(id='current-filters', data=default_filters),
    dcc.Store(id='upload-state', data=None),
    dcc.Store(id='category-selection', data=default_filters['categories']),

    # Hidden div for view type
    html.Div(id='view-type', style={'display': 'none'}),
], id='main-container')

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
            #place-summary-container {
                /* Removed slow transition */
            }
            #drag-handle {
                cursor: grab;
            }
            #place-summary-container.dragging {
                opacity: 0.7;
            }
            /* Button hover effects */
            #corpus-button:hover, #place-names-toggle:hover {
                background-color: #1e293b !important;
            }
            #map-button:hover, #heatmap-button:hover {
                background-color: #1d4ed8 !important;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script>
            $("#place-summary-container").draggable({
                handle: "#drag-handle",
                containment: "parent",
                start: function(event, ui) {
                    $(this).addClass("dragging");
                },
                stop: function(event, ui) {
                    $(this).removeClass("dragging");
                    var pos = $(this).position();
                    $("#summary-position").text(JSON.stringify({top: pos.top, left: pos.left}));
                }
            });
            var initialPos = $("#summary-position").text() ? JSON.parse($("#summary-position").text()) : {top: 0, left: 0};
            $("#place-summary-container").css({top: initialPos.top, left: initialPos.left});
        </script>
    </body>
</html>
'''

@app.callback(
    [Output('upload-status', 'children'),
     Output('upload-state', 'data'),
     Output('current-filters', 'data')],
    [Input('upload-corpus', 'contents'),
     Input('max-places-slider', 'value'),
     Input('sample-size', 'value'),
     Input('reset-corpus', 'n_clicks')],
    [State('upload-corpus', 'filename'),
     State('upload-corpus', 'last_modified'),
     State('current-filters', 'data')]
)
def update_state_and_filters(contents, max_places, sample_size, reset_clicks, filename, date, current_filters):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'reset-corpus':
        return '', {}, default_filters
    
    if trigger_id == 'upload-corpus' and contents:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            df = pd.read_excel(io.BytesIO(decoded))
            if 'dhlabid' not in df.columns:
                return html.Div('Error: File must contain a dhlabid column', style={'color': 'red'}), {}, current_filters
            
            dhlabids = df['dhlabid'].tolist()
            new_filters = current_filters.copy() if current_filters else default_filters.copy()
            new_filters['uploaded_corpus'] = dhlabids
            new_filters['sample_size'] = sample_size
            new_filters['max_places'] = max_places
            
            return html.Div(f'Successfully loaded {len(dhlabids)} books', style={'color': 'green'}), {'uploaded': True}, new_filters
        except Exception as e:
            return html.Div(f'Error processing file: {str(e)}', style={'color': 'red'}), {}, current_filters
    
    new_filters = current_filters.copy() if current_filters else default_filters.copy()
    new_filters['sample_size'] = sample_size
    new_filters['max_places'] = max_places
    
    return html.Div('', style={'display': 'none'}), current_filters.get('upload_state', {}), new_filters

# Add this callback to toggle the info modal

@app.callback(
    Output('info-modal', 'is_open'),
    [Input('info-button', 'n_clicks'),
     Input('close-info-modal', 'n_clicks')],
    [State('info-modal', 'is_open')]
)
def toggle_info_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


@app.callback(
    Output('place-names-container', 'style'),
    [Input('place-names-toggle', 'n_clicks')],
    [State('place-names-container', 'style')]
)
def toggle_place_names_container(n_clicks, current_style):
    if n_clicks is None:
        raise PreventUpdate
    
    new_style = dict(current_style)
    new_style['display'] = 'block' if current_style.get('display') == 'none' else 'none'
    return new_style

# Close button callback
app.clientside_callback(
    """
    function(n_clicks, currentStyle) {
        if (!n_clicks) return dash_clientside.no_update;
        
        const newStyle = {...currentStyle};
        newStyle.display = 'none';
        return newStyle;
    }
    """,
    Output('place-names-container', 'style', allow_duplicate=True),
    [Input('close-places', 'n_clicks')],
    [State('place-names-container', 'style')],
    prevent_initial_call=True
)


@app.callback(
    Output('filtered-data', 'data'),
    [Input('current-filters', 'data'),
     Input('upload-state', 'data'),
     Input('reset-corpus', 'n_clicks')],
    [State('upload-corpus', 'filename')],
    prevent_initial_call=False
)
def update_filtered_data(filters, upload_state, reset_clicks, filename):
    print("!!! update_filtered_data TRIGGERED !!!")
    print(f"Filters: {filters}")
    print(f"Upload state: {upload_state}")
    print(f"Reset clicks: {reset_clicks}")
    
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if triggered_id == 'reset-corpus' and reset_clicks:
        print("Resetting to default corpus...")
        # Use default filters to get places data
        places_df = get_places_for_map(default_filters)
        print(f"Reset to default corpus, got {len(places_df)} places")
        return places_df.to_json(date_format='iso', orient='split')
    
    if not filters:
        filters = default_filters
    
    # Handle uploaded corpus data
    if triggered_id == 'upload-state' and upload_state:
        try:
            if isinstance(upload_state, dict) and 'uploaded' in upload_state:
                print("Using uploaded corpus data from state")
                # The dhlabids are already in the filters from the upload_state callback
                pass
            else:
                print("Invalid upload state format")
                return dash.no_update
        except Exception as e:
            print(f"Error processing upload state: {e}")
            return dash.no_update
    
    try:
        places_df = get_places_for_map(filters)
        print(f"Cached {len(places_df)} places")
        return places_df.to_json(date_format='iso', orient='split')
    except Exception as e:
        print(f"Error getting places data: {e}")
        return dash.no_update

@app.callback(
    [Output('category-selection', 'data')] + [
        Output({'type': 'category-button', 'index': cat}, 'color')
        for cat in categories_list
    ],
    [Input({'type': 'category-button', 'index': cat}, 'n_clicks')
     for cat in categories_list],
    [State('category-selection', 'data')]
)
def update_category_selection(*args):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    selected_categories = args[-1] if args[-1] else []
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    category = eval(triggered_id)['index']
    
    if category in selected_categories:
        selected_categories.remove(category)
    else:
        selected_categories.append(category)
    
    # Update button colors
    button_colors = ['primary' if cat in selected_categories else 'secondary' for cat in categories_list]
    
    return [selected_categories] + button_colors

@app.callback(
    Output('main-map', 'figure'),
    [Input('filtered-data', 'data'),
     Input('map-style', 'value'),
     Input('marker-size-slider', 'value'),
     Input('view-toggle', 'value'),
     Input('heatmap-intensity', 'value'),
     Input('heatmap-radius', 'value'),
     Input('top-cluster-toggle', 'value')]
)
def update_map(filtered_data_json, map_style, marker_size, view_type, heatmap_intensity, heatmap_radius, cluster_toggle):
    print("!!! update_map TRIGGERED !!!")
    print(f"View type: {view_type}")
    print(f"Filtered data: {filtered_data_json is not None}")
    print(f"Cluster toggle: {cluster_toggle}")
    
    if filtered_data_json is None:
        print("No cached data available")
        return go.Figure()
    
    # Load cached data
    places_df = pd.read_json(io.StringIO(filtered_data_json), orient='split')
    print(f"Number of places from cache: {len(places_df)}")
    print(f"Places data: {places_df.head()}")
    
    fig = go.Figure()
    if places_df.empty:
        print("Returning empty figure")
        fig.update_layout(
            map=dict(style=map_style or 'open-street-map', center=dict(lat=60.5, lon=9.0), zoom=5),
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        return fig
    
    # Clean data
    places_df = places_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude', 'frequency'])
    print(f"Places after cleaning: {len(places_df)}")
    
    # Logarithmic scale for marker sizes with constrained relative scaling
    sizes = places_df['frequency'].fillna(1).copy()
    sizes = np.log1p(sizes)  # Logarithmic transformation (log(1 + x))
    min_size, max_size = sizes.min(), sizes.max()
    base_size = 8 * marker_size  # Slightly smaller base size
    size_range = 15 * marker_size  # Reduced range for more relative consistency
    if min_size != max_size:
        sizes = base_size + (sizes - min_size) / (max_size - min_size) * size_range
    else:
        sizes = [base_size] * len(sizes)
    print(f"Marker sizes (log scale, constrained) - min: {sizes.min()}, max: {sizes.max()}")
    
    # Aggregate data for tooltips
    places_df['hover_text'] = places_df.apply(
        lambda row: f"{row['token']} ({row['name']})<br>Mentions: {int(row['frequency'])}<br>Books: {int(row['book_count'])}",
        axis=1
    )
    
    # Determine if clustering is enabled
    use_clustering = cluster_toggle and 'cluster' in cluster_toggle
    
    if use_clustering:
        # Simple clustering based on zoom level with a wider radius (approx 200km)
        zoom = 5  # Default zoom, to be updated with map-view-state if available
        
        # Increase the base threshold for larger clusters
        # For reference, 1 degree of latitude is roughly 111km
        # So for a 200km radius, we want a threshold around 1.8 degrees
        base_threshold = 1.8  # Approximately 200km radius
        threshold = max(0.1, base_threshold / (zoom / 5))  # Adjust with zoom but keep larger base value
        
        clustered = places_df.copy()
        # Ensure we have valid numeric values for clustering
        clustered['latitude'] = pd.to_numeric(clustered['latitude'], errors='coerce')
        clustered['longitude'] = pd.to_numeric(clustered['longitude'], errors='coerce')
        clustered = clustered.dropna(subset=['latitude', 'longitude'])
        
        if not clustered.empty:
            clustered['cluster'] = ((clustered['latitude'] / threshold).round() * 1000 + 
                                  (clustered['longitude'] / threshold).round()).astype(int)
            
            # Aggregate clustered points with unique place names
            cluster_data = clustered.groupby('cluster').agg({
                'latitude': 'mean',
                'longitude': 'mean',
                'frequency': 'sum',
                'book_count': 'sum',
                'token': lambda x: '<br>'.join([str(t) for t in dict.fromkeys(x) if t is not None]),  # Handle None values
                'name': lambda x: '<br>'.join([str(n) for n in dict.fromkeys(x) if n is not None]),  # Handle None values
                'hover_text': 'first'  # Use first for simplicity
            }).reset_index()
            cluster_data['count'] = clustered.groupby('cluster').size().values
            cluster_data['hover_text'] = cluster_data.apply(
                lambda row: f"""Cluster of {row['count']} places<br>Total Mentions: {int(row['frequency'])}<br>Total Books: {int(row['book_count'])}<br>Example place: {row['token'].split('<br>')[0] if row['token'] else 'Unknown'}""",
                axis=1
            )
            cluster_data['size'] = np.log1p(cluster_data['count']) * marker_size * 5  # Size based on cluster count
            
            # Add clustered markers
            fig.add_trace(go.Scattermap(
                lat=cluster_data['latitude'],
                lon=cluster_data['longitude'],
                mode='markers',
                marker=dict(size=cluster_data['size'], color='#1E40AF', opacity=0.7, sizemode='diameter'),
                text=cluster_data['hover_text'],
                hoverinfo='text',
                visible=(view_type == 'points'),
                name='Clusters'
            ))
        else:
            print("No valid data for clustering")
    else:
        # Add individual markers
        fig.add_trace(go.Scattermap(
            lat=places_df['latitude'],
            lon=places_df['longitude'],
            mode='markers',
            marker=dict(size=sizes, color='#3b82f6', opacity=0.7, sizemode='diameter'),
            text=places_df['hover_text'],
            hoverinfo='text',
            customdata=places_df['token'],
            visible=(view_type == 'points'),
            name='Places'
        ))
    
    heatmap_visible = view_type == 'heatmap'
    print(f"Heatmap mode: {heatmap_visible}, Places available: {len(places_df)}")
    if len(places_df) > 0 and heatmap_visible:
        try:
            x = places_df['longitude'].values
            y = places_df['latitude'].values
            z = places_df['frequency'].fillna(1).values
            z = np.log1p(z)  # Logarithmic transformation for heatmap intensity
            print(f"Raw heatmap data - x: {len(x)}, y: {len(y)}, z: {len(z)}")
            mask = (~np.isnan(x)) & (~np.isnan(y)) & (~np.isnan(z)) & (~np.isinf(x)) & (~np.isinf(y)) & (~np.isinf(z))
            x, y, z = x[mask], y[mask], z[mask]
            print(f"Cleaned heatmap data - x: {len(x)}, y: {len(y)}, z: {len(z)}")
            if len(x) < 2:
                print("Not enough valid data for heatmap, using fallback")
                fig.add_trace(go.Densitymap(
                    lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap'
                ))
            else:
                heatmap_actual_radius = (heatmap_radius ** 0.5) * 10

                fig.add_trace(go.Densitymap(
                    lat=y,
                    lon=x,
                    z=z,
                    radius=heatmap_actual_radius,  # Use this transformed value
                    colorscale='Viridis',
                    opacity=0.8 * (heatmap_intensity / 10),
                    showscale=True,
                    visible=True,
                    name='Heatmap'
                ))
        except Exception as e:
            print(f"Heatmap error: {e}")
            fig.add_trace(go.Densitymap(
                lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap'
            ))
    else:
        fig.add_trace(go.Densitymap(visible=False, name='Heatmap'))
    
    fig.update_layout(
        map=dict(style=map_style or 'open-street-map', center=dict(lat=60.5, lon=9.0), zoom=5),
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        uirevision='constant'
    )
    print("Returning populated figure")
    return fig

@app.callback(
    Output('place-list', 'children'),
    [Input('filtered-data', 'data'),
     Input('places-limit-dropdown', 'value'),
     Input('place-search', 'value')]
)
def update_place_list(filtered_data_json, limit, search_term):
    if filtered_data_json is None:
        return html.Div("No places available")
    
    # Load cached data
    places_df = pd.read_json(io.StringIO(filtered_data_json), orient='split')
    
    if places_df.empty:
        return html.Div("No places available")
    
    # Sort by frequency
    places_df = places_df.sort_values(by='frequency', ascending=False)
    
    # Apply search filter if provided
    if search_term and len(search_term) > 2:
        search_term = search_term.lower()
        places_df = places_df[
            places_df['token'].str.lower().str.contains(search_term) | 
            places_df['name'].str.lower().str.contains(search_term)
        ]
    
    # Limit to top N places
    places_df = places_df.head(limit)
    
    # Create list items
    place_items = []
    for i, row in places_df.iterrows():
        place_items.append(html.Div([
            html.Div(f"{row['token']} ({row['name']})", style={'fontWeight': 'bold'}),
            html.Div(f"Mentions: {int(row['frequency'])} • Books: {int(row['book_count'])}", 
                     style={'fontSize': '0.8rem', 'color': '#666'})
        ], style={'borderBottom': '1px solid #eee', 'padding': '5px 0'}))
    
    if not place_items:
        return html.Div("No matching places found")
    
    return html.Div([
        html.Div(f"Showing {len(place_items)} of {len(places_df)} places", 
                 style={'marginBottom': '8px', 'fontSize': '0.8rem', 'color': '#666'}),
        html.Div(place_items)
    ])


# Callback to update place summary
@app.callback(
    [Output('place-summary-container', 'style'),
     Output('place-summary', 'children')],
    [Input('main-map', 'clickData')],
    [State('place-summary-container', 'style'),
     State('current-filters', 'data')]
)
def update_place_summary(click_data, current_style, filters):
    print("Place summary callback triggered")
    if click_data is None:
        print("No click data")
        return dash.no_update, dash.no_update
    
    try:
        point = click_data['points'][0]
        token = point.get('customdata')
        text = point.get('text', '')
        parts = text.split('<br>')
        
        # Handle both individual points and clusters
        if 'Cluster of' in text:
            # This is a cluster
            cluster_info = parts[0].split('Cluster of ')[1].split(' places')[0]
            total_mentions = int(parts[1].split('Total Mentions: ')[1])
            total_books = int(parts[2].split('Total Books: ')[1])
            example_place = parts[3].split('Example place: ')[1]
            
            summary = html.Div([
                html.Div([
                    html.H5(f"Cluster of {cluster_info} Places", style={'marginBottom': '5px'}),
                    html.P(f"Total Mentions: {total_mentions}", style={'fontSize': '14px', 'color': '#666'}),
                    html.P(f"Total Books: {total_books}", style={'fontSize': '14px', 'color': '#666'}),
                    html.P(f"Example place: {example_place}", style={'fontSize': '14px', 'color': '#666'}),
                    html.Hr(style={'margin': '10px 0'})
                ])
            ])
        else:
            # This is an individual point
            place_info = parts[0]
            if '(' in place_info and ')' in place_info:
                token_part = place_info.split('(')[0].strip()
                modern_part = place_info.split('(')[1].split(')')[0].strip()
            else:
                token_part = place_info
                modern_part = ""
            
            frequency = 0
            book_count = 0
            if len(parts) > 1 and 'Mentions' in parts[1]:
                mentions_part = parts[1].split('Mentions: ')
                try:
                    frequency = int(mentions_part[1].split('<br>')[0].strip())
                    book_count = int(parts[2].split('Books: ')[1].strip())
                except (ValueError, IndexError):
                    print("Could not parse frequency/book count")
            
            try:
                books_df = get_place_details(token, filters)
                print(f"Got {len(books_df)} books for place {token}")
            except Exception as e:
                print(f"Error getting place details: {e}")
                books_df = pd.DataFrame(columns=['title', 'author', 'year', 'urn', 'book_count'])
            
            summary = html.Div([
                html.Div([
                    html.H5(token_part, style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                    html.P(f"Appears in {book_count} books with {frequency} total mentions", style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                html.Div([
                    html.H6(f"Books mentioning this place:", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            html.Div(f"{row['title']} ({row['year']})", style={'fontWeight': '500'}),
                            html.Div([
                                html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                                html.Span(f" • {int(row['book_count'])} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between'}),
                            html.Div([
                                html.A("View at National Library", href=f"https://www.nb.no/items/{row['urn']}?searchText=\"{token}\"",
                                       target="_blank", style={'fontSize': '13px', 'color': '#4285F4'})
                                if pd.notna(row['urn']) else ""
                            ])
                        ], style={'marginBottom': '10px', 'paddingBottom': '8px', 'borderBottom': '1px solid #eee'})
                        for i, row in books_df.iterrows() if pd.notna(row['title'])
                    ]) if not books_df.empty else html.Div("No book details available")
                ])
            ])
        
        new_style = dict(current_style)
        new_style['display'] = 'block'
        return new_style, summary
    except Exception as e:
        print(f"Error updating place summary: {e}")
        return dash.no_update, dash.no_update

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

# Callback to toggle heatmap settings visibility
@callback(
    Output('heatmap-settings', 'style'),
    [Input('view-toggle', 'value')]
)
def toggle_heatmap_settings(view):
    if view == 'heatmap':
        return {'display': 'block'}
    return {'display': 'none'}

# Callback to update map view state
app.clientside_callback(
    """
    function(relayoutData) {
        if (relayoutData && relayoutData['map.zoom']) {
            return {'zoom': relayoutData['map.zoom']};
        }
        return dash_clientside.no_update;
    }
    """,
    Output('map-view-state', 'data'),
    [Input('main-map', 'relayoutData')],
    prevent_initial_call=True
)

# Callback to update corpus stats
@app.callback(
    Output('corpus-stats', 'children'),
    [Input('current-filters', 'data')]
)
def update_corpus_stats(filters):
    print("!!! update_corpus_stats TRIGGERED !!!")
    if not filters:
        return "No filters available"
    
    # Determine the corpus source
    conn = get_db_connection()
    if filters.get('uploaded_corpus'):
        dhlabids = filters['uploaded_corpus']
        print(f"Using uploaded corpus with {len(dhlabids)} dhlabids")
        num_books = len(dhlabids)
        book_query = f"""
        SELECT dhlabid, year
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(dhlabids))})
        AND year IS NOT NULL
        """
        books_df = pd.read_sql_query(book_query, conn, params=tuple(dhlabids))
    elif filters.get('categories') and filters['categories']:
        categories = filters['categories']
        print(f"Using category-based corpus with categories: {categories}")
        book_query = f"""
        SELECT dhlabid, year
        FROM corpus
        WHERE category IN ({','.join(['?'] * len(categories))})
        AND year IS NOT NULL
        """
        books_df = pd.read_sql_query(book_query, conn, params=tuple(categories))
        num_books = len(books_df)
    else:
        print("Falling back to default Epikk sample")
        book_query = """
        SELECT dhlabid, year
        FROM corpus
        WHERE category = 'Diktning: Epikk'
        AND year IS NOT NULL
        LIMIT 50
        """
        books_df = pd.read_sql_query(book_query, conn)
        num_books = len(books_df)
    
    # Get the period from metadata
    if not books_df.empty:
        min_year = int(books_df['year'].min())
        max_year = int(books_df['year'].max())
        year_range = f"{min_year}–{max_year}"
    else:
        year_range = "Unknown period"
    
    # Get total places and filtered places
    places_df, total_places = get_places_for_map(filters, return_total=True)
    if places_df.empty:
        return "No places match the current filters"
    
    total_places_shown = len(places_df)
    total_mentions = int(places_df['frequency'].sum())
    total_books = int(places_df['book_count'].sum())
    category_count = len(filters['categories']) if filters['categories'] else 0
    title_count = len(filters['titles']) if filters['titles'] else 0
    
    conn.close()
    
    # Customize description based on corpus source
    corpus_source = "Uploaded corpus" if filters.get('uploaded_corpus') else "Category-based corpus" if filters.get('categories') else "Default Epikk sample"
    return html.Div([
        html.P(f"Corpus source: {corpus_source}"),
        html.P(f"Number of books: {num_books}"),
        html.P(f"Total places in corpus: {total_places}"),  # Added back
        html.P(f"Period: {year_range}"),
        html.P(f"Filters: {category_count} categories, {title_count} works"),
        html.P(f"Places shown: {total_places_shown}"),
        html.P(f"Total mentions: {total_mentions:,}"),
    ])

# Add callback to toggle corpus modal
@app.callback(
    Output('corpus-modal', 'is_open'),
    [Input('corpus-button', 'n_clicks'),
     Input('close-corpus-modal', 'n_clicks')],
    [State('corpus-modal', 'is_open')]
)
def toggle_corpus_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open

# Callback to handle view type from buttons
@app.callback(
    Output('view-toggle', 'value'),
    [Input('map-button', 'n_clicks'),
     Input('heatmap-button', 'n_clicks')],
    [State('view-toggle', 'value')]
)
def update_view_type_from_buttons(map_clicks, heatmap_clicks, current_view):
    ctx = callback_context
    if not ctx.triggered:
        return current_view
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if button_id == 'map-button':
        return 'points'
    elif button_id == 'heatmap-button':
        return 'heatmap'
    return current_view

# Run Server
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8065, dev_tools_hot_reload=False)
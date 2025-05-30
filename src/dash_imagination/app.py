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
from dash_imagination.components.map import create_map_controls
from dash_imagination.components.corpus import create_corpus_controls, create_visualization_controls
from scipy.spatial import ConvexHull
import math
from dash_imagination.components.places.place_similarity import create_place_similarity_controls
from dash_imagination.components.places.place_similarity_dialog import create_place_similarity_dialog
from dash_imagination.utils.db import get_db_connection
from dash_imagination.utils.global_state import get_current_state, update_from_books, clear_state
import plotly.express as px
import json
from flask import request, send_file

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
    # Development environment - use the correct path directly
    db_path = "/mnt/disk1/Github/Dash_Imagination/src/dash_imagination/data/imagination.db"
    if not os.path.exists(db_path):
        print(f"Warning: Database not found at {db_path}")
        # Try alternative path
        alt_path = "/mnt/disk1/Github/Dash_Imagination/src/data/imagination.db"
        if os.path.exists(alt_path):
            print(f"Found database at alternative path: {alt_path}")
            db_path = alt_path

print(f"Using database at: {db_path}")

# Initialize Dash App
if is_production:
    app = dash.Dash(
        __name__,
        routes_pathname_prefix=f'/{app_name}/',
        requests_pathname_prefix=f"/run/{app_name}/app/",
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ],
        suppress_callback_exceptions=True
    )
else:
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

# Initialize variables before layout
default_filters = {
    'categories': [],
    'titles': [],
    'sample_size': 0,
    'max_places': 0,
    'year_range': [1814, 1905]
}

def get_places_for_map(filters=None, return_total=False, selected_tokens=None):
    """Get places data for the map visualization."""
    if filters is None:
        filters = {}
    
    # Enforce maximum limit on places for performance
    MAX_PLACES = 2000  # Hard limit for map performance
    
    conn = get_db_connection()
    try:
        # Get current state
        books, places = get_current_state()
        
        if selected_tokens:
            # If we have selected tokens, use them directly but include corpus stats
            query = """
            WITH selected_places AS (
                SELECT 
                    p.token,
                    p.modern as name,
                    p.latitude,
                    p.longitude
                FROM places p
                WHERE p.token IN ({})
                AND p.latitude IS NOT NULL 
                AND p.longitude IS NOT NULL
                AND p.latitude != '0'
                AND p.longitude != '0'
            )
            SELECT 
                sp.token,
                sp.name,
                sp.latitude,
                sp.longitude,
                SUM(b.book_count) as frequency,
                COUNT(DISTINCT b.dhlabid) as book_count
            FROM selected_places sp
            LEFT JOIN books b ON sp.token = b.token
            WHERE b.dhlabid IN ({})
            GROUP BY sp.token, sp.name, sp.latitude, sp.longitude
            """
            # Format the query with both selected tokens and books
            query = query.format(
                ','.join(['?'] * len(selected_tokens)),
                ','.join(['?'] * len(books))
            )
            places_df = pd.read_sql_query(query, conn, params=tuple(selected_tokens + books))
        else:
            # Use books for corpus-based place generation
            query = """
            WITH filtered_books AS (
                SELECT DISTINCT b.dhlabid
                FROM books b
                WHERE b.dhlabid IN ({})
            )
            SELECT 
                b.token,
                p.modern as name,
                p.latitude,
                p.longitude,
                SUM(b.book_count) as frequency,
                COUNT(DISTINCT b.dhlabid) as book_count
            FROM books b
            JOIN places p ON b.token = p.token
            JOIN filtered_books fb ON b.dhlabid = fb.dhlabid
            WHERE p.latitude IS NOT NULL 
            AND p.longitude IS NOT NULL
            AND p.latitude != '0'
            AND p.longitude != '0'
            GROUP BY b.token, p.modern, p.latitude, p.longitude
            ORDER BY frequency DESC
            """
            
            # Use books as source of truth
            if not books:
                return pd.DataFrame(), 0
                
            # Format the query with the books
            query = query.format(','.join(['?'] * len(books)))
            places_df = pd.read_sql_query(query, conn, params=tuple(books))
        
        # Convert latitude and longitude to numeric
        places_df['latitude'] = pd.to_numeric(places_df['latitude'], errors='coerce')
        places_df['longitude'] = pd.to_numeric(places_df['longitude'], errors='coerce')
        
        # Always apply a limit to protect performance
        # Use the smaller of user-specified max_places or MAX_PLACES
        user_max = filters.get('max_places', 0)
        effective_max = min(user_max if user_max > 0 else MAX_PLACES, MAX_PLACES)
        places_df = places_df.head(effective_max)
        
        return places_df
    finally:
        conn.close()

def get_place_details(token, page=1, per_page=20):
    """Get details about a place from the database."""
    conn = get_db_connection()
    try:
        # Get current state
        books, _ = get_current_state()
        if not books:
            return pd.DataFrame(), 0

        # Query to get book details with pagination
        query = """
        WITH place_stats AS (
            SELECT 
                COUNT(DISTINCT b.dhlabid) as total_books,
                SUM(b.book_count) as total_mentions
            FROM books b
            WHERE b.token = ?
            AND b.dhlabid IN ({})
        ),
        book_mentions AS (
            SELECT 
                b.dhlabid,
                b.book_count as mention_count
            FROM books b
            WHERE b.token = ?
            AND b.dhlabid IN ({})
        )
        SELECT 
            c.title,
            c.author,
            c.year,
            c.dhlabid,
            c.urn,
            bm.mention_count,
            (SELECT total_books FROM place_stats) as total_books,
            (SELECT total_mentions FROM place_stats) as total_mentions
        FROM book_mentions bm
        JOIN corpus c ON bm.dhlabid = c.dhlabid
        ORDER BY c.year DESC, c.title
        LIMIT ? OFFSET ?
        """.format(','.join(['?'] * len(books)), ','.join(['?'] * len(books)))
        
        # Get the data
        params = [token] + books + [token] + books + [per_page, (page - 1) * per_page]
        df = pd.read_sql_query(query, conn, params=params)
        
        # Get total count for pagination
        count_query = """
        SELECT COUNT(DISTINCT c.title) as total
        FROM books b
        JOIN corpus c ON b.dhlabid = c.dhlabid
        WHERE b.token = ?
        AND b.dhlabid IN ({})
        """.format(','.join(['?'] * len(books)))
        
        total = pd.read_sql_query(count_query, conn, params=[token] + books).iloc[0]['total']
        
        return df, total
        
    finally:
        conn.close()

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
            config={
                'displayModeBar': False,  # Hide the mode bar
                'scrollZoom': True,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                'displaylogo': False,
                'showTips': True,
                'showLink': False,
                'showEditInChartStudio': False,
                'showSendToCloud': False,
                'responsive': True,
                'editable': False,
                'edits': {
                    'shapePosition': False,
                    'annotationPosition': False
                }
            }
        ),
        # Loading overlay
        html.Div([
            html.Div([
                html.I(className="fas fa-spinner fa-spin", style={'fontSize': '24px', 'marginRight': '10px'}),
                html.Span("Preparing places...", style={'fontSize': '16px'})
            ], style={
                'backgroundColor': 'rgba(255, 255, 255, 0.9)',
                'padding': '15px 25px',
                'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'center'
            })
        ], id='loading-overlay', style={
            'position': 'absolute',
            'top': '50%',
            'left': '50%',
            'transform': 'translate(-50%, -50%)',
            'zIndex': 1000,
            'display': 'none'
        })
    ], style={'position': 'absolute', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0}),
    
    # Top bar (top layer with translucent background)
    html.Div([
        # Left section with search and corpus controls
        html.Div([
            # Search field
            html.Div([
                html.Div([
                    html.I(className="fas fa-search", style={
                        "color": "#666",
                        "marginRight": "8px",
                        "fontSize": "16px"
                    }),
                    dcc.Input(
                        id="global-place-search",
                        type="text",
                        placeholder="Search places...",
                        style={
                            "width": "100%",
                            "height": "100%",
                            "border": "none",
                            "outline": "none",
                            "fontSize": "14px",
                            "color": "#333",
                            "backgroundColor": "transparent",
                            "padding": "0"
                        }
                    )
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "0 12px",
                    "height": "36px",
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "boxShadow": "0 2px 6px rgba(0,0,0,0.15)",
                    "transition": "box-shadow 0.3s ease",
                    "pointerEvents": "auto",
                    "width": "240px"
                })
            ], style={
                "display": "flex",
                "alignItems": "center"
            }),

            # Tools button
            html.Button(
                html.I(className="fas fa-sliders-h"),
                id='visualization-button',
                style={
                    'padding': '8px',
                    'backgroundColor': 'white',
                    'color': '#475569',
                    'border': 'none',
                    'borderRadius': '50%',
                    'cursor': 'pointer',
                    'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                    'transition': 'all 0.2s',
                    'width': '36px',
                    'height': '36px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'center',
                    'fontSize': '14px',
                    'marginLeft': '8px',
                    'flexShrink': '0'  # Prevent the button from shrinking
                }
            ),

            # Corpus and Places buttons
            html.Div([
                html.Button("Corpus", id='corpus-button', style={
                    'padding': '8px 16px',
                    'backgroundColor': 'white',
                    'color': '#475569',
                    'border': 'none',
                    'borderRadius': '20px',
                    'cursor': 'pointer',
                    'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                    'transition': 'all 0.2s',
                    'fontSize': '14px',
                    'fontWeight': '500',
                    'lineHeight': '1.5',
                    'flexShrink': '0'  # Prevent the button from shrinking
                }),
                html.Button("Places", id='place-names-toggle', style={
                    'padding': '8px 16px',
                    'backgroundColor': 'white',
                    'color': '#475569',
                    'border': 'none',
                    'borderRadius': '20px',
                    'cursor': 'pointer',
                    'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                    'transition': 'all 0.2s',
                    'marginLeft': '8px',
                    'fontSize': '14px',
                    'fontWeight': '500',
                    'lineHeight': '1.5',
                    'flexShrink': '0'  # Prevent the button from shrinking
                })
            ], style={
                'display': 'flex', 
                'alignItems': 'center', 
                'marginLeft': '8px',
                'flexShrink': '0'  # Prevent the container from shrinking
            })
        ], style={
            'display': 'flex',
            'alignItems': 'center',
            'position': 'absolute',
            'left': '20px',
            'top': '20px',
            'zIndex': 1000,
            'pointerEvents': 'auto',
            'flexWrap': 'wrap',  # Allow wrapping on small screens
            'gap': '8px',  # Add gap between wrapped items
            'maxWidth': 'calc(100% - 40px)'  # Ensure it doesn't overflow on mobile
        }),

        # Right section with map view button
        html.Div([
            html.Button([
                html.I(className="fas fa-map-marker-alt", style={'marginRight': '8px'}),
                "Map View"
            ], id='map-button', style={
                'padding': '8px 16px',
                'backgroundColor': 'white',
                'color': '#475569',
                'border': 'none',
                'borderRadius': '20px',
                'cursor': 'pointer',
                'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                'transition': 'all 0.2s',
                'fontSize': '14px',
                'fontWeight': '500',
                'lineHeight': '1.5',
                'display': 'flex',
                'alignItems': 'center',
                'whiteSpace': 'nowrap'  # Prevent text wrapping
            })
        ], style={
            'position': 'absolute',
            'right': '20px',
            'top': '20px',
            'zIndex': 1000,
            'pointerEvents': 'auto'
        })
    ], style={
        'position': 'fixed',
        'top': 0,
        'left': 0,
        'right': 0,
        'height': '80px',
        'backgroundColor': 'rgba(255, 255, 255, 0)',
        'zIndex': 1000,
        'pointerEvents': 'none',
        'padding': '0 20px',  # Add padding for better mobile spacing
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center'
    }),

    # Rest of the components...
    html.Div(id='cached-data', style={'display': 'none'}),

    # Map controls in a modal
    create_corpus_controls(categories_list, titles_list, default_filters),
    create_visualization_controls(categories_list, titles_list, default_filters),

    # ImagiNation info button and modal
    html.Div([
        html.Button([
            html.H3("ImagiNation v1.0.1", style={
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
    dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-grip-horizontal me-2"),
                html.H4("Place Details", className="mb-0"),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-summary',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-info text-white", id='summary-header'),
        dbc.CardBody([
            html.Div(id='place-summary')
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'})  # 56px is header height
    ], id='place-summary-container', className="position-absolute", style={
        'width': '350px',
        'height': '500px',
        'zIndex': 800,
        'display': 'none',
        'top': '100px',  # Position below the top button container
        'left': '20px',  # Align with other containers
        'cursor': 'move'  # Add cursor style
    }),

    # Place Names Container
    dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-map-marker me-2"),
                html.H4("Place Names", className="mb-0"),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-place-names',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center", id='place-names-header')
        ], className="bg-warning text-dark"),
        dbc.CardBody([
            # Search input
            html.Div([
                html.Label("Search Places", className="form-label"),
                dcc.Input(
                    id='place-search',
                    type='text',
                    placeholder='Type to search...',
                    className="form-control mb-3"
                ),
                html.Button([
                    html.I(className="fas fa-search me-2"),
                    "Find Similar Places"
                ], id='find-similar-places', className="btn btn-primary w-100")
            ], className="mb-4"),
            
            # Place list
            html.Div([
                html.H5("Results", className="mb-3"),
                html.Div(id='place-names-list', children=[
                    html.P("Type in the search box to find places", className="text-muted")
                ])
            ])
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'})  # 56px is header height
    ], id='place-names-container', className="position-absolute", style={
        'width': '350px',
        'height': '500px',
        'zIndex': 800,
        'display': 'none',
        'top': '60px',
        'right': '10px',  # Initial right position
        'cursor': 'move'  # Add cursor style
    }),

    # Add place similarity dialog
    create_place_similarity_dialog(),

    # Hidden divs and stores
    html.Div(id='reset-status', style={'display': 'none'}),
    dcc.Store(id='filtered-data'),
    dcc.Store(id='selected-place', data=None),
    dcc.Store(id='map-view-state'),
    dcc.Store(id='current-filters', data={}),  # Initialize with empty dict
    dcc.Store(id='upload-state', data=None),
    dcc.Store(id='category-selection', data=[]),  # Initialize with empty list

    # Change view-type from Div to Store
    dcc.Store(id='view-type', data='points'),

    # Add this to the app layout, near the other Store components
    dcc.Store(id='current-dhlabids-store', data=[]),
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
            #visualization-button:hover {
                background-color: #1e293b !important;
                transform: scale(1.1);
            }
            .place-item:hover {
                background-color: #f8f9fa;
            }
            .place-item:active {
                background-color: #e9ecef;
            }
            #place-names-container {
                cursor: move;
            }
            #place-names-container.dragging {
                opacity: 0.7;
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
            $(document).ready(function() {
                // Initialize draggable elements
                function initializeDraggable() {
                    $("#place-names-container").draggable({
                        handle: "#place-names-header",
                        containment: "parent",
                        start: function(event, ui) {
                            $(this).addClass("dragging");
                        },
                        stop: function(event, ui) {
                            $(this).removeClass("dragging");
                        }
                    });

                    $("#place-summary-container").draggable({
                        handle: "#summary-header",
                        containment: "parent",
                        start: function(event, ui) {
                            $(this).addClass("dragging");
                        },
                        stop: function(event, ui) {
                            $(this).removeClass("dragging");
                        }
                    });

                    $("#corpus-controls-container").draggable({
                        handle: "#corpus-header",
                        containment: "parent",
                        start: function(event, ui) {
                            $(this).addClass("dragging");
                        },
                        stop: function(event, ui) {
                            $(this).removeClass("dragging");
                        }
                    });

                    $("#visualization-controls-container").draggable({
                        handle: "#visualization-header",
                        containment: "parent",
                        start: function(event, ui) {
                            $(this).addClass("dragging");
                        },
                        stop: function(event, ui) {
                            $(this).removeClass("dragging");
                        }
                    });
                }

                // Initialize on document ready
                initializeDraggable();

                // Also initialize when elements become visible
                var observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                            var element = mutation.target;
                            if (element.style.display === 'block' && !$(element).hasClass('ui-draggable')) {
                                initializeDraggable();
                            }
                        }
                    });
                });

                // Observe all draggable containers
                ['#place-summary-container', '#place-names-container', '#corpus-controls-container', '#visualization-controls-container'].forEach(function(selector) {
                    var element = document.querySelector(selector);
                    if (element) {
                        observer.observe(element, { attributes: true });
                    }
                });
            });
        </script>
    </body>
</html>
'''

@app.callback(
    [Output('popup-upload-status', 'children'),
     Output('upload-state', 'data'),
     Output('current-filters', 'data', allow_duplicate=True)],
    [Input('popup-upload-corpus', 'contents'),
     Input('popup-reset-corpus', 'n_clicks')],
    [State('popup-upload-corpus', 'filename'),
     State('current-filters', 'data')],
    prevent_initial_call=True
)
def update_state_and_filters(contents, reset_clicks, filename, current_filters):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if trigger_id == 'popup-reset-corpus':
        clear_state()
        return '', {}, default_filters
    
    if trigger_id == 'popup-upload-corpus' and contents:
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        try:
            df = pd.read_excel(io.BytesIO(decoded))
            if 'dhlabid' not in df.columns:
                return html.Div('Error: File must contain a dhlabid column', style={'color': 'red'}), {}, current_filters
            
            new_books = df['dhlabid'].tolist()
            conn = get_db_connection()
            try:
                query = """
                SELECT DISTINCT token
                FROM books
                WHERE dhlabid IN ({})
                """.format(','.join(['?'] * len(new_books)))
                places_df = pd.read_sql_query(query, conn, params=tuple(new_books))
                new_places = places_df['token'].tolist()
            finally:
                conn.close()
            
            books, places = update_from_books(new_books, new_places)
            new_filters = current_filters.copy() if current_filters else default_filters.copy()
            new_filters['corpus_source'] = filename
            new_filters['selected_tokens'] = places
            
            return html.Div(f'Successfully loaded {len(books)} books and {len(places)} places from {filename}', style={'color': 'green'}), {'uploaded': True, 'filename': filename}, new_filters
        except Exception as e:
            return html.Div(f'Error processing file: {str(e)}', style={'color': 'red'}), {}, current_filters
    
    return html.Div('', style={'display': 'none'}), current_filters.get('upload_state', {}), current_filters

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
    [Input('close-place-names', 'n_clicks')],
    [State('place-names-container', 'style')],
    prevent_initial_call=True
)


@app.callback(
    [Output('filtered-data', 'data', allow_duplicate=True),
     Output('current-dhlabids-store', 'data')],
    [Input('current-filters', 'data'),
     Input('upload-state', 'data'),
     Input('popup-reset-corpus', 'n_clicks')],
    [State('popup-upload-corpus', 'filename')],
    prevent_initial_call=True
)
def update_filtered_data(filters, upload_state, reset_clicks, filename):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if triggered_id == 'popup-reset-corpus' and reset_clicks:
        return pd.DataFrame().to_json(date_format='iso', orient='split'), []
    
    if not filters:
        return pd.DataFrame().to_json(date_format='iso', orient='split'), []
    
    # Handle uploaded corpus data
    if triggered_id == 'upload-state' and upload_state:
        try:
            if isinstance(upload_state, dict) and 'uploaded' in upload_state:
                pass
            else:
                return dash.no_update, dash.no_update
        except Exception as e:
            return dash.no_update, dash.no_update
    
    try:
        # Get current state
        books, places = get_current_state()
        
        if not books and not places:
            return pd.DataFrame().to_json(date_format='iso', orient='split'), []
        
        # Get places for the map
        places_result = get_places_for_map(filters, selected_tokens=places)
        if isinstance(places_result, tuple):
            places_df = places_result[0]
        else:
            places_df = places_result
        
        # Debug: Log the shape and content of places_df
        print(f"DEBUG: places_df shape: {places_df.shape}")
        print(f"DEBUG: places_df head: {places_df.head()}")
        
        json_output = places_df.to_json(date_format='iso', orient='split')
        return json_output, books
    except Exception as e:
        print(f"Error in update_filtered_data: {e}")
        return dash.no_update, dash.no_update

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
    [Output('main-map', 'figure'),
     Output('view-type', 'data'),
     Output('map-button', 'children')],
    [Input('filtered-data', 'data'),
     Input('map-button', 'n_clicks'),
     Input('heatmap-intensity', 'value'),
     Input('heatmap-radius', 'value'),
     Input('heatmap-colorscale', 'value'),
     Input('top-cluster-toggle', 'value'),
     Input('selected-place', 'data'),
     Input('main-map', 'clickData'),
     Input('marker-size-slider', 'value'),
     Input('cluster-size-slider', 'value'),
     Input('cluster-radius-slider', 'value')],
    [State('view-type', 'data')],
    prevent_initial_call=True
)
def update_map(filtered_data_json, map_clicks, heatmap_intensity, heatmap_radius, heatmap_colorscale, cluster_toggle, selected_place, click_data, marker_size, cluster_size, cluster_radius, current_view_type):
    try:
        ctx = callback_context
        if not ctx.triggered:
            view_type = 'points'  # Default view
        else:
            trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
            if trigger_id == 'map-button':
                view_type = 'heatmap' if current_view_type == 'points' else 'points'
            else:
                view_type = current_view_type or 'points'  # Use current view type or default to points

        # Update button content based on view type
        button_content = [
            html.I(className="fas fa-fire" if view_type == 'heatmap' else "fas fa-map-marker-alt", 
                   style={'marginRight': '8px'}),
            "Heatmap View" if view_type == 'heatmap' else "Map View"
        ]

        # Create base figure with default view of Norway
        fig = go.Figure()
        
        # Add a dummy trace to ensure the map displays
        fig.add_trace(go.Scattermap(
            lat=[60.5],
            lon=[9.0],
            mode='markers',
            marker=dict(size=1, color='rgba(0,0,0,0)'),
            showlegend=False
        ))
        
        if filtered_data_json is None:
            fig.update_layout(
                map=dict(
                    style='open-street-map',
                    center=dict(lat=60.5, lon=9.0),
                    zoom=4
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False,
                uirevision='constant'
            )
            return fig, view_type, button_content
        
        # Load cached data
        places_df = pd.read_json(io.StringIO(filtered_data_json), orient='split')
        
        if places_df.empty:
            fig.update_layout(
                map=dict(
                    style='open-street-map',
                    center=dict(lat=60.5, lon=9.0),
                    zoom=4
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False,
                uirevision='constant'
            )
            return fig, view_type, button_content
        
        # Clean data
        places_df = places_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude', 'frequency'])
        
        # Logarithmic scale for marker sizes with constrained relative scaling
        sizes = places_df['frequency'].fillna(1).copy()
        sizes = np.log1p(sizes)  # Logarithmic transformation (log(1 + x))
        min_size, max_size = sizes.min(), sizes.max()
        base_size = marker_size if marker_size is not None else 8  # Use slider value as base size
        size_range = 15  # Reduced range for more relative consistency
        if min_size != max_size:
            sizes = base_size + (sizes - min_size) / (max_size - min_size) * size_range
        else:
            sizes = [base_size] * len(sizes)
        
        # Aggregate data for tooltips
        places_df['hover_text'] = places_df.apply(
            lambda row: f"{row['token']} ({row['name']})<br>Mentions: {int(row['frequency'])}<br>Books: {int(row['book_count'])}",
            axis=1
        )
        
        # Determine if clustering is enabled
        use_clustering = cluster_toggle and 'cluster' in cluster_toggle
        
        if use_clustering:
            # Convert cluster radius from km to degrees (approximate)
            radius_km = cluster_radius if cluster_radius is not None else 50
            radius_deg = radius_km / 111.32  # Convert km to degrees (approximate)
            
            clustered = places_df.copy()
            # Ensure we have valid numeric values for clustering
            clustered['latitude'] = pd.to_numeric(clustered['latitude'], errors='coerce')
            clustered['longitude'] = pd.to_numeric(clustered['longitude'], errors='coerce')
            clustered = clustered.dropna(subset=['latitude', 'longitude'])
            
            if not clustered.empty:
                clustered['cluster'] = ((clustered['latitude'] / radius_deg).round() * 1000 + 
                                      (clustered['longitude'] / radius_deg).round()).astype(int)
                
                # Store original points for each cluster for polygon creation
                cluster_points = {}
                for _, row in clustered.iterrows():
                    cluster_id = row['cluster']
                    if cluster_id not in cluster_points:
                        cluster_points[cluster_id] = []
                    cluster_points[cluster_id].append((row['longitude'], row['latitude']))
                
                # Aggregate clustered points with unique place names
                cluster_data = clustered.groupby('cluster').agg({
                    'latitude': 'mean',
                    'longitude': 'mean',
                    'frequency': 'sum',
                    'book_count': 'sum',
                    'token': lambda x: '<br>'.join([str(t) for t in dict.fromkeys(x) if t is not None]),
                    'name': lambda x: '<br>'.join([str(n) for n in dict.fromkeys(x) if n is not None]),
                    'hover_text': 'first'
                }).reset_index()
                cluster_data['count'] = clustered.groupby('cluster').size().values
                cluster_data['hover_text'] = cluster_data.apply(
                    lambda row: f"""Cluster of {row['count']} places<br>Total Mentions: {int(row['frequency'])}<br>Total Books: {int(row['book_count'])}<br>Example place: {row['token'].split('<br>')[0] if row['token'] else 'Unknown'}""",
                    axis=1
                )
                
                # Use cluster_size slider to control cluster marker size
                base_cluster_size = cluster_size if cluster_size is not None else 3
                cluster_data['size'] = np.log1p(cluster_data['count']) * base_cluster_size * 2  # Reduced multiplier for more reasonable sizes
                
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
                
                # If a cluster is clicked, add a polygon showing its coverage area
                if click_data and 'points' in click_data:
                    point = click_data['points'][0]
                    if 'Cluster of' in point.get('text', ''):
                        try:
                            # Find the clicked cluster
                            clicked_lat = point['lat']
                            clicked_lon = point['lon']
                            
                            # Find the cluster ID that matches these coordinates
                            matching_clusters = cluster_data[
                                (cluster_data['latitude'] == clicked_lat) & 
                                (cluster_data['longitude'] == clicked_lon)
                            ]
                            
                            if not matching_clusters.empty:
                                clicked_cluster = matching_clusters['cluster'].iloc[0]
                                
                                # Get the points for this cluster
                                points = cluster_points[clicked_cluster]
                                
                                if len(points) == 2:
                                    # For two points, create an oval aligned with the points
                                    p1_lon, p1_lat = points[0]
                                    p2_lon, p2_lat = points[1]
                                    
                                    # Calculate center point
                                    center_lat = (p1_lat + p2_lat) / 2
                                    center_lon = (p1_lon + p2_lon) / 2
                                    
                                    # Calculate distance between points
                                    lat_diff = p2_lat - p1_lat
                                    lon_diff = p2_lon - p1_lon
                                    distance_km = math.sqrt(lat_diff**2 + lon_diff**2) * 111.32
                                    
                                    # Calculate bearing between points
                                    bearing = calculate_bearing(p1_lat, p1_lon, p2_lat, p2_lon)
                                    
                                    # Create rotated ellipse
                                    lats, lons = create_rotated_ellipse(
                                        center_lat, center_lon,
                                        distance_km/2,
                                        bearing,
                                        points=100
                                    )
                                    
                                    fig.add_trace(go.Scattermap(
                                        lat=lats,
                                        lon=lons,
                                        mode='lines',
                                        line=dict(color='#1E40AF', width=3),
                                        fill='toself',
                                        fillcolor='rgba(30, 64, 175, 0.3)',
                                        hoverinfo='skip',
                                        showlegend=False,
                                        visible=True
                                    ))
                                    
                                elif len(points) >= 3:
                                    # For three or more points, use convex hull
                                    points_array = np.array(points)
                                    
                                    try:
                                        # Calculate convex hull
                                        hull = ConvexHull(points_array)
                                        
                                        # Get the hull vertices
                                        hull_points = points_array[hull.vertices]
                                        
                                        # Add some padding to make the hull slightly larger
                                        center = np.mean(hull_points, axis=0)
                                        padding = 0.05  # 5% padding
                                        padded_points = center + (1 + padding) * (hull_points - center)
                                        
                                        # Ensure the polygon is closed by adding the first point at the end
                                        padded_points = np.vstack([padded_points, padded_points[0]])
                                        
                                        # Add the polygon
                                        fig.add_trace(go.Scattermap(
                                            lat=padded_points[:, 1],
                                            lon=padded_points[:, 0],
                                            mode='lines',
                                            line=dict(color='#1E40AF', width=3),
                                            fill='toself',
                                            fillcolor='rgba(30, 64, 175, 0.3)',
                                            hoverinfo='skip',
                                            showlegend=False,
                                            visible=True
                                        ))
                                    except Exception as e:
                                        print(f"Error calculating convex hull: {e}")
                                        # Fallback to circle if convex hull fails
                                        radius_km = radius_km  # Use the cluster radius
                                        radius_deg = radius_km / 111.32
                                        angles = np.linspace(0, 2*np.pi, 100)
                                        circle_lats = clicked_lat + radius_deg * np.cos(angles)
                                        circle_lons = clicked_lon + radius_deg * np.sin(angles)
                                        
                                        fig.add_trace(go.Scattermap(
                                            lat=circle_lats,
                                            lon=circle_lons,
                                            mode='lines',
                                            line=dict(color='#1E40AF', width=3),
                                            fill='toself',
                                            fillcolor='rgba(30, 64, 175, 0.3)',
                                            hoverinfo='skip',
                                            showlegend=False,
                                            visible=True
                                        ))
                                else:
                                    # For single points, use a small circle
                                    radius_km = radius_km  # Use the cluster radius
                                    radius_deg = radius_km / 111.32
                                    angles = np.linspace(0, 2*np.pi, 100)
                                    circle_lats = clicked_lat + radius_deg * np.cos(angles)
                                    circle_lons = clicked_lon + radius_deg * np.sin(angles)
                                    
                                    fig.add_trace(go.Scattermap(
                                        lat=circle_lats,
                                        lon=circle_lons,
                                        mode='lines',
                                        line=dict(color='#1E40AF', width=3),
                                        fill='toself',
                                        fillcolor='rgba(30, 64, 175, 0.3)',
                                        hoverinfo='skip',
                                        showlegend=False,
                                        visible=True
                                    ))
                        except Exception as e:
                            print(f"Error handling cluster click: {e}")
                            # Continue without showing the cluster polygon
                            pass
            else:
                print("No valid data for clustering")
        
        # Add individual markers if not clustering or if clustering failed
        if not use_clustering or clustered.empty:
            if selected_place:
                selected_df = places_df[places_df['token'] == selected_place]
                unselected_df = places_df[places_df['token'] != selected_place]
                
                # Add unselected places first
                if not unselected_df.empty:
                    fig.add_trace(go.Scattermap(
                        lat=unselected_df['latitude'],
                        lon=unselected_df['longitude'],
                        mode='markers',
                        marker=dict(size=sizes[unselected_df.index], color='#3b82f6', opacity=0.7, sizemode='diameter'),
                        text=unselected_df['hover_text'],
                        hoverinfo='text',
                        customdata=unselected_df['token'].tolist(),
                        visible=(view_type == 'points'),
                        name='Places'
                    ))
                
                # Add selected place with different color
                if not selected_df.empty:
                    fig.add_trace(go.Scattermap(
                        lat=selected_df['latitude'],
                        lon=selected_df['longitude'],
                        mode='markers',
                        marker=dict(size=sizes[selected_df.index] * 1.2, color='#dc2626', opacity=0.9, sizemode='diameter'),
                        text=selected_df['hover_text'],
                        hoverinfo='text',
                        customdata=selected_df['token'].tolist(),
                        visible=(view_type == 'points'),
                        name='Selected Place'
                    ))
            else:
                # No place selected, show all places normally
                fig.add_trace(go.Scattermap(
                    lat=places_df['latitude'],
                    lon=places_df['longitude'],
                    mode='markers',
                    marker=dict(size=sizes, color='#3b82f6', opacity=0.7, sizemode='diameter'),
                    text=places_df['hover_text'],
                    hoverinfo='text',
                    customdata=places_df['token'].tolist(),
                    visible=(view_type == 'points'),
                    name='Places'
                ))
        
        heatmap_visible = view_type == 'heatmap'
        if len(places_df) > 0 and heatmap_visible:
            try:
                x = places_df['longitude'].values
                y = places_df['latitude'].values
                z = places_df['frequency'].fillna(1).values
                z = np.log1p(z)
                mask = (~np.isnan(x)) & (~np.isnan(y)) & (~np.isnan(z)) & (~np.isinf(x)) & (~np.isinf(y)) & (~np.isinf(z))
                x, y, z = x[mask], y[mask], z[mask]
                
                if len(x) < 2:
                    fig.add_trace(go.Densitymap(
                        lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap'
                    ))
                else:
                    heatmap_actual_radius = (heatmap_radius ** 0.5) * 10
                    fig.add_trace(go.Densitymap(
                        lat=y,
                        lon=x,
                        z=z,
                        radius=heatmap_actual_radius,
                        colorscale=heatmap_colorscale,
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
        
        # Update layout
        fig.update_layout(
            map=dict(
                style='open-street-map',
                center=dict(lat=60.5, lon=9.0),
                zoom=4
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
            uirevision='constant',
            hovermode='closest',
            dragmode='pan',
            clickmode='event'
        )
        
        return fig, view_type, button_content
    except Exception as e:
        print(f"Error in update_map: {e}")
        return dash.no_update, dash.no_update, dash.no_update

@app.callback(
    [Output('place-names-list', 'children'),
     Output('selected-place', 'data')],
    [Input('filtered-data', 'data'),
     Input('place-search', 'value')],
    [State('selected-place', 'data')]
)
def update_place_list(filtered_data_json, search_term, selected_place):
    if filtered_data_json is None:
        return html.Div("No places available"), None
    
    # Load cached data
    places_df = pd.read_json(io.StringIO(filtered_data_json), orient='split')
    
    if places_df.empty:
        return html.Div("No places available"), None
    
    # Sort by frequency
    places_df = places_df.sort_values(by='frequency', ascending=False)
    
    # Apply search filter if provided
    if search_term and len(search_term) > 2:
        search_term = search_term.lower()
        places_df = places_df[
            places_df['token'].str.lower().str.contains(search_term) | 
            places_df['name'].str.lower().str.contains(search_term)
        ]
    
    # Create hover text before creating place items
    places_df['hover_text'] = places_df.apply(
        lambda row: f"{row['token']} ({row['name']})<br>Modern name: {row['name']}<br>Mentions: {int(row['frequency'])}<br>Books: {int(row['book_count'])}",
        axis=1
    )
    
    # Limit to top 5000 places
    places_df = places_df.head(5000)
    
    def create_place_item(row):
        is_selected = selected_place == row['token']
        return html.Div([
            html.Div([
                html.Div(f"{row['token']}", style={'fontWeight': 'bold', 'fontSize': '1rem'}),
                html.Div(f"{row['name']}", style={'color': '#666', 'fontSize': '0.9rem'})
            ], style={'marginBottom': '4px'}),
            html.Div([
                html.Span(f"📚 {int(row['book_count'])} books", style={'marginRight': '12px', 'color': '#666', 'fontSize': '0.85rem'}),
                html.Span(f"📝 {int(row['frequency'])} mentions", style={'color': '#666', 'fontSize': '0.85rem'})
            ])
        ], style={
            'borderBottom': '1px solid #eee',
            'padding': '8px 0',
            'transition': 'background-color 0.2s',
            'cursor': 'pointer',
            'backgroundColor': '#ffebee' if is_selected else 'transparent'
        }, 
        className='place-item', 
        id={'type': 'place-item', 'index': row['token']},
        **{'data-lat': row['latitude'], 'data-lon': row['longitude'], 'data-hover': row['hover_text']})
    
    if places_df.empty:
        return html.Div("No matching places found"), None
    
    # Create the list container with improved performance
    return html.Div([
        html.Div([
            html.Div(f"Showing {len(places_df)} places", 
                     style={'marginBottom': '8px', 'fontSize': '0.9rem', 'color': '#666'}),
            html.Div([
                # Table header
                html.Div([
                    html.Div("Place", style={'flex': '2', 'fontWeight': 'bold', 'padding': '8px'}),
                    html.Div("📚", style={'flex': '1', 'fontWeight': 'bold', 'padding': '8px', 'textAlign': 'center'}),
                    html.Div("📝", style={'flex': '1', 'fontWeight': 'bold', 'padding': '8px', 'textAlign': 'center'})
                ], style={
                    'display': 'flex',
                    'borderBottom': '2px solid #eee',
                    'marginBottom': '4px',
                    'fontSize': '0.9rem'
                }),
                # Table rows
                html.Div([
                    html.Div([
                        html.Div([
                            html.Div(f"{row['token']}", style={'fontWeight': '500', 'fontSize': '0.9rem'}),
                            html.Div(f"{row['name']}", style={'color': '#666', 'fontSize': '0.8rem'})
                        ], style={'flex': '2', 'padding': '8px'}),
                        html.Div(f"{int(row['book_count'])}", 
                                style={'flex': '1', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'}),
                        html.Div(f"{int(row['frequency'])}", 
                                style={'flex': '1', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'})
                    ], style={
                        'display': 'flex',
                        'borderBottom': '1px solid #eee',
                        'transition': 'background-color 0.2s',
                        'cursor': 'pointer',
                        'backgroundColor': '#ffebee' if selected_place == row['token'] else 'transparent'
                    }, 
                    className='place-item', 
                    id={'type': 'place-item', 'index': row['token']},
                    **{'data-lat': row['latitude'], 'data-lon': row['longitude'], 'data-hover': row['hover_text']})
                    for _, row in places_df.iterrows()
                ], style={'maxHeight': '400px', 'overflowY': 'auto'})
            ], style={'border': '1px solid #eee', 'borderRadius': '4px'})
        ], style={'padding': '12px'})
    ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}), selected_place

# Add callback for place item clicks
@app.callback(
    [Output('selected-place', 'data', allow_duplicate=True),
     Output('main-map', 'clickData', allow_duplicate=True)],
    [Input({'type': 'place-item', 'index': dash.ALL}, 'n_clicks')],
    [State({'type': 'place-item', 'index': dash.ALL}, 'id'),
     State({'type': 'place-item', 'index': dash.ALL}, 'data-lat'),
     State({'type': 'place-item', 'index': dash.ALL}, 'data-lon'),
     State({'type': 'place-item', 'index': dash.ALL}, 'data-hover')],
    prevent_initial_call=True
)
def handle_place_click(n_clicks, ids, lats, lons, hovers):
    if not any(n_clicks):
        raise PreventUpdate
    
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    triggered_id = ctx.triggered[0]['prop_id']
    if not triggered_id:
        raise PreventUpdate
    
    # Get the index of the clicked item
    try:
        # Parse the triggered ID to get the place token
        triggered_id_dict = eval(triggered_id.split('.')[0])
        clicked_idx = next(i for i, id_dict in enumerate(ids) if id_dict['index'] == triggered_id_dict['index'])
    except (ValueError, SyntaxError, StopIteration):
        raise PreventUpdate
    
    # Get the place data from the clicked item's data attributes
    place_token = ids[clicked_idx]['index']
    lat = lats[clicked_idx]
    lon = lons[clicked_idx]
    hover_text = hovers[clicked_idx]
    
    # Create click data structure using the stored data
    click_data = {
        'points': [{
            'lat': lat,
            'lon': lon,
            'customdata': place_token,
            'text': hover_text
        }]
    }
    
    return place_token, click_data

# Callback to update place summary
@app.callback(
    [Output('place-summary-container', 'style'),
     Output('place-summary', 'children')],
    [Input('main-map', 'clickData')],
    [State('place-summary-container', 'style')],
    prevent_initial_call=True
)
def update_place_summary(click_data, current_style):
    if not click_data:
        return dash.no_update, dash.no_update
    
    try:
        # Get the clicked place
        point = click_data['points'][0]
        token = point['customdata']
        
        # Get the hover text from the point
        hover_text = point.get('text', '')
        parts = hover_text.split('<br>')
        
        token_part = parts[0]
        modern_part = ""
        frequency = 0
        book_count = 0
        
        # Parse the hover text to get additional information
        for part in parts:
            if 'Modern name:' in part:
                modern_part = part.split('Modern name: ')[1].strip()
            elif 'Mentions:' in part:
                try:
                    frequency = int(part.split('Mentions: ')[1].strip())
                except (ValueError, IndexError):
                    print("Could not parse frequency")
            elif 'Books:' in part:
                try:
                    book_count = int(part.split('Books: ')[1].strip())
                except (ValueError, IndexError):
                    print("Could not parse book count")
        
        # Get current state
        books, places = get_current_state()
        if not books:
            return dash.no_update, dash.no_update
        
        # Get book details for the place
        books_df, total_books = get_place_details(token)
        print(f"Got {len(books_df)} books for place {token}")
        
        # Get total counts from the first row (they're the same for all rows)
        total_books = int(books_df['total_books'].iloc[0]) if not books_df.empty else 0
        total_mentions = int(books_df['total_mentions'].iloc[0]) if not books_df.empty else 0
        
        summary = html.Div([
            html.Div([
                html.H5(token_part, style={'marginBottom': '5px'}),
                html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                html.P(f"Appears in {total_books:,} books with {total_mentions:,} total mentions", style={'marginTop': '5px'}),
                html.Hr(style={'margin': '10px 0'})
            ]),
            html.Div([
                html.H6(f"Books mentioning this place (showing {len(books_df):,} of {total_books:,}):", style={'marginBottom': '10px'}),
                html.Div([
                    html.Div([
                        html.A(
                            f"{row['title']} ({row['year']})",
                            href=f"https://www.nb.no/items/{row['urn']}?searchText={token}",
                            target="_blank",
                            style={'fontWeight': '500', 'color': '#1a56db', 'textDecoration': 'none'}
                        ),
                        html.Div([
                            html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                            html.Span(f" • {int(row['mention_count']):,} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                        ], style={'display': 'flex', 'justifyContent': 'space-between'})
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
@app.callback(
    Output('heatmap-settings', 'style'),
    [Input('view-toggle', 'value')],
    prevent_initial_call=True
)
def toggle_heatmap_settings(view_type):
    if view_type is None:
        raise PreventUpdate
    return {'display': 'block'} if view_type == 'heatmap' else {'display': 'none'}

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

# Update corpus stats callback to be more efficient
@app.callback(
    Output('corpus-stats', 'children'),
    [Input('current-filters', 'data')],
    prevent_initial_call=True
)
def update_corpus_stats(filters):
    if not filters:
        return "No filters available"
    
    # Get current state
    books, places = get_current_state()
    if not books:
        return "No corpus loaded"
    
    conn = get_db_connection()
    try:
        # Get book details for the current corpus
        book_query = f"""
        SELECT dhlabid, year, category, title
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(books))})
        AND year IS NOT NULL
        """
        books_df = pd.read_sql_query(book_query, conn, params=tuple(books))
        
        print(f"DEBUG: Total books before year filter: {len(books_df)}")
        print(f"DEBUG: Year range in books_df: {books_df['year'].min()}-{books_df['year'].max()}")
        
        # Apply year range filter if specified
        if filters.get('year_range'):
            min_year, max_year = filters['year_range']
            print(f"DEBUG: Applying year range filter: {min_year}-{max_year}")
            books_df = books_df[(books_df['year'] >= min_year) & (books_df['year'] <= max_year)]
            print(f"DEBUG: Books after year filter: {len(books_df)}")
            print(f"DEBUG: Year range after filter: {books_df['year'].min()}-{books_df['year'].max()}")
        
        num_books = len(books_df)
        
        # Get the period from metadata
        if not books_df.empty:
            min_year = int(books_df['year'].min())
            max_year = int(books_df['year'].max())
            year_range = f"{min_year}–{max_year}"
        else:
            year_range = "No period data"
        
        # Get total places and filtered places
        places_df = get_places_for_map(filters, selected_tokens=places)
        if places_df.empty:
            return "No places match the current filters"
        
        total_places_shown = len(places_df)
        total_mentions = int(places_df['frequency'].sum())
        total_books = int(places_df['book_count'].sum())
        category_count = len(filters['categories']) if filters['categories'] else 0
        title_count = len(filters['titles']) if filters['titles'] else 0
        
        # Build the stats display
        stats = [
            html.P(f"Corpus source: {filters.get('corpus_source', 'No corpus selected')}"),
            html.P(f"Number of books: {num_books}"),
            html.P(f"Total places in corpus: {total_places_shown}"),
            html.P(f"Period: {year_range}"),
            html.P(f"Filters: {category_count} categories, {title_count} works"),
            html.P(f"Places shown: {total_places_shown}"),
            html.P(f"Total mentions: {total_mentions:,}")
        ]
        
        # Add selected places information if available
        if places:
            stats.extend([
                html.Hr(),
                html.H5("Selected Places", className="mt-3"),
                html.P(f"Number of selected places: {len(places)}"),
                html.P("Selected places:", style={'marginBottom': '5px'}),
                html.Div([
                    html.Span(place, style={'marginRight': '10px', 'marginBottom': '5px'})
                    for place in places
                ], style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '5px'})
            ])
        
        return html.Div(stats)
    finally:
        conn.close()

# Update corpus controls callback
@app.callback(
    Output('corpus-controls-container', 'style'),
    [Input('corpus-button', 'n_clicks'),
     Input('close-corpus', 'n_clicks')],
    [State('corpus-controls-container', 'style')],
    prevent_initial_call=True
)
def toggle_corpus_controls(n1, n2, current_style):
    if n1 or n2:
        new_style = dict(current_style)
        new_style['display'] = 'block' if current_style.get('display') == 'none' else 'none'
        return new_style
    return current_style

# Update visualization controls callback
@app.callback(
    Output('visualization-controls-container', 'style'),
    [Input('visualization-button', 'n_clicks'),
     Input('close-visualization', 'n_clicks')],
    [State('visualization-controls-container', 'style')],
    prevent_initial_call=True
)
def toggle_visualization_controls(n1, n2, current_style):
    if n1 or n2:
        new_style = dict(current_style)
        new_style['display'] = 'block' if current_style.get('display') == 'none' else 'none'
        return new_style
    return current_style

# Update button styles callback
@app.callback(
    [Output('corpus-button', 'style'),
     Output('place-names-toggle', 'style'),
     Output('visualization-button', 'style')],
    [Input('corpus-controls-container', 'style'),
     Input('place-names-container', 'style'),
     Input('visualization-controls-container', 'style')],
    [State('corpus-button', 'style'),
     State('place-names-toggle', 'style'),
     State('visualization-button', 'style')],
    prevent_initial_call=True
)
def update_button_styles(corpus_style, places_style, viz_style, corpus_btn_style, places_btn_style, viz_btn_style):
    # Base styles
    base_style = {
        'padding': '8px 16px',
        'backgroundColor': 'white',
        'color': '#475569',
        'border': 'none',
        'borderRadius': '20px',
        'cursor': 'pointer',
        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
        'transition': 'all 0.2s',
        'fontSize': '14px',
        'fontWeight': '500',
        'lineHeight': '1.5'
    }
    
    active_style = {
        'padding': '8px 16px',
        'backgroundColor': '#475569',
        'color': 'white',
        'border': 'none',
        'borderRadius': '20px',
        'cursor': 'pointer',
        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
        'transition': 'all 0.2s',
        'fontSize': '14px',
        'fontWeight': '500',
        'lineHeight': '1.5'
    }
    
    # Update corpus button style
    corpus_btn_style = active_style.copy() if corpus_style and corpus_style.get('display') == 'block' else base_style.copy()
    
    # Update places button style
    places_btn_style = active_style.copy() if places_style and places_style.get('display') == 'block' else base_style.copy()
    places_btn_style['marginLeft'] = '8px'
    
    # Update visualization button style - maintain position and size
    viz_btn_style = {
        'padding': '8px',
        'backgroundColor': '#475569' if viz_style and viz_style.get('display') == 'block' else 'white',
        'color': 'white' if viz_style and viz_style.get('display') == 'block' else '#475569',
        'border': 'none',
        'borderRadius': '50%',
        'cursor': 'pointer',
        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
        'transition': 'all 0.2s',
        'width': '36px',
        'height': '36px',
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'center',
        'fontSize': '14px',
        'marginLeft': '8px',
        'flexShrink': '0'
    }
    
    return corpus_btn_style, places_btn_style, viz_btn_style

# Add callback for category and title selection
@app.callback(
    [Output('current-filters', 'data', allow_duplicate=True),
     Output('filtered-data', 'data', allow_duplicate=True)],
    [Input('apply-filters', 'n_clicks')],
    [State('category-dropdown', 'value'),
     State('title-dropdown', 'value'),
     State('popup-sample-size', 'value'),
     State('popup-max-places-slider', 'value'),
     State('year-range-slider', 'value'),
     State('current-filters', 'data')],
    prevent_initial_call=True
)
def update_corpus_from_selections(n_clicks, selected_categories, selected_titles, sample_size, max_places, year_range, current_filters):
    if not n_clicks:
        raise PreventUpdate
    
    if current_filters is None:
        current_filters = {}
    
    # Update filters with new selections
    new_filters = {
        'categories': selected_categories or [],
        'titles': selected_titles or [],
        'sample_size': sample_size or 0,
        'max_places': max_places or 0,
        'year_range': year_range or [1814, 1905]  # Default to full range if not set
    }
    
    try:
        # Get dhlabids for the selected filters
        conn = get_db_connection()
        try:
            query_parts = []
            params = []
            
            if selected_categories:
                query_parts.append("category IN ({})".format(','.join(['?'] * len(selected_categories))))
                params.extend(selected_categories)
            
            if selected_titles:
                query_parts.append("title IN ({})".format(','.join(['?'] * len(selected_titles))))
                params.extend(selected_titles)
            
            # Always apply year range filter
            min_year, max_year = new_filters['year_range']
            query_parts.append("year BETWEEN ? AND ?")
            params.extend([min_year, max_year])
            
            where_clause = " AND ".join(query_parts) if query_parts else "1=1"
            query = f"""
            SELECT DISTINCT dhlabid
            FROM corpus
            WHERE {where_clause}
            """
            
            print(f"DEBUG: Applying filters - Categories: {selected_categories}, Year range: {min_year}-{max_year}")
            dhlabids = pd.read_sql_query(query, conn, params=tuple(params))['dhlabid'].tolist()
            print(f"DEBUG: Found {len(dhlabids)} books matching filters")
            
            # Get places for these books
            places_query = """
            SELECT DISTINCT token
            FROM books
            WHERE dhlabid IN ({})
            """.format(','.join(['?'] * len(dhlabids)))
            places = pd.read_sql_query(places_query, conn, params=tuple(dhlabids))['token'].tolist()
            
            # Update state with new books and places
            books, places = update_from_books(dhlabids, places)
            
        finally:
            conn.close()
        
        # Get filtered data
        places_df = get_places_for_map(new_filters, selected_tokens=places)
        if isinstance(places_df, tuple):
            places_df = places_df[0]
        
        return new_filters, places_df.to_json(date_format='iso', orient='split')
    except Exception as e:
        print(f"Error in update_corpus_from_selections: {e}")
        return dash.no_update, dash.no_update

# Add callback for corpus info
@app.callback(
    Output('corpus-controls-info', 'children'),
    [Input('current-filters', 'data'),
     Input('apply-filters', 'n_clicks')],
    prevent_initial_call=True
)
def update_corpus_info(filters, n_clicks):
    if not filters:
        return html.P("No corpus loaded", className="text-muted")
    
    # Get current state
    books, places = get_current_state()
    if not books:
        return html.P("No corpus loaded", className="text-muted")
    
    conn = get_db_connection()
    try:
        # Get corpus information using current books
        query = f"""
        SELECT COUNT(DISTINCT dhlabid) as book_count,
               COUNT(DISTINCT author) as author_count,
               MIN(year) as min_year,
               MAX(year) as max_year
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(books))})
        AND year IS NOT NULL
        """
        
        info = pd.read_sql_query(query, conn, params=tuple(books)).iloc[0]
        print(f"DEBUG: Corpus info - Book count: {info['book_count']}, Year range: {info['min_year']}-{info['max_year']}")
        
        return html.Div([
            html.P(f"Books in corpus: {info['book_count']:,}"),
            html.P(f"Authors: {info['author_count']:,}"),
            html.P(f"Time period: {int(info['min_year'])}–{int(info['max_year'])}"),
            html.P(f"Categories: {', '.join(filters['categories']) if filters.get('categories') else 'All'}"),
            html.P(f"Sample size: {filters.get('sample_size', 'Not set')}"),
            html.P(f"Max places: {filters.get('max_places', 'Not set')}")
        ])
    finally:
        conn.close()

def add_edge_points(points_array):
    """Add edge points to ensure the convex hull covers the entire cluster area."""
    if len(points_array) < 2:
        return points_array
    
    # Calculate the bounding box
    min_lon, min_lat = points_array.min(axis=0)
    max_lon, max_lat = points_array.max(axis=0)
    
    # Add corner points with some padding
    padding = 0.1  # 10% padding
    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat
    
    edge_points = np.array([
        [min_lon - padding * lon_range, min_lat - padding * lat_range],  # Bottom left
        [max_lon + padding * lon_range, min_lat - padding * lat_range],  # Bottom right
        [max_lon + padding * lon_range, max_lat + padding * lat_range],  # Top right
        [min_lon - padding * lon_range, max_lat + padding * lat_range]   # Top left
    ])
    
    # Combine original points with edge points
    return np.vstack([points_array, edge_points])

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate the bearing between two points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(y, x)
    return math.degrees(bearing)

def create_rotated_ellipse(center_lat, center_lon, radius_km, bearing, points=100):
    """Create a rotated ellipse around a center point."""
    # Convert radius from km to degrees (approximate)
    radius_deg = radius_km / 111.32
    
    # Create points for the ellipse
    angles = np.linspace(0, 2*np.pi, points)
    
    # Create the ellipse points
    x = radius_deg * np.cos(angles)
    y = radius_deg * np.sin(angles)
    
    # Rotate the points
    bearing_rad = math.radians(bearing)
    cos_bearing = math.cos(bearing_rad)
    sin_bearing = math.sin(bearing_rad)
    
    x_rot = x * cos_bearing - y * sin_bearing
    y_rot = x * sin_bearing + y * cos_bearing
    
    # Translate to center point
    lats = center_lat + y_rot
    lons = center_lon + x_rot
    
    return lats, lons

# Add callback for loading state
@app.callback(
    Output('loading-overlay', 'style'),
    [Input('apply-filters', 'n_clicks'),
     Input('main-map', 'figure')],
    [State('loading-overlay', 'style')]
)
def update_loading_state(apply_clicks, map_figure, current_style):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Show loading when apply button is clicked
    if trigger_id == 'apply-filters' and apply_clicks:
        new_style = dict(current_style)
        new_style['display'] = 'block'
        return new_style
    
    # Hide loading when map is updated
    if trigger_id == 'main-map' and map_figure:
        new_style = dict(current_style)
        new_style['display'] = 'none'
        return new_style
    
    return current_style

# Add download endpoint
@app.server.route('/download-map', methods=['GET'])
def download_map():
    try:
        # Get data from query parameters
        data_str = request.args.get('data')
        if not data_str:
            return 'No data provided', 400
            
        data = json.loads(data_str)
        figure = data.get('figure')
        format = data.get('format', 'png')
        width = data.get('width', 3840)
        height = data.get('height', 2160)
        scale = data.get('scale', 2)
        
        # Create figure from JSON
        fig = go.Figure(figure)
        
        # Update layout for download
        fig.update_layout(
            width=width,
            height=height,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        
        # Generate image
        if format == 'png':
            img_bytes = fig.to_image(format='png', scale=scale)
            mimetype = 'image/png'
            filename = 'imagination_map.png'
        elif format == 'pdf':
            img_bytes = fig.to_image(format='pdf', scale=scale)
            mimetype = 'application/pdf'
            filename = 'imagination_map.pdf'
        elif format == 'svg':
            img_bytes = fig.to_image(format='svg', scale=scale)
            mimetype = 'image/svg+xml'
            filename = 'imagination_map.svg'
        else:
            return 'Invalid format', 400
        
        return send_file(
            io.BytesIO(img_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error generating download: {e}")
        return str(e), 500

# Add download callback
@app.callback(
    Output('download-status', 'children'),
    [Input('download-map', 'n_clicks')],
    [State('download-format', 'value'),
     State('download-resolution', 'value'),
     State('main-map', 'figure')],
    prevent_initial_call=True
)
def trigger_download(n_clicks, format, resolution, figure):
    if not n_clicks:
        raise PreventUpdate
    
    # Set resolution based on selection
    resolution_map = {
        'standard': {'width': 1920, 'height': 1080},
        'high': {'width': 3840, 'height': 2160},
        'publication': {'width': 6000, 'height': 4000}
    }
    
    # Get the selected resolution
    dimensions = resolution_map.get(resolution, resolution_map['standard'])
    
    # Prepare download data
    download_data = {
        'figure': figure,
        'format': format,
        'width': dimensions['width'],
        'height': dimensions['height'],
        'scale': 2 if resolution in ['high', 'publication'] else 1
    }
    
    # Create download URL
    download_url = f'/download-map?data={json.dumps(download_data)}'
    
    # Return a link that will be clicked by JavaScript
    return html.Div([
        html.A(
            "Download Map",
            href=download_url,
            id="download-link",
            style={'display': 'none'}
        ),
        html.Script("""
            document.getElementById('download-link').click();
        """),
        html.Div("Download started...", style={'color': 'green', 'marginTop': '10px'})
    ])

# Add new callback for data loading
@app.callback(
    Output('filtered-data', 'data'),
    [Input('current-filters', 'data'),
     Input('current-dhlabids-store', 'data')],
    prevent_initial_call=True
)
def load_filtered_data(filters, books):
    if not filters or not books:
        return pd.DataFrame().to_json(date_format='iso', orient='split')
    
    try:
        # Get current state
        books, places = get_current_state()
        
        if not books and not places:
            return pd.DataFrame().to_json(date_format='iso', orient='split')
        
        # Get places for the map
        places_result = get_places_for_map(filters, selected_tokens=places)
        if isinstance(places_result, tuple):
            places_df = places_result[0]
        else:
            places_df = places_result
        
        # Debug: Log the shape and content of places_df
        print(f"DEBUG: places_df shape: {places_df.shape}")
        print(f"DEBUG: places_df head: {places_df.head()}")
        
        return places_df.to_json(date_format='iso', orient='split')
    except Exception as e:
        print(f"Error in load_filtered_data: {e}")
        return dash.no_update

# Update update_filtered_data to only handle dhlabids
@app.callback(
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    [Input('current-filters', 'data'),
     Input('upload-state', 'data'),
     Input('popup-reset-corpus', 'n_clicks')],
    [State('popup-upload-corpus', 'filename')],
    prevent_initial_call=True
)
def update_filtered_data(filters, upload_state, reset_clicks, filename):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    
    if triggered_id == 'popup-reset-corpus' and reset_clicks:
        return []
    
    if not filters:
        return []
    
    # Handle uploaded corpus data
    if triggered_id == 'upload-state' and upload_state:
        try:
            if isinstance(upload_state, dict) and 'uploaded' in upload_state:
                pass
            else:
                return dash.no_update
        except Exception as e:
            return dash.no_update
    
    try:
        # Get current state
        books, places = get_current_state()
        
        if not books and not places:
            return []
        
        return books
    except Exception as e:
        print(f"Error in update_filtered_data: {e}")
        return dash.no_update

# Add new callback for global place search
@app.callback(
    [Output('main-map', 'figure', allow_duplicate=True),
     Output('place-summary-container', 'style', allow_duplicate=True),
     Output('place-summary', 'children', allow_duplicate=True)],
    [Input('global-place-search', 'value')],
    [State('main-map', 'figure')],
    prevent_initial_call=True
)
def handle_global_search(search_term, current_figure):
    if not search_term or len(search_term) < 2:
        raise PreventUpdate
    
    try:
        conn = get_db_connection()
        try:
            # Search in both historical and modern names
            query = """
            SELECT 
                p.token,
                p.modern as name,
                p.latitude,
                p.longitude,
                COUNT(DISTINCT b.dhlabid) as book_count,
                COUNT(b.dhlabid) as frequency
            FROM places p
            JOIN books b ON p.token = b.token
            WHERE (LOWER(p.token) LIKE LOWER(?) OR LOWER(p.modern) LIKE LOWER(?))
            AND p.latitude IS NOT NULL 
            AND p.longitude IS NOT NULL
            AND p.latitude != '0'
            AND p.longitude != '0'
            GROUP BY p.token, p.modern, p.latitude, p.longitude
            ORDER BY frequency DESC
            LIMIT 1
            """
            
            # Add wildcards for partial matching
            search_pattern = f"%{search_term}%"
            places_df = pd.read_sql_query(query, conn, params=(search_pattern, search_pattern))
            
            if places_df.empty:
                return current_figure, dash.no_update, dash.no_update
            
            # Get the first matching place
            place = places_df.iloc[0]
            
            # Create hover text
            hover_text = f"{place['token']} ({place['name']})<br>Mentions: {int(place['frequency'])}<br>Books: {int(place['book_count'])}"
            
            # Update the map to center on the found place
            fig = go.Figure(current_figure)
            fig.update_layout(
                map=dict(
                    center=dict(lat=float(place['latitude']), lon=float(place['longitude'])),
                    zoom=10
                )
            )
            
            # Get book details for the place
            books_df, total_books = get_place_details(place['token'])
            
            # Create summary content
            summary = html.Div([
                html.Div([
                    html.H5(place['token'], style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {place['name']}", style={'fontSize': '14px', 'color': '#666'}) if place['name'] else None,
                    html.P(f"Appears in {len(books_df):,} books with {int(place['frequency']):,} total mentions", style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                html.Div([
                    html.H6(f"Books mentioning this place ({len(books_df):,} total):", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            html.A(
                                f"{row['title']} ({row['year']})",
                                href=f"https://www.nb.no/items/{row['urn']}?searchText={place['token']}",
                                target="_blank",
                                style={'fontWeight': '500', 'color': '#1a56db', 'textDecoration': 'none'}
                            ),
                            html.Div([
                                html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                                html.Span(f" • {int(row.get('mention_count', 1)):,} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between'})
                        ], style={'marginBottom': '10px', 'paddingBottom': '8px', 'borderBottom': '1px solid #eee'})
                        for i, row in books_df.iterrows() if pd.notna(row['title'])
                    ]) if not books_df.empty else html.Div("No book details available")
                ])
            ])
            
            # Show the summary container
            summary_style = {
                'position': 'absolute',
                'bottom': '80px',
                'left': '20px',
                'width': '350px',
                'maxHeight': '500px',
                'overflowY': 'auto',
                'zIndex': 800,
                'display': 'block',
                'cursor': 'auto'
            }
            
            return fig, summary_style, summary
            
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Error in handle_global_search: {e}")
        return current_figure, dash.no_update, dash.no_update

@app.callback(
    Output('similar-places-list', 'children'),
    [Input('similar-place-search', 'value')],
    prevent_initial_call=True
)
def update_similar_places(search_term):
    if not search_term or len(search_term) < 2:
        return html.Div("Enter at least 2 characters to search", style={'color': '#666'})
    
    try:
        conn = get_db_connection()
        try:
            # Get current state
            books, _ = get_current_state()
            if not books:
                return html.Div("No corpus loaded", style={'color': '#666'})
            
            # Search in both historical and modern names
            query = """
            SELECT 
                p.token,
                p.modern as name,
                p.latitude,
                p.longitude,
                COUNT(DISTINCT b.dhlabid) as book_count,
                SUM(b.book_count) as frequency
            FROM places p
            JOIN books b ON p.token = b.token
            WHERE (LOWER(p.token) LIKE LOWER(?) OR LOWER(p.modern) LIKE LOWER(?))
            AND b.dhlabid IN ({})
            AND p.latitude IS NOT NULL 
            AND p.longitude IS NOT NULL
            AND p.latitude != '0'
            AND p.longitude != '0'
            GROUP BY p.token, p.modern, p.latitude, p.longitude
            ORDER BY frequency DESC
            LIMIT 50
            """.format(','.join(['?'] * len(books)))
            
            # Add wildcards for partial matching
            search_pattern = f"%{search_term}%"
            places_df = pd.read_sql_query(query, conn, params=(search_pattern, search_pattern) + tuple(books))
            
            if places_df.empty:
                return html.Div("No matching places found", style={'color': '#666'})
            
            # Create hover text
            places_df['hover_text'] = places_df.apply(
                lambda row: f"{row['token']} ({row['name']})<br>Mentions: {int(row['frequency'])}<br>Books: {int(row['book_count'])}",
                axis=1
            )
            
            return html.Div([
                html.Div([
                    html.Div([
                        html.Div("Place", style={'flex': '2', 'fontWeight': 'bold', 'padding': '8px'}),
                        html.Div("📚", style={'flex': '1', 'fontWeight': 'bold', 'padding': '8px', 'textAlign': 'center'}),
                        html.Div("📝", style={'flex': '1', 'fontWeight': 'bold', 'padding': '8px', 'textAlign': 'center'})
                    ], style={
                        'display': 'flex',
                        'borderBottom': '2px solid #eee',
                        'marginBottom': '4px',
                        'fontSize': '0.9rem'
                    }),
                    html.Div([
                        html.Div([
                            html.Div([
                                html.Div(f"{row['token']}", style={'fontWeight': '500', 'fontSize': '0.9rem'}),
                                html.Div(f"{row['name']}", style={'color': '#666', 'fontSize': '0.8rem'})
                            ], style={'flex': '2', 'padding': '8px'}),
                            html.Div(f"{int(row['book_count'])}", 
                                    style={'flex': '1', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'}),
                            html.Div(f"{int(row['frequency'])}", 
                                    style={'flex': '1', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'})
                        ], style={
                            'display': 'flex',
                            'borderBottom': '1px solid #eee',
                            'transition': 'background-color 0.2s',
                            'cursor': 'pointer'
                        }, 
                        className='similar-place-item', 
                        id={'type': 'similar-place-item', 'index': row['token']},
                        **{'data-lat': row['latitude'], 'data-lon': row['longitude'], 'data-hover': row['hover_text']})
                        for _, row in places_df.iterrows()
                    ], style={'maxHeight': '300px', 'overflowY': 'auto'})
                ], style={'border': '1px solid #eee', 'borderRadius': '4px'})
            ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'})
        finally:
            conn.close()
    except Exception as e:
        print(f"Error in update_similar_places: {e}")
        return html.Div("Error searching for places", style={'color': 'red'})

# Add callback for resampling places
@app.callback(
    [Output('total-places', 'children'),
     Output('sample-places', 'children'),
     Output('max-sample-size', 'children'),
     Output('resample-container', 'style')],
    [Input('current-filters', 'data'),
     Input('resample-places', 'n_clicks')],
    [State('popup-max-places-slider', 'value')],
    prevent_initial_call=True
)
def update_places_info(filters, n_clicks, max_places):
    if not filters:
        return "No corpus loaded", "", "", {'display': 'none'}
    
    # Get current state
    books, places = get_current_state()
    if not books:
        return "No corpus loaded", "", "", {'display': 'none'}
    
    conn = get_db_connection()
    try:
        # Get total places in corpus
        total_places_query = f"""
        SELECT COUNT(DISTINCT token) as total_places
        FROM books
        WHERE dhlabid IN ({','.join(['?'] * len(books))})
        """
        total_places = pd.read_sql_query(total_places_query, conn, params=tuple(books))['total_places'].iloc[0]
        
        # Get current sample size
        current_sample = len(places) if places else 0
        
        # If resample button was clicked, resample places
        ctx = callback_context
        if ctx.triggered and ctx.triggered[0]['prop_id'] == 'resample-places.n_clicks':
            if max_places > 0:
                # Get all places and randomly sample
                places_query = f"""
                SELECT DISTINCT token
                FROM books
                WHERE dhlabid IN ({','.join(['?'] * len(books))})
                ORDER BY RANDOM()
                LIMIT ?
                """
                sampled_places = pd.read_sql_query(places_query, conn, params=tuple(books + [max_places]))['token'].tolist()
                books, places = update_from_books(books, sampled_places)
                current_sample = len(sampled_places)
        elif max_places > 0 and current_sample > max_places:
            # If we have more places than the max limit, resample
            places_query = f"""
            SELECT DISTINCT token
            FROM books
            WHERE dhlabid IN ({','.join(['?'] * len(books))})
            ORDER BY RANDOM()
            LIMIT ?
            """
            sampled_places = pd.read_sql_query(places_query, conn, params=tuple(books + [max_places]))['token'].tolist()
            books, places = update_from_books(books, sampled_places)
            current_sample = len(sampled_places)
        
        # Update display
        total_places_text = f"Total places in corpus: {total_places:,}"
        sample_places_text = f"Currently sampled: {current_sample:,} places"
        max_sample_text = f"Maximum sample size: {max_places:,} places" if max_places > 0 else "No sample size limit"
        
        return total_places_text, sample_places_text, max_sample_text, {'display': 'block'}
    except Exception as e:
        print(f"Error in update_places_info: {e}")
        return "Error loading places", "", "", {'display': 'none'}
    finally:
        conn.close()

# Run Server
if __name__ == '__main__':
    app.run(debug=True, port=8053)
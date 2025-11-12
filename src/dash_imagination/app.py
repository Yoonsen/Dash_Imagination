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
from dash_imagination.components.corpus import create_corpus_controls, create_visualization_controls, create_corpus_builder_card
from scipy.spatial import ConvexHull
import math
from dash_imagination.components.places.place_similarity import create_place_similarity_controls
from dash_imagination.components.places.place_similarity_dialog import create_place_similarity_dialog
from dash_imagination.utils.db import get_db_connection
from dash_imagination.utils.global_state import get_current_state, update_from_books, clear_state
import plotly.express as px
import dhlab as dh
import re
import json
from flask import request, send_file
from dash import dash_table
from typing import Tuple

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
    # Split authors on '/', strip whitespace, flatten, deduplicate, and sort
    authors = set()
    for author_str in df['author'].dropna():
        for author in str(author_str).split('/'):
            author = author.strip()
            if author:
                authors.add(author)
    return sorted(authors)

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
    'max_places': 500,
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
                    "width": "240px",
                    "flexShrink": "0"  # Prevent search field from shrinking
                })
            ], style={
                "display": "flex",
                "alignItems": "center",
                "flexShrink": "0"  # Prevent container from shrinking
            }),

            # Buttons container
            html.Div([
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
                        'flexShrink': '0'  # Prevent the button from shrinking
                    }
                ),

                # Corpus and Places buttons
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
                    'flexShrink': '0',  # Prevent the button from shrinking
                    'marginLeft': '8px'  # Add margin between buttons
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
                    'fontSize': '14px',
                    'fontWeight': '500',
                    'lineHeight': '1.5',
                    'flexShrink': '0',  # Prevent the button from shrinking
                    'marginLeft': '8px'  # Add margin between buttons
                })
            ], style={
                'display': 'flex',
                'flexDirection': 'row',  # Default to horizontal layout
                'alignItems': 'center',
                'flexWrap': 'wrap',  # Allow wrapping only when needed
                'gap': '8px',  # Add gap between wrapped items
                'marginLeft': '8px',  # Add margin between search and buttons
                'flexShrink': '0'  # Prevent container from shrinking
            })
        ], style={
            'display': 'flex',
            'flexDirection': 'row',  # Change to horizontal layout
            'alignItems': 'center',
            'position': 'absolute',
            'left': '20px',
            'top': '20px',
            'zIndex': 1000,
            'pointerEvents': 'auto',
            'flexWrap': 'wrap',  # Allow wrapping when needed
            'gap': '8px',  # Add gap between wrapped items
            'maxWidth': 'calc(100% - 180px)'  # Reserve space for map view button
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
                'whiteSpace': 'nowrap',  # Prevent text wrapping
                'flexShrink': '0'  # Prevent button from shrinking
            })
        ], style={
            'position': 'absolute',
            'right': '20px',
            'top': '20px',
            'zIndex': 1000,
            'pointerEvents': 'auto',
            'flexShrink': '0'  # Prevent container from shrinking
        }),
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
            html.H3("ImagiNation", style={
                'margin': '0',
                'fontWeight': '400',
                'color': '#333',
                'fontSize': '20px'
            })
        ], 
        id='info-button',
        style={
            'background': 'rgba(255,255,255,0.6)',
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
                html.H5("Place Details", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-summary',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-danger-subtle text-dark", id='summary-header'),
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
        'cursor': 'grab'  # Change cursor to grab
    }),

    # Place Names Container
    dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-map-marker me-2"),
                html.H5("Place Names", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-place-names',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center", id='place-names-header')
        ], className="bg-warning-subtle text-dark"),
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
                    html.I(className="fas fa-sync-alt me-2"),
                    "Resample Places"
                ], id='resample-places', className="btn btn-primary w-100")
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
        'cursor': 'grab'  # Change cursor to grab
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
    dcc.Store(id='corpus-operation', data='intersection'),

    # Add the new corpus builder card
    create_corpus_builder_card(categories_list=categories_list, authors_list=authors_list),
    # Add interval for clearing download status
    dcc.Interval(id='clear-download-status-interval', interval=6000, n_intervals=0, disabled=True),
    dcc.Store(id='all-places-store'),  # Store for caching all places for current corpus
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
            /* Resize handle styles */
            .resize-handle {
                position: absolute;
                background: #94a3b8;
                border-radius: 2px;
                opacity: 0;
                transition: opacity 0.2s;
                z-index: 1000;
            }
            .resize-handle:hover {
                opacity: 1;
            }
            .resize-handle.e {
                width: 8px;
                height: 100%;
                right: -4px;
                top: 0;
                cursor: e-resize;
            }
            .resize-handle.s {
                width: 100%;
                height: 8px;
                bottom: -4px;
                left: 0;
                cursor: s-resize;
            }
            .resize-handle.se {
                width: 12px;
                height: 12px;
                right: -6px;
                bottom: -6px;
                cursor: se-resize;
                border-radius: 50%;
            }
            .resize-handle.w {
                width: 8px;
                height: 100%;
                left: -4px;
                top: 0;
                cursor: w-resize;
            }
            .resize-handle.n {
                width: 100%;
                height: 8px;
                top: -4px;
                left: 0;
                cursor: n-resize;
            }
            .resize-handle.sw {
                width: 12px;
                height: 12px;
                left: -6px;
                bottom: -6px;
                cursor: sw-resize;
                border-radius: 50%;
            }
            .resize-handle.ne {
                width: 12px;
                height: 12px;
                right: -6px;
                top: -6px;
                cursor: ne-resize;
                border-radius: 50%;
            }
            .resize-handle.nw {
                width: 12px;
                height: 12px;
                left: -6px;
                top: -6px;
                cursor: nw-resize;
                border-radius: 50%;
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
            document.addEventListener('DOMContentLoaded', function() {
                function initializeDraggable(element) {
                    let isDragging = false;
                    let startX, startY;
                    let initialLeft, initialTop;
                    let touchIdentifier = null;
                    
                    const header = element.querySelector('.card-header');
                    if (!header) return;
                    
                    // Mouse event handlers
                    header.addEventListener('mousedown', startDrag);
                    document.addEventListener('mousemove', drag);
                    document.addEventListener('mouseup', stopDrag);
                    
                    // Enhanced touch event handlers
                    header.addEventListener('touchstart', handleTouchStart, { passive: false });
                    document.addEventListener('touchmove', handleTouchMove, { passive: false });
                    document.addEventListener('touchend', handleTouchEnd);
                    document.addEventListener('touchcancel', handleTouchEnd);
                    
                    function startDrag(e) {
                        e.preventDefault();
                        isDragging = true;
                        element.classList.add('dragging');
                        startX = e.clientX;
                        startY = e.clientY;
                        initialLeft = parseInt(window.getComputedStyle(element).left);
                        initialTop = parseInt(window.getComputedStyle(element).top);
                    }
                    
                    function handleTouchStart(e) {
                        if (e.touches.length > 1) return; // Ignore multi-touch
                        e.preventDefault();
                        const touch = e.touches[0];
                        touchIdentifier = touch.identifier;
                        isDragging = true;
                        element.classList.add('dragging');
                        startX = touch.clientX;
                        startY = touch.clientY;
                        initialLeft = parseInt(window.getComputedStyle(element).left);
                        initialTop = parseInt(window.getComputedStyle(element).top);
                    }
                    
                    function drag(e) {
                        if (!isDragging) return;
                        e.preventDefault();
                        
                        const dx = e.clientX - startX;
                        const dy = e.clientY - startY;
                        
                        // Add bounds checking to keep element within viewport
                        const newLeft = Math.max(0, Math.min(window.innerWidth - element.offsetWidth, initialLeft + dx));
                        const newTop = Math.max(0, Math.min(window.innerHeight - element.offsetHeight, initialTop + dy));
                        
                        element.style.left = `${newLeft}px`;
                        element.style.top = `${newTop}px`;
                    }
                    
                    function handleTouchMove(e) {
                        if (!isDragging) return;
                        e.preventDefault();
                        
                        // Find the touch that matches our identifier
                        const touch = Array.from(e.touches).find(t => t.identifier === touchIdentifier);
                        if (!touch) return;
                        
                        const dx = touch.clientX - startX;
                        const dy = touch.clientY - startY;
                        
                        // Add bounds checking to keep element within viewport
                        const newLeft = Math.max(0, Math.min(window.innerWidth - element.offsetWidth, initialLeft + dx));
                        const newTop = Math.max(0, Math.min(window.innerHeight - element.offsetHeight, initialTop + dy));
                        
                        element.style.left = `${newLeft}px`;
                        element.style.top = `${newTop}px`;
                    }
                    
                    function stopDrag() {
                        if (isDragging) {
                            isDragging = false;
                            element.classList.remove('dragging');
                            touchIdentifier = null;
                        }
                    }
                    
                    function handleTouchEnd(e) {
                        e.preventDefault();
                        stopDrag();
                    }
                }
                
                // Initialize all cards
                const cards = [
                    '#place-names-container',
                    '#place-summary-container',
                    '#corpus-controls-container',
                    '#visualization-controls-container',
                    '#place-similarity-dialog'
                ];
                
                cards.forEach(selector => {
                    const element = document.querySelector(selector);
                    if (element) {
                        initializeDraggable(element);
                    }
                });
                
                // Initialize new cards when they become visible
                const observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                            const element = mutation.target;
                            if (element.style.display === 'block' && !element.classList.contains('initialized')) {
                                initializeDraggable(element);
                                element.classList.add('initialized');
                            }
                        }
                    });
                });
                
                cards.forEach(selector => {
                    const element = document.querySelector(selector);
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
    [Input('popup-upload-corpus', 'contents')],
    [State('popup-upload-corpus', 'filename'),
     State('current-filters', 'data'),
     State('corpus-operation', 'data')],
    prevent_initial_call=True
)
def update_state_and_filters(contents, filename, current_filters, operation):
    import pandas as pd
    import io
    import base64
    from dash_imagination.utils.global_state import update_from_books
    if not contents:
        return html.Div('', style={'display': 'none'}), {}, current_filters
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        df = pd.read_excel(io.BytesIO(decoded))
        if 'dhlabid' not in df.columns:
            return html.Div('Error: File must contain a dhlabid column', style={'color': 'red'}), {}, current_filters
        new_books = [int(x) for x in df['dhlabid'].dropna().tolist()]
        if not new_books:
            return html.Div('No valid dhlabids found in file.', style={'color': 'red'}), {}, current_filters
        # Query DB for valid places for these books
        conn = get_db_connection()
        try:
            query = f"""
            SELECT DISTINCT token
            FROM books
            WHERE dhlabid IN ({','.join(['?'] * len(new_books))})
            """
            places_df = pd.read_sql_query(query, conn, params=tuple(new_books))
            new_places = places_df['token'].tolist()
        finally:
            conn.close()
        # Update global state using the same logic as the builder
        books, places = update_from_books(new_books, new_places, operation=operation or "intersection")
        # Update filters to reflect new corpus source
        new_filters = current_filters.copy() if current_filters else default_filters.copy()
        new_filters['corpus_source'] = filename
        new_filters['last_operation'] = operation or "intersection"
        new_filters['selected_tokens'] = places
        return html.Div('', style={'display': 'none'}), {'uploaded': True, 'filename': filename}, new_filters
    except Exception as e:
        return html.Div(f'Error processing file: {str(e)}', style={'color': 'red'}), {}, current_filters


@app.callback(
    Output('corpus-operation', 'data'),
    Input('corpus-op-union-controls', 'n_clicks'),
    Input('corpus-op-intersection-controls', 'n_clicks'),
    Input('corpus-op-diff-controls', 'n_clicks'),
    Input('corpus-op-union-builder', 'n_clicks'),
    Input('corpus-op-intersection-builder', 'n_clicks'),
    Input('corpus-op-diff-builder', 'n_clicks'),
    State('corpus-operation', 'data'),
    prevent_initial_call=True
)
def set_corpus_operation(
    union_controls,
    intersection_controls,
    diff_controls,
    union_builder,
    intersection_builder,
    diff_builder,
    current_operation,
):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    mapping = {
        'corpus-op-union-controls': 'union',
        'corpus-op-intersection-controls': 'intersection',
        'corpus-op-diff-controls': 'difference',
        'corpus-op-union-builder': 'union',
        'corpus-op-intersection-builder': 'intersection',
        'corpus-op-diff-builder': 'difference',
    }
    return mapping.get(triggered, (current_operation or 'intersection'))


def _operation_button_styles(selected: str, target: str) -> Tuple[str, bool]:
    op = (selected or 'intersection').lower()
    active = op == target
    return ('primary' if active else 'secondary', not active)


@app.callback(
    Output('corpus-op-union-controls', 'color'),
    Output('corpus-op-intersection-controls', 'color'),
    Output('corpus-op-diff-controls', 'color'),
    Output('corpus-op-union-controls', 'outline'),
    Output('corpus-op-intersection-controls', 'outline'),
    Output('corpus-op-diff-controls', 'outline'),
    Input('corpus-operation', 'data')
)
def style_corpus_operation_controls(operation):
    c_union, o_union = _operation_button_styles(operation, 'union')
    c_intersection, o_intersection = _operation_button_styles(operation, 'intersection')
    c_diff, o_diff = _operation_button_styles(operation, 'difference')
    return c_union, c_intersection, c_diff, o_union, o_intersection, o_diff


@app.callback(
    Output('corpus-op-union-builder', 'color'),
    Output('corpus-op-intersection-builder', 'color'),
    Output('corpus-op-diff-builder', 'color'),
    Output('corpus-op-union-builder', 'outline'),
    Output('corpus-op-intersection-builder', 'outline'),
    Output('corpus-op-diff-builder', 'outline'),
    Input('corpus-operation', 'data')
)
def style_corpus_operation_builder(operation):
    c_union, o_union = _operation_button_styles(operation, 'union')
    c_intersection, o_intersection = _operation_button_styles(operation, 'intersection')
    c_diff, o_diff = _operation_button_styles(operation, 'difference')
    return c_union, c_intersection, c_diff, o_union, o_intersection, o_diff


@app.callback(
    Output('collocation-results', 'children'),
    Input('run-collocations', 'n_clicks'),
    State('collocation-words-input', 'value'),
    State('collocation-before-input', 'value'),
    State('collocation-after-input', 'value'),
    State('current-dhlabids-store', 'data'),
    State('all-places-store', 'data'),
    prevent_initial_call=True
)
def run_collocation_search(n_clicks, words_value, before, after, current_books, all_places_json):
    if not n_clicks:
        raise PreventUpdate
    if not words_value:
        return html.Div("Enter one or more keywords to analyse collocations.", style={'color': '#dc2626', 'fontSize': '0.8rem'})
    if not current_books:
        return html.Div("Corpus is empty. Build or upload a corpus first.", style={'color': '#dc2626', 'fontSize': '0.8rem'})

    words = [w.strip() for w in words_value.split(',') if w.strip()]
    if not words:
        return html.Div("No valid keywords provided.", style={'color': '#dc2626', 'fontSize': '0.8rem'})

    before = int(before or 50)
    after = int(after or 50)

    conn = get_db_connection()
    try:
        placeholders = ",".join(["?"] * len(current_books))
        query = f"""
            SELECT urn
            FROM corpus
            WHERE dhlabid IN ({placeholders})
              AND urn IS NOT NULL
        """
        urns = pd.read_sql_query(query, conn, params=tuple(current_books))['urn'].dropna().tolist()
    finally:
        conn.close()

    if not urns:
        return html.Div("No URNs found for the current corpus; collocations require identifiable texts.", style={'color': '#dc2626', 'fontSize': '0.8rem'})

    sample_size = min(len(urns), 5000)

    try:
        coll = dh.Collocations(urns, words, before=before, after=after, samplesize=sample_size)
        coll_df = coll.frame.copy()
    except Exception as err:
        return html.Div(f"Error retrieving collocations: {err}", style={'color': '#dc2626', 'fontSize': '0.8rem'})

    if coll_df is None or coll_df.empty:
        return html.Div("No collocations found for the selected keywords.", style={'color': '#475569', 'fontSize': '0.8rem'})

    coll_df = coll_df.reset_index()
    if 'index' in coll_df.columns:
        coll_df = coll_df.rename(columns={'index': 'word'})
    if 'counts' in coll_df.columns:
        coll_df = coll_df.rename(columns={'counts': 'count'})
    elif 'total' in coll_df.columns:
        coll_df = coll_df.rename(columns={'total': 'count'})

    coll_df['word'] = coll_df['word'].astype(str)
    coll_df['lower_word'] = coll_df['word'].str.lower()

    word_counts = coll_df.groupby('lower_word')['count'].sum().to_dict()
    collocate_tokens = set(word_counts.keys())

    if all_places_json:
        places_df = pd.read_json(io.StringIO(all_places_json), orient='split')
    else:
        places_df = get_all_places_for_corpus(current_books)

    matching_places = []
    for _, row in places_df[['token', 'name']].dropna().drop_duplicates().iterrows():
        place_name = str(row['name'])
        tokens = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", place_name.lower())
        tokens = [tok for tok in tokens if tok]
        if not tokens:
            continue
        if all(tok in collocate_tokens for tok in tokens):
            total_count = int(sum(word_counts[tok] for tok in tokens))
            matching_places.append({
                'Place': place_name,
                'Tokens': ", ".join(tokens),
                'Total count': total_count,
                'Token': row['token']
            })

    if not matching_places:
        top = coll_df.sort_values(by='count', ascending=False).head(20)
        return html.Div([
            html.Div("No place matches found. Showing top collocations instead:", style={'color': '#475569', 'fontSize': '0.8rem', 'marginBottom': '0.5rem'}),
            dash_table.DataTable(
                columns=[{'name': 'Word', 'id': 'word'}, {'name': 'Count', 'id': 'count'}],
                data=top[['word', 'count']].to_dict('records'),
                style_table={'overflowX': 'auto', 'fontSize': '0.75rem'},
                style_cell={'padding': '4px'},
                page_action='none',
                fixed_rows={'headers': True},
                sort_action='native'
            )
        ])

    match_df = (
        pd.DataFrame(matching_places)
        .drop_duplicates()
        .sort_values(by='Total count', ascending=False)
        .head(50)
    )
    return dash_table.DataTable(
        columns=[
            {'name': 'Place', 'id': 'Place'},
            {'name': 'Tokens', 'id': 'Tokens'},
            {'name': 'Total count', 'id': 'Total count'},
            {'name': 'Token', 'id': 'Token'}
        ],
        data=match_df.to_dict('records'),
        style_table={'overflowX': 'auto', 'fontSize': '0.75rem'},
        style_cell={
            'padding': '4px',
            'whiteSpace': 'pre-line',
            'textAlign': 'left'
        },
        style_data_conditional=[
            {
                'if': {'column_id': 'Token'},
                'display': 'none'
            }
        ],
        page_action='none',
        fixed_rows={'headers': True},
        sort_action='native'
    )

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
     Output('current-dhlabids-store', 'data'),
     Output('current-filters', 'data')],
    [Input('current-filters', 'data'),
     Input('upload-state', 'data'),
     Input('reset-corpus-confirm-modal', 'n_clicks')],
    [State('popup-upload-corpus', 'filename')],
    prevent_initial_call=True
)
def update_filtered_data(filters, upload_state, reset_confirm_clicks, filename):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    if triggered_id == 'reset-corpus-confirm-modal' and reset_confirm_clicks:
        from dash_imagination.utils.global_state import clear_state
        clear_state()
        return pd.DataFrame().to_json(date_format='iso', orient='split'), [], {}
    if triggered_id == 'upload-state' and upload_state:
        try:
            if isinstance(upload_state, dict) and 'uploaded' in upload_state:
                pass
            else:
                return dash.no_update, dash.no_update, dash.no_update
        except Exception as e:
            return dash.no_update, dash.no_update, dash.no_update
    if not filters:
        return pd.DataFrame().to_json(date_format='iso', orient='split'), [], {}
    try:
        # Get current state
        books, places = get_current_state()
        if not books and not places:
            return pd.DataFrame().to_json(date_format='iso', orient='split'), [], {}
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
        return json_output, books, filters
    except Exception as e:
        print(f"Error in update_filtered_data: {e}")
        return dash.no_update, dash.no_update, dash.no_update

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
                        lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap', showscale=False
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
                        showscale=False,
                        visible=True,
                        name='Heatmap'
                    ))
            except Exception as e:
                print(f"Heatmap error: {e}")
                fig.add_trace(go.Densitymap(
                    lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap', showscale=False
                ))
        else:
            fig.add_trace(go.Densitymap(visible=False, name='Heatmap', showscale=False))
        
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
    print("DEBUG columns:", places_df.columns)
    places_df['hover_text'] = places_df.apply(
        lambda row: f"{row.get('token', '')} ({row.get('name', '')})<br>Modern name: {row.get('name', '')}<br>Mentions: {int(row.get('frequency', 0))}<br>Books: {int(row.get('book_count', 0))}",
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
    [Input('main-map', 'clickData'),
     Input('selected-place', 'data')],
    [State('place-summary-container', 'style')],
    prevent_initial_call=True
)
def update_place_summary(click_data, selected_place, current_style):
    ctx = callback_context
    triggered = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    # If triggered by map click
    if triggered == 'main-map':
        try:
            if not click_data or 'points' not in click_data or not click_data['points']:
                return current_style, dash.no_update
            point = click_data['points'][0]
            token = point.get('customdata') or point.get('text')
            # Try to extract modern name and hover text if available
            hover_text = point.get('text', '')
            modern_part = ''
            frequency = 0
            book_count = 0
            # Parse hover_text for modern name, frequency, and book count
            if '<br>' in hover_text:
                parts = hover_text.split('<br>')
                if len(parts) > 0:
                    token_part = parts[0]
                    if '(' in token_part and ')' in token_part:
                        token = token_part.split('(')[0].strip()
                        modern_part = token_part.split('(')[1].split(')')[0].strip()
                if len(parts) > 1 and 'Mentions:' in parts[1] and 'Books:' in parts[2]:
                    try:
                        frequency = int(parts[1].replace('Mentions:', '').strip())
                        book_count = int(parts[2].replace('Books:', '').strip())
                    except Exception:
                        pass
            # Get book details for the place
            books_df, total_books = get_place_details(token)
            if not books_df.empty:
                if 'total_mentions' in books_df.columns:
                    frequency = int(books_df.iloc[0]['total_mentions'])
                if 'total_books' in books_df.columns:
                    book_count = int(books_df.iloc[0]['total_books'])
                else:
                    book_count = len(books_df)
            summary = html.Div([
                html.Div([
                    html.H5(token, style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                    html.P(f"Appears in {book_count:,} books with {frequency:,} total mentions", style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                html.Div([
                    html.H6(f"Books mentioning this place (showing {len(books_df):,} of {book_count:,}):", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            html.A(
                                f"{row['title']} ({row['year']})",
                                href=f"https://www.nb.no/items/{row['urn']}?searchText=\"{token}\"",
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
            new_style = dict(current_style)
            new_style['display'] = 'block'
            return new_style, summary
        except Exception as e:
            print(f"Error updating place summary (map): {e}")
            return dash.no_update, dash.no_update
    # If triggered by list click
    elif triggered == 'selected-place':
        try:
            if not selected_place:
                return current_style, dash.no_update
            # Use selected_place (token) to fetch and display the place info
            token = selected_place
            # Get book details for the place
            books_df, total_books = get_place_details(token)
            # Fallbacks for summary info
            modern_part = ""
            frequency = 0
            book_count = 0
            # Try to get modern name, frequency, and book count from books_df if available
            if not books_df.empty:
                # Try to get modern name from the first row if present
                if 'modern' in books_df.columns:
                    modern_part = books_df.iloc[0]['modern']
                # Try to get total mentions and books from the columns if present
                if 'total_mentions' in books_df.columns:
                    frequency = int(books_df.iloc[0]['total_mentions'])
                if 'total_books' in books_df.columns:
                    book_count = int(books_df.iloc[0]['total_books'])
                else:
                    book_count = len(books_df)
            summary = html.Div([
                html.Div([
                    html.H5(token, style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                    html.P(f"Appears in {book_count:,} books with {frequency:,} total mentions", style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                html.Div([
                    html.H6(f"Books mentioning this place (showing {len(books_df):,} of {book_count:,}):", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            html.A(
                                f"{row['title']} ({row['year']})",
                                href=f"https://www.nb.no/items/{row['urn']}?searchText=\"{token}\"",
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
            new_style = dict(current_style)
            new_style['display'] = 'block'
            return new_style, summary
        except Exception as e:
            print(f"Error updating place summary (list): {e}")
            return dash.no_update, dash.no_update
    else:
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
    [Output('current-filters', 'data', allow_duplicate=True)],
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
    return new_filters



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
    [Input('build-corpus-btn', 'n_clicks'),  # Changed from apply-filters to build-corpus-btn
     Input('main-map', 'figure')],
    [State('loading-overlay', 'style')]
)
def update_loading_state(build_clicks, map_figure, current_style):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Show loading when build button is clicked
    if trigger_id == 'build-corpus-btn' and build_clicks:
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

@app.callback(
    [Output('download-map-file', 'data'),
     Output('download-status', 'children'),
     Output('clear-download-status-interval', 'disabled'),
     Output('clear-download-status-interval', 'n_intervals')],
    [Input('download-map', 'n_clicks')],
    [State('download-format', 'value'),
     State('download-resolution', 'value'),
     State('main-map', 'figure')],
    prevent_initial_call=True
)
def trigger_download(n_clicks, format, resolution, figure):
    import dash
    from dash import dcc, html
    import plotly.graph_objects as go
    import io
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    # Set resolution based on selection
    resolution_map = {
        'standard': {'width': 1920, 'height': 1080},
        'high': {'width': 3840, 'height': 2160},
        'publication': {'width': 6000, 'height': 4000}
    }
    # Get the selected resolution
    dimensions = resolution_map.get(resolution, resolution_map['standard'])
    try:
        # Create figure from JSON
        fig = go.Figure(figure)
        fig.update_layout(
            width=dimensions['width'],
            height=dimensions['height'],
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        # Generate image bytes
        if format == 'png':
            img_bytes = fig.to_image(format='png', scale=2 if resolution in ['high', 'publication'] else 1)
            filename = 'imagination_map.png'
            mime = 'image/png'
        elif format == 'pdf':
            img_bytes = fig.to_image(format='pdf', scale=2 if resolution in ['high', 'publication'] else 1)
            filename = 'imagination_map.pdf'
            mime = 'application/pdf'
        elif format == 'svg':
            img_bytes = fig.to_image(format='svg', scale=2 if resolution in ['high', 'publication'] else 1)
            filename = 'imagination_map.svg'
            mime = 'image/svg+xml'
        else:
            return None, html.Div('Invalid format selected', style={'color': 'red'}), True, 0
        # Enable the interval to clear the message
        return dcc.send_bytes(lambda buf: buf.write(img_bytes), filename), html.Div('Download started...', style={'color': 'green', 'marginTop': '10px'}), False, 0
    except Exception as e:
        print(f"Error generating download: {e}")
        return None, html.Div(f'Error generating download: {e}', style={'color': 'red'}), True, 0

@app.callback(
    Output('download-status', 'children', allow_duplicate=True),
    [Input('clear-download-status-interval', 'n_intervals')],
    [State('clear-download-status-interval', 'disabled')],
    prevent_initial_call=True
)
def clear_download_status(n_intervals, disabled):
    if not disabled and n_intervals > 0:
        return ''
    raise dash.exceptions.PreventUpdate

@app.callback(
    Output('clear-download-status-interval', 'disabled', allow_duplicate=True),
    [Input('download-status', 'children')],
    prevent_initial_call=True
)
def disable_interval_on_clear(status):
    # Disable the interval if the status is cleared
    if not status:
        return True
    raise dash.exceptions.PreventUpdate

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
                                href=f"https://www.nb.no/items/{row['urn']}?searchText=\"{place['token']}\"",
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




# Add a clientside callback for instant download status feedback
app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks) {
            return 'Download started...';
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('download-status', 'children', allow_duplicate=True),
    [Input('download-map', 'n_clicks')],
    prevent_initial_call=True
)



@app.callback(
    Output('test-info-output', 'children'),
    [Input('test-info-btn', 'n_clicks')],
    prevent_initial_call=True
)
def test_info_btn_callback(n_clicks):
    print(f"[DEBUG] test_info_btn_callback triggered: n_clicks={n_clicks}")
    return f"Button clicked {n_clicks} times."

@app.callback(
    [
        Output('corpus-info-books', 'children'),
        Output('corpus-info-authors', 'children'),
        Output('corpus-info-places', 'children'),
        Output('corpus-info-years', 'children'),
        Output('corpus-browse-table', 'children'),
    ],
    [Input('filtered-data', 'data'), Input('corpus-table-filter', 'data')],
    prevent_initial_call=True
)
def update_corpus_info_and_table(_, filter_data):
    books, _ = get_current_state()
    if not books:
        return "0", "0", "0", "", html.Div("No books in corpus.", style={'color': '#666'})
    import pandas as pd
    conn = get_db_connection()
    try:
        # Info section
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
        # Places count
        places_query = f"""
        SELECT COUNT(DISTINCT token) as place_count
        FROM books
        WHERE dhlabid IN ({','.join(['?'] * len(books))})
        """
        place_count = pd.read_sql_query(places_query, conn, params=tuple(books))['place_count'].iloc[0]
        # Year range
        if pd.notnull(info['min_year']) and pd.notnull(info['max_year']):
            years = f"{int(info['min_year'])}–{int(info['max_year'])}"
        else:
            years = ""
        # --- Build SQL filter for the table ---
        where_clauses = [f"c.dhlabid IN ({','.join(['?'] * len(books))})"]
        params = list(books)
        if filter_data and filter_data.get('column') and filter_data.get('value') is not None:
            col = filter_data['column']
            val = filter_data['value']
            if col == 'year':
                where_clauses.append("c.year <= ?")
                params.append(val)
            elif col == 'placename_count':
                # placename_count is a subquery, so filter after fetch
                pass
            elif col in ['title', 'author', 'category']:
                where_clauses.append(f"LOWER(c.{col}) LIKE ?")
                params.append(f"%{str(val).lower()}%")
        where_sql = ' AND '.join(where_clauses)
        table_query = f'''
        SELECT c.title, c.author, c.category, c.year, c.urn,
               (SELECT COUNT(DISTINCT b.token) FROM books b WHERE b.dhlabid = c.dhlabid) as placename_count
        FROM corpus c
        WHERE {where_sql}
        ORDER BY c.year DESC, c.title
        LIMIT 100
        '''
        df = pd.read_sql_query(table_query, conn, params=tuple(params))
        # placename_count filter (must be applied after fetch)
        if filter_data and filter_data.get('column') == 'placename_count' and filter_data.get('value') is not None:
            val = filter_data['value']
            df = df[df['placename_count'] <= val]
        if df.empty:
            table_section = html.Div("No books found in corpus.", style={'color': '#666'})
        else:
            # Wrap DataTable in a div to move horizontal scrollbar to the top
            table_section = html.Div([
                dash_table.DataTable(
                    columns=[
                        {"name": "Title", "id": "title", "presentation": "markdown"},
                        {"name": "Author", "id": "author"},
                        {"name": "≡", "id": "category"},
                        {"name": "📅\ufe0e", "id": "year"},
                        {"name": "◆", "id": "placename_count"}
                    ],
                    data=[{
                        **row.to_dict(),
                        "title": f"[ {(row['title'] or '')[:20] + ('…' if row['title'] and len(row['title']) > 20 else '')} ](https://www.nb.no/items/{row['urn']})",
                        "author": (row['author'] or '')[:20] + ('…' if row['author'] and len(row['author']) > 20 else ''),
                        "_title_full": row['title'] or '',
                        "_author_full": row['author'] or ''
                    } for _, row in df.iterrows()],
                    tooltip_data=[
                        {"title": {"value": row['title'] or '', "type": "markdown"}, "author": {"value": row['author'] or '', "type": "markdown"}} for _, row in df.iterrows()
                    ],
                    style_header={
                        'backgroundColor': '#f8fafc',
                        'color': '#4B6CB7',
                        'fontWeight': '500',
                        'fontSize': '0.85rem',
                        'borderBottom': '1px solid #e5e7eb',
                    },
                    style_table={
                        "maxHeight": "350px",
                        "overflowY": "auto",
                        "overflowX": "hidden",
                        "minWidth": "100%"
                    },
                    style_cell={
                        "fontSize": "0.75rem",
                        "padding": "2px 4px",
                        "whiteSpace": "pre-line",
                        "overflow": "hidden",
                        "textOverflow": "ellipsis",
                        "maxWidth": "90px",
                        "minWidth": "40px",
                        "wordBreak": "break-word"
                    },
                    style_cell_conditional=[
                        {"if": {"column_id": "title"}, "maxWidth": "110px", "minWidth": "60px"},
                        {"if": {"column_id": "author"}, "maxWidth": "80px", "minWidth": "40px"},
                        {"if": {"column_id": "category"}, "maxWidth": "60px", "minWidth": "40px", "textAlign": "center"},
                        {"if": {"column_id": "year"}, "maxWidth": "36px", "minWidth": "26px", "textAlign": "center"},
                        {"if": {"column_id": "placename_count"}, "maxWidth": "36px", "minWidth": "26px", "textAlign": "center"}
                    ],
                    style_data_conditional=[
                        {"if": {"row_index": "odd"}, "backgroundColor": "#f6f6f6"}
                    ],
                    markdown_options={"link_target": "_blank"},
                    page_action="none",
                    fixed_rows={"headers": True},
                    sort_action="native",
                    fill_width=True,
                    id="corpus-browse-datatable",
                    tooltip_duration=None
                )
            ], style={
                "width": "100%"
            })
        return (
            f"{info['book_count']:,}",
            f"{info['author_count']:,}",
            f"{place_count:,}",
            years,
            table_section
        )
    except Exception as e:
        print(f"Error in update_corpus_info_and_table: {e}")
        return "0", "0", "0", "", html.Div("Error displaying corpus table.", style={'color': 'red'})
    finally:
        conn.close()



@app.callback(
    Output('corpus-download-unique', 'data'),
    [Input('corpus-download-btn-unique', 'n_clicks')],
    [State('current-dhlabids-store', 'data')],
    prevent_initial_call=True
)
def download_corpus_excel(n_clicks, dhlabids):
    if not n_clicks or not dhlabids:
        raise dash.exceptions.PreventUpdate
    print(f"Download triggered, first 5 dhlabids: {dhlabids[:5]}")
    import pandas as pd
    import io
    conn = get_db_connection()
    try:
        # Fetch metadata for current corpus
        query = f'''
        SELECT dhlabid, title, author, year, category, urn
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(dhlabids))})
        '''
        df = pd.read_sql_query(query, conn, params=tuple(dhlabids))
        if df.empty:
            raise dash.exceptions.PreventUpdate
        # Add URL column
        df['url'] = df['urn'].apply(lambda urn: f"https://www.nb.no/items/{urn}" if pd.notnull(urn) else '')
        # Reorder columns
        df = df[['dhlabid', 'title', 'author', 'year', 'category', 'url']]
        # Write to Excel in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Corpus')
        output.seek(0)
        return dcc.send_bytes(lambda buf: buf.write(output.getvalue()), filename='imagination_corpus.xlsx')
    except Exception as e:
        print(f"Download error: {e}")
        raise
    finally:
        conn.close()

def get_all_places_for_corpus(book_ids):
    """Return all valid places for a list of book IDs (no sampling, no limit)."""
    import pandas as pd
    if not book_ids:
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
    conn = get_db_connection()
    try:
        query = f'''
        SELECT 
            b.token,
            p.modern as name,
            p.latitude,
            p.longitude,
            SUM(b.book_count) as frequency,
            COUNT(DISTINCT b.dhlabid) as book_count
        FROM books b
        JOIN places p ON b.token = p.token
        WHERE b.dhlabid IN ({','.join(['?'] * len(book_ids))})
          AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
          AND p.latitude != '0' AND p.longitude != '0'
        GROUP BY b.token, p.modern, p.latitude, p.longitude
        '''
        df = pd.read_sql_query(query, conn, params=tuple(book_ids))
        df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
        df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
        return df
    finally:
        conn.close()

def sample_places(places_df, n=2000):
    """Return a random sample of n places from a DataFrame."""
    import pandas as pd
    if places_df is None or places_df.empty:
        return places_df
    n = min(n, len(places_df))
    return places_df.sample(n=n, random_state=None).reset_index(drop=True)

@app.callback(
    Output('all-places-store', 'data'),
    [Input('current-dhlabids-store', 'data'),
     Input('upload-state', 'data'),
     Input('reset-corpus-btn-main', 'n_clicks')],
    [State('all-places-store', 'data')],
    prevent_initial_call=True
)
def update_all_places_store(book_ids, upload_state, reset_n_clicks, current_data):
    import pandas as pd
    import io
    if not book_ids:
        return pd.DataFrame().to_json(date_format='iso', orient='split')
    df = get_all_places_for_corpus(book_ids)
    return df.to_json(date_format='iso', orient='split')

@app.callback(
    Output('filtered-data', 'data', allow_duplicate=True),
    [Input('all-places-store', 'data'),
     Input('current-filters', 'data'),
     Input('resample-places', 'n_clicks')],
    [State('filtered-data', 'data')],
    prevent_initial_call=True
)
def update_filtered_data_auto_resample(all_places_json, filters, resample_clicks, prev_filtered_data):
    import pandas as pd
    import io
    ctx = dash.callback_context
    if not all_places_json:
        return pd.DataFrame().to_json(date_format='iso', orient='split')
    all_places_df = pd.read_json(io.StringIO(all_places_json), orient='split')
    n = filters.get('max_places', 2000) if filters else 2000
    # Always resample on any change
    sampled_df = sample_places(all_places_df, n=n)
    return sampled_df.to_json(date_format='iso', orient='split')

# Run Server
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8065, dev_tools_hot_reload=False)

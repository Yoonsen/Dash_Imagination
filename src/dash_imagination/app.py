import dash
from dash import dcc, html, Input, Output, State, callback
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
import sqlite3
import os

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
    """Get places data filtered by user selections"""
    conn = get_db_connection()
    
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
    JOIN 
        corpus c ON bp.dhlabid = c.dhlabid
    """
    
    where_clauses = []
    params = []
    
    if filters:
        if 'year_range' in filters and filters['year_range']:
            where_clauses.append("c.year BETWEEN ? AND ?")
            params.extend([filters['year_range'][0], filters['year_range'][1]])
        
        if 'categories' in filters and filters['categories']:
            placeholders = ','.join(['?'] * len(filters['categories']))
            where_clauses.append(f"c.category IN ({placeholders})")
            params.extend(filters['categories'])
        
        if 'authors' in filters and filters['authors']:
            placeholders = ','.join(['?'] * len(filters['authors']))
            where_clauses.append(f"c.author IN ({placeholders})")
            params.extend(filters['authors'])
            
        if 'titles' in filters and filters['titles']:
            # Extract just the title part without the year
            title_only = [t.split(' (')[0] for t in filters['titles']]
            placeholders = ','.join(['?'] * len(title_only))
            where_clauses.append(f"c.title IN ({placeholders})")
            params.extend(title_only)
    
    # Add WHERE clause if we have any filters
    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)
    
    # Add grouping and limit
    base_query += """
    GROUP BY p.token, p.modern, p.latitude, p.longitude
    ORDER BY frequency DESC
    LIMIT ?
    """
    
    # Add the limit parameter (default to 200 if not specified)
    max_places = filters.get('max_places', 200) if filters else 200
    params.append(max_places)
    
    try:
        df = pdquery(conn, base_query, tuple(params))
        conn.close()
        return df
    except Exception as e:
        print(f"Error querying database: {e}")
        conn.close()
        # Return empty DataFrame with correct columns
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])

def get_place_details(token):
    """Get details for a specific place including books where it appears"""
    conn = get_db_connection()
    
    # Query to get books containing this place
    query = """
    SELECT c.title, c.author, c.year, c.urn, bp.frequency
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

# Initialize the app with proper routing configuration
if is_production:
    app = dash.Dash(
        __name__,  
        routes_pathname_prefix='/imagination_map/', 
        requests_pathname_prefix="/run/imagination_map/",
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ]
    )
else:
    # For local development
    app = dash.Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ]
    )

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
        ], style={'padding': '15px', 'borderBottom': '1px solid #eee'}),
        
        # Accordion sections for filters
        dbc.Accordion([
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
                    marks={i: str(i) for i in [50, 200, 350, 500]},
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

    # Add a hidden div to store the current position
    html.Div(id='summary-position', style={'display': 'none'}),
    
    # Store components for maintaining state
    dcc.Store(id='filtered-data'),
    dcc.Store(id='selected-place'),
    dcc.Store(id='map-view-state'),
    dcc.Store(id='current-filters'),
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
     Input('max-places-slider', 'value')]
)
def update_filters(years, categories, authors, titles, max_places):
    return {
        'year_range': years,
        'categories': categories,
        'authors': authors,
        'titles': titles,
        'max_places': max_places
    }

# Callback to update the map with filtered data
@callback(
    [Output('main-map', 'figure'),
     Output('filtered-data', 'data')],
    [Input('current-filters', 'data'),
     Input('map-style', 'value'),
     Input('marker-size-slider', 'value'),
     Input('view-toggle', 'value'),
     Input('heatmap-intensity', 'value'),
     Input('heatmap-radius', 'value')]
)
def update_map(filters, map_style, marker_size, view_type, 
              heatmap_intensity, heatmap_radius):
    # Get data based on filters
    try:
        places_df = get_places_for_map(filters)
    except Exception as e:
        print(f"Error retrieving places: {e}")
        places_df = pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
    
    # If we have no data, show an empty map
    if places_df.empty:
        fig = go.Figure()
        fig.update_layout(
            mapbox=dict(
                style=map_style,
                center=dict(lat=60.5, lon=9.0),  # Center on Norway
                zoom=5
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        return fig, places_df.to_json(date_format='iso', orient='split')
    
    # Set base figure properties
    fig = go.Figure()
    
    # Base map configuration
    fig.update_layout(
        mapbox=dict(
            style=map_style,
            center=dict(lat=60.5, lon=9.0),  # Center on Norway
            zoom=5
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        showlegend=False,
        uirevision='constant'  # Preserves zoom on updates
    )
    
    # Add data based on view type
    if view_type == 'map':
        # Calculate marker sizes based on frequency
        sizes = places_df['frequency'].copy()
        min_freq, max_freq = sizes.min(), sizes.max()
        
        # Normalize sizes to range from 5 to 20, then scale by marker_size
        if min_freq != max_freq:
            normalized_sizes = 5 + (sizes - min_freq) / (max_freq - min_freq) * 15
            sizes = normalized_sizes * (marker_size / 3)
        else:
            sizes = [10 * (marker_size / 3)] * len(sizes)
        
        # Add markers
        # Add markers
        fig.add_trace(go.Scattermapbox(
            lat=places_df['latitude'],
            lon=places_df['longitude'],
            mode='markers',
            marker=dict(
                size=sizes,
                color='#4285F4',  # Google Maps blue
                opacity=0.7,
                sizemode='diameter'
            ),
            text=places_df.apply(
                lambda row: f"{row['token']} ({row['name']})<br>{int(row['frequency'])} mentions in {int(row['book_count'])} books", 
                axis=1
            ),
            hoverinfo='text',
            customdata=places_df['token'],  # Store token for use in click callback
            name='Places'
        ))
    else:  # Heatmap view
        # Add heatmap layer
        fig.add_trace(go.Densitymapbox(
            lat=places_df['latitude'],
            lon=places_df['longitude'],
            z=places_df['frequency'],
            radius=heatmap_radius,
            colorscale='Viridis',
            zmin=0,
            zmax=places_df['frequency'].max() * (heatmap_intensity / 3),
            opacity=0.8,
            hoverinfo='none'
        ))
    
    # Store filtered data as JSON
    filtered_data = places_df.to_json(date_format='iso', orient='split')
    
    return fig, filtered_data

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
     Output('place-summary', 'children'),
     Output('selected-place', 'data')],
    [Input('main-map', 'clickData')],
    [State('place-summary-container', 'style'),
     State('filtered-data', 'data')]
)
def update_place_summary(click_data, current_style, filtered_data_json):
    if click_data is None or not filtered_data_json:
        return dash.no_update, dash.no_update, dash.no_update
    
    try:
        # Get the clicked point's data
        point = click_data['points'][0]
        
        # For scatter mapbox, we can access the custom data
        if 'customdata' in point:
            token = point['customdata']
        else:
            # If it's a densitymapbox (heatmap), we can't get the exact point
            # Return a generic message
            new_style = dict(current_style)
            new_style['display'] = 'block'
            return new_style, html.Div([
                html.P("Click on individual markers in map view to see place details.")
            ]), None
        
        # Get the data for the clicked place from filtered data
        places_df = pd.read_json(filtered_data_json, orient='split')
        place = places_df[places_df['token'] == token].iloc[0]
        
        # Get books related to this place
        books_df = get_place_details(token)
        
        # Create the place summary
        summary = html.Div([
            # Place info
            html.Div([
                html.H5(place['token'], style={'marginBottom': '5px'}),
                html.P(f"Modern name: {place['name']}", style={'fontSize': '14px', 'color': '#666'}),
                html.P([
                    f"Appears in {int(place['book_count'])} books with ",
                    html.Strong(f"{int(place['frequency'])} total mentions")
                ]),
                html.Hr(style={'margin': '10px 0'})
            ]),
            
            # Books section
            html.Div([
                html.H6(f"Books mentioning this place:", style={'marginBottom': '10px'}),
                html.Div([
                    html.Div([
                        html.Div(f"{row['title']} ({row['year']})", style={'fontWeight': '500'}),
                        html.Div([
                            html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                            html.Span(f" • {row['frequency']} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                        ], style={'display': 'flex', 'justifyContent': 'space-between'}),
                        html.Div([
                            html.A(
                                "View at National Library", 
                                href=f"https://nb.no/items/{row['urn']}?searchText=\"{token}\"",
                                target="_blank",
                                style={'fontSize': '13px', 'color': '#4285F4'}
                            ) if row['urn'] else ""
                        ])
                    ], className='book-item')
                    for _, row in books_df.iterrows()
                ])
            ])
        ])
        
        # Update the style to make visible
        new_style = dict(current_style)
        new_style['display'] = 'block'
        
        # Store the selected place info
        selected_place = {
            'token': place['token'],
            'name': place['name'],
            'latitude': float(place['latitude']),
            'longitude': float(place['longitude']),
            'frequency': int(place['frequency']),
            'book_count': int(place['book_count'])
        }
        
        return new_style, summary, selected_place
    except Exception as e:
        print(f"Error updating place summary: {e}")
        return dash.no_update, dash.no_update, dash.no_update

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
    app.run_server(debug=True, host='0.0.0.0', port=8055)
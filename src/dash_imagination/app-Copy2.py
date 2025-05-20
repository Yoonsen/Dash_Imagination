import dash
from dash import dcc, html, Input, Output, State, callback
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
import sqlite3
import os
import folium
from folium.plugins import HeatMap, MarkerCluster  # Corrected import
import base64
import io
from dash.exceptions import PreventUpdate

# Database Connection & Queries
def get_db_connection():
    db_path = "/mnt/disk1/Github/Dash_Imagination/src/dash_imagination/data/imagination.db"
    print(f"Connecting to database at: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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

def get_places_for_map(filters=None):
    conn = get_db_connection()
    sample_size = filters.get('sample_size', 50) if filters else 50
    max_places = filters.get('max_places', 1500) if filters else 1500

    if filters and 'uploaded_corpus' in filters and filters['uploaded_corpus']:
        dhlabids = filters['uploaded_corpus']
        print(f"Using uploaded corpus with {len(dhlabids)} dhlabids")
        book_sample_query = f"""
        SELECT dhlabid
        FROM (SELECT DISTINCT dhlabid FROM book_places WHERE dhlabid IN ({','.join(['?'] * len(dhlabids))}))
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
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])

    sampled_dhlabids = sampled_books['dhlabid'].tolist()
    print(f"Sampled dhlabids: {len(sampled_dhlabids)} - {sampled_dhlabids[:5]}...")

    base_query = """
    SELECT p.token, p.modern as name, p.latitude, p.longitude, SUM(bp.frequency) as frequency,
           COUNT(DISTINCT bp.dhlabid) as book_count
    FROM places p
    JOIN book_places bp ON p.token = bp.token
    WHERE bp.dhlabid IN ({})
    GROUP BY p.token, p.modern, p.latitude, p.longitude
    ORDER BY frequency DESC
    LIMIT ?
    """.format(','.join(['?'] * len(sampled_dhlabids)))
    df = pd.read_sql_query(base_query, conn, params=tuple(sampled_dhlabids) + (max_places,))
    print(f"Sampled {len(sampled_dhlabids)} books, got {len(df)} places")
    conn.close()
    return df

def get_place_details(token, filters=None):
    conn = get_db_connection()
    query = """
    SELECT DISTINCT c.title, c.author, c.year, c.urn, bp.frequency
    FROM corpus c
    JOIN book_places bp ON c.dhlabid = bp.dhlabid
    WHERE bp.token = ?
    """
    params = [token]
    conditions = []
    if filters:
        if 'uploaded_corpus' in filters and filters['uploaded_corpus']:
            dhlabids = filters['uploaded_corpus']
            conditions.append(f"c.dhlabid IN ({','.join(['?'] * len(dhlabids))})")
            params.extend(dhlabids)
        if 'year_range' in filters and filters['year_range']:
            year_min, year_max = filters['year_range']
            conditions.append("c.year BETWEEN ? AND ?")
            params.extend([year_min, year_max])
        if 'categories' in filters and filters['categories']:
            categories = filters['categories']
            conditions.append(f"c.category IN ({','.join(['?'] * len(categories))})")
            params.extend(categories)
        if 'authors' in filters and filters['authors']:
            authors = filters['authors']
            conditions.append(f"c.author IN ({','.join(['?'] * len(authors))})")
            params.extend(authors)
        if 'titles' in filters and filters['titles']:
            titles = [title.split(' (')[0] for title in filters['titles']]
            conditions.append(f"c.title IN ({','.join(['?'] * len(titles))})")
            params.extend(titles)
    if conditions:
        query += " AND " + " AND ".join(conditions)
    query += " ORDER BY bp.frequency DESC LIMIT 20"
    books = pdquery(conn, query, tuple(params))
    conn.close()
    return books

# Initialize Dash App
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
    ]
)

default_filters = {
    'year_range': [1850, 1880],
    'categories': [],
    'authors': [],
    'titles': [],
    'max_places': 1500,
    'sample_size': 50
}

try:
    authors_list = get_authors()
    categories_list = get_categories()
    titles_list = get_titles()
except Exception as e:
    print(f"Error loading filter options: {e}")
    authors_list = ["Ibsen", "Bjørnson", "Collett", "Lie", "Kielland"]
    categories_list = ["Fiksjon", "Sakprosa", "Poesi", "Drama"]
    titles_list = ["Et dukkehjem (1879)", "Synnøve Solbakken (1857)", "Amtmandens Døttre (1854)"]

# App Layout with Folium Map
app.layout = html.Div([
    html.Div([
        html.Iframe(
            id='main-map',
            srcDoc="",
            style={'width': '100%', 'height': '100vh', 'position': 'absolute', 'top': 0, 'left': 0}
        ),
    ], style={'position': 'relative'}),
    
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
    
    html.Div([
        html.Button(
            html.I(className="fa fa-bars"),
            id='sidebar-toggle',
            style={
                'background': 'white',
                'border': 'none',
                'borderRadius': '50%',
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
    
    html.Div([
        html.Div([
            html.H3("Layers & Filters", style={'margin': '0', 'fontWeight': '400'})
        ], style={'padding': '15px', 'borderBottom': '1px solid #eee', 'marginTop': '50px'}),
        dbc.Accordion([
            dbc.AccordionItem([
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
                    html.Div(id='upload-status', style={'fontSize': '13px', 'marginBottom': '15px'}),
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
            dbc.AccordionItem([
                html.Label("Sample Size"),
                dcc.Dropdown(
                    id='sample-size',
                    options=[{'label': f"{n} Books", 'value': n} for n in [10, 50, 100, 500]],
                    value=default_filters['sample_size'],
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
                    value=default_filters['max_places'],
                    step=50,
                    marks={i: str(i) for i in [50, 200, 350, 500, 1000]},
                    className='mb-4'
                ),
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
            dbc.AccordionItem([
                html.Label("Period"),
                dcc.RangeSlider(
                    id='year-slider',
                    min=1814,
                    max=1905,
                    value=default_filters['year_range'],
                    marks={i: str(i) for i in range(1814, 1906, 20)},
                    className='mb-4'
                ),
                html.Label("Category"),
                dcc.Dropdown(
                    id='category-dropdown',
                    options=[{'label': cat, 'value': cat} for cat in categories_list],
                    value=default_filters['categories'],
                    multi=True,
                    placeholder="Select categories...",
                    className='mb-3'
                ),
                html.Label("Author"),
                dcc.Dropdown(
                    id='author-dropdown',
                    options=[{'label': author, 'value': author} for author in authors_list],
                    value=default_filters['authors'],
                    multi=True,
                    placeholder="Select authors...",
                    className='mb-3'
                ),
                html.Label("Work"),
                dcc.Dropdown(
                    id='title-dropdown',
                    options=[{'label': title, 'value': title} for title in titles_list],
                    value=default_filters['titles'],
                    multi=True,
                    placeholder="Select works...",
                    className='mb-3'
                ),
            ], title="Corpus Filters", className="sidebar-section"),
            dbc.AccordionItem([
                dbc.RadioItems(
                    id='map-style',
                    options=[
                        {'label': 'Street', 'value': 'OpenStreetMap'},
                        {'label': 'Light', 'value': 'CartoDB Positron'},
                        {'label': 'Dark', 'value': 'CartoDB DarkMatter'},
                        {'label': 'Satellite', 'value': 'Stamen Terrain'}
                    ],
                    value='CartoDB Positron',
                    inline=False,
                    labelStyle={'display': 'block', 'margin': '8px 0'}
                ),
            ], title="Base Map", className="sidebar-section"),
        ], id="sidebar-accordion", start_collapsed=True),
        html.Div(id='corpus-stats', style={'padding': '15px', 'borderTop': '1px solid #eee', 'fontSize': '14px'})
    ], id='sidebar', style={
        'position': 'absolute',
        'top': 0,
        'left': 0,
        'width': '0',
        'height': '100vh',
        'backgroundColor': 'white',
        'boxShadow': '2px 0 4px rgba(0,0,0,0.2)',
        'zIndex': 900,
        'overflowY': 'auto',
        'overflowX': 'hidden',
        'transition': 'width 0.3s ease'
    }),
    
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
    html.Div(id='reset-status', style={'display': 'none'}),
    dcc.Store(id='filtered-data'),
    dcc.Store(id='selected-place'),
    dcc.Store(id='map-view-state', data={'zoom': 5}),
    dcc.Store(id='current-filters', data=default_filters),
    dcc.Store(id='upload-state', data=None),
    dcc.Store(id='map-click-data', data=None),  # Added here
])

# Callbacks
@app.callback(
    [Output('upload-status', 'children'),
     Output('upload-state', 'data'),
     Output('current-filters', 'data')],
    [Input('upload-corpus', 'contents'),
     Input('year-slider', 'value'),
     Input('category-dropdown', 'value'),
     Input('author-dropdown', 'value'),
     Input('title-dropdown', 'value'),
     Input('max-places-slider', 'value'),
     Input('sample-size', 'value'),
     Input('reset-corpus', 'n_clicks')],
    [State('upload-corpus', 'filename'),
     State('upload-corpus', 'last_modified'),
     State('current-filters', 'data')]
)
def update_state_and_filters(contents, years, categories, authors, titles, max_places, sample_size, reset_clicks, filename, date, current_filters):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    print(f"!!! Combined callback triggered by: {triggered_id} !!!")
    
    if not current_filters:
        current_filters = default_filters.copy()
    
    if triggered_id == 'reset-corpus' and reset_clicks:
        print("Resetting to default corpus...")
        return html.Div([
            html.I(className="fas fa-info-circle", style={'color': 'blue', 'marginRight': '8px'}),
            'Reset to default corpus.'
        ]), None, current_filters  # Reset upload-state to None
    
    if triggered_id == 'upload-corpus':
        print("Processing upload...")
        if contents is None:
            return html.Div("Upload a corpus file to begin"), None, current_filters
        try:
            content_type, content_string = contents.split(',')
            decoded = base64.b64decode(content_string)
            if filename.endswith('.csv'):
                uploaded_df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
            elif filename.endswith('.xlsx'):
                uploaded_df = pd.read_excel(io.BytesIO(decoded))
            else:
                return html.Div(['Unsupported file type.'], style={'color': 'red'}), None, current_filters
            id_column = 'dhlabid' if 'dhlabid' in uploaded_df.columns else 'urn'
            if id_column == 'urn':
                conn = get_db_connection()
                urns = uploaded_df['urn'].tolist()
                urn_query = f"SELECT dhlabid, urn FROM corpus WHERE urn IN ({','.join(['?'] * len(urns))})"
                urn_mapping = pd.read_sql_query(urn_query, conn, params=tuple(urns))
                conn.close()
                uploaded_df = uploaded_df.merge(urn_mapping, on='urn', how='inner')
            dhlabids = uploaded_df['dhlabid'].tolist()
            current_filters['uploaded_corpus'] = dhlabids
            filtered_corpus_json = uploaded_df.to_json(date_format='iso', orient='split')
            print(f"Uploaded {len(dhlabids)} dhlabids: {dhlabids[:5]}...")
            status = html.Div([html.I(className="fas fa-check-circle", style={'color': 'green', 'marginRight': '8px'}),
                               f'Uploaded {filename} with {len(dhlabids)} books.'])
            print(f"Returning status: {status}")
            return status, filtered_corpus_json, current_filters
        except Exception as e:
            print(f"Upload error: {e}")
            return html.Div(['Error processing file.'], style={'color': 'red'}), None, current_filters
    
    current_filters.update({
        'year_range': years if years else current_filters['year_range'],
        'categories': categories or [],
        'authors': authors or [],
        'titles': titles or [],
        'max_places': max_places if max_places else current_filters['max_places'],
        'sample_size': sample_size if sample_size else current_filters['sample_size']
    })
    print(f"Updated filters from UI: {current_filters}")
    return dash.no_update, dash.no_update, current_filters

# @app.callback(
#     Output('upload-status', 'children'),
#     [Input('reset-corpus', 'n_clicks')],
#     prevent_initial_call=True
# )
# def update_reset_status(n_clicks):
#     if n_clicks is None:
#         raise PreventUpdate
#     return html.Div([
#         html.I(className="fas fa-info-circle", style={'color': 'blue', 'marginRight': '8px'}),
#         'Reset to default corpus.'
#     ])

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

# Callback to toggle heatmap settings visibility
@app.callback(
    Output('heatmap-settings', 'style'),
    [Input('view-toggle', 'value')]
)
def toggle_heatmap_settings(view):
    if view == 'heatmap':
        return {'display': 'block'}
    return {'display': 'none'}

# Callback to update the Folium map
@app.callback(
    Output('main-map', 'srcDoc'),
    [Input('filtered-data', 'data'),
     Input('map-style', 'value'),
     Input('marker-size-slider', 'value'),
     Input('view-toggle', 'value'),
     Input('heatmap-intensity', 'value'),
     Input('heatmap-radius', 'value')]
)
def update_map(filtered_data_json, map_style, marker_size, view_type, heatmap_intensity, heatmap_radius):
    from folium import Map  # Added import inside callback
    print("!!! update_map TRIGGERED !!!")
    if filtered_data_json is None:
        print("No cached data available")
        m = Map(location=[60.5, 9.0], zoom_start=5, tiles=map_style, control_scale=True)
        return m._repr_html_()
    
    # Load cached data
    places_df = pd.read_json(io.StringIO(filtered_data_json), orient='split')
    print(f"Number of places from cache: {len(places_df)}")
    
    # Clean data
    places_df = places_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude', 'frequency'])
    print(f"Points after cleaning: {len(places_df)}")
    
    # Create Folium map
    m = Map(location=[60.5, 9.0], zoom_start=5, tiles=map_style, control_scale=True)
    
    if view_type == 'map':
        # Use MarkerCluster for clustering
        marker_cluster = MarkerCluster().add_to(m)
        for idx, row in places_df.iterrows():
            popup_text = f"{row['token']} ({row['name']})<br>{int(row['frequency'])} mentions in {int(row['book_count'])} books"
            marker = Marker(
                [row['latitude'], row['longitude']],
                popup=popup_text,
                tooltip=popup_text,
                icon=folium.Icon(color='blue', icon='info-sign')
            )
            # Add JavaScript to capture click and send token to Dash
            marker.add_child(folium.ClickForMarker(
                popup=popup_text,
                on_click=f"""
                function(e) {{
                    var token = "{row['token']}";
                    var text = "{popup_text}";
                    window.parent.postMessage({{
                        id: "map-click-data",
                        data: {{ token: token, text: text }}
                    }}, "*");
                }}
                """
            ))
            marker.add_to(marker_cluster)
    else:  # Heatmap
        HeatMap(
            data=places_df[['latitude', 'longitude', 'frequency']].values,
            radius=heatmap_radius * 10,
            blur=10,
            gradient={0.4: 'blue', 0.65: 'lime', 1: 'red'},
            min_opacity=0.5,
            max_opacity=0.8 * (heatmap_intensity / 10)
        ).add_to(m)
    
    # Add JavaScript to listen for messages and update Dash store
    js = """
    <script>
    window.addEventListener("message", function(event) {
        if (event.data.id === "map-click-data") {
            var store = document.getElementById("map-click-data");
            if (store) {
                store.value = JSON.stringify(event.data.data);
                store.dispatchEvent(new Event('change'));
            }
        }
    });
    </script>
    """
    return m._repr_html_() + js

# Callback to update place summary
@app.callback(
    [Output('place-summary-container', 'style'),
     Output('place-summary', 'children')],
    [Input('map-click-data', 'data')],
    [State('place-summary-container', 'style'),
     State('current-filters', 'data')]
)
def update_place_summary(click_data, current_style, filters):
    print("Place summary callback triggered")
    if click_data is None:
        print("No click data")
        return dash.no_update, dash.no_update
    
    try:
        token = click_data['token']
        text = click_data['text']
        parts = text.split('<br>')
        place_info = parts[0]
        if '(' in place_info and ')' in place_info:
            token_part = place_info.split('(')[0].strip()
            modern_part = place_info.split('(')[1].split(')')[0].strip()
        else:
            token_part = place_info
            modern_part = ""
        frequency = 0
        book_count = 0
        if len(parts) > 1 and 'mentions in' in parts[1]:
            mentions_part = parts[1].split('mentions in')
            try:
                frequency = int(mentions_part[0].strip())
                book_count = int(mentions_part[1].split('books')[0].strip())
            except ValueError:
                print("Could not parse frequency/book count")
        
        try:
            books_df = get_place_details(token, filters)
        except Exception as e:
            print(f"Error getting place details: {e}")
            books_df = pd.DataFrame(columns=['title', 'author', 'year', 'urn', 'frequency'])
        
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
                            html.Span(f" • {int(row['frequency'])} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                        ], style={'display': 'flex', 'justifyContent': 'space-between'}),
                        html.Div([
                            html.A("View at National Library", href=f"https://nb.no/items/{row['urn']}?searchText=\"{token}\"",
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

# Run Server
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=8065, dev_tools_hot_reload=False)
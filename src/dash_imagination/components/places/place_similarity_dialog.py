from dash import dcc, html, callback, no_update, callback_context
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from .word_similarity import WordSimilarityAPI
import pandas as pd
from dash_imagination.utils.db import get_db_connection
import dash

def create_place_similarity_dialog():
    """Create the place similarity dialog."""
    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-search me-2"),
                html.H5("Place Similarity", className="mb-0", style={"fontSize": "14px", "fontWeight": 500}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-similarity',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-info-subtle text-dark", id='similarity-header'),
        dbc.CardBody([
            # Input section
            html.Div([
                html.Label("Place Name", className="form-label"),
                dbc.InputGroup([
                    dcc.Input(
                        id='similar-place-input',
                        type='text',
                        placeholder='Enter a place name...',
                        className="form-control"
                    ),
                    dbc.Button(
                        html.I(className="fas fa-search"),
                        id='find-similar',
                        color="primary"
                    )
                ], className="mb-3"),
                html.Label("Similarity Threshold", className="form-label"),
                dcc.Slider(
                    id='similarity-threshold',
                    min=0,
                    max=1,
                    step=0.1,
                    value=0.7,
                    marks={i/10: f"{i/10:.1f}" for i in range(0, 11, 2)},
                    className="mb-3"
                ),
                html.Div([
                    html.Label("Max Places", className="form-label"),
                    dcc.Input(
                        id='max-places',
                        type='number',
                        min=1,
                        max=500,
                        value=100,
                        className="form-control"
                    )
                ], className="mb-3")
            ], className="mb-4"),
            
            # Results section
            html.Div([
                html.H5("Results", className="mb-3"),
                html.Div(id='similar-places-results', children=[
                    html.P("Enter a place name and click 'Find Similar Places' to see results", className="text-muted")
                ]),
                html.Div([
                    dbc.Button(
                        "Select All Places and Build Corpus",
                        color="primary",
                        className="w-100",
                        id="select-all-build-corpus-button"
                    ),
                    dbc.Spinner(
                        html.Div(id="select-all-loading"),
                        color="primary",
                        type="grow",
                        fullscreen=False,
                        spinner_style={"width": "1rem", "height": "1rem"}
                    )
                ], id="select-all-container", style={'display': 'none', 'marginBottom': '15px'})
            ])
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'})  # 56px is header height
    ], id='place-similarity-dialog', className="position-absolute", style={
        'width': '350px',
        'height': '500px',
        'zIndex': 800,
        'display': 'none',
        'top': '100px',  # Position below the top button container
        'left': '20px',   # Align with other containers
        'cursor': 'move'  # Add cursor style
    })

@callback(
    Output('place-similarity-dialog', 'style', allow_duplicate=True),
    [Input('close-similarity', 'n_clicks'),
     Input('find-similar-places', 'n_clicks')],
    [State('place-similarity-dialog', 'style')],
    prevent_initial_call=True
)
def toggle_similarity_dialog(n_clicks_close, n_clicks_show, current_style):
    ctx = callback_context
    if not ctx.triggered:
        return current_style
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id == 'close-similarity':
        return {'display': 'none'}
    elif trigger_id == 'find-similar-places':
        new_style = dict(current_style) if current_style else {}
        new_style['display'] = 'block'
        return new_style
    return current_style

@callback(
    Output('form-submit-trigger', 'children'),
    Input('similar-place-form', 'submit'),
    prevent_initial_call=True
)
def handle_form_submit(submit):
    if submit:
        return 'submitted'
    return no_update

@callback(
    [Output('similar-places-results', 'children'),
     Output('similar-places-results', 'style')],
    [Input('find-similar', 'n_clicks')],
    [State('similar-place-input', 'value'),
     State('similarity-threshold', 'value'),
     State('max-places', 'value')],
    prevent_initial_call=True
)
def handle_similar_places(n_clicks, search_word, threshold, max_places):
    if not n_clicks:
        return no_update, no_update
        
    if not search_word:
        return html.Div("Please enter a search term"), {'display': 'block'}
    
    conn = None
    try:
        # Get similar words from API with limit
        api = WordSimilarityAPI()
        similar_words = api.find_similar_words(search_word, collection_name="vss_1850_cos", limit=max_places)
        
        if not similar_words:
            return html.Div("No similar places found"), {'display': 'block'}
        
        # Filter similar words based on threshold
        filtered_words = [word for word, score in similar_words if score >= threshold]
        
        if not filtered_words:
            return html.Div("No places meet the similarity threshold"), {'display': 'block'}
        
        # Connect to database and get place information
        conn = get_db_connection()
        
        # Get place information in a single query with CTE
        query = """
        WITH valid_tokens AS (
            SELECT DISTINCT token 
            FROM books 
            WHERE token IN ({})
        )
        SELECT DISTINCT 
            p.token,
            p.modern as name,
            p.latitude,
            p.longitude,
            COUNT(DISTINCT b.dhlabid) as book_count,
            SUM(b.book_count) as frequency
        FROM places p
        JOIN books b ON p.token = b.token
        JOIN valid_tokens vt ON p.token = vt.token
        WHERE p.latitude IS NOT NULL 
        AND p.longitude IS NOT NULL
        AND p.latitude != '0'
        AND p.longitude != '0'
        GROUP BY p.token, p.modern, p.latitude, p.longitude
        ORDER BY frequency DESC
        LIMIT ?
        """.format(','.join(['?'] * len(filtered_words)))
        
        places_df = pd.read_sql_query(query, conn, params=tuple(filtered_words + [max_places]))
        
        if places_df.empty:
            return html.Div("No matching places found in the database"), {'display': 'block'}
        
        # Create hover text more efficiently
        places_df['hover_text'] = places_df.apply(
            lambda row: f"{row['token']} ({row['name']})<br>Mentions: {int(row['frequency'])}<br>Books: {int(row['book_count'])}",
            axis=1
        )
        
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
                            'cursor': 'pointer'
                        }, 
                        className='place-item', 
                        id={'type': 'place-item', 'index': row['token']},
                        **{'data-lat': row['latitude'], 'data-lon': row['longitude'], 'data-hover': row['hover_text']})
                        for _, row in places_df.iterrows()
                    ], style={
                        'maxHeight': '400px', 
                        'overflowY': 'auto'
                    })
                ], style={'border': '1px solid #eee', 'borderRadius': '4px'})
            ], style={'padding': '12px'})
        ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}), {'display': 'block'}
        
    except Exception as e:
        print(f"Error in handle_similar_places: {e}")
        return html.Div(f"Error: {str(e)}"), {'display': 'block'}
    finally:
        if conn:
            conn.close() 

@callback(
    Output('select-all-container', 'style'),
    Input('similar-places-results', 'children'),
    prevent_initial_call=True
)
def show_select_all_button(results):
    if results and not isinstance(results, str):
        return {'display': 'block', 'marginBottom': '15px'}
    return {'display': 'none'}

@callback(
    Output('current-filters', 'data', allow_duplicate=True),
    Input('select-all-build-corpus-button', 'n_clicks'),
    [State('similar-places-results', 'children')],
    prevent_initial_call=True
)
def build_corpus_from_places(n_clicks, results):
    if not n_clicks:
        return no_update
        
    # Extract place tokens from the results
    place_tokens = []
    if isinstance(results, dict) and 'props' in results:
        # Navigate through the nested structure to find place items
        def extract_tokens(element):
            if isinstance(element, dict):
                if 'props' in element:
                    props = element['props']
                    if 'id' in props and isinstance(props['id'], dict):
                        if 'type' in props['id'] and props['id']['type'] == 'place-item':
                            place_tokens.append(props['id']['index'])
                    if 'children' in props:
                        for child in props['children']:
                            extract_tokens(child)
            elif isinstance(element, list):
                for item in element:
                    extract_tokens(item)
        
        extract_tokens(results)
    
    if not place_tokens:
        return no_update
        
    # Get books for these places
    conn = get_db_connection()
    try:
        query = """
        SELECT DISTINCT dhlabid
        FROM books
        WHERE token IN ({})
        """.format(','.join(['?'] * len(place_tokens)))
        
        books_df = pd.read_sql_query(query, conn, params=tuple(place_tokens))
        book_ids = books_df['dhlabid'].tolist()
        
        # Create new filters
        new_filters = {
            'selected_tokens': place_tokens,
            'books': book_ids,
            'corpus_source': 'Similar Places'
        }
        
        return new_filters
    finally:
        conn.close() 
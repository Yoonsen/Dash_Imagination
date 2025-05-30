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
                html.H4("Find Similar Places", className="mb-0"),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-similarity',
                    className="btn-close"
                )
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-success text-white", id='similarity-header'),
        dbc.CardBody([
            # Input section
            html.Div([
                html.Label("Place Name", className="form-label"),
                dcc.Input(
                    id='similar-place-input',
                    type='text',
                    placeholder='Enter a place name...',
                    className="form-control mb-3"
                ),
                html.Label("Similarity Threshold", className="form-label"),
                dcc.Slider(
                    id='similarity-threshold',
                    min=0,
                    max=1,
                    step=0.1,
                    value=0.8,
                    marks={i/10: f"{i/10:.1f}" for i in range(0, 11, 2)},
                    className="mb-3"
                ),
                dbc.Button(
                    [
                        html.I(className="fas fa-search me-2"),
                        "Find Similar Places"
                    ],
                    id='find-similar',
                    color="primary",
                    className="w-100"
                )
            ], className="mb-4"),
            
            # Results section
            html.Div([
                html.H5("Results", className="mb-3"),
                html.Div(id='similar-places-results', children=[
                    html.P("Enter a place name and click 'Find Similar Places' to see results", className="text-muted")
                ])
            ])
        ])
    ], id='place-similarity-dialog', className="position-absolute", style={
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',
        'top': '100px',  # Position below the top button container
        'left': '20px'   # Align with other containers
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
    [Output('similar-places-results', 'children'),
     Output('similar-places-results', 'style')],
    [Input('find-similar', 'n_clicks'),
     Input('similar-place-input', 'value'),
     Input('similarity-threshold', 'value')],
    [State('similar-place-input', 'value')],
    prevent_initial_call=True
)
def handle_similar_places(n_clicks, search_word, threshold, current_value):
    if not search_word:
        return html.Div("Please enter a search term"), {'display': 'block'}
    
    conn = None
    try:
        # Get similar words from API with limit
        api = WordSimilarityAPI()
        similar_words = api.find_similar_words(search_word, limit=500)
        
        if not similar_words:
            return html.Div("No similar places found"), {'display': 'block'}
        
        # Filter similar words based on threshold
        filtered_words = [word for word, score in similar_words if score >= threshold]
        
        if not filtered_words:
            return html.Div("No places meet the similarity threshold"), {'display': 'block'}
        
        # Connect to database and get place information
        conn = get_db_connection()
        
        # Get valid tokens from the database
        valid_tokens = [word for word in filtered_words if word in pd.read_sql_query(
            "SELECT DISTINCT token FROM books", conn)['token'].tolist()]
        
        if not valid_tokens:
            return html.Div("No matching places found in the database"), {'display': 'block'}
        
        # Get place information
        query = """
        SELECT DISTINCT p.token, p.modern as name, p.latitude, p.longitude,
               COUNT(DISTINCT b.dhlabid) as book_count,
               SUM(b.book_count) as frequency
        FROM books b
        JOIN places p ON b.token = p.token
        WHERE b.token IN ({})
        GROUP BY p.token, p.modern, p.latitude, p.longitude
        LIMIT ?
        """.format(','.join(['?'] * len(valid_tokens)))
        
        places_df = pd.read_sql_query(query, conn, params=tuple(valid_tokens + [500]))
        
        # Create hover text
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
                    ], style={'maxHeight': '400px', 'overflowY': 'auto'})
                ], style={'border': '1px solid #eee', 'borderRadius': '4px'})
            ], style={'padding': '12px'})
        ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}), {'display': 'block'}
        
    except Exception as e:
        print(f"Error in handle_similar_places: {e}")
        return html.Div(f"Error: {str(e)}"), {'display': 'block'}
    finally:
        if conn:
            conn.close() 
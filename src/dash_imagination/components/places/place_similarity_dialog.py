from dash import html, dcc, Input, Output, State, callback, callback_context, ALL
import dash_bootstrap_components as dbc
from .word_similarity import WordSimilarityAPI
import pandas as pd
from dash.exceptions import PreventUpdate
from dash_imagination.utils.db import get_db_connection
from dash_imagination.utils.global_state import update_current_dhlabids
import io
import dash

def create_place_similarity_dialog():
    """Create the place similarity dialog (draggable, not modal, no spinner)."""
    return html.Div([
        html.Div([
            html.Div([
                html.I(className="fa fa-search", style={'marginRight': '8px'}),
                html.H4("Find Similar Places", style={'marginBottom': '0', 'fontWeight': '400', 'flex': '1'}),
                html.Button(
                    html.I(className="fa fa-times"),
                    id='close-similarity-dialog',
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
            }, id='similarity-header'),
            html.Div([
                dbc.InputGroup([
                    dbc.Input(
                        id="similar-place-search",
                        placeholder="Enter a word to find similar places...",
                        type="text",
                        className="form-control",
                        n_submit=0
                    ),
                    dbc.Button(
                        html.I(className="fas fa-search"),
                        id="similar-place-search-button",
                        color="primary",
                        className="ms-2"
                    )
                ], className="mb-3"),
                html.Div([
                    html.Div([
                        html.Label("Similarity Threshold", className="form-label"),
                        dcc.Slider(
                            id="similarity-threshold",
                            min=0.5,
                            max=1.0,
                            step=0.05,
                            value=0.7,
                            marks={i/10: f"{i/10:.1f}" for i in range(5, 11)},
                            className="mb-3"
                        )
                    ], style={'flex': '2', 'marginRight': '15px'}),
                    html.Div([
                        html.Label("Max Places", className="form-label"),
                        dbc.Input(
                            id="max-places-input",
                            type="number",
                            min=1,
                            max=500,
                            value=100,
                            className="form-control"
                        )
                    ], style={'flex': '1'})
                ], style={'display': 'flex', 'alignItems': 'flex-start', 'marginBottom': '15px'}),
                html.Div([
                    dbc.Button(
                        "Select All Places and Build Corpus",
                        color="primary",
                        className="w-100",
                        id="select-all-build-corpus-button"
                    )
                ], id="select-all-container", style={'display': 'block', 'marginBottom': '15px'}),
                html.Div(
                    id="similar-places-results-dialog",
                    className="similar-places-list"
                ),
                html.Div(
                    id="corpus-info-dialog",
                    className="mt-3",
                    style={'display': 'none'}
                ),
                html.Div(id="similar-places-loading-dialog"),
                dcc.Store(id="valid-place-tokens", data=[])
            ])
        ], style={
            'padding': '15px',
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'boxShadow': '0 4px 15px rgba(0,0,0,0.15)',
            'border': '1px solid rgba(0,0,0,0.05)'
        })
    ], id='place-similarity-dialog', style={
        'position': 'absolute',
        'top': '80px',
        'right': '20px',
        'width': '350px',
        'maxHeight': '500px',
        'overflowY': 'auto',
        'zIndex': 800,
        'display': 'none',
        'cursor': 'auto'
    })

# Callback to open the dialog
@callback(
    Output('place-similarity-dialog', 'style'),
    [Input('similar-places-button', 'n_clicks')],
    [State('place-similarity-dialog', 'style')]
)
def toggle_similarity_dialog(n_clicks, current_style):
    if n_clicks is None:
        raise PreventUpdate
    current_style = current_style or {}
    new_style = dict(current_style)
    new_style['display'] = 'block'
    return new_style

# Callback to close the dialog
@callback(
    Output('place-similarity-dialog', 'style', allow_duplicate=True),
    [Input('close-similarity-dialog', 'n_clicks')],
    [State('place-similarity-dialog', 'style')],
    prevent_initial_call=True
)
def close_similarity_dialog(n_clicks, current_style):
    if n_clicks is None:
        raise PreventUpdate
    current_style = current_style or {}
    new_style = dict(current_style)
    new_style['display'] = 'none'
    return new_style

@callback(
    [Output('select-all-build-corpus-button', 'disabled', allow_duplicate=True),
     Output('similar-places-results-dialog', 'children', allow_duplicate=True),
     Output('corpus-info-dialog', 'children', allow_duplicate=True),
     Output('corpus-info-dialog', 'style', allow_duplicate=True),
     Output('current-filters', 'data', allow_duplicate=True),
     Output('similar-places-loading-dialog', 'children', allow_duplicate=True),
     Output('corpus-controls-container', 'style', allow_duplicate=True),
     Output('current-dhlabids-store', 'data', allow_duplicate=True)],
    [Input('similar-place-search-button', 'n_clicks'),
     Input('similar-place-search', 'n_submit'),
     Input('similarity-threshold', 'value'),
     Input('max-places-input', 'value')],
    [State('similar-place-search', 'value'),
     State('filtered-data', 'data'),
     State('corpus-controls-container', 'style')],
    prevent_initial_call=True
)
def handle_similar_places(n_clicks, n_submit, threshold, max_places, search_word, filtered_data, corpus_style):
    if not search_word:
        return False, html.Div("Please enter a search term"), None, {'display': 'none'}, {}, "", dash.no_update, dash.no_update
    
    try:
        # Get similar words from API with limit
        api = WordSimilarityAPI()
        similar_words = api.find_similar_words(search_word, limit=max_places)
        
        if not similar_words:
            return False, html.Div("No similar words found"), None, {'display': 'none'}, {}, "", dash.no_update, dash.no_update
        
        # Get places from the database that match our valid tokens
        conn = get_db_connection()
        try:
            # Filter by similarity threshold
            valid_tokens = [word for word, score in similar_words if score >= threshold]
            
            if not valid_tokens:
                return False, html.Div("No places found above threshold"), None, {'display': 'none'}, {}, "", dash.no_update, dash.no_update
            
            # Get place details for the valid tokens
            query = f"""
            SELECT 
                p.token,
                p.modern as name,
                p.latitude,
                p.longitude,
                COUNT(DISTINCT b.dhlabid) as book_count,
                COUNT(b.dhlabid) as frequency
            FROM places p
            JOIN books b ON p.token = b.token
            WHERE p.token IN ({','.join(['?'] * len(valid_tokens))})
            GROUP BY p.token, p.modern, p.latitude, p.longitude
            ORDER BY frequency DESC
            LIMIT ?
            """
            
            places_df = pd.read_sql_query(query, conn, params=tuple(valid_tokens + [max_places]))
            
            # Get corpus information and dhlabids
            corpus_query = f"""
            SELECT 
                COUNT(DISTINCT c.dhlabid) as total_books,
                COUNT(DISTINCT c.author) as total_authors,
                MIN(c.year) as min_year,
                MAX(c.year) as max_year,
                GROUP_CONCAT(DISTINCT c.dhlabid) as dhlabids
            FROM corpus c
            JOIN books b ON c.dhlabid = b.dhlabid
            WHERE b.token IN ({','.join(['?'] * len(valid_tokens))})
            """
            
            corpus_info = pd.read_sql_query(corpus_query, conn, params=tuple(valid_tokens)).iloc[0]
            
            # Get dhlabids for the store
            dhlabids = []
            if corpus_info['dhlabids']:
                dhlabids = [int(x) for x in corpus_info['dhlabids'].split(',')]
            
            # Create place list items
            place_items = []
            for _, row in places_df.iterrows():
                place_items.append(
                    html.Div([
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
                        'cursor': 'pointer'
                    }, className='similar-place-item', id={'type': 'similar-place-item', 'index': row['token']})
                )
            
            # Create results container
            results = html.Div([
                html.Div([
                    html.Div(f"Found {len(places_df)} similar places", 
                             style={'marginBottom': '8px', 'fontSize': '0.9rem', 'color': '#666'}),
                    html.Div(place_items, style={'maxHeight': '400px', 'overflowY': 'auto'})
                ], style={'padding': '12px'})
            ], style={'backgroundColor': 'white', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'})
            
            # Create corpus info display
            corpus_info_display = html.Div([
                html.H5("Corpus Information", className="mt-3"),
                html.P(f"Total books: {corpus_info['total_books']:,}"),
                html.P(f"Total authors: {corpus_info['total_authors']:,}"),
                html.P(f"Time period: {int(corpus_info['min_year'])}–{int(corpus_info['max_year'])}")
            ])
            
            # Update filters with selected tokens
            new_filters = {'selected_tokens': valid_tokens}
            
            return False, results, corpus_info_display, {'display': 'block'}, new_filters, "", dash.no_update, dhlabids
            
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Error in handle_similar_places: {e}")
        return False, html.Div(f"Error: {str(e)}"), None, {'display': 'none'}, {}, "", dash.no_update, dash.no_update 
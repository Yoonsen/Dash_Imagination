from dash import html, dcc, Input, Output, State, callback, callback_context, ALL
import dash_bootstrap_components as dbc
from .word_similarity import WordSimilarityAPI
import pandas as pd
from dash.exceptions import PreventUpdate
from dash_imagination.utils.db import get_db_connection
import io  # Add this import
import dash

def create_place_similarity_controls():
    """Create the place similarity search interface."""
    return html.Div([
        html.H5("Find Similar Places", className="mb-3"),
        
        # Search input with return key trigger
        dbc.InputGroup([
            dbc.Input(
                id="similar-place-search",
                placeholder="Enter a word to find similar places...",
                type="text",
                className="form-control",
                n_submit=0  # Add this to track return key presses
            ),
            dbc.Button(
                html.I(className="fas fa-search"),
                id="similar-place-search-button",
                color="primary",
                className="ms-2"
            )
        ], className="mb-3"),
        
        # Similarity threshold slider and size input in a row
        html.Div([
            # Left side: Similarity threshold
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
            
            # Right side: Size input
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
        
        # Select All button
        html.Div(
            dbc.Button(
                "Select All Places and Build Corpus",
                color="primary",
                className="w-100",
                id="select-all-build-corpus-button"
            ),
            id="select-all-container",
            style={'display': 'none', 'marginBottom': '15px'}
        ),
        
        # Results container
        html.Div(
            id="similar-places-results",
            className="similar-places-list"
        ),
        
        # Corpus info
        html.Div(
            id="corpus-info",
            className="mt-3",
            style={'display': 'none'}
        ),
        
        # Loading indicator
        dbc.Spinner(
            html.Div(id="similar-places-loading"),
            color="primary"
        ),
        # Add hidden store for valid place tokens
        dcc.Store(id="valid-place-tokens", data=[])
    ], className="place-similarity-controls p-3")

@callback(
    [Output("similar-places-results", "children"),
     Output("similar-places-loading", "children"),
     Output("select-all-container", "style"),
     Output("corpus-info", "style"),
     Output("corpus-info", "children"),
     Output("valid-place-tokens", "data")],
    [Input("similar-place-search-button", "n_clicks"),
     Input("similar-place-search", "n_submit"),
     Input("similarity-threshold", "value"),
     Input("max-places-input", "value")],
    [State("similar-place-search", "value"),
     State("filtered-data", "data")],
    prevent_initial_call=True
)
def update_similar_places(n_clicks, n_submit, threshold, max_places, search_word, filtered_data):
    """Update the list of similar places based on search and threshold."""
    if not search_word:
        return [], "", {'display': 'none'}, {'display': 'none'}, "", []
    
    # Get similar words from API with limit
    api = WordSimilarityAPI()
    try:
        similar_words = api.find_similar_words(search_word, limit=max_places)
        
        if not similar_words:
            return html.Div([
                html.P("No similar words found in the database.", className="text-muted"),
                html.P("Try a different search term or check the spelling.", className="text-muted")
            ]), "", {'display': 'none'}, {'display': 'block'}, html.Div([
                html.P("No results found", className="text-danger"),
                html.P("The API returned no similar words. This could be because:", className="text-muted"),
                html.Ul([
                    html.Li("The word is not in our database"),
                    html.Li("The word is spelled differently"),
                    html.Li("The API is temporarily unavailable")
                ], className="text-muted")
            ]), []
        
        # Check which similar words exist in the places table
        conn = get_db_connection()
        try:
            # Get all place tokens that match the similar words
            place_tokens = [word for word, _ in similar_words]
            place_tokens_str = ','.join([f"'{token}'" for token in place_tokens])
            
            query = f"""
            SELECT p.token, p.modern as name, p.latitude, p.longitude,
                   COUNT(DISTINCT bp.dhlabid) as book_count,
                   SUM(bp.book_count) as frequency
            FROM places p
            JOIN books bp ON p.token = bp.token
            WHERE p.token IN ({place_tokens_str})
            GROUP BY p.token, p.modern, p.latitude, p.longitude
            """
            
            places_df = pd.read_sql_query(query, conn)
            
            # Filter by similarity threshold and ensure we have valid coordinates
            valid_places = []
            for word, score in similar_words:
                if score >= threshold and word in places_df['token'].values:
                    place_data = places_df[places_df['token'] == word].iloc[0]
                    # Only include places with valid coordinates
                    if pd.notna(place_data['latitude']) and pd.notna(place_data['longitude']):
                        valid_places.append((word, score, place_data))
            
            if not valid_places:
                return html.Div([
                    html.P(f"Found {len(similar_words)} similar words, but none match places in the database.", className="text-muted"),
                    html.P("Try adjusting the similarity threshold or search for a different place.", className="text-muted")
                ]), "", {'display': 'none'}, {'display': 'block'}, html.Div([
                    html.P("No matching places found", className="text-warning"),
                    html.P(f"The API found {len(similar_words)} similar words, but none of them match places in the database.", className="text-muted"),
                    html.P("You can:", className="text-muted"),
                    html.Ul([
                        html.Li("Lower the similarity threshold"),
                        html.Li("Try a different search term"),
                        html.Li("Check if the place exists in the database")
                    ], className="text-muted")
                ]), []
            
            # Create list of place items
            place_items = []
            for word, score, place_data in valid_places:
                place_items.append(
                    dbc.ListGroupItem(
                        [
                            html.Div([
                                html.Div([
                                    html.Div(f"{place_data['token']}", style={'fontWeight': 'bold', 'fontSize': '1rem'}),
                                    html.Div(f"{place_data['name']}", style={'color': '#666', 'fontSize': '0.9rem'})
                                ], style={'marginBottom': '4px'}),
                                html.Div([
                                    html.Span(f"📚 {int(place_data['book_count'])} books", style={'marginRight': '12px', 'color': '#666', 'fontSize': '0.85rem'}),
                                    html.Span(f"📝 {int(place_data['frequency'])} mentions", style={'color': '#666', 'fontSize': '0.85rem'})
                                ])
                            ], style={'flex': '1'}),
                            html.Div([
                                html.Span(f"Similarity: {score:.2f}", style={'color': '#666', 'fontSize': '0.85rem'})
                            ], style={'textAlign': 'right'})
                        ],
                        className="similar-place-item d-flex justify-content-between align-items-start"
                    )
                )
            
            valid_tokens = [word for word, score, place_data in valid_places]
            
            if not place_items:
                return html.Div("No similar places found above threshold.", className="text-muted"), "", {'display': 'none'}, {'display': 'none'}, "", []
            
            # Show Select All button if we have results
            return html.Div([
                html.P(f"Found {len(place_items)} similar places", className="text-muted mb-3"),
                dbc.ListGroup(place_items)
            ]), "", {'display': 'block'}, {'display': 'block'}, html.Div([
                html.P("Click 'Select All Places and Build Corpus' to create a corpus from these places.", className="text-muted")
            ]), valid_tokens
            
        finally:
            conn.close()
        
    except Exception as e:
        return html.Div([
            html.P("An error occurred while searching for similar places.", className="text-danger"),
            html.P("Please try again or contact support if the problem persists.", className="text-muted")
        ]), "", {'display': 'none'}, {'display': 'block'}, html.Div([
            html.P("Error occurred", className="text-danger"),
            html.P(f"Error details: {str(e)}", className="text-muted"),
            html.P("Please try:", className="text-muted"),
            html.Ul([
                html.Li("Refreshing the page"),
                html.Li("Using a different search term"),
                html.Li("Checking your internet connection")
            ], className="text-muted")
        ]), []

@callback(
    Output("current-filters", "data", allow_duplicate=True),
    Output("filtered-data", "data", allow_duplicate=True),
    Output("corpus-info", "children", allow_duplicate=True),
    Input("select-all-build-corpus-button", "n_clicks"),
    State("valid-place-tokens", "data"),
    prevent_initial_call=True
)
def select_all_and_build_corpus(n_clicks, valid_tokens):
    if not n_clicks:
        raise PreventUpdate
        
    if not valid_tokens:
        return dash.no_update, dash.no_update, dash.no_update
        
    conn = None
    try:
        conn = get_db_connection()
        
        if not valid_tokens:
            return dash.no_update, dash.no_update, dash.no_update
            
        # Split tokens into chunks to avoid SQLite parameter limit
        chunk_size = 500
        token_chunks = [valid_tokens[i:i + chunk_size] for i in range(0, len(valid_tokens), chunk_size)]
        
        # Build query with UNION ALL for each chunk
        query_parts = []
        all_params = []
        
        for chunk in token_chunks:
            chunk_query = f"""
            SELECT DISTINCT dhlabid
            FROM books
            WHERE token IN ({','.join(['?'] * len(chunk))})
            """
            query_parts.append(chunk_query)
            all_params.extend(chunk)
            
        # Combine all parts with UNION ALL
        final_query = " UNION ALL ".join(query_parts)
        
        # Get unique dhlabids and ensure uniqueness with set
        dhlabids = list(set(pd.read_sql_query(final_query, conn, params=tuple(all_params))['dhlabid'].tolist()))
        
        # Update global variable using the new function
        from dash_imagination.app import update_current_dhlabids
        update_current_dhlabids(dhlabids)
        
        # Get places for map with all valid tokens
        from dash_imagination.app import get_places_for_map
        
        # Create a complete filters dictionary with all required fields
        filters = {
            'year_range': [1850, 1880],  # Default year range
            'categories': [],  # Empty categories list
            'authors': [],    # Empty authors list
            'titles': [],     # Empty titles list
            'max_places': 1500,  # Default max places
            'sample_size': 50,   # Default sample size
            'selected_tokens': valid_tokens,  # Add the selected tokens
            'current_corpus': dhlabids  # Add the current corpus
        }
        
        # Get places for map with the filters and selected tokens
        places_df = get_places_for_map(filters=filters, selected_tokens=valid_tokens)
        places_json = places_df.to_json(orient='records', date_format='iso')
        
        # Create corpus info content
        corpus_info = html.Div([
            html.P(f"Selected {len(valid_tokens)} places", className="text-muted"),
            html.P(f"Found {len(dhlabids)} unique books containing these places", className="text-muted"),
            html.P(f"Showing {len(places_df)} places on the map", className="text-muted")
        ])
        
        return filters, places_json, corpus_info
        
    except Exception as e:
        print(f"Error in select_all_and_build_corpus: {str(e)}")
        return dash.no_update, dash.no_update, dash.no_update
    finally:
        if conn:
            conn.close()

def create_place_item(row):
    """Create a place item for the list."""
    try:
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
            'cursor': 'pointer'
        }, className='place-item', id={'type': 'place-item', 'index': row['token']})
    except Exception as e:
        print(f"Error creating place item: {e}")
        return None

def update_corpus_from_places(df, current_filters):
    """Update the corpus based on selected places."""
    if df.empty:
        return
    
    # Get all unique dhlabids from books containing these places
    conn = get_db_connection()
    try:
        # Get all books that contain any of the selected places
        place_tokens = df['token'].unique()
        place_tokens_str = ','.join([f"'{token}'" for token in place_tokens])
        
        query = f"""
        SELECT DISTINCT dhlabid
        FROM books
        WHERE token IN ({place_tokens_str})
        """
        
        books_df = pd.read_sql_query(query, conn)
        
        # Update current_filters with new corpus
        if current_filters is None:
            current_filters = {}
        
        current_filters['current_corpus'] = books_df['dhlabid'].tolist()
        
    finally:
        conn.close()
    
    return current_filters 
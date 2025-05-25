from dash import html, dcc, Input, Output, State, callback, callback_context, ALL
import dash_bootstrap_components as dbc
from .word_similarity import WordSimilarityAPI
import pandas as pd
from dash.exceptions import PreventUpdate

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
        
        # Similarity threshold slider
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
        ]),
        
        # Results container
        html.Div(
            id="similar-places-results",
            className="similar-places-list"
        ),
        
        # Loading indicator
        dbc.Spinner(
            html.Div(id="similar-places-loading"),
            color="primary"
        )
    ], className="place-similarity-controls p-3")

@callback(
    [Output("similar-places-results", "children"),
     Output("similar-places-loading", "children")],
    [Input("similar-place-search-button", "n_clicks"),
     Input("similar-place-search", "n_submit"),  # Add return key trigger
     Input("similarity-threshold", "value")],
    [State("similar-place-search", "value"),
     State("filtered-data", "data")],
    prevent_initial_call=True
)
def update_similar_places(n_clicks, n_submit, threshold, search_word, filtered_data):
    """Update the list of similar places based on search and threshold."""
    if not search_word:
        return [], ""
    
    # Get similar words from API
    api = WordSimilarityAPI()
    try:
        similar_words = api.find_similar_words(search_word)
        
        # Convert filtered data to DataFrame
        if filtered_data:
            df = pd.read_json(filtered_data, orient='split')
        else:
            df = pd.DataFrame()
        
        # Filter similar words to only include places in current corpus
        valid_places = []
        for word, score in similar_words:
            if score >= threshold:
                # Check if word exists in current corpus places
                if not df.empty and word in df['name'].values:
                    valid_places.append((word, score))
        
        # Create list of place items
        place_items = []
        for word, score in valid_places:
            place_items.append(
                dbc.ListGroupItem(
                    [
                        html.Div([
                            html.Span(word, className="place-name"),
                            html.Span(f"{score:.2f}", className="similarity-score ms-2")
                        ], className="d-flex justify-content-between align-items-center"),
                        dbc.Button(
                            "Add to List",
                            color="primary",
                            size="sm",
                            className="mt-2",
                            id={"type": "add-place-button", "index": word}
                        )
                    ],
                    className="similar-place-item"
                )
            )
        
        if not place_items:
            return html.Div("No similar places found above threshold.", className="text-muted"), ""
        
        return dbc.ListGroup(place_items), ""
        
    except Exception as e:
        return html.Div(f"Error: {str(e)}", className="text-danger"), ""

@callback(
    Output("place-list", "children", allow_duplicate=True),
    [Input({"type": "add-place-button", "index": ALL}, "n_clicks")],
    [State("filtered-data", "data"),
     State("place-list", "children")],
    prevent_initial_call=True
)
def add_place_to_list(n_clicks, filtered_data, current_places):
    """Add a selected place to the main place list."""
    if not n_clicks or not any(n_clicks):
        raise PreventUpdate
    
    # Get the clicked button's index
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    place_name = eval(button_id)["index"]
    
    # Convert filtered data to DataFrame
    if filtered_data:
        df = pd.read_json(filtered_data, orient='split')
    else:
        df = pd.DataFrame()
    
    # Find the place in the filtered data
    place_data = df[df['name'] == place_name]
    if place_data.empty:
        raise PreventUpdate
    
    # Create new place item
    new_place = create_place_item(place_data.iloc[0])
    
    # Add to current places if not already present
    if current_places is None:
        current_places = []
    
    # Check if place is already in list
    place_names = [p['props']['children'][0]['props']['children'] for p in current_places]
    if place_name not in place_names:
        current_places.append(new_place)
    
    return current_places 
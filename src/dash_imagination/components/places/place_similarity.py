from dash import html, dcc
import dash_bootstrap_components as dbc
from .word_similarity import WordSimilarityAPI
import pandas as pd
from dash.exceptions import PreventUpdate
from dash_imagination.utils.db import get_db_connection
import io  # Add this import
import dash

def create_place_similarity_controls():
    """Create the place similarity search controls."""
    return html.Div([
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
        
        # Select All button with loading spinner
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
        ], id="select-all-container", style={'display': 'none', 'marginBottom': '15px'}),
        
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

def create_place_item(row):
    """Create a place item for the list."""
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

def update_corpus_from_places(df, current_filters):
    """Update the corpus based on selected places."""
    if current_filters is None:
        current_filters = {}
    
    # Update filters with new selections
    new_filters = current_filters.copy()
    new_filters['selected_tokens'] = df['token'].tolist()
    
    return new_filters 
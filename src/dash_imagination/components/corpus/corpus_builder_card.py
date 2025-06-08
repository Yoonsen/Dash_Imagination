import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash, ctx, no_update
import pandas as pd
from ...utils.corpus_build import corpus_builder, get_corpus_stats, count_words
from ...utils.global_state import update_from_books
import dhlab as dh

def create_corpus_builder_card(categories_list=None, authors_list=None, default_filters=None):
    """Creates a Bootstrap card component for corpus building."""
    if categories_list is None:
        categories_list = []
    if authors_list is None:
        authors_list = []
    if default_filters is None:
        default_filters = {'categories': []}

    return dbc.Card([
        dbc.CardHeader([
            html.Div([
                html.I(className="fa fa-book me-2"),
                html.H5("Build Corpus", className="mb-0 d-inline"),
                dbc.Button(
                    "×",
                    id="close-corpus-builder",
                    className="float-end btn-close",
                    size="sm",
                ),
            ], className="d-flex justify-content-between align-items-center")
        ], className="bg-primary-subtle text-dark"),
        dbc.CardBody([
            dbc.Tabs([
                dbc.Tab([
                    # Metadata Tab Content
                    html.Div([
                        html.Label("Maximum Places", className="form-label"),
                        html.Div([
                            dcc.Slider(
                                id='corpus-max-places-slider',
                                min=100,
                                max=2000,
                                step=100,
                                value=500,
                                marks={i: str(i) for i in range(500, 2001, 500)},
                                className="form-range"
                            ),
                            html.Div("Recommended range: 500-2000 places for optimal performance", className="form-text")
                        ])
                    ], className="mb-4"),
                    html.Div([
                        html.Label("Year Range", className="form-label"),
                        dcc.RangeSlider(
                            id='corpus-year-range',
                            min=1814,
                            max=1905,
                            step=1,
                            value=[1814, 1905],
                            marks={i: str(i) for i in range(1814, 1906, 10)},
                            className="mb-3"
                        )
                    ], className="mb-4"),
                    html.Div([
                        html.Label("Select Categories", className="form-label"),
                        dcc.Dropdown(
                            id='corpus-category-dropdown',
                            options=[{'label': cat, 'value': cat} for cat in categories_list],
                            value=default_filters.get('categories', []),
                            multi=True,
                            placeholder="Select categories..."
                        )
                    ], className="mb-4"),
                    html.Div([
                        html.Label("Select Authors", className="form-label"),
                        dcc.Dropdown(
                            id='corpus-author-dropdown',
                            options=[{'label': author, 'value': author} for author in authors_list],
                            value=default_filters.get('authors', []),
                            multi=True,
                            placeholder="Select authors..."
                        )
                    ], className="mb-4"),
                    html.Div([
                        html.Button([
                            html.I(className="fas fa-hammer me-2"),
                            "Build Corpus"
                        ], id='build-corpus-btn', className="btn btn-primary w-100")
                    ], className="mb-4"),
                    dbc.Button([
                        html.I(className="fas fa-undo me-2"),
                        "Reset"
                    ], id='reset-corpus-btn', color="secondary", className="w-100 mb-4"),
                    html.Div([
                        html.Hr(),
                        html.H5("Corpus Statistics", className="mb-3"),
                        html.Div(id="corpus-stats-content"),
                    ], id="corpus-stats-section", style={"display": "none"})
                ], label="Metadata", tab_id="metadata"),
                dbc.Tab([
                    html.Div([
                        html.Label("Wordforms (comma-separated)", className="form-label"),
                        dcc.Input(
                            id='content-wordforms-input',
                            type='text',
                            placeholder='e.g. krig, krigen',
                            className="form-control mb-3"
                        ),
                        html.Label("Minimum occurrences (n)", className="form-label"),
                        dcc.Input(
                            id='content-min-count-input',
                            type='number',
                            min=1,
                            value=1,
                            className="form-control mb-3"
                        ),
                        html.Button([
                            html.I(className="fas fa-hammer me-2"),
                            "Build Corpus"
                        ], id='build-content-corpus-btn', className="btn btn-primary w-100 mb-4"),
                        html.Div([
                            html.Hr(),
                            html.H5("Corpus Statistics", className="mb-3"),
                            html.Div(id="content-corpus-stats-content"),
                        ], id="content-corpus-stats-section", style={"display": "none"})
                    ])
                ], label="Content", tab_id="content"),
            ], id="corpus-builder-tabs", active_tab="metadata"),
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'}),
    ], id="corpus-builder-card", className="shadow position-absolute m-3", style={
        "width": "350px",
        "height": "500px",
        "zIndex": 800,
        "display": "none",
        "top": "60px",
        "left": "400px",
        "transition": "display 0.3s ease-in-out"
    })

@callback(
    [Output("corpus-builder-card", "style"),
     Output("corpus-controls-container", "style", allow_duplicate=True)],
    [Input("open-corpus-builder", "n_clicks"),
     Input("close-corpus-builder", "n_clicks")],
    [State("corpus-builder-card", "style"),
     State("corpus-controls-container", "style")],
    prevent_initial_call=True
)
def toggle_card_visibility(n1, n2, builder_style, controls_style):
    """Toggle the visibility of the corpus builder card while keeping controls visible."""
    if not ctx.triggered:
        return dash.no_update, dash.no_update
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Initialize styles if they're None
    builder_style = builder_style or {}
    controls_style = controls_style or {}
    
    if button_id == "open-corpus-builder":
        # Show builder card and ensure controls stay visible
        builder_style["display"] = "block"
        builder_style["left"] = "400px"
        controls_style["display"] = "block"
        return builder_style, controls_style
    elif button_id == "close-corpus-builder":
        # Hide builder card but keep controls visible
        builder_style["display"] = "none"
        return builder_style, controls_style
    
    return dash.no_update, dash.no_update

@callback(
    [Output("corpus-stats-section", "style"),
     Output("corpus-stats-content", "children"),
     Output("current-filters", "data", allow_duplicate=True)],
    [Input("build-corpus-btn", "n_clicks")],
    [State("corpus-category-dropdown", "value"),
     State("corpus-author-dropdown", "value"),
     State("corpus-year-range", "value"),
     State("corpus-max-places-slider", "value"),
     State("current-filters", "data")],
    prevent_initial_call=True
)
def build_corpus_and_show_stats(n_clicks, categories, authors, year_range, max_places, current_filters):
    """Build the corpus with selected filters and display statistics."""
    if not n_clicks:
        return {"display": "none"}, [], dash.no_update
    
    # Initialize or update filters
    if current_filters is None:
        current_filters = {}
    new_filters = current_filters.copy()
    
    # Update filter values
    new_filters['categories'] = categories if categories else []
    new_filters['authors'] = authors if authors else []
    new_filters['year_range'] = year_range if year_range else [1814, 1905]
    new_filters['max_places'] = max_places
    new_filters['corpus_source'] = 'Corpus Builder'
    
    # Build corpus with filters
    # For now, use first category and all selected authors (if any)
    category = categories[0] if categories else None
    author = authors[0] if authors else None
    dhlabids = corpus_builder.build_corpus(
        category=category,
        year_range=tuple(year_range) if year_range else None,
        author=author
    )
    # Get places for these books (downsampled)
    places_df = corpus_builder.get_places(max_places=max_places)
    place_tokens = places_df['place_token'].tolist()
    # Update global state
    update_from_books(dhlabids, place_tokens)
    
    # Get and format statistics with place sampling
    stats = get_corpus_stats(max_places=max_places)
    
    stats_display = [
        dbc.ListGroup(
            [
                dbc.ListGroupItem([
                    html.I(className="fas fa-book me-2"),
                    f"Total Books: {stats['total_books']}"
                ]),
                dbc.ListGroupItem([
                    html.I(className="fas fa-user me-2"),
                    f"Unique Authors: {stats['unique_authors']}"
                ]),
                dbc.ListGroupItem([
                    html.I(className="fas fa-map-marker-alt me-2"),
                    f"Places Shown: {stats['total_places']:,} ",
                    html.Small(f"(sampled from {stats['sampled_from']:,})", className="text-muted")
                ]),
                dbc.ListGroupItem([
                    html.I(className="fas fa-calendar me-2"),
                    f"Year Range: {stats['year_range'][0]} - {stats['year_range'][1]}"
                ]),
                dbc.ListGroupItem(
                    [
                        html.I(className="fas fa-tags me-2"),
                        html.Strong("Categories:"),
                        html.Ul(
                            [
                                html.Li(f"{cat}: {count}")
                                for cat, count in stats['categories'].items()
                            ],
                            className="mb-0 mt-2"
                        )
                    ]
                ),
            ],
            className="shadow-sm"
        )
    ]
    
    return {"display": "block"}, stats_display, new_filters

@callback(
    [Output("corpus-category-dropdown", "value"),
     Output("corpus-author-dropdown", "value"),
     Output("corpus-year-range", "value"),
     Output("corpus-max-places-slider", "value"),
     Output("current-filters", "data", allow_duplicate=True)],
    [Input("reset-corpus-btn", "n_clicks")],
    prevent_initial_call=True
)
def reset_corpus_filters(n_clicks):
    """Reset all corpus filters to their default values."""
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    
    # Reset filters to default values
    default_filters = {
        'categories': [],
        'authors': [],
        'year_range': [1814, 1905],
        'max_places': 500,
        'corpus_source': 'Corpus Builder'
    }
    
    return [], [], [1814, 1905], 500, default_filters

@callback(
    [Output("content-corpus-stats-section", "style"),
     Output("content-corpus-stats-content", "children"),
     Output("current-filters", "data", allow_duplicate=True)],
    [Input("build-content-corpus-btn", "n_clicks")],
    [State("content-wordforms-input", "value"),
     State("content-min-count-input", "value"),
     State("current-filters", "data")],
    prevent_initial_call=True
)
def build_content_corpus_and_show_stats(n_clicks, wordforms, min_count, current_filters):
    if not n_clicks:
        return {"display": "none"}, [], dash.no_update
    # Get current corpus dhlabids from global state
    from ...utils.global_state import get_current_state
    dhlabids, _ = get_current_state()
    if not dhlabids:
        return {"display": "none"}, ["No corpus to filter. Please build a metadata corpus first."], dash.no_update
    # Parse word list
    words = [w.strip() for w in (wordforms or '').split(',') if w.strip()]
    if not words:
        return {"display": "none"}, ["Please enter at least one wordform."], dash.no_update
    # Run DH Lab Counts
    try:
        counts_df = count_words(dhlabids, words)
        print(f"[ContentTab] Counts dataframe shape: {counts_df.shape}")
        # Sum across words for each dhlabid (column)
        dhlabid_sums = counts_df.sum(axis=0)
        selected_dhlabids = [int(dhl) for dhl, total in dhlabid_sums.items() if total >= (min_count or 1)]
    except Exception as e:
        return {"display": "none"}, [f"Error running content search: {e}"], dash.no_update
    if not selected_dhlabids:
        return {"display": "block"}, ["No books matched the content criteria."], dash.no_update
    # Get places for these books (downsample to default 500 for now)
    places_df = corpus_builder.get_places(max_places=500)
    place_tokens = places_df['place_token'].tolist()
    # Update global state
    update_from_books(selected_dhlabids, place_tokens)
    # Update filters
    new_filters = current_filters.copy() if current_filters else {}
    new_filters['content_words'] = words
    new_filters['content_min_count'] = min_count
    new_filters['corpus_source'] = 'Content'
    # Get and format statistics
    stats = get_corpus_stats(max_places=500)
    stats_display = [
        dbc.ListGroup([
            dbc.ListGroupItem([
                html.I(className="fas fa-book me-2"),
                f"Total Books: {stats['total_books']}"
            ]),
            dbc.ListGroupItem([
                html.I(className="fas fa-user me-2"),
                f"Unique Authors: {stats['unique_authors']}"
            ]),
            dbc.ListGroupItem([
                html.I(className="fas fa-map-marker-alt me-2"),
                f"Places Shown: {stats['total_places']:,} ",
                html.Small(f"(sampled from {stats['sampled_from']:,})", className="text-muted")
            ]),
            dbc.ListGroupItem([
                html.I(className="fas fa-calendar me-2"),
                f"Year Range: {stats['year_range'][0]} - {stats['year_range'][1]}"
            ]),
            dbc.ListGroupItem(
                [
                    html.I(className="fas fa-tags me-2"),
                    html.Strong("Categories:"),
                    html.Ul(
                        [
                            html.Li(f"{cat}: {count}")
                            for cat, count in stats['categories'].items()
                        ],
                        className="mb-0 mt-2"
                    )
                ]
            ),
        ], className="shadow-sm")
    ]
    return {"display": "block"}, stats_display, new_filters 
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash, ctx, no_update
import pandas as pd
from ...utils.corpus_build import corpus_builder, get_corpus_stats, count_words
from ...utils.db import get_db_connection
import dhlab as dh
from dash import dcc


def apply_book_operation(current_books, incoming_books, operation):
    op = (operation or 'intersection').lower()
    current = set(current_books or [])
    incoming = set(incoming_books or [])

    if not current:
        if op == 'difference':
            return []
        return sorted(incoming)

    if op == 'union':
        result = current | incoming
    elif op == 'difference':
        result = current - incoming
    else:  # intersection
        result = current & incoming if incoming else set()
    return sorted(result)


def fetch_place_tokens(book_ids):
    if not book_ids:
        return []
    query = """
        SELECT DISTINCT b.token
        FROM books b
        WHERE b.dhlabid IN ({})
    """
    conn = get_db_connection()
    try:
        formatted = ','.join(['?'] * len(book_ids))
        df = pd.read_sql_query(query.format(formatted), conn, params=tuple(book_ids))
    finally:
        conn.close()
    if df.empty:
        return []
    return df['token'].dropna().astype(str).tolist()

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
                html.H5("Build Corpus", className="mb-0 d-inline", style={"fontSize": "14px", "fontWeight": 500}),
                dbc.Button(
                    "×",
                    id="close-corpus-builder",
                    className="float-end btn-close dialog-close-btn",
                    size="sm",
                    title="Close"
                ),
            ], className="d-flex justify-content-between align-items-center", id="corpus-builder-header", style={"cursor": "grab", "userSelect": "none"})
        ], className="bg-success-subtle text-dark"),
        dbc.CardBody([
            dbc.Tabs([
                dbc.Tab([
                    # Metadata Tab Content
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
                        html.Label("Combine with existing corpus", className="form-label mb-1"),
                        dbc.ButtonGroup([
                            dbc.Button("+", id='corpus-op-union-builder', n_clicks=0, size="sm", color="secondary", outline=True, title="Add to current corpus"),
                            dbc.Button("&", id='corpus-op-intersection-builder', n_clicks=0, size="sm", color="secondary", outline=True, title="Keep only overlap"),
                            dbc.Button("-", id='corpus-op-diff-builder', n_clicks=0, size="sm", color="secondary", outline=True, title="Remove from current corpus"),
                        ], size="sm")
                    ], className="mb-4"),
                    html.Div([
                        dcc.Loading(
                            id="build-corpus-loading",
                            type="default",
                            children=[
                                html.Button([
                                    html.I(className="fas fa-plus me-2"),
                                    "Add Books"
                                ], id='build-corpus-btn', className="btn btn-primary w-100"),
                                html.Div(id="build-corpus-status", className="mt-2")
                            ]
                        )
                    ], className="mb-4"),
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
                        dcc.Loading(
                            id="build-content-corpus-loading",
                            type="default",
                            children=[
                                html.Button([
                                    html.I(className="fas fa-plus me-2"),
                                    "Add Books"
                                ], id='build-content-corpus-btn', className="btn btn-primary w-100 mb-4"),
                                html.Div(id="build-content-corpus-status", className="mt-2")
                            ]
                        )
                    ])
                ], label="Content", tab_id="content"),
                dbc.Tab([
                    html.Div([
                        html.Label("Keywords (comma-separated)", className="form-label"),
                        dbc.Input(
                            id='collocation-words-input',
                            type='text',
                            placeholder='e.g. krig, krigen',
                            size='sm',
                            className="mb-3"
                        ),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Words before", className="form-label"),
                                dbc.Input(
                                    id='collocation-before-input',
                                    type='number',
                                    min=1,
                                    max=200,
                                    step=1,
                                    value=50,
                                    size='sm'
                                )
                            ], width=6),
                            dbc.Col([
                                dbc.Label("Words after", className="form-label"),
                                dbc.Input(
                                    id='collocation-after-input',
                                    type='number',
                                    min=1,
                                    max=200,
                                    step=1,
                                    value=50,
                                    size='sm'
                                )
                            ], width=6),
                        ], className="g-2 mb-3"),
                        dbc.Button(
                            "Find collocations",
                            id='run-collocations',
                            color='secondary',
                            size='sm',
                            className="w-100 mb-3"
                        ),
                        dcc.Loading(
                            html.Div(id='collocation-results', style={'maxHeight': '200px', 'overflowY': 'auto'}),
                            type='default'
                        ),
                        dbc.Button("Highlight places", id='apply-collocation-highlight', color='danger', size='sm', className="w-100 mb-2"),
                        dbc.Button("Clear highlight", id='clear-collocation-highlight', color='secondary', outline=True, size='sm', className="w-100 mb-3")
                    ])
                ], label="Collocations", tab_id="collocations"),
            ], id="corpus-builder-tabs", active_tab="metadata"),
        ], style={'overflowY': 'auto', 'maxHeight': 'calc(500px - 56px)'}),
    ], id="corpus-builder-card", className="shadow position-absolute m-3", style={
        "width": "350px",
        "height": "500px",
        "zIndex": 800,
        "display": "none",
        "top": "60px",
        "left": "100px"
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
    import dash
    from dash import no_update
    import dash_bootstrap_components as dbc
    import flask
    import os
    import sys
    import math
    import json
    from dash import ctx
    if not ctx.triggered:
        return dash.no_update, dash.no_update
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Initialize styles if they're None
    builder_style = builder_style or {}
    controls_style = controls_style or {}
    
    if button_id == "open-corpus-builder":
        # Show builder card and ensure controls stay visible
        builder_style["display"] = "block"
        builder_style["width"] = "350px"
        builder_style["height"] = "500px"
        builder_style["zIndex"] = 800
        builder_style["top"] = "60px"
        builder_style["left"] = "100px"
        # Remove transform if present
        builder_style.pop("transform", None)
        controls_style["display"] = "block"
        return builder_style, controls_style
    elif button_id == "close-corpus-builder":
        # Hide builder card but keep controls visible
        builder_style["display"] = "none"
        return builder_style, controls_style
    
    return dash.no_update, dash.no_update

# New simplified callback: only updates filters/global state for metadata tab
@callback(
    [Output("current-filters", "data", allow_duplicate=True),
     Output("build-corpus-status", "children"),
     Output("current-dhlabids-store", "data", allow_duplicate=True)],
    [Input("build-corpus-btn", "n_clicks")],
    [State("corpus-category-dropdown", "value"),
     State("corpus-author-dropdown", "value"),
     State("corpus-year-range", "value"),
     State("corpus-max-places-slider", "value"),
     State("current-filters", "data"),
     State("corpus-operation", "data"),
     State("current-dhlabids-store", "data")],
    prevent_initial_call=True
)
def build_corpus_and_show_stats(
    n_clicks,
    categories,
    authors,
    year_range,
    max_places,
    current_filters,
    operation,
    current_books
):
    import time
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    if current_filters is None:
        current_filters = {}
    # Show spinner/message while building
    status = dbc.Spinner("Preparing books...", color="primary", size="sm", fullscreen=False, spinner_style={"width": "1.5rem", "height": "1.5rem"})
    new_filters = current_filters.copy()
    new_filters['categories'] = categories if categories else []
    new_filters['authors'] = authors if authors else []
    new_filters['year_range'] = year_range if year_range else [1814, 1905]
    new_filters['max_places'] = max_places
    new_filters['corpus_source'] = 'Corpus Builder'
    op = (operation or "intersection").lower()
    new_filters['last_operation'] = op
    category = categories[0] if categories else None
    author = authors[0] if authors else None
    dhlabids = corpus_builder.build_corpus(
        category=category,
        year_range=tuple(year_range) if year_range else None,
        author=author
    )
    current_books = current_books or []
    updated_books = apply_book_operation(current_books, dhlabids, operation=op)
    place_tokens = fetch_place_tokens(updated_books)
    # Optionally, show a success message
    status_done = html.Span("Books added!", style={"color": "#059669", "fontWeight": "500"})
    new_filters['selected_tokens'] = place_tokens
    return new_filters, status_done, updated_books

@callback(
    [Output("corpus-category-dropdown", "value"),
     Output("corpus-author-dropdown", "value"),
     Output("corpus-year-range", "value"),
     Output("corpus-max-places-slider", "value"),
     Output("current-filters", "data", allow_duplicate=True),
     Output("reset-corpus-btn", "color"),
     Output("reset-corpus-btn", "title")],
    [Input("reset-corpus-btn", "n_clicks_timestamp")],
    [State("reset-corpus-btn", "n_clicks"),
     State("reset-corpus-btn", "color"),
     State("reset-corpus-btn", "title")],
    prevent_initial_call=True
)
def reset_corpus_filters(n_clicks_timestamp, n_clicks, color, title):
    """Require double-click to confirm reset. On first click, change color/title. On second click within 3s, reset."""
    ctx = callback_context
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    # Store last click timestamp in a hidden div or use local state
    if color != "danger":
        # First click: warn
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, "danger", "Click again to confirm reset"
    else:
        # Second click: reset
        default_filters = {
            'categories': [],
            'authors': [],
            'year_range': [1814, 1905],
            'max_places': 500,
            'corpus_source': 'Corpus Builder'
        }
        return [], [], [1814, 1905], 500, default_filters, "secondary", "Clear Filters (double-click to confirm)"

# New simplified callback: only updates filters/global state
@callback(
    [Output("current-filters", "data", allow_duplicate=True),
     Output("build-content-corpus-status", "children"),
     Output("current-dhlabids-store", "data", allow_duplicate=True)],
    [Input("build-content-corpus-btn", "n_clicks")],
    [State("content-wordforms-input", "value"),
     State("content-min-count-input", "value"),
     State("current-filters", "data"),
     State("corpus-operation", "data"),
     State("current-dhlabids-store", "data")],
    prevent_initial_call=True
)
def build_content_corpus_and_show_stats(n_clicks, wordforms, min_count, current_filters, operation, current_books):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    from ...utils.corpus_build import corpus_builder
    current_books = current_books or []
    dhlabids = current_books.copy()
    # If corpus is empty, use all dhlabids from the database
    if not dhlabids:
        dhlabids = corpus_builder.get_corpus()
        if not dhlabids:
            # If still empty, fetch all from DB
            import pandas as pd
            from ...utils.db import get_db_connection
            conn = get_db_connection()
            df = pd.read_sql_query("SELECT dhlabid FROM corpus", conn)
            dhlabids = df['dhlabid'].tolist()
            conn.close()
    words = [w.strip() for w in (wordforms or '').split(',') if w.strip()]
    if not words:
        return dash.no_update, dash.no_update
    # Show spinner/message while building
    status = dbc.Spinner("Preparing books...", color="primary", size="sm", fullscreen=False, spinner_style={"width": "1.5rem", "height": "1.5rem"})
    try:
        counts_df = count_words(dhlabids, words)
        print(f"[ContentTab] Counts dataframe shape: {counts_df.shape}")
        dhlabid_sums = counts_df.sum(axis=0)
        selected_dhlabids = [int(dhl) for dhl, total in dhlabid_sums.items() if total >= (min_count or 1)]
    except Exception as e:
        return dash.no_update, dash.no_update
    if not selected_dhlabids:
        return dash.no_update, dash.no_update
    op = (operation or "intersection").lower()
    updated_books = apply_book_operation(current_books, selected_dhlabids, operation=op)
    place_tokens = fetch_place_tokens(updated_books)
    new_filters = current_filters.copy() if current_filters else {}
    new_filters['content_words'] = words
    new_filters['content_min_count'] = min_count
    new_filters['corpus_source'] = 'Content'
    new_filters['last_operation'] = op
    # Optionally, show a success message
    status_done = html.Span("Books added!", style={"color": "#059669", "fontWeight": "500"})
    new_filters['selected_tokens'] = place_tokens
    return new_filters, status_done, updated_books
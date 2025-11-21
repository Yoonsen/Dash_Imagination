import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash, ctx, no_update
import pandas as pd
from functools import lru_cache
from ...utils.corpus_build import corpus_builder, get_corpus_stats, count_words
from ...utils.db import get_db_connection
import dhlab as dh
from ..common.size_controls import DEFAULT_CARD_SIZES, card_title_bar

DEFAULT_YEAR_RANGE = [1814, 1905]


def _format_title_label(title: str, year) -> str:
    if not title:
        return ""
    year_str = "(n.d.)"
    if year:
        try:
            year_int = int(year)
            year_str = f"({year_int})"
        except (ValueError, TypeError):
            pass
    return f"{title} {year_str}"


def _split_authors(author_value):
    if not author_value:
        return []
    authors = []
    for piece in str(author_value).split('/'):
        trimmed = piece.strip()
        if trimmed:
            authors.append(trimmed)
    return authors


@lru_cache(maxsize=1)
def get_filter_metadata():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(
            """
            SELECT title, author, category, year
            FROM corpus
            WHERE title IS NOT NULL
            """,
            conn
        )
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame(columns=['title_label', 'author', 'category'])

    df['title_label'] = [_format_title_label(row['title'], row['year']) for _, row in df.iterrows()]
    df['category'] = df['category'].astype(str).str.strip().replace({'nan': '', 'None': ''})
    df['authors_list'] = df['author'].apply(_split_authors)

    exploded = df.explode('authors_list')
    exploded['author'] = exploded['authors_list'].astype(str).str.strip()
    filtered = exploded[['title_label', 'author', 'category']].dropna(subset=['title_label'])
    filtered['author'] = filtered['author'].replace({'None': '', 'nan': ''}).str.strip()
    filtered['category'] = filtered['category'].replace({'None': '', 'nan': ''}).str.strip()
    return filtered.drop_duplicates()


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


def parse_title_label(label):
    """Split a label of the form 'Title (Year)' into title + optional year."""
    if not label:
        return None, None
    text = str(label).strip()
    if ' (' not in text or not text.endswith(')'):
        return text, None
    base, year_part = text.rsplit('(', 1)
    base = base.strip()
    year_text = year_part.rstrip(')').strip()
    if year_text.lower().startswith('n.d'):
        return base, None
    try:
        return base, int(year_text)
    except ValueError:
        return base, None


def fetch_dhlabids_for_titles(title_labels):
    """Resolve dropdown labels to their matching dhlabids."""
    if not title_labels:
        return []

    title_map = {}
    for label in title_labels:
        title, year = parse_title_label(label)
        if not title:
            continue
        title_map.setdefault(title, set()).add(year)

    if not title_map:
        return []

    conn = get_db_connection()
    try:
        placeholders = ','.join(['?'] * len(title_map))
        df = pd.read_sql_query(
            f"SELECT dhlabid, title, year FROM corpus WHERE title IN ({placeholders})",
            conn,
            params=list(title_map.keys())
        )
    finally:
        conn.close()

    dhlabids = []
    for _, row in df.iterrows():
        row_title = row['title']
        row_year = row['year']
        allowed_years = title_map.get(row_title, set())
        if not allowed_years:
            continue
        if None in allowed_years:
            dhlabids.append(int(row['dhlabid']))
            continue
        try:
            row_year_int = int(row_year) if row_year is not None else None
        except (ValueError, TypeError):
            row_year_int = None
        if row_year_int in allowed_years:
            dhlabids.append(int(row['dhlabid']))
    return dhlabids


def create_corpus_builder_card(categories_list=None, authors_list=None, titles_list=None, default_filters=None):
    """Creates a Bootstrap card component for corpus modification."""
    if categories_list is None:
        categories_list = []
    if authors_list is None:
        authors_list = []
    if titles_list is None:
        titles_list = []
    if default_filters is None:
        default_filters = {'categories': [], 'titles': []}

    return dbc.Card([
        dbc.CardHeader(
            card_title_bar(
                'corpus-builder',
                'fa fa-tools',
                'Corpus Modify',
                close_button_id="close-corpus-builder",
                close_button_title="Hide builder"
            ),
            className="bg-success-subtle text-dark",
            id="corpus-builder-header"
        ),
        dbc.CardBody([
            html.Div(
                dbc.Tabs([
                dbc.Tab([
                    # Metadata Tab Content
                    html.Div([
                        html.Label("Year Range", className="form-label"),
                        dcc.RangeSlider(
                            id='corpus-year-range',
                            min=DEFAULT_YEAR_RANGE[0],
                            max=DEFAULT_YEAR_RANGE[1],
                            step=1,
                            value=DEFAULT_YEAR_RANGE.copy(),
                            marks={i: str(i) for i in range(DEFAULT_YEAR_RANGE[0], DEFAULT_YEAR_RANGE[1] + 1, 10)},
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
                        html.Label("Select Titles", className="form-label"),
                        dcc.Dropdown(
                            id='corpus-title-dropdown',
                            options=[{'label': title, 'value': title} for title in titles_list],
                            value=default_filters.get('titles', []),
                            multi=True,
                            placeholder="Search and select works..."
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
                        html.Div([
                            html.Label("Combine with existing corpus", className="form-label mb-1"),
                            dbc.ButtonGroup([
                                dbc.Button("+", id='corpus-op-union-content', n_clicks=0, size="sm", color="secondary", outline=True, title="Add to current corpus"),
                                dbc.Button("&", id='corpus-op-intersection-content', n_clicks=0, size="sm", color="secondary", outline=True, title="Keep only overlap"),
                                dbc.Button("-", id='corpus-op-diff-content', n_clicks=0, size="sm", color="secondary", outline=True, title="Remove from current corpus"),
                            ], size="sm")
                        ], className="mb-4"),
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
                ], id="corpus-builder-tabs", active_tab="metadata", className="flex-grow-1")
            , className="flex-grow-1 d-flex flex-column", style={'minHeight': 0, 'gap': '0.75rem'})
        ], style={'flex': '1 1 auto', 'minHeight': 0, 'overflowY': 'auto'}),
    ], id="corpus-builder-card", className="shadow position-absolute m-3 dialog-card", style={
        "width": f"{DEFAULT_CARD_SIZES['corpus-builder']['width']}px",
        "height": f"{DEFAULT_CARD_SIZES['corpus-builder']['height']}px",
        "zIndex": 800,
        "display": "none",
        "top": "60px",
        "left": "620px"
    })

@callback(
    [Output("corpus-builder-card", "style"),
     Output("corpus-controls-container", "style", allow_duplicate=True)],
    [Input("open-corpus-builder", "n_clicks"),
     Input("close-corpus-builder", "n_clicks"),
     Input("card-chip-builder", "n_clicks")],
    [State("corpus-builder-card", "style"),
     State("corpus-controls-container", "style")],
    prevent_initial_call=True
)
def toggle_card_visibility(n1, n2, chip_clicks, builder_style, controls_style):
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
    
    if button_id in ("open-corpus-builder", "card-chip-builder"):
        # Show builder card and ensure controls stay visible without overriding size presets
        current_display = builder_style.get("display", "none")
        if button_id == "card-chip-builder" and current_display != "none":
            builder_style["display"] = "none"
            return builder_style, controls_style
        builder_style["display"] = "flex"
        builder_style.pop("transform", None)
        controls_style["display"] = "flex"
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
     State("corpus-title-dropdown", "value"),
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
    titles,
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
    categories = categories or []
    authors = authors or []
    titles = titles or []
    year_range = list(year_range or DEFAULT_YEAR_RANGE)
    new_filters['categories'] = categories
    new_filters['authors'] = authors
    new_filters['titles'] = titles
    new_filters['year_range'] = year_range
    new_filters['max_places'] = max_places
    new_filters['corpus_source'] = 'Corpus Builder'
    op = (operation or "intersection").lower()
    new_filters['last_operation'] = op

    metadata_filters_applied = bool(categories) or bool(authors) or (year_range != DEFAULT_YEAR_RANGE)
    metadata_books = set()
    if metadata_filters_applied:
        target_years = tuple(year_range) if year_range else None
        category_filters = categories or [None]
        author_filters = authors or [None]
        for category in category_filters:
            for author in author_filters:
                metadata_books.update(
                    corpus_builder.build_corpus(
                        category=category,
                        year_range=target_years,
                        author=author
                    )
                )

    title_books = set(fetch_dhlabids_for_titles(titles))

    if titles:
        if metadata_filters_applied:
            incoming_books = sorted(metadata_books & title_books or title_books)
        else:
            incoming_books = sorted(title_books)
    else:
        incoming_books = sorted(metadata_books)

    if not incoming_books:
        status_error = html.Span("Fant ingen bøker for filteret", style={"color": "#dc2626", "fontWeight": "500"})
        return dash.no_update, status_error, dash.no_update

    current_books = current_books or []
    updated_books = apply_book_operation(current_books, incoming_books, operation=op)
    place_tokens = fetch_place_tokens(updated_books)
    # Optionally, show a success message
    status_done = html.Span("Books added!", style={"color": "#059669", "fontWeight": "500"})
    new_filters['selected_tokens'] = place_tokens
    return new_filters, status_done, updated_books


def _build_option_list(values):
    return [{'label': value, 'value': value} for value in values]


def _sanitize_selection(selected, allowed):
    if not selected:
        return []
    allowed_set = set(allowed)
    return [value for value in selected if value in allowed_set]


@callback(
    [
        Output("corpus-category-dropdown", "options"),
        Output("corpus-author-dropdown", "options"),
        Output("corpus-title-dropdown", "options"),
        Output("corpus-category-dropdown", "value", allow_duplicate=True),
        Output("corpus-author-dropdown", "value", allow_duplicate=True),
        Output("corpus-title-dropdown", "value", allow_duplicate=True),
    ],
    [
        Input("corpus-category-dropdown", "value"),
        Input("corpus-author-dropdown", "value"),
        Input("corpus-title-dropdown", "value"),
    ],
    prevent_initial_call="initial_duplicate"
)
def synchronize_metadata_filters(selected_categories, selected_authors, selected_titles):
    metadata = get_filter_metadata()
    if metadata.empty:
        return dash.no_update, dash.no_update, dash.no_update, selected_categories, selected_authors, selected_titles

    filtered_for_categories = metadata.copy()
    if selected_authors:
        filtered_for_categories = filtered_for_categories[filtered_for_categories['author'].isin(selected_authors)]
    if selected_titles:
        filtered_for_categories = filtered_for_categories[filtered_for_categories['title_label'].isin(selected_titles)]
    if filtered_for_categories.empty:
        filtered_for_categories = metadata

    filtered_for_authors = metadata.copy()
    if selected_categories:
        filtered_for_authors = filtered_for_authors[filtered_for_authors['category'].isin(selected_categories)]
    if selected_titles:
        filtered_for_authors = filtered_for_authors[filtered_for_authors['title_label'].isin(selected_titles)]
    if filtered_for_authors.empty:
        filtered_for_authors = metadata

    filtered_for_titles = metadata.copy()
    if selected_categories:
        filtered_for_titles = filtered_for_titles[filtered_for_titles['category'].isin(selected_categories)]
    if selected_authors:
        filtered_for_titles = filtered_for_titles[filtered_for_titles['author'].isin(selected_authors)]
    if filtered_for_titles.empty:
        filtered_for_titles = metadata

    available_categories = sorted([value for value in filtered_for_categories['category'].dropna().unique() if value])
    available_authors = sorted([value for value in filtered_for_authors['author'].dropna().unique() if value])
    available_titles = sorted([value for value in filtered_for_titles['title_label'].dropna().unique() if value])

    sanitized_categories = _sanitize_selection(selected_categories, available_categories)
    sanitized_authors = _sanitize_selection(selected_authors, available_authors)
    sanitized_titles = _sanitize_selection(selected_titles, available_titles)

    return (
        _build_option_list(available_categories),
        _build_option_list(available_authors),
        _build_option_list(available_titles),
        sanitized_categories,
        sanitized_authors,
        sanitized_titles,
    )

@callback(
    [Output("corpus-category-dropdown", "value"),
     Output("corpus-author-dropdown", "value"),
     Output("corpus-title-dropdown", "value"),
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
    ctx = dash.callback_context
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    # Store last click timestamp in a hidden div or use local state
    if color != "danger":
        # First click: warn
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, "danger", "Click again to confirm reset"
    else:
        # Second click: reset
        default_filters = {
            'categories': [],
            'authors': [],
            'titles': [],
            'year_range': DEFAULT_YEAR_RANGE.copy(),
            'max_places': 500,
            'corpus_source': 'Corpus Builder'
        }
        return [], [], [], DEFAULT_YEAR_RANGE.copy(), 500, default_filters, "secondary", "Clear Filters (double-click to confirm)"

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
        error = html.Span(f"Error during content search: {e}", style={"color": "#dc2626"})
        return dash.no_update, error, dash.no_update
    if not selected_dhlabids:
        no_matches = html.Span("Fant ingen bøker som matcher innholdssøket.", style={"color": "#dc2626", "fontWeight": "500"})
        return dash.no_update, no_matches, dash.no_update
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
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash, ctx, no_update, callback_context
from dash.exceptions import PreventUpdate
import pandas as pd
from functools import lru_cache
from ...utils.corpus_build import corpus_builder, get_corpus_stats, count_words
from ...utils.db import get_db_connection
import dhlab as dh
from ..common.size_controls import DEFAULT_CARD_SIZES, card_title_bar

DEFAULT_YEAR_RANGE = [1814, 1905]

LABEL_STYLE = {
    'fontSize': '0.72rem',
    'textTransform': 'uppercase',
    'letterSpacing': '0.08em',
    'color': '#475569',
    'fontWeight': 700,
    'marginBottom': '0.15rem'
}

HELP_TEXT_STYLE = {'fontSize': '0.75rem', 'color': '#94a3b8'}

DROPDOWN_STYLE = {
    'backgroundColor': '#f8fafc',
    'border': '1px solid #e2e8f0',
    'borderRadius': '10px',
    'padding': '2px 6px'
}


def _render_year_slider(value=None):
    slider_value = list(value) if value else DEFAULT_YEAR_RANGE.copy()
    return dcc.RangeSlider(
        id='corpus-year-range',
        min=DEFAULT_YEAR_RANGE[0],
        max=DEFAULT_YEAR_RANGE[1],
        step=1,
        value=slider_value,
        marks={i: str(i) for i in range(DEFAULT_YEAR_RANGE[0], DEFAULT_YEAR_RANGE[1] + 1, 10)},
        className="mb-3"
    )


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
                close_button_title="Hide builder",
                minimize_button_id='minimize-corpus-builder',
                minimize_button_title="Minimize builder"
            ),
            className="bg-success-subtle text-dark",
            id="corpus-builder-header"
        ),
        dbc.CardBody([
            html.Div([
                html.Button(
                    [
                        html.I(
                            className="fas fa-filter me-2",
                            style={'color': '#dc2626', 'opacity': 0.65}
                        ),
                        "Tøm alle filtre"
                    ],
                    id='reset-filters-btn',
                    className="btn btn-link p-0",
                    title="Nullstill år/kategori/forfatter/tittel, maks steder og innholdssøk",
                    style={
                        'color': '#475569',
                        'textDecoration': 'none',
                        'boxShadow': 'none',
                        'border': 'none',
                        'fontSize': '0.95rem'
                    }
                ),
                html.Button(
                    [
                        "Nullstill korpus",
                        html.I(
                            className="fas fa-trash-alt ms-2",
                            style={'color': '#dc2626', 'opacity': 0.65}
                        )
                    ],
                    id='reset-corpus-btn-builder',
                    title="Tøm korpus",
                    className="btn btn-link p-0",
                    style={
                        'color': '#475569',
                        'textDecoration': 'none',
                        'boxShadow': 'none',
                        'border': 'none',
                        'fontSize': '0.95rem'
                    }
                )
            ], className="mb-2 d-flex justify-content-between align-items-center gap-2"),
            html.Div([
                html.Div([
                    html.Label("Year Range", style=LABEL_STYLE),
                    html.Div(
                        _render_year_slider(DEFAULT_YEAR_RANGE.copy()),
                        id='corpus-year-slider-wrapper',
                        style={'marginBottom': '0.3rem'}
                    ),
                    dbc.Row([
                        dbc.Col(
                            dbc.Input(
                                id='corpus-year-start-input',
                                type='number',
                                min=DEFAULT_YEAR_RANGE[0],
                                max=DEFAULT_YEAR_RANGE[1],
                                value=DEFAULT_YEAR_RANGE[0],
                                step=1,
                                placeholder="From",
                                className="form-control form-control-sm"
                            ),
                            width=6
                        ),
                        dbc.Col(
                            dbc.Input(
                                id='corpus-year-end-input',
                                type='number',
                                min=DEFAULT_YEAR_RANGE[0],
                                max=DEFAULT_YEAR_RANGE[1],
                                value=DEFAULT_YEAR_RANGE[1],
                                step=1,
                                placeholder="To",
                                className="form-control form-control-sm"
                            ),
                            width=6
                        )
                    ], className="g-2")
                ], className="mb-2"),

                html.Div([
                    html.Label("Metadata", style=LABEL_STYLE),
                    dcc.Dropdown(
                        id='corpus-category-dropdown',
                        options=[{'label': cat, 'value': cat} for cat in categories_list],
                        value=default_filters.get('categories', []),
                        multi=True,
                        placeholder="Categories…",
                        style=DROPDOWN_STYLE
                    )
                ], className="mb-1"),

                html.Div([
                    dcc.Dropdown(
                        id='corpus-author-dropdown',
                        options=[{'label': author, 'value': author} for author in authors_list],
                        value=default_filters.get('authors', []),
                        multi=True,
                        placeholder="Authors…",
                        style=DROPDOWN_STYLE
                    )
                ], className="mb-1"),

                html.Div([
                    dcc.Dropdown(
                        id='corpus-title-dropdown',
                        options=[{'label': title, 'value': title} for title in titles_list],
                        value=default_filters.get('titles', []),
                        multi=True,
                        placeholder="Titles…",
                        style=DROPDOWN_STYLE
                    )
                ], className="mb-2"),

                html.Div([
                    html.Label("Content Filters", style=LABEL_STYLE),
                    dcc.Input(
                        id='content-wordforms-input',
                        type='text',
                        placeholder='e.g. krig, krigen',
                        className="form-control form-control-sm"
                    )
                ], className="mb-3"),

                html.Div([
                    dcc.Loading(
                        id="build-corpus-loading",
                        type="default",
                        children=[
                            dbc.Row([
                                dbc.Col(
                                    dbc.ButtonGroup([
                                        dbc.Button("+", id='corpus-op-union-builder', n_clicks=0, size="sm", color="secondary", outline=True, title="Add to current corpus"),
                                        dbc.Button("&", id='corpus-op-intersection-builder', n_clicks=0, size="sm", color="secondary", outline=True, title="Keep only overlap"),
                                        dbc.Button("-", id='corpus-op-diff-builder', n_clicks=0, size="sm", color="secondary", outline=True, title="Remove from current corpus"),
                                    ], size="sm"),
                                    width="auto"
                                ),
                                dbc.Col(
                                    html.Button([
                                        html.I(className="fas fa-sync-alt me-2"),
                                        "Update"
                                    ], id='build-corpus-btn', className="btn btn-primary w-100"),
                                    width=True
                                )
                            ], className="g-2 align-items-center flex-nowrap"),
                            html.Div(id="build-corpus-status", className="mt-2")
                        ]
                    )
                ])
            ], className="flex-grow-1 d-flex flex-column", style={'minHeight': 0, 'gap': '0.5rem'})
        ], id='corpus-builder-body', style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden'
        })
    ], id="corpus-builder-card", className="shadow position-absolute m-3 dialog-card", style={
        "width": f"{DEFAULT_CARD_SIZES['corpus-builder']['width']}px",
        "height": f"{DEFAULT_CARD_SIZES['corpus-builder']['height']}px",
        "zIndex": 800,
        "display": "none",
        "top": "60px",
        "left": "620px",
        "flexDirection": "column"
    })


@callback(
    Output('corpus-year-start-input', 'value', allow_duplicate=True),
    Output('corpus-year-end-input', 'value', allow_duplicate=True),
    Input('corpus-year-range', 'value'),
    prevent_initial_call=True
)
def sync_year_inputs_from_slider(year_range):
    """Keep precise year inputs in sync with the range slider."""
    year_range = (year_range or DEFAULT_YEAR_RANGE).copy() if isinstance(year_range, list) else list(year_range or DEFAULT_YEAR_RANGE)
    if len(year_range) != 2:
        year_range = DEFAULT_YEAR_RANGE.copy()
    return year_range[0], year_range[1]


@callback(
    Output('corpus-year-slider-wrapper', 'children', allow_duplicate=True),
    Output('corpus-year-start-input', 'value', allow_duplicate=True),
    Output('corpus-year-end-input', 'value', allow_duplicate=True),
    Input('corpus-year-start-input', 'value'),
    Input('corpus-year-end-input', 'value'),
    State('corpus-year-range', 'value'),
    prevent_initial_call=True
)
def sync_year_slider_from_inputs(start_value, end_value, current_range):
    """Update the slider component when users type exact years."""
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate

    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    slider_min, slider_max = DEFAULT_YEAR_RANGE
    current_range = list(current_range or DEFAULT_YEAR_RANGE.copy())

    start_val, end_val = current_range
    changed = False

    if trigger == 'corpus-year-start-input':
        if start_value is None:
            raise PreventUpdate
        new_start = max(slider_min, min(slider_max, int(start_value)))
        if new_start != start_val:
            start_val = new_start
            changed = True
    elif trigger == 'corpus-year-end-input':
        if end_value is None:
            raise PreventUpdate
        new_end = max(slider_min, min(slider_max, int(end_value)))
        if new_end != end_val:
            end_val = new_end
            changed = True

    if start_val > end_val:
        if trigger == 'corpus-year-start-input':
            end_val = start_val
        else:
            start_val = end_val
        changed = True

    if not changed:
        raise PreventUpdate

    slider = _render_year_slider([start_val, end_val])
    return slider, start_val, end_val


@callback(
    Output("corpus-builder-card", "style"),
    Output("corpus-builder-window-state", "data", allow_duplicate=True),
    Output("corpus-builder-body", "style", allow_duplicate=True),
    Output("corpus-controls-container", "style", allow_duplicate=True),
    [Input("open-corpus-builder", "n_clicks"),
     Input("close-corpus-builder", "n_clicks")],
    [State("corpus-builder-card", "style"),
     State("corpus-builder-window-state", "data"),
     State("corpus-builder-body", "style"),
     State("corpus-controls-container", "style")],
    prevent_initial_call=True
)
def toggle_card_visibility(n1, n2, builder_style, window_state, body_style, controls_style):
    """Toggle the visibility of the corpus builder card only."""
    import dash
    from dash import ctx

    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    button_id = ctx.triggered[0]["prop_id"].split(".")[0]

    builder_style = (builder_style or {}).copy()
    controls_style = controls_style or {}
    body_style = (body_style or {}).copy()
    window_state = (window_state or {'minimized': False}).copy()

    MINIMIZE_BODY_PROPS = [
        'display', 'height', 'maxHeight', 'opacity',
        'pointerEvents', 'overflow', 'flex',
        'marginTop', 'marginBottom', 'paddingTop', 'paddingBottom'
    ]

    def _restore_from_minimize(style_dict, state_dict, body_dict):
        restored_state = {'minimized': False}
        stored_height = state_dict.get('stored_height')
        stored_min_height = state_dict.get('stored_min_height')
        stored_body_styles = state_dict.get('stored_body_styles', {})

        if stored_height:
            style_dict['height'] = stored_height
        if stored_min_height is None:
            style_dict.pop('minHeight', None)
        elif stored_min_height:
            style_dict['minHeight'] = stored_min_height

        for prop in MINIMIZE_BODY_PROPS:
            if prop in stored_body_styles:
                value = stored_body_styles[prop]
                if value is None:
                    body_dict.pop(prop, None)
                else:
                    body_dict[prop] = value
            else:
                body_dict.pop(prop, None)

        # Ensure flex layout defaults are restored
        body_dict.setdefault('display', 'flex')
        body_dict.setdefault('flexDirection', 'column')
        body_dict.setdefault('flex', '1 1 auto')
        body_dict.setdefault('minHeight', 0)
        body_dict.setdefault('overflow', 'hidden')

        return restored_state, body_dict

    if button_id == "open-corpus-builder":
        current_display = builder_style.get("display", "none")
        builder_style["display"] = "flex"
        builder_style.pop("transform", None)

        if window_state.get('minimized'):
            window_state, body_style = _restore_from_minimize(builder_style, window_state, body_style)
        else:
            body_style.setdefault('display', 'flex')
            body_style.setdefault('flexDirection', 'column')
            body_style.setdefault('flex', '1 1 auto')
            body_style.setdefault('minHeight', 0)
            body_style.setdefault('overflow', 'hidden')
            body_style['opacity'] = '1'
            body_style['pointerEvents'] = 'auto'

        return builder_style, window_state, body_style, dash.no_update

    if button_id == "close-corpus-builder":
        builder_style["display"] = "none"
        return builder_style, dash.no_update, dash.no_update, dash.no_update

    return dash.no_update, dash.no_update, dash.no_update, dash.no_update

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
     State("content-wordforms-input", "value"),
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
    content_wordforms,
    current_filters,
    operation,
    current_books
):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    if current_filters is None:
        current_filters = {}
    # Show spinner/message while building
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

    content_words = [w.strip() for w in (content_wordforms or '').split(',') if w.strip()]
    apply_content_filter = bool(content_words)

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

    def _resolve_content_pool():
        if incoming_books:
            return incoming_books
        if current_books:
            return current_books
        base = corpus_builder.get_corpus()
        if base:
            return [int(b) for b in base]
        conn = get_db_connection()
        try:
            df_all = pd.read_sql_query("SELECT dhlabid FROM corpus", conn)
            return df_all['dhlabid'].dropna().astype(int).tolist()
        finally:
            conn.close()

    if apply_content_filter:
        content_pool = _resolve_content_pool()
        if not content_pool:
            status_error = html.Span("Fant ingen bøker å bruke for innholdssøk.", style={"color": "#dc2626", "fontWeight": "500"})
            return dash.no_update, status_error, dash.no_update
        try:
            counts_df = count_words(content_pool, content_words)
            dhlabid_sums = counts_df.sum(axis=0)
            content_books = [int(dhl) for dhl, total in dhlabid_sums.items() if total >= 1]
        except Exception as e:
            error = html.Span(f"Error during content search: {e}", style={"color": "#dc2626"})
            return dash.no_update, error, dash.no_update
        incoming_books = sorted(content_books)
        new_filters['content_words'] = content_words
    else:
        new_filters.pop('content_words', None)

    if not incoming_books:
        status_error = html.Span("Fant ingen bøker for valgte filter.", style={"color": "#dc2626", "fontWeight": "500"})
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
    [Output("corpus-category-dropdown", "value", allow_duplicate=True),
     Output("corpus-author-dropdown", "value", allow_duplicate=True),
     Output("corpus-title-dropdown", "value", allow_duplicate=True),
     Output("corpus-year-range", "value", allow_duplicate=True),
     Output("corpus-max-places-slider", "value", allow_duplicate=True),
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
        raise PreventUpdate
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


@callback(
    Output("corpus-category-dropdown", "value", allow_duplicate=True),
    Output("corpus-author-dropdown", "value", allow_duplicate=True),
    Output("corpus-title-dropdown", "value", allow_duplicate=True),
    Output("corpus-year-range", "value", allow_duplicate=True),
    Output("corpus-max-places-slider", "value", allow_duplicate=True),
    Output("content-wordforms-input", "value", allow_duplicate=True),
    Input("reset-filters-btn", "n_clicks"),
    prevent_initial_call=True
)
def reset_filter_controls(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return [], [], [], DEFAULT_YEAR_RANGE.copy(), 500, ""

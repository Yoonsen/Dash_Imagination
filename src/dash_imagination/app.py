import dash
from dash import dcc, html, Input, Output, State, callback, callback_context, ALL
import plotly.graph_objects as go
import pandas as pd
import numpy as np
import dash_bootstrap_components as dbc
import sqlite3
import os
import base64
import io
from dash.exceptions import PreventUpdate
from scipy.spatial import ConvexHull
import math
from dash_imagination.utils.db import get_db_connection
import plotly.express as px
import dhlab as dh
import re
import json
import copy
from flask import request, send_file
from typing import Tuple

#=== initialize

# Determine environment
is_production = os.getenv('ENVIRONMENT', 'development') == 'production'
is_chromebook = os.getenv('ENVIRONMENT', 'development') == 'chromebook'
app_name = os.getenv('APP_NAME', 'imagination-map')  # Default to 'imagination_map' if not set
assets_version = os.getenv('ASSETS_VERSION', 'v20251115')

if is_production:
    db_path = "/app/src/dash_imagination/data/imagination.db"
elif is_chromebook:
    db_path = "/home/yoonsen/Dash_Imagination/src/dash_imagination/data/imagination.db"
else:
    # Development environment - use the correct path directly
    db_path = "/mnt/disk1/Github/Dash_Imagination/src/dash_imagination/data/imagination.db"
    if not os.path.exists(db_path):
        print(f"Warning: Database not found at {db_path}")
        # Try alternative path
        alt_path = "/mnt/disk1/Github/Dash_Imagination/src/data/imagination.db"
        if os.path.exists(alt_path):
            print(f"Found database at alternative path: {alt_path}")
            db_path = alt_path

print(f"Using database at: {db_path}")

# Initialize Dash App
if is_production:
    app = dash.Dash(
        __name__,
        routes_pathname_prefix=f'/{app_name}/',
        requests_pathname_prefix=f"/run/{app_name}/app/",
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ],
        suppress_callback_exceptions=True
    )
else:
    app = dash.Dash(
        __name__,
        external_stylesheets=[
            dbc.themes.BOOTSTRAP,
            "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
        ],
        suppress_callback_exceptions=True
    )

app._assets_version = assets_version

server = app.server

from dash_imagination.components.corpus import create_corpus_controls, create_visualization_controls, create_corpus_builder_card
from dash_imagination.components.places.place_similarity_dialog import create_place_similarity_dialog
from dash_imagination.components.common.size_controls import (
    SIZE_PRESETS,
    CARD_DEFAULT_PRESET,
    DEFAULT_CARD_SIZES,
    card_title_bar,
)
from dash_imagination.components.common.places_table import render_place_preview


def load_places_frame(json_payload):
    if not json_payload:
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
    return pd.read_json(io.StringIO(json_payload), orient='split')


def filter_places_search(df, search_term):
    if df is None or df.empty:
        return df
    if not search_term or len(search_term.strip()) < 3:
        return df
    term = search_term.strip().lower()
    mask = (
        df['token'].astype(str).str.lower().str.contains(term, na=False) |
        df['name'].astype(str).str.lower().str.contains(term, na=False)
    )
    return df[mask]


def truncate_text(value: str, length: int = 40) -> tuple[str, str]:
    if not value:
        return "", ""
    text = str(value)
    return (text if len(text) <= length else text[:length] + "…"), text


def build_html_table(rows, columns, *, table_class="table table-sm table-striped", container_style=None):
    header_cells = [html.Th(label, scope="col") for _, label in columns]
    body_rows = []
    for row in rows:
        cells = []
        for key, _ in columns:
            cells.append(html.Td(row.get(key, "")))
        body_rows.append(html.Tr(cells))
    table = html.Table(
        [html.Thead(html.Tr(header_cells)), html.Tbody(body_rows)],
        className=table_class,
        style={'margin': 0, 'tableLayout': 'fixed', 'width': '100%'}
    )
    wrapper_style = {'flex': '1 1 auto', 'minHeight': 0, 'overflow': 'auto'}
    if container_style:
        wrapper_style.update(container_style)
    return html.Div(table, className="table-flex-container", style=wrapper_style)




SIZE_LIMITS = {
    'width': {'min': 280, 'max': 960},
    'height': {'min': 260, 'max': 900},
}


def _nudge_size(store, card_key, axis, delta):
    base = copy.deepcopy(DEFAULT_CARD_SIZES)
    store = copy.deepcopy(store) if store else base
    dims = store.get(card_key, base[card_key]).copy()
    limits = SIZE_LIMITS[axis]
    dims[axis] = max(limits['min'], min(limits['max'], dims[axis] + delta))
    store[card_key] = dims
    return store


def _apply_size_to_style(store, card_key, current_style):
    base = DEFAULT_CARD_SIZES
    dims = (store or base).get(card_key, base[card_key])
    style = (current_style or {}).copy()
    style['width'] = f"{dims['width']}px"
    style['height'] = f"{dims['height']}px"
    return style


MINIMIZE_BODY_PROPS = [
    'display',
    'height',
    'maxHeight',
    'opacity',
    'pointerEvents',
    'overflow',
    'flex',
    'marginTop',
    'marginBottom',
    'paddingTop',
    'paddingBottom'
]

MINIMIZED_BODY_VALUES = {
    'height': '0px',
    'maxHeight': '0px',
    'opacity': '0',
    'pointerEvents': 'none',
    'overflow': 'hidden',
    'flex': '0 0 auto',
    'marginTop': '0',
    'marginBottom': '0',
    'paddingTop': '0',
    'paddingBottom': '0'
}


def _toggle_window_minimize(card_key, window_state, container_style, body_style):
    """
    Toggle minimized state for floating dialog cards.
    """
    state = (window_state or {}).copy()
    container = (container_style or {}).copy()
    body = (body_style or {}).copy()

    is_minimized = state.get('minimized', False)
    default_height = f"{DEFAULT_CARD_SIZES.get(card_key, {}).get('height', 320)}px"

    if is_minimized:
        restored_height = state.get('stored_height') or default_height
        restored_min_height = state.get('stored_min_height')
        stored_body_styles = state.get('stored_body_styles', {})

        container['height'] = restored_height
        if restored_min_height is None:
            container.pop('minHeight', None)
        else:
            container['minHeight'] = restored_min_height

        for prop in MINIMIZE_BODY_PROPS:
            if prop in stored_body_styles:
                value = stored_body_styles[prop]
                if value is None:
                    body.pop(prop, None)
                else:
                    body[prop] = value
            else:
                body.pop(prop, None)
        return {'minimized': False}, container, body

    new_state = {
        'minimized': True,
        'stored_height': container.get('height', default_height),
        'stored_min_height': container.get('minHeight'),
        'stored_body_styles': {prop: body.get(prop) for prop in MINIMIZE_BODY_PROPS}
    }
    container['height'] = 'auto'
    container['minHeight'] = '0'
    body['display'] = body.get('display', 'flex')
    for prop, value in MINIMIZED_BODY_VALUES.items():
        body[prop] = value
    return new_state, container, body


def _enforce_minimized_dimensions(style, window_state):
    minimized = (window_state or {}).get('minimized')
    if minimized:
        style['height'] = 'auto'
        style['minHeight'] = '0'
    return style


SEARCH_RESULTS_BASE_STYLE = {
    'position': 'absolute',
    'top': '44px',
    'left': 0,
    'minWidth': '340px',
    'backgroundColor': '#ffffff',
    'borderRadius': '16px',
    'boxShadow': '0 24px 60px rgba(15, 23, 42, 0.25)',
    'padding': '16px',
    'maxHeight': '420px',
    'overflow': 'hidden',
    'zIndex': 1200,
    'pointerEvents': 'auto',
    'display': 'none'
}


def _search_results_style(visible: bool) -> dict:
    style = SEARCH_RESULTS_BASE_STYLE.copy()
    style['display'] = 'block' if visible else 'none'
    return style


def _normalize_search_tokens(text: str) -> list[str]:
    return [token for token in re.split(r'\s+', text.strip()) if token]


def _build_like_clause(tokens: list[str], columns: list[str]) -> tuple[str | None, list[str]]:
    if not tokens:
        return None, []
    clauses = []
    params: list[str] = []
    for token in tokens:
        pattern = f"%{token.lower()}%"
        column_clause = ' OR '.join([f"LOWER({col}) LIKE ?" for col in columns])
        clauses.append(f"({column_clause})")
        params.extend([pattern for _ in columns])
    return ' AND '.join(clauses), params


def _fetch_place_overview(token: str) -> dict | None:
    if not token:
        return None
    conn = get_db_connection()
    try:
        info_df = pd.read_sql_query(
            """
            SELECT 
                p.token,
                p.modern AS name,
                p.latitude,
                p.longitude,
                COUNT(DISTINCT b.dhlabid) AS book_count,
                COALESCE(SUM(b.book_count), 0) AS frequency
            FROM places p
            LEFT JOIN books b ON p.token = b.token
            WHERE LOWER(p.token) = LOWER(?)
            GROUP BY p.token, p.modern, p.latitude, p.longitude
            """,
            conn,
            params=(token,)
        )
        if info_df.empty:
            return None
        info = info_df.iloc[0]
        books_df = pd.read_sql_query(
            """
            SELECT 
                c.title,
                c.author,
                c.year,
                c.urn,
                c.dhlabid,
                b.book_count AS mentions
            FROM books b
            JOIN corpus c ON b.dhlabid = c.dhlabid
            WHERE b.token = ?
            ORDER BY b.book_count DESC, c.year DESC
            LIMIT 20
            """,
            conn,
            params=(token,)
        )
        return {
            'token': info['token'],
            'name': info.get('name'),
            'latitude': info.get('latitude'),
            'longitude': info.get('longitude'),
            'book_count': int(info.get('book_count') or 0),
            'frequency': int(info.get('frequency') or 0),
            'books': books_df.to_dict('records')
        }
    finally:
        conn.close()


def _render_place_summary_from_search(place: dict) -> html.Div:
    books = place.get('books', [])
    header = html.Div([
        html.H5(place.get('token'), style={'marginBottom': '4px'}),
        html.P(
            f"Modern name: {place.get('name')}" if place.get('name') else "Historisk navn",
            style={'fontSize': '14px', 'color': '#666'} if place.get('name') else {'fontSize': '14px', 'color': '#94a3b8'}
        ),
        html.P(
            f"Appears in {place.get('book_count', 0):,} books with {place.get('frequency', 0):,} total mentions",
            style={'marginTop': '8px'}
        )
    ])
    book_list = html.Div([
        html.Div([
            html.A(
                f"{row.get('title')} ({row.get('year')})",
                href=f"https://www.nb.no/items/{row.get('urn')}" if row.get('urn') else "#",
                target="_blank",
                style={'fontWeight': '500', 'color': '#1a56db', 'textDecoration': 'none'}
            ),
            html.Div([
                html.Span(f"by {row.get('author')}", style={'color': '#666', 'fontSize': '13px'}),
                html.Span(
                    f" • {int(row.get('mentions', 0)):,} mentions",
                    style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'}
                )
            ], style={'display': 'flex', 'justifyContent': 'space-between'})
        ], style={'marginBottom': '10px', 'paddingBottom': '8px', 'borderBottom': '1px solid #eee'})
        for row in books if row.get('title')
    ]) if books else html.Div("No book details available", style={'color': '#475569'})

    return html.Div([header, html.Hr(style={'margin': '10px 0'}), book_list])


def _fetch_author_book_ids(author_name: str) -> list[int]:
    if not author_name:
        return []
    conn = get_db_connection()
    try:
        pattern = f"%{author_name}%"
        df = pd.read_sql_query(
            """
            SELECT DISTINCT dhlabid
            FROM corpus
            WHERE author IS NOT NULL
            AND TRIM(author) != ''
            AND LOWER(author) LIKE LOWER(?)
            """,
            conn,
            params=(pattern,)
        )
        if df.empty:
            return []
        return df['dhlabid'].dropna().astype(int).tolist()
    finally:
        conn.close()


def build_places_tab(summary_id, table_id, download_btn_id, download_id, apply_btn_id,
                     action_prefix=None, include_resample=False,
                     activate_btn_id=None, source_key=None, activate_title=None,
                     highlight_toggle_id=None, extra_controls=None):
    def _normalize_prefix(prefix):
        if prefix is None:
            return []
        if isinstance(prefix, (list, tuple)):
            return list(prefix)
        return [prefix]

    action_children = _normalize_prefix(action_prefix)
    if activate_btn_id and source_key:
        action_children.append(
            dbc.Button(
                html.I(className="far fa-lightbulb"),
                id=activate_btn_id,
                color="light",
                size="sm",
                className="places-icon-btn places-lamp-btn",
                title=activate_title or "Vis denne listen på kartet",
                n_clicks=0
            )
        )
    if highlight_toggle_id:
        action_children.append(
            dbc.Button(
                html.I(className="far fa-highlighter"),
                id=highlight_toggle_id,
                color="light",
                size="sm",
                className="places-icon-btn",
                title="Toggle collocation highlight",
                n_clicks=0
            )
        )
    if include_resample:
        action_children.append(
            dbc.Button(
                html.I(className="fas fa-sync-alt"),
                id='resample-places',
                color="light",
                size="sm",
                className="places-icon-btn",
                title="Resample places"
            )
        )
    action_children.append(
        dbc.Button(
            html.I(className="fas fa-arrow-down"),
            id=download_btn_id,
            color="light",
            size="sm",
            className="places-icon-btn",
            title="Last ned CSV"
        )
    )

    summary_block = html.Div(
        id=summary_id,
        className="text-muted",
        style={'fontSize': '0.85rem'}
    )
    if action_children:
        toolbar = html.Div([
            summary_block,
            html.Div(action_children, className="d-flex align-items-center gap-2 flex-wrap justify-content-end")
        ], className="places-tab-toolbar d-flex align-items-center justify-content-between")
    else:
        toolbar = summary_block

    children = []
    if extra_controls is not None:
        children.append(extra_controls)
    children.extend([
        toolbar,
        html.Div(id=table_id, style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'overflowY': 'auto',
            'border': '1px solid #eee',
            'borderRadius': '6px',
            'padding': '4px',
            'backgroundColor': '#fff'
        }),
        dcc.Download(id=download_id)
    ])

    return html.Div(children, className="places-tab-panel", style={
        'display': 'flex',
        'flexDirection': 'column',
        'flex': '1 1 auto',
        'minHeight': 0,
        'gap': '0.5rem'
    })


def create_collocation_controls():
    return html.Div([
        html.Label("Keywords (comma-separated)", className="form-label"),
        dbc.Input(
            id='collocation-words-input',
            type='text',
            placeholder='e.g. krig, krigen',
            size='sm',
            className="mb-2"
        ),
        html.Div([
            html.Span("Before", className="me-1 text-muted small"),
            dbc.Input(
                id='collocation-before-input',
                type='number',
                min=1,
                max=200,
                step=1,
                value=50,
                size='sm',
                style={'maxWidth': '90px'}
            ),
            html.Span("After", className="ms-3 me-1 text-muted small"),
            dbc.Input(
                id='collocation-after-input',
                type='number',
                min=1,
                max=200,
                step=1,
                value=50,
                size='sm',
                style={'maxWidth': '90px'}
            ),
            dbc.Button(
                html.Span("Go", className="px-2"),
                id='run-collocations',
                color='secondary',
                size='sm',
                className="ms-3"
            )
        ], className="d-flex align-items-center flex-wrap gap-1 mb-2"),
        dcc.Loading(
            html.Div(id='collocation-results', className="text-muted", style={'minHeight': '1.5rem'}),
            type='default'
        )
    ], className="collocation-controls", style={
        'flex': '0 0 auto',
        'border': '1px solid #e2e8f0',
        'borderRadius': '6px',
        'padding': '0.75rem',
        'backgroundColor': '#fff',
        'boxShadow': '0 1px 2px rgba(15,23,42,0.05)'
    })


def create_collocation_card():
    return dbc.Card([
        dbc.CardHeader(
            card_title_bar(
                'collocation-card',
                'fa fa-highlighter',
                "Collocations",
                close_button_id='close-collocations',
                close_button_title="Hide collocation card",
                minimize_button_id='minimize-collocation-card',
                minimize_button_title="Minimize collocation card"
            ),
            className="bg-warning-subtle text-dark",
            id='collocation-card-header'
        ),
        dbc.CardBody([
            create_collocation_controls(),
            html.Div(
                build_places_tab(
                    'places-collocation-summary',
                    'places-collocation-table',
                    'download-places-collocation-btn',
                    'download-places-collocations',
                    'apply-places-collocations',
                    activate_btn_id='activate-places-collocations',
                    source_key='collocations',
                    activate_title="Vis kollokasjonslisten på kartet",
                    highlight_toggle_id='toggle-collocation-highlight'
                ),
                className="flex-grow-1 d-flex flex-column",
                style={'minHeight': 0}
            )
        ], id='collocation-card-body', style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '0.75rem',
            'overflow': 'hidden'
        })
    ], id='collocation-card', className="position-absolute dialog-card", style={
        'width': f"{DEFAULT_CARD_SIZES['collocation-card']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['collocation-card']['height']}px",
        'zIndex': 800,
        'display': 'none',
        'top': '130px',
        'left': '620px',
        'cursor': 'grab',
        'flexDirection': 'column'
    })


CARD_CHIP_GROUPS = [
    {
        'group_id': 'corpus',
        'label': 'Corpus',
        'pill_class': 'chip-pill-corpus',
        'children': [
            {
                'chip_id': 'card-chip-corpus',
                'label': 'Corpus',
                'subtitle': 'View',
                'color_class': 'chip-corpus',
                'title': 'Toggle Corpus View'
            },
            {
                'chip_id': 'card-chip-builder',
                'label': 'Corpus',
                'subtitle': 'Modify',
                'color_class': 'chip-builder',
                'title': 'Toggle Corpus Modify'
            }
        ]
    },
    {
        'group_id': 'places',
        'label': 'Places',
        'pill_class': 'chip-pill-places',
        'children': [
            {
                'chip_id': 'card-chip-places',
                'label': 'Places',
                'subtitle': 'Liste',
                'color_class': 'chip-places',
                'title': 'Toggle Places dialog'
            },
            {
                'chip_id': 'card-chip-collocations',
                'label': 'Places',
                'subtitle': 'Coll',
                'color_class': 'chip-collocations',
                'title': 'Toggle Collocations'
            },
            {
                'chip_id': 'card-chip-similarity',
                'label': 'Places',
                'subtitle': 'Sim',
                'color_class': 'chip-similarity',
                'title': 'Toggle Place Similarity'
            }
        ]
    }
]

CHIP_GROUP_TRIGGER_IDS = [f"chip-trigger-{group['group_id']}" for group in CARD_CHIP_GROUPS]
CHIP_CHILD_IDS = [
    child['chip_id']
    for group in CARD_CHIP_GROUPS
    for child in group['children']
]
CHIP_LAUNCHER_IDS = [f"chip-launcher-{group['group_id']}" for group in CARD_CHIP_GROUPS]

WINDOW_CONTROL_CONFIG = [
    {
        'card_key': 'place-summary',
        'store_id': 'place-summary-window-state',
        'container_id': 'place-summary-container',
        'body_id': 'place-summary-body',
        'minimize_id': 'minimize-place-summary',
        'close_id': 'close-summary'
    },
    {
        'card_key': 'places',
        'store_id': 'place-names-window-state',
        'container_id': 'place-names-container',
        'body_id': 'place-names-body',
        'minimize_id': 'minimize-place-names',
        'close_id': 'close-place-names'
    },
    {
        'card_key': 'corpus-controls',
        'store_id': 'corpus-controls-window-state',
        'container_id': 'corpus-controls-container',
        'body_id': 'corpus-controls-body',
        'minimize_id': 'minimize-corpus-controls',
        'close_id': 'close-corpus'
    },
    {
        'card_key': 'visualization-controls',
        'store_id': 'visualization-controls-window-state',
        'container_id': 'visualization-controls-container',
        'body_id': 'visualization-controls-body',
        'minimize_id': 'minimize-visualization-controls',
        'close_id': 'close-visualization'
    },
    {
        'card_key': 'corpus-builder',
        'store_id': 'corpus-builder-window-state',
        'container_id': 'corpus-builder-card',
        'body_id': 'corpus-builder-body',
        'minimize_id': 'minimize-corpus-builder',
        'close_id': 'close-corpus-builder'
    },
    {
        'card_key': 'collocation-card',
        'store_id': 'collocation-card-window-state',
        'container_id': 'collocation-card',
        'body_id': 'collocation-card-body',
        'minimize_id': 'minimize-collocation-card',
        'close_id': 'close-collocations'
    },
    {
        'card_key': 'similarity-card',
        'store_id': 'similarity-card-window-state',
        'container_id': 'place-similarity-dialog',
        'body_id': 'place-similarity-body',
        'minimize_id': 'minimize-similarity-card',
        'close_id': 'close-similarity'
    }
]


def create_card_launcher():
    group_elements = [dcc.Store(id='chip-group-open', data=None)]
    for group in CARD_CHIP_GROUPS:
        trigger_id = f"chip-trigger-{group['group_id']}"
        group_elements.append(
            html.Div(
                [
                    html.Button(
                        html.Span(group['label'], className="chip-pill-label"),
                        id=trigger_id,
                        className=f"chip-pill {group['pill_class']}",
                        title=f"Show {group['label']} actions",
                        n_clicks=0
                    ),
                    html.Div(
                        [
                            html.Button(
                                [
                                    html.Span(card['label'], className="card-chip-label"),
                                    html.Span(card['subtitle'], className="card-chip-subtext")
                                ],
                                id=card['chip_id'],
                                className=f"card-chip chip-option {card['color_class']}",
                                title=card['title'],
                                n_clicks=0
                            )
                            for card in group['children']
                        ],
                        id=f"chip-options-{group['group_id']}",
                        className="chip-options-menu"
                    )
                ],
                id=f"chip-launcher-{group['group_id']}",
                className="chip-launcher-group"
            )
        )
    group_elements.append(
        html.Button(
            [
                html.Span("Viz", className="card-chip-label"),
                html.Span("Ctrl", className="card-chip-subtext")
            ],
            id='card-chip-visualization',
            className="chip-pill chip-pill-visualization",
            title="Toggle Visualization Controls",
            n_clicks=0
        )
    )
    return html.Div(group_elements, id='card-launcher')


@app.callback(
    Output('chip-group-open', 'data'),
    [Input(trigger_id, 'n_clicks') for trigger_id in (*CHIP_GROUP_TRIGGER_IDS, *CHIP_CHILD_IDS)],
    State('chip-group-open', 'data'),
    prevent_initial_call=True
)
def toggle_chip_group(*callback_args):
    open_group = callback_args[-1] if callback_args else None
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id in CHIP_GROUP_TRIGGER_IDS:
        group_id = trigger_id.replace('chip-trigger-', '')
        if open_group == group_id:
            return None
        return group_id
    if trigger_id in CHIP_CHILD_IDS:
        return None
    raise PreventUpdate


@app.callback(
    [Output(launcher_id, 'className') for launcher_id in CHIP_LAUNCHER_IDS],
    Input('chip-group-open', 'data')
)
def reflect_chip_group_state(open_group):
    base_class = 'chip-launcher-group'
    return [
        f"{base_class} open" if open_group == group['group_id'] else base_class
        for group in CARD_CHIP_GROUPS
    ]


def _register_window_callbacks():
    for cfg in WINDOW_CONTROL_CONFIG:
        minimize_id = cfg['minimize_id']
        close_id = cfg['close_id']
        store_id = cfg['store_id']
        container_id = cfg['container_id']
        body_id = cfg['body_id']
        card_key = cfg['card_key']

        @app.callback(
            Output(store_id, 'data'),
            Output(container_id, 'style', allow_duplicate=True),
            Output(body_id, 'style', allow_duplicate=True),
            Input(minimize_id, 'n_clicks'),
            Input(close_id, 'n_clicks'),
            State(store_id, 'data'),
            State(container_id, 'style'),
            State(body_id, 'style'),
            prevent_initial_call=True
        )
        def _handle_window_controls(min_clicks, close_clicks, state, container_style, body_style, cfg=cfg, card_key=card_key):
            ctx = dash.callback_context
            if not ctx.triggered:
                raise PreventUpdate
            trigger = ctx.triggered[0]['prop_id'].split('.')[0]
            if trigger == cfg['close_id']:
                # Ensure state resets and body is visible before the actual close callback hides the card.
                # Avoid touching the container style so the close-specific callback remains in charge of display.
                if state and state.get('minimized'):
                    restored_state, _, restored_body = _toggle_window_minimize(
                        card_key,
                        state,
                        container_style,
                        body_style
                    )
                    restored_state['minimized'] = False
                    return restored_state, dash.no_update, restored_body
                return {'minimized': False}, dash.no_update, dash.no_update
            if trigger == cfg['minimize_id']:
                new_state, new_container_style, new_body_style = _toggle_window_minimize(
                    card_key,
                    state,
                    container_style,
                    body_style
                )
                return new_state, new_container_style, new_body_style
            raise PreventUpdate


_register_window_callbacks()

# Database Connection & Queries
def pdquery(conn, query, params=()):
    return pd.read_sql_query(query, conn, params=params)

def get_authors():
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT author FROM corpus WHERE author IS NOT NULL ORDER BY author")
    conn.close()
    # Split authors on '/', strip whitespace, flatten, deduplicate, and sort
    authors = set()
    for author_str in df['author'].dropna():
        for author in str(author_str).split('/'):
            author = author.strip()
            if author:
                authors.add(author)
    return sorted(authors)

def get_categories():
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT category FROM corpus WHERE category IS NOT NULL ORDER BY category")
    conn.close()
    categories = [str(category) for category in df['category'].tolist() if category is not None]
    return categories

def get_titles():
    conn = get_db_connection()
    df = pdquery(conn, "SELECT DISTINCT title, year FROM corpus WHERE title IS NOT NULL ORDER BY title")
    title_year_list = []
    for _, row in df.iterrows():
        title = row['title']
        year = row['year']
        if title is not None:
            year_str = f"({year})" if year is not None else "(n.d.)"
            title_year_list.append(f"{title} {year_str}")
    conn.close()
    return title_year_list

# Initialize variables before layout
default_filters = {
    'categories': [],
    'titles': [],
    'sample_size': 0,
    'max_places': 500,
    'year_range': [1814, 1905]
}


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
    df = get_all_places_for_corpus(book_ids)
    if df.empty:
        return []
    return df['token'].dropna().astype(str).unique().tolist()


def fetch_books_for_tokens(tokens):
    if not tokens:
        return []
    conn = get_db_connection()
    try:
        placeholders = ','.join(['?'] * len(tokens))
        df = pd.read_sql_query(
            f"SELECT DISTINCT dhlabid FROM books WHERE token IN ({placeholders})",
            conn,
            params=tuple(tokens)
        )
    finally:
        conn.close()
    if df.empty:
        return []
    return df['dhlabid'].dropna().astype(int).tolist()

def get_places_for_map(filters=None, books=None, return_total=False, selected_tokens=None):
    """Get places data for the map visualization."""
    filters = filters or {}
    books = list(books or [])
    tokens = [str(t) for t in (selected_tokens or [])]

    MAX_PLACES = 2000  # Hard limit for map performance

    if not books and not tokens:
        empty = pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
        return (empty, 0) if return_total else empty

    conn = get_db_connection()
    try:
        if tokens:
            if not books:
                empty = pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
                return (empty, 0) if return_total else empty

            query = """
            WITH selected_places AS (
                SELECT 
                    p.token,
                    p.modern as name,
                    p.latitude,
                    p.longitude
                FROM places p
                WHERE p.token IN ({})
                AND p.latitude IS NOT NULL 
                AND p.longitude IS NOT NULL
                AND p.latitude != '0'
                AND p.longitude != '0'
            )
            SELECT 
                sp.token,
                sp.name,
                sp.latitude,
                sp.longitude,
                SUM(b.book_count) as frequency,
                COUNT(DISTINCT b.dhlabid) as book_count
            FROM selected_places sp
            LEFT JOIN books b ON sp.token = b.token
            WHERE b.dhlabid IN ({})
            GROUP BY sp.token, sp.name, sp.latitude, sp.longitude
            """
            query = query.format(
                ','.join(['?'] * len(tokens)),
                ','.join(['?'] * len(books))
            )
            params = tuple(tokens + books)
            places_df = pd.read_sql_query(query, conn, params=params)
        else:
            query = """
            SELECT 
                b.token,
                p.modern as name,
                p.latitude,
                p.longitude,
                SUM(b.book_count) as frequency,
                COUNT(DISTINCT b.dhlabid) as book_count
            FROM books b
            JOIN places p ON b.token = p.token
            WHERE b.dhlabid IN ({})
            AND p.latitude IS NOT NULL 
            AND p.longitude IS NOT NULL
            AND p.latitude != '0'
            AND p.longitude != '0'
            GROUP BY b.token, p.modern, p.latitude, p.longitude
            ORDER BY frequency DESC
            """
            if not books:
                empty = pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
                return (empty, 0) if return_total else empty
            query = query.format(','.join(['?'] * len(books)))
            places_df = pd.read_sql_query(query, conn, params=tuple(books))

        places_df['latitude'] = pd.to_numeric(places_df['latitude'], errors='coerce')
        places_df['longitude'] = pd.to_numeric(places_df['longitude'], errors='coerce')

        user_max = filters.get('max_places', 0)
        effective_max = min(user_max if user_max and user_max > 0 else MAX_PLACES, MAX_PLACES)
        places_df = places_df.head(effective_max)

        if return_total:
            total = len(places_df)
            return places_df, total
        return places_df
    finally:
        conn.close()

def get_place_details(token, books, page=1, per_page=20):
    """Get details about a place from the database."""
    conn = get_db_connection()
    try:
        if not books:
           return pd.DataFrame(), 0

        
        # Query to get book details with pagination
        query = """
        WITH place_stats AS (
            SELECT 
                COUNT(DISTINCT b.dhlabid) as total_books,
                SUM(b.book_count) as total_mentions
            FROM books b
            WHERE b.token = ?
            AND b.dhlabid IN ({})
        ),
        book_mentions AS (
            SELECT 
                b.dhlabid,
                b.book_count as mention_count
            FROM books b
            WHERE b.token = ?
            AND b.dhlabid IN ({})
        )
        SELECT 
            c.title,
            c.author,
            c.year,
            c.dhlabid,
            c.urn,
            bm.mention_count,
            (SELECT total_books FROM place_stats) as total_books,
            (SELECT total_mentions FROM place_stats) as total_mentions
        FROM book_mentions bm
        JOIN corpus c ON bm.dhlabid = c.dhlabid
        ORDER BY c.year DESC, c.title
        LIMIT ? OFFSET ?
        """.format(','.join(['?'] * len(books)), ','.join(['?'] * len(books)))
        
        # Get the data
        params = [token] + books + [token] + books + [per_page, (page - 1) * per_page]
        df = pd.read_sql_query(query, conn, params=params)
        
        # Get total count for pagination
        count_query = """
        SELECT COUNT(DISTINCT c.title) as total
        FROM books b
        JOIN corpus c ON b.dhlabid = c.dhlabid
        WHERE b.token = ?
        AND b.dhlabid IN ({})
        """.format(','.join(['?'] * len(books)))
        
        total = pd.read_sql_query(count_query, conn, params=[token] + books).iloc[0]['total']
        
        return df, total
        
    finally:
        conn.close()

# Initialize lists with defaults
authors_list = ["Ibsen", "Bjørnson", "Collett", "Lie", "Kielland"]
categories_list = ["Fiksjon", "Sakprosa", "Poesi", "Drama"]
titles_list = ["Et dukkehjem (1879)", "Synnøve Solbakken (1857)", "Amtmandens Døttre (1854)"]

try:
    authors_list = get_authors()
    categories_list = get_categories()
    titles_list = get_titles()
except Exception as e:
    print(f"Error loading filter options: {e}")

# App Layout
app.layout = html.Div([
    # Main map area (bottom layer)
    html.Div([
        dcc.Graph(
            id='main-map',
            style={'height': '100vh'},
            config={
                'displayModeBar': False,  # Hide the mode bar
                'scrollZoom': True,
                'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                'displaylogo': False,
                'showTips': True,
                'showLink': False,
                'showEditInChartStudio': False,
                'showSendToCloud': False,
                'responsive': True,
                'editable': False,
                'edits': {
                    'shapePosition': False,
                    'annotationPosition': False
                }
            }
        ),
        # Loading overlay
        html.Div([
            html.Div([
                html.I(className="fas fa-spinner fa-spin", style={'fontSize': '24px', 'marginRight': '10px'}),
                html.Span("Preparing places...", style={'fontSize': '16px'})
            ], style={
                'backgroundColor': 'rgba(255, 255, 255, 0.9)',
                'padding': '15px 25px',
                'borderRadius': '8px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)',
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'center'
            })
        ], id='loading-overlay', style={
            'position': 'absolute',
            'top': '50%',
            'left': '50%',
            'transform': 'translate(-50%, -50%)',
            'zIndex': 1000,
            'display': 'none'
        })
    ], style={'position': 'absolute', 'top': 0, 'left': 0, 'right': 0, 'bottom': 0}),
    
    # Top bar (top layer with translucent background)
    html.Div([
        # Left section with search and corpus controls
        html.Div([
            # Search field
            html.Div([
                html.Div([
                    html.I(className="fas fa-search", style={
                        "color": "#666",
                        "marginRight": "8px",
                        "fontSize": "16px"
                    }),
                    dcc.Input(
                        id="global-place-search",
                        type="text",
                        placeholder="Søk i ImagiNation...",
                        style={
                            "width": "100%",
                            "height": "100%",
                            "border": "none",
                            "outline": "none",
                            "fontSize": "14px",
                            "color": "#333",
                            "backgroundColor": "transparent",
                            "padding": "0"
                        }
                    )
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "0 12px",
                    "height": "36px",
                    "backgroundColor": "white",
                    "borderRadius": "8px",
                    "boxShadow": "0 2px 6px rgba(0,0,0,0.15)",
                    "transition": "box-shadow 0.3s ease",
                    "pointerEvents": "auto",
                    "width": "320px",
                    "flexShrink": "0"
                }),
                html.Div(id='global-search-results', style=_search_results_style(False))
            ], style={
                "display": "flex",
                "flexDirection": "column",
                "alignItems": "stretch",
                "flexShrink": "0",
                "position": "relative"
            }),

            # Buttons container
            html.Div([
                html.Button(
                    html.I(className="fas fa-sliders-h"),
                    id='visualization-button',
                    style={
                        'padding': '8px',
                        'backgroundColor': 'white',
                        'color': '#475569',
                        'border': 'none',
                        'borderRadius': '50%',
                        'cursor': 'pointer',
                        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
                        'transition': 'all 0.2s',
                        'width': '36px',
                        'height': '36px',
                        'display': 'flex',
                        'alignItems': 'center',
                        'justifyContent': 'center',
                        'fontSize': '14px',
                        'flexShrink': '0'  # Prevent the button from shrinking
                    }
                )
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'marginLeft': '8px',
                'flexShrink': '0'
            })
        ], style={
            'display': 'flex',
            'flexDirection': 'row',  # Change to horizontal layout
            'alignItems': 'center',
            'position': 'absolute',
            'left': '20px',
            'top': '20px',
            'zIndex': 1000,
            'pointerEvents': 'auto',
            'flexWrap': 'wrap',  # Allow wrapping when needed
            'gap': '8px',  # Add gap between wrapped items
            'maxWidth': 'calc(100% - 180px)'  # Reserve space for map view button
        }),

        # Right section with map/heatmap toggle
        html.Div([
            dbc.ButtonGroup([
                dbc.Button("Map", id='map-mode-map', n_clicks=0, color="secondary", size="sm",
                           active=True, className="map-mode-btn"),
                dbc.Button("Heatmap", id='map-mode-heat', n_clicks=0, color="secondary", size="sm",
                           active=False, outline=True, className="map-mode-btn")
            ], size="sm", className="map-mode-button-group")
        ], style={
            'position': 'absolute',
            'right': '20px',
            'top': '20px',
            'zIndex': 1000,
            'pointerEvents': 'auto',
            'flexShrink': '0'
        }),
    ], style={
        'position': 'fixed',
        'top': 0,
        'left': 0,
        'right': 0,
        'height': '80px',
        'backgroundColor': 'rgba(255, 255, 255, 0)',
        'zIndex': 1000,
        'pointerEvents': 'none',
        'padding': '0 20px',  # Add padding for better mobile spacing
        'display': 'flex',
        'justifyContent': 'space-between',
        'alignItems': 'center'
    }),

    # Rest of the components...
    html.Div(id='cached-data', style={'display': 'none'}),

    # Map controls in a modal
    create_corpus_controls(categories_list, titles_list, default_filters),
    create_visualization_controls(categories_list, titles_list, default_filters),
    create_card_launcher(),

    # ImagiNation info button and modal
    html.Div([
        html.Button([
            html.H3("ImagiNation", style={
                'margin': '0',
                'fontWeight': '400',
                'color': '#333',
                'fontSize': '20px'
            })
        ], 
        id='info-button',
        style={
            'background': 'rgba(255,255,255,0.6)',
            'border': 'none',
            'borderRadius': '4px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.2)',
            'padding': '8px 12px',
            'cursor': 'pointer',
            'textAlign': 'left',
            'width': '100%'
        }),
        
        # Modal for project information
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("About the ImagiNation Project")),
            dbc.ModalBody([
                html.H5("Project Overview"),
                html.P("The ImagiNation project maps places mentioned in Norwegian literature, visualizing the geography of our literary imagination."),
                
                html.H5("Tools & Resources"),
                html.P([
                    "Build your own corpus with our ",
                    html.A("Corpus App", 
                           href="https://korpus.imagination.it.ntnu.no/", 
                           target="_blank",
                           style={'fontWeight': 'bold'})
                ]),
                
                html.H5("How to Use This Map"),
                html.P("Use the controls to toggle between map and heatmap views. Enable clustering for a clearer overview of dense areas. Click on places to see details about their mentions in literature."),
                
                html.H5("About the Data"),
                html.P("This visualization uses a database of literary works from the National Library of Norway, with place names extracted using natural language processing techniques."),
                
                html.Hr(),
                html.P("A research project by the Norwegian University of Science and Technology (NTNU)", style={'fontSize': '0.9rem', 'color': '#666'}),
            ]),
            dbc.ModalFooter(
                dbc.Button("Close", id="close-info-modal", className="ml-auto")
            ),
        ], id="info-modal", is_open=False, size="lg"),
    ], style={
        'position': 'absolute',
        'bottom': '20px',
        'left': '20px',
        'zIndex': 800,
        'width': 'auto'
    }),
    
    # Place summary container
    dbc.Card([
        dbc.CardHeader(
            card_title_bar(
                'place-summary',
                'fa fa-grip-horizontal',
                "Place Details",
                close_button_id='close-summary',
                close_button_title="Hide place details",
                minimize_button_id='minimize-place-summary',
                minimize_button_title="Minimize place details"
            ),
            className="bg-danger-subtle text-dark",
            id='summary-header'
        ),
        dbc.CardBody([
            html.Div(id='place-summary', style={
                'flex': '1 1 auto',
                'minHeight': 0,
                'overflowY': 'auto'
            })
        ], id='place-summary-body', style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column'
        })
    ], id='place-summary-container', className="position-absolute dialog-card", style={
        'width': f"{DEFAULT_CARD_SIZES['place-summary']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['place-summary']['height']}px",
        'minWidth': '300px',
        'minHeight': '320px',
        'zIndex': 800,
        'display': 'none',
        'top': '100px',  # Position below the top button container
        'left': '140px',  # Align with launcher offset
        'cursor': 'grab',
        'flexDirection': 'column'
    }),

    # Place Names Container
    dbc.Card([
        dbc.CardHeader(
            card_title_bar(
                'places',
                'fa fa-map-marker',
                "Place Names",
                close_button_id='close-place-names',
                close_button_title="Hide place names",
                minimize_button_id='minimize-place-names',
                minimize_button_title="Minimize place names"
            ),
            className="bg-warning-subtle text-dark",
            id='place-names-header'
        ),
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.Label("Search", className="form-label mb-1"),
                    dcc.Input(
                        id='place-search',
                        type='text',
                        placeholder='Type to search...',
                        className="form-control"
                    )
                ], className="flex-fill me-md-3 mb-3 mb-md-0"),
                html.Div([
                    html.Label("Max places", className="form-label mb-1"),
                    dcc.Slider(
                        id='corpus-max-places-slider',
                        min=100,
                        max=2000,
                        step=100,
                        value=500,
                        marks={i: str(i) for i in range(500, 2001, 500)},
                        className="mb-1"
                    )
                ], className="flex-fill")
            ], className="mb-3 d-flex flex-column flex-md-row"),
            html.Div([
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Bruk underliste i heatmap", "value": "subset"}],
                        value=[],
                        id='heatmap-subset-checkbox',
                        switch=True,
                        persistence=True
                    )
                ], className="mb-2", style={'fontSize': '0.85rem', 'flex': '0 0 auto'}),
                html.Div([
                    html.Div([
                        html.Span("Visning", className="places-mode-label"),
                        dbc.ButtonGroup([
                            dbc.Button(
                                "Frekvens",
                                id='places-mode-frequency',
                                n_clicks=0,
                                color="primary",
                                outline=False,
                                size="sm",
                                className="places-mode-btn"
                            ),
                            dbc.Button(
                                "Sampling",
                                id='places-mode-sampling',
                                n_clicks=0,
                                color="light",
                                outline=True,
                                size="sm",
                                className="places-mode-btn"
                            )
                        ], size="sm", className="places-mode-button-group")
                    ], className="places-mode-toggle d-flex align-items-center justify-content-between flex-wrap gap-2"),
                    html.Div([
                        html.Div(
                            build_places_tab(
                                'places-frequency-summary',
                                'places-frequency-table',
                                'download-places-frequency-btn',
                                'download-places-frequency',
                                'apply-places-frequency',
                                action_prefix=html.Span("Frekvenskutt", className="places-tab-pill"),
                                activate_btn_id='activate-places-frequency',
                                source_key='frequency',
                                activate_title="Vis frekvenslisten på kartet"
                            ),
                            id='places-frequency-panel',
                            style={'flex': '1 1 auto', 'minHeight': 0, 'display': 'flex'}
                        ),
                        html.Div(
                            build_places_tab(
                                'places-sampling-summary',
                                'places-sampling-table',
                                'download-places-sampling-btn',
                                'download-places-sampling',
                                'apply-places-sampling',
                                include_resample=True,
                                activate_btn_id='activate-places-sampling',
                                source_key='sampling',
                                activate_title="Vis eksempellisten på kartet"
                            ),
                            id='places-sampling-panel',
                            style={'flex': '1 1 auto', 'minHeight': 0, 'display': 'none'}
                        )
                    ], className="places-mode-panels flex-grow-1 d-flex flex-column", style={'minHeight': 0, 'gap': '0.75rem'})
                ], className="flex-grow-1 d-flex flex-column", style={'minHeight': 0, 'gap': '0.75rem'})
            ], id='place-names-list', style={
                'flex': '1 1 auto',
                'minHeight': 0,
                'display': 'flex',
                'flexDirection': 'column',
                'gap': '0.5rem',
                'overflow': 'hidden'
            })
        ], id='place-names-body', style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column'
        })
    ], id='place-names-container', className="position-absolute dialog-card", style={
        'width': f"{DEFAULT_CARD_SIZES['places']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['places']['height']}px",
        'minWidth': '320px',
        'minHeight': '360px',
        'zIndex': 800,
        'display': 'none',
        'top': '60px',
        'left': '620px',
        'cursor': 'grab',
        'flexDirection': 'column'
    }),

    # Add collocation and similarity dialogs
    create_collocation_card(),
    create_place_similarity_dialog(),

    # Hidden divs and stores
    html.Div(id='reset-status', style={'display': 'none'}),
    dcc.Store(id='filtered-data'),
    dcc.Store(id='selected-place', data=None),
    dcc.Store(id='map-view-state'),
    dcc.Store(id='current-filters', data={}),  # Initialize with empty dict
    dcc.Store(id='upload-state', data=None),

    # Change view-type from Div to Store
    dcc.Store(id='view-type', data='points'),

    # Add this to the app layout, near the other Store components
    dcc.Store(id='current-dhlabids-store', data=[]),
    dcc.Store(id='corpus-operation', data='intersection'),
    dcc.Store(id='places-frequency-data'),
    dcc.Store(id='places-sample-data'),
    dcc.Store(id='places-collocation-data'),
    dcc.Store(id='places-active-mode', data='frequency'),
    dcc.Store(id='heatmap-subset-mode', data='all'),
    dcc.Store(id='dialog-size-store', data=copy.deepcopy(DEFAULT_CARD_SIZES)),
    dcc.Store(id='place-summary-window-state', data={'minimized': False}),
    dcc.Store(id='place-names-window-state', data={'minimized': False}),
    dcc.Store(id='corpus-controls-window-state', data={'minimized': False}),
    dcc.Store(id='visualization-controls-window-state', data={'minimized': False}),
    dcc.Store(id='corpus-builder-window-state', data={'minimized': False}),
    dcc.Store(id='collocation-card-window-state', data={'minimized': False}),
    dcc.Store(id='similarity-card-window-state', data={'minimized': False}),
    dcc.Store(id='global-search-filter-store', data=['places', 'books', 'authors']),
    dcc.Store(id='similarity-places-data'),

    # Add the new corpus builder card
    create_corpus_builder_card(categories_list=categories_list, authors_list=authors_list, titles_list=titles_list),
    # Add interval for clearing download status
    dcc.Interval(id='clear-download-status-interval', interval=6000, n_intervals=0, disabled=True),
    dcc.Store(id='all-places-store'),  # Store for caching all places for current corpus
    dcc.Store(id='collocation-place-tokens', data=[]),
    dcc.Store(id='collocation-highlight', data=[]),
], id='main-container')

# Add custom CSS
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
        <link rel="stylesheet" href="https://code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://code.jquery.com/ui/1.12.1/jquery-ui.min.js"></script>
        <style>
            #place-summary-container {
                /* Removed slow transition */
            }
            #drag-handle {
                cursor: grab;
            }
            #place-summary-container.dragging {
                opacity: 0.7;
            }
            #visualization-button:hover {
                background-color: #1e293b !important;
                transform: scale(1.1);
            }
            .place-item:hover {
                background-color: #f8f9fa;
            }
            .place-item:active {
                background-color: #e9ecef;
            }
            #place-names-container {
                cursor: move;
            }
            #place-names-container.dragging {
                opacity: 0.7;
            }
            /* Resize handle styles */
            .ui-resizable-handle {
                position: absolute;
                background: rgba(148, 163, 184, 0.45);
                border-radius: 2px;
                opacity: 0;
                transition: opacity 0.2s;
                z-index: 1200;
            }
            .ui-resizable-handle:hover,
            .ui-resizable-handle:active {
                opacity: 1;
            }
            .ui-resizable-n,
            .ui-resizable-s {
                left: 0;
                right: 0;
                height: 6px;
                cursor: ns-resize;
            }
            .ui-resizable-n {
                top: -3px;
            }
            .ui-resizable-s {
                bottom: -3px;
            }
            .ui-resizable-e,
            .ui-resizable-w {
                top: 0;
                bottom: 0;
                width: 6px;
                cursor: ew-resize;
            }
            .ui-resizable-e {
                right: -3px;
            }
            .ui-resizable-w {
                left: -3px;
            }
            .ui-resizable-se,
            .ui-resizable-ne,
            .ui-resizable-sw,
            .ui-resizable-nw {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                cursor: pointer;
            }
            .ui-resizable-se {
                right: -6px;
                bottom: -6px;
                cursor: se-resize;
            }
            .ui-resizable-ne {
                right: -6px;
                top: -6px;
                cursor: ne-resize;
            }
            .ui-resizable-sw {
                left: -6px;
                bottom: -6px;
                cursor: sw-resize;
            }
            .ui-resizable-nw {
                left: -6px;
                top: -6px;
                cursor: nw-resize;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                function initializeDraggable(element) {
                    let isDragging = false;
                    let startX, startY;
                    let initialLeft, initialTop;
                    let touchIdentifier = null;
                    
                    const header = element.querySelector('.card-header');
                    if (!header) return;
                    
                    // Mouse event handlers
                    header.addEventListener('mousedown', startDrag);
                    document.addEventListener('mousemove', drag);
                    document.addEventListener('mouseup', stopDrag);
                    
                    // Enhanced touch event handlers
                    header.addEventListener('touchstart', handleTouchStart, { passive: false });
                    document.addEventListener('touchmove', handleTouchMove, { passive: false });
                    document.addEventListener('touchend', handleTouchEnd);
                    document.addEventListener('touchcancel', handleTouchEnd);
                    
                    function startDrag(e) {
                        e.preventDefault();
                        isDragging = true;
                        element.classList.add('dragging');
                        startX = e.clientX;
                        startY = e.clientY;
                        initialLeft = parseInt(window.getComputedStyle(element).left);
                        initialTop = parseInt(window.getComputedStyle(element).top);
                    }
                    
                    function handleTouchStart(e) {
                        if (e.touches.length > 1) return; // Ignore multi-touch
                        e.preventDefault();
                        const touch = e.touches[0];
                        touchIdentifier = touch.identifier;
                        isDragging = true;
                        element.classList.add('dragging');
                        startX = touch.clientX;
                        startY = touch.clientY;
                        initialLeft = parseInt(window.getComputedStyle(element).left);
                        initialTop = parseInt(window.getComputedStyle(element).top);
                    }
                    
                    function drag(e) {
                        if (!isDragging) return;
                        e.preventDefault();
                        
                        const dx = e.clientX - startX;
                        const dy = e.clientY - startY;
                        
                        // Add bounds checking to keep element within viewport
                        const newLeft = Math.max(0, Math.min(window.innerWidth - element.offsetWidth, initialLeft + dx));
                        const newTop = Math.max(0, Math.min(window.innerHeight - element.offsetHeight, initialTop + dy));
                        
                        element.style.left = `${newLeft}px`;
                        element.style.top = `${newTop}px`;
                    }
                    
                    function handleTouchMove(e) {
                        if (!isDragging) return;
                        e.preventDefault();
                        
                        // Find the touch that matches our identifier
                        const touch = Array.from(e.touches).find(t => t.identifier === touchIdentifier);
                        if (!touch) return;
                        
                        const dx = touch.clientX - startX;
                        const dy = touch.clientY - startY;
                        
                        // Add bounds checking to keep element within viewport
                        const newLeft = Math.max(0, Math.min(window.innerWidth - element.offsetWidth, initialLeft + dx));
                        const newTop = Math.max(0, Math.min(window.innerHeight - element.offsetHeight, initialTop + dy));
                        
                        element.style.left = `${newLeft}px`;
                        element.style.top = `${newTop}px`;
                    }
                    
                    function stopDrag() {
                        if (isDragging) {
                            isDragging = false;
                            element.classList.remove('dragging');
                            touchIdentifier = null;
                        }
                    }
                    
                    function handleTouchEnd(e) {
                        e.preventDefault();
                        stopDrag();
                    }
                }
                
                // Initialize all cards
                const cards = [
                    '#place-names-container',
                    '#place-summary-container',
                    '#corpus-controls-container',
                    '#visualization-controls-container',
                    '#place-similarity-dialog'
                ];
                
                cards.forEach(selector => {
                    const element = document.querySelector(selector);
                    if (element) {
                        initializeDraggable(element);
                    }
                });
                
                // Initialize new cards when they become visible
                const observer = new MutationObserver(function(mutations) {
                    mutations.forEach(function(mutation) {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                            const element = mutation.target;
                            if (element.style.display === 'block' && !element.classList.contains('initialized')) {
                                initializeDraggable(element);
                                element.classList.add('initialized');
                            }
                        }
                    });
                });
                
                cards.forEach(selector => {
                    const element = document.querySelector(selector);
                    if (element) {
                        observer.observe(element, { attributes: true });
                    }
                });
            });
        </script>
    </body>
</html>
'''

@app.callback(
    [Output('popup-upload-status', 'children'),
     Output('upload-state', 'data'),
     Output('current-filters', 'data', allow_duplicate=True),
     Output('current-dhlabids-store', 'data', allow_duplicate=True)],
    [Input('popup-upload-corpus', 'contents')],
    [State('popup-upload-corpus', 'filename'),
     State('current-filters', 'data'),
     State('corpus-operation', 'data'),
     State('current-dhlabids-store', 'data')],
    prevent_initial_call=True
)
def update_state_and_filters(contents, filename, current_filters, operation, current_books):
    import pandas as pd
    import io
    import base64
    current_books = current_books or []
    if not contents:
        return html.Div('', style={'display': 'none'}), {}, current_filters, dash.no_update
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        df = pd.read_excel(io.BytesIO(decoded))
        if 'dhlabid' not in df.columns:
            return html.Div('Error: File must contain a dhlabid column', style={'color': 'red'}), {}, current_filters, dash.no_update
        new_books = [int(x) for x in df['dhlabid'].dropna().tolist()]
        if not new_books:
            return html.Div('No valid dhlabids found in file.', style={'color': 'red'}), {}, current_filters, dash.no_update

        updated_books = apply_book_operation(current_books, new_books, operation)
        place_tokens = fetch_place_tokens(updated_books)
        # Update filters to reflect new corpus source
        new_filters = current_filters.copy() if current_filters else default_filters.copy()
        new_filters['corpus_source'] = filename
        new_filters['last_operation'] = operation or "intersection"
        new_filters['selected_tokens'] = place_tokens
        return (
            html.Div('', style={'display': 'none'}),
            {'uploaded': True, 'filename': filename},
            new_filters,
            updated_books
        )
    except Exception as e:
        return html.Div(f'Error processing file: {str(e)}', style={'color': 'red'}), {}, current_filters, dash.no_update


@app.callback(
    Output('corpus-operation', 'data'),
    Input('corpus-op-union-controls', 'n_clicks'),
    Input('corpus-op-intersection-controls', 'n_clicks'),
    Input('corpus-op-diff-controls', 'n_clicks'),
    Input('corpus-op-union-builder', 'n_clicks'),
    Input('corpus-op-intersection-builder', 'n_clicks'),
    Input('corpus-op-diff-builder', 'n_clicks'),
    Input('corpus-op-union-content', 'n_clicks'),
    Input('corpus-op-intersection-content', 'n_clicks'),
    Input('corpus-op-diff-content', 'n_clicks'),
    Input('corpus-op-union-similarity', 'n_clicks'),
    Input('corpus-op-intersection-similarity', 'n_clicks'),
    Input('corpus-op-diff-similarity', 'n_clicks'),
    State('corpus-operation', 'data'),
    prevent_initial_call=True
)
def set_corpus_operation(
    union_controls,
    intersection_controls,
    diff_controls,
    union_builder,
    intersection_builder,
    diff_builder,
    union_content,
    intersection_content,
    diff_content,
    union_similarity,
    intersection_similarity,
    diff_similarity,
    current_operation,
):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    triggered = ctx.triggered[0]['prop_id'].split('.')[0]
    mapping = {
        'corpus-op-union-controls': 'union',
        'corpus-op-intersection-controls': 'intersection',
        'corpus-op-diff-controls': 'difference',
        'corpus-op-union-builder': 'union',
        'corpus-op-intersection-builder': 'intersection',
        'corpus-op-diff-builder': 'difference',
        'corpus-op-union-content': 'union',
        'corpus-op-intersection-content': 'intersection',
        'corpus-op-diff-content': 'difference',
        'corpus-op-union-similarity': 'union',
        'corpus-op-intersection-similarity': 'intersection',
        'corpus-op-diff-similarity': 'difference',
    }
    return mapping.get(triggered, (current_operation or 'intersection'))


def _operation_button_styles(selected: str, target: str) -> Tuple[str, bool]:
    op = (selected or 'intersection').lower()
    active = op == target
    return ('primary' if active else 'secondary', not active)


@app.callback(
    Output('corpus-op-union-controls', 'color'),
    Output('corpus-op-intersection-controls', 'color'),
    Output('corpus-op-diff-controls', 'color'),
    Output('corpus-op-union-controls', 'outline'),
    Output('corpus-op-intersection-controls', 'outline'),
    Output('corpus-op-diff-controls', 'outline'),
    Input('corpus-operation', 'data')
)
def style_corpus_operation_controls(operation):
    c_union, o_union = _operation_button_styles(operation, 'union')
    c_intersection, o_intersection = _operation_button_styles(operation, 'intersection')
    c_diff, o_diff = _operation_button_styles(operation, 'difference')
    return c_union, c_intersection, c_diff, o_union, o_intersection, o_diff


@app.callback(
    Output('corpus-op-union-builder', 'color'),
    Output('corpus-op-intersection-builder', 'color'),
    Output('corpus-op-diff-builder', 'color'),
    Output('corpus-op-union-builder', 'outline'),
    Output('corpus-op-intersection-builder', 'outline'),
    Output('corpus-op-diff-builder', 'outline'),
    Input('corpus-operation', 'data')
)
def style_corpus_operation_builder(operation):
    c_union, o_union = _operation_button_styles(operation, 'union')
    c_intersection, o_intersection = _operation_button_styles(operation, 'intersection')
    c_diff, o_diff = _operation_button_styles(operation, 'difference')
    return c_union, c_intersection, c_diff, o_union, o_intersection, o_diff


@app.callback(
    Output('corpus-op-union-content', 'color'),
    Output('corpus-op-intersection-content', 'color'),
    Output('corpus-op-diff-content', 'color'),
    Output('corpus-op-union-content', 'outline'),
    Output('corpus-op-intersection-content', 'outline'),
    Output('corpus-op-diff-content', 'outline'),
    Input('corpus-operation', 'data')
)
def style_corpus_operation_content(operation):
    c_union, o_union = _operation_button_styles(operation, 'union')
    c_intersection, o_intersection = _operation_button_styles(operation, 'intersection')
    c_diff, o_diff = _operation_button_styles(operation, 'difference')
    return c_union, c_intersection, c_diff, o_union, o_intersection, o_diff


@app.callback(
    Output('corpus-op-union-similarity', 'color'),
    Output('corpus-op-intersection-similarity', 'color'),
    Output('corpus-op-diff-similarity', 'color'),
    Output('corpus-op-union-similarity', 'outline'),
    Output('corpus-op-intersection-similarity', 'outline'),
    Output('corpus-op-diff-similarity', 'outline'),
    Input('corpus-operation', 'data')
)
def style_corpus_operation_similarity(operation):
    c_union, o_union = _operation_button_styles(operation, 'union')
    c_intersection, o_intersection = _operation_button_styles(operation, 'intersection')
    c_diff, o_diff = _operation_button_styles(operation, 'difference')
    return c_union, c_intersection, c_diff, o_union, o_intersection, o_diff


@app.callback(
    Output('collocation-results', 'children'),
    Output('collocation-place-tokens', 'data'),
    Input('run-collocations', 'n_clicks'),
    State('collocation-words-input', 'value'),
    State('collocation-before-input', 'value'),
    State('collocation-after-input', 'value'),
    State('current-dhlabids-store', 'data'),
    State('all-places-store', 'data'),
    prevent_initial_call=True
)
def run_collocation_search(n_clicks, words_value, before, after, current_books, all_places_json):
    if not n_clicks:
        raise PreventUpdate
    if not words_value:
        return html.Div("Enter one or more keywords to analyse collocations.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), []
    if not current_books:
        return html.Div("Corpus is empty. Build or upload a corpus first.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), []

    words = [w.strip() for w in words_value.split(',') if w.strip()]
    if not words:
        return html.Div("No valid keywords provided.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), []

    before = int(before or 50)
    after = int(after or 50)

    conn = get_db_connection()
    try:
        placeholders = ",".join(["?"] * len(current_books))
        query = f"""
            SELECT urn
            FROM corpus
            WHERE dhlabid IN ({placeholders})
              AND urn IS NOT NULL
        """
        urns = pd.read_sql_query(query, conn, params=tuple(current_books))['urn'].dropna().tolist()
    finally:
        conn.close()

    if not urns:
        return html.Div("No URNs found for the current corpus; collocations require identifiable texts.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), []

    sample_size = min(len(urns), 5000)

    try:
        coll = dh.Collocations(urns, words, before=before, after=after, samplesize=sample_size)
        coll_df = coll.frame.copy()
    except Exception as err:
        return html.Div(f"Error retrieving collocations: {err}", style={'color': '#dc2626', 'fontSize': '0.8rem'}), []

    if coll_df is None or coll_df.empty:
        return html.Div("No collocations found for the selected keywords.", style={'color': '#475569', 'fontSize': '0.8rem'}), []

    coll_df = coll_df.reset_index()
    if 'index' in coll_df.columns:
        coll_df = coll_df.rename(columns={'index': 'word'})
    if 'counts' in coll_df.columns:
        coll_df = coll_df.rename(columns={'counts': 'count'})
    elif 'total' in coll_df.columns:
        coll_df = coll_df.rename(columns={'total': 'count'})

    coll_df['word'] = coll_df['word'].astype(str)
    coll_df['lower_word'] = coll_df['word'].str.lower()

    word_counts = coll_df.groupby('lower_word')['count'].sum().to_dict()
    collocate_tokens = set(word_counts.keys())

    if all_places_json:
        places_df = pd.read_json(io.StringIO(all_places_json), orient='split')
    else:
        places_df = get_all_places_for_corpus(current_books)

    matching_places = []
    for _, row in places_df[['token', 'name']].dropna().drop_duplicates().iterrows():
        place_name = str(row['name'])
        tokens = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", place_name.lower())
        tokens = [tok for tok in tokens if tok]
        if not tokens:
            continue
        if all(tok in collocate_tokens for tok in tokens):
            total_count = int(sum(word_counts[tok] for tok in tokens))
            matching_places.append({
                'Place': place_name,
                'Tokens': ", ".join(tokens),
                'Total count': total_count,
                'Token': row['token']
            })

    if not matching_places:
        message = html.Div(
            "Fant ingen steder som matcher dette kollokasjonssøket. Prøv andre søkeord eller vindu.",
            style={'color': '#475569', 'fontSize': '0.85rem'}
        )
        return message, []

    match_df_raw = pd.DataFrame(matching_places)

    def merge_tokens(token_series):
        pieces = []
        for entry in token_series:
            pieces.extend([p.strip() for p in entry.split(',') if p.strip()])
        return ", ".join(sorted(set(pieces)))

    match_df = (
        match_df_raw
        .groupby('Place', as_index=False)
        .agg({
            'Tokens': merge_tokens,
            'Total count': 'sum',
            'Token': 'first'
        })
        .sort_values(by='Total count', ascending=False)
        .head(50)
    )
    tokens = match_df['Token'].dropna().astype(str).unique().tolist()
    summary = html.Div(
        f"Fant {len(tokens)} steder. Se tabellen under for detaljer.",
        style={'color': '#0f172a', 'fontSize': '0.85rem'}
    )
    return summary, tokens

@app.callback(
    Output('collocation-highlight', 'data'),
    Input('toggle-collocation-highlight', 'n_clicks'),
    State('collocation-highlight', 'data'),
    State('collocation-place-tokens', 'data'),
    prevent_initial_call=True
)
def toggle_collocation_highlight(n_clicks, current_highlight, tokens):
    if not n_clicks:
        raise PreventUpdate
    tokens = tokens or []
    if current_highlight:
        return []
    if not tokens:
        raise PreventUpdate
    return tokens


@app.callback(
    Output('toggle-collocation-highlight', 'color'),
    Output('toggle-collocation-highlight', 'children'),
    Input('collocation-highlight', 'data')
)
def style_collocation_highlight_button(highlight_tokens):
    is_active = bool(highlight_tokens)
    color = 'warning' if is_active else 'light'
    icon_style = {'opacity': 0.95 if is_active else 0.6}
    return color, html.I(className='fas fa-highlighter', style=icon_style)


@app.callback(
    Output('places-frequency-data', 'data'),
    Output('places-sample-data', 'data'),
    Output('places-collocation-data', 'data'),
    Input('all-places-store', 'data'),
    Input('corpus-max-places-slider', 'value'),
    Input('resample-places', 'n_clicks'),
    Input('collocation-place-tokens', 'data'),
    State('places-sample-data', 'data')
)
def update_places_datasets(all_places_json, max_places, resample_n, collocation_tokens, current_sample_json):
    import pandas as pd
    ctx = dash.callback_context
    triggered = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    max_places = max_places or 500
    base_columns = ['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count']
    empty_json = pd.DataFrame(columns=base_columns).to_json(date_format='iso', orient='split')
    if not all_places_json:
        return empty_json, empty_json, empty_json

    df = load_places_frame(all_places_json)
    if df.empty:
        return empty_json, empty_json, empty_json

    freq_df = (
        df.sort_values(by='frequency', ascending=False)
        .head(max_places)
        .reset_index(drop=True)
    )
    recompute_sample = triggered in ('all-places-store', 'resample-places') or current_sample_json is None
    if recompute_sample:
        sample_df = sample_places(df, n=max_places).reset_index(drop=True)
    else:
        sample_df = load_places_frame(current_sample_json)
        if sample_df.empty:
            sample_df = sample_places(df, n=max_places).reset_index(drop=True)
        else:
            sample_df = sample_df.head(max_places).reset_index(drop=True)

    tokens = set(collocation_tokens or [])
    if tokens:
        colloc_df = (
            df[df['token'].isin(tokens)]
            .sort_values(by='frequency', ascending=False)
            .head(max_places)
            .reset_index(drop=True)
        )
    else:
        colloc_df = pd.DataFrame(columns=base_columns)

    return (
        freq_df.to_json(date_format='iso', orient='split'),
        sample_df.to_json(date_format='iso', orient='split'),
        colloc_df.to_json(date_format='iso', orient='split')
    )


@app.callback(
    Output('places-active-mode', 'data'),
    Input('places-mode-frequency', 'n_clicks'),
    Input('places-mode-sampling', 'n_clicks'),
    State('places-active-mode', 'data'),
    prevent_initial_call=True
)
def set_places_active_mode(freq_clicks, sampling_clicks, current_mode):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'places-mode-frequency':
        return 'frequency'
    if trigger == 'places-mode-sampling':
        return 'sampling'
    return current_mode or 'frequency'


@app.callback(
    Output('places-frequency-panel', 'style'),
    Output('places-sampling-panel', 'style'),
    Input('places-active-mode', 'data')
)
def toggle_places_mode_panels(active_mode):
    freq_style = {'flex': '1 1 auto', 'minHeight': 0, 'display': 'flex'}
    sample_style = {'flex': '1 1 auto', 'minHeight': 0, 'display': 'flex'}
    if active_mode == 'sampling':
        freq_style['display'] = 'none'
    else:
        sample_style['display'] = 'none'
    return freq_style, sample_style


@app.callback(
    Output('places-mode-frequency', 'color'),
    Output('places-mode-frequency', 'outline'),
    Output('places-mode-sampling', 'color'),
    Output('places-mode-sampling', 'outline'),
    Input('places-active-mode', 'data')
)
def style_places_mode_buttons(active_mode):
    freq_active = (active_mode != 'sampling')
    sample_active = not freq_active
    freq_color = 'primary' if freq_active else 'light'
    sample_color = 'primary' if sample_active else 'light'
    freq_outline = not freq_active
    sample_outline = not sample_active
    return freq_color, freq_outline, sample_color, sample_outline


@app.callback(
    Output('places-frequency-summary', 'children'),
    Output('places-frequency-table', 'children'),
    Input('places-frequency-data', 'data'),
    Input('place-search', 'value'),
    State('selected-place', 'data')
)
def display_frequency_places(freq_json, search_term, selected_place):
    df = load_places_frame(freq_json)
    df = filter_places_search(df, search_term)
    summary, table = render_place_preview(df, selected_place, empty_message="Ingen steder tilgjengelig ennå.")
    return summary, table


@app.callback(
    Output('places-sampling-summary', 'children'),
    Output('places-sampling-table', 'children'),
    Input('places-sample-data', 'data'),
    Input('place-search', 'value'),
    State('selected-place', 'data')
)
def display_sampling_places(sample_json, search_term, selected_place):
    df = load_places_frame(sample_json)
    df = filter_places_search(df, search_term)
    summary, table = render_place_preview(df, selected_place, empty_message="Trykk «Resample Places» for å hente en ny liste.")
    return summary, table


@app.callback(
    Output('places-collocation-summary', 'children'),
    Output('places-collocation-table', 'children'),
    Input('places-collocation-data', 'data'),
    Input('place-search', 'value'),
    State('selected-place', 'data')
)
def display_collocation_places(colloc_json, search_term, selected_place):
    df = load_places_frame(colloc_json)
    if df.empty:
        return (
            html.Div("Kjør et kollokasjonssøk for å fylle denne fanen.", style={'fontSize': '0.85rem'}),
            html.Div("Ingen kollokasjoner funnet.", className="text-muted")
        )
    df = filter_places_search(df, search_term)
    summary, table = render_place_preview(df, selected_place, empty_message="Ingen kollokasjonstreff som matcher søket.")
    return summary, table


def _download_places_frame(json_payload, filename_prefix):
    df = load_places_frame(json_payload)
    if df.empty:
        raise PreventUpdate
    columns = ['token', 'name', 'frequency', 'book_count', 'latitude', 'longitude']
    safe_df = df.reindex(columns=columns)
    return dcc.send_data_frame(safe_df.to_csv, f"{filename_prefix}.csv", index=False)


@app.callback(
    Output('download-places-frequency', 'data'),
    Input('download-places-frequency-btn', 'n_clicks'),
    State('places-frequency-data', 'data'),
    prevent_initial_call=True
)
def download_frequency_places(n_clicks, freq_json):
    return _download_places_frame(freq_json, "places_frequency")


@app.callback(
    Output('download-places-sampling', 'data'),
    Input('download-places-sampling-btn', 'n_clicks'),
    State('places-sample-data', 'data'),
    prevent_initial_call=True
)
def download_sampling_places(n_clicks, sample_json):
    return _download_places_frame(sample_json, "places_sampling")


@app.callback(
    Output('download-places-collocations', 'data'),
    Input('download-places-collocation-btn', 'n_clicks'),
    State('places-collocation-data', 'data'),
    prevent_initial_call=True
)
def download_collocation_places(n_clicks, colloc_json):
    return _download_places_frame(colloc_json, "places_collocations")


@app.callback(
    Output('dialog-size-store', 'data', allow_duplicate=True),
    Input({'type': 'size-btn', 'card': ALL, 'axis': ALL, 'delta': ALL}, 'n_clicks'),
    State('dialog-size-store', 'data'),
    prevent_initial_call=True
)
def handle_size_buttons(n_clicks, store):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    trigger = ctx.triggered[0]
    if not trigger or not trigger['value']:
        raise PreventUpdate

    btn_id = trigger['prop_id'].split('.')[0]
    try:
        btn = json.loads(btn_id)
    except json.JSONDecodeError:
        raise PreventUpdate

    store = _nudge_size(store, btn['card'], btn['axis'], btn['delta'])
    return store


@app.callback(
    Output('current-filters', 'data', allow_duplicate=True),
    Output('heatmap-subset-mode', 'data', allow_duplicate=True),
    Input('activate-places-frequency', 'n_clicks'),
    Input('activate-places-sampling', 'n_clicks'),
    Input('activate-places-collocations', 'n_clicks'),
    State('places-frequency-data', 'data'),
    State('places-sample-data', 'data'),
    State('places-collocation-data', 'data'),
    State('heatmap-subset-checkbox', 'value'),
    State('place-search', 'value'),
    State('corpus-max-places-slider', 'value'),
    State('current-filters', 'data'),
    prevent_initial_call=True
)
def apply_places_to_map(freq_lamp_clicks, sample_lamp_clicks, colloc_lamp_clicks,
                        freq_json, sample_json, colloc_json,
                        heatmap_subset_value,
                        search_term, max_places, current_filters):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'activate-places-frequency':
        mode = 'frequency'
        df = load_places_frame(freq_json)
    elif trigger == 'activate-places-sampling':
        mode = 'sampling'
        df = load_places_frame(sample_json)
    elif trigger == 'activate-places-collocations':
        mode = 'collocations'
        df = load_places_frame(colloc_json)
    else:
        raise PreventUpdate

    df = filter_places_search(df, search_term)
    if df.empty:
        raise PreventUpdate

    tokens = df['token'].dropna().astype(str).tolist()
    new_filters = (current_filters or {}).copy()
    new_filters['selected_tokens'] = tokens
    new_filters['max_places'] = max_places or len(tokens)
    new_filters['places_source'] = mode
    new_filters['corpus_source'] = 'Places'
    subset_mode = 'subset' if heatmap_subset_value else 'all'
    return new_filters, subset_mode


@app.callback(
    Output('activate-places-frequency', 'children'),
    Output('activate-places-frequency', 'color'),
    Output('activate-places-sampling', 'children'),
    Output('activate-places-sampling', 'color'),
    Output('activate-places-collocations', 'children'),
    Output('activate-places-collocations', 'color'),
    Input('current-filters', 'data')
)
def update_places_lamps(current_filters):
    active = (current_filters or {}).get('places_source', 'frequency')

    def lamp_props(source):
        is_active = active == source
        icon_class = 'fas fa-lightbulb' if is_active else 'far fa-lightbulb'
        color = 'warning' if is_active else 'light'
        return html.I(className=icon_class), color

    freq_icon, freq_color = lamp_props('frequency')
    sample_icon, sample_color = lamp_props('sampling')
    colloc_icon, colloc_color = lamp_props('collocations')
    return freq_icon, freq_color, sample_icon, sample_color, colloc_icon, colloc_color


@app.callback(
    Output('place-summary-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('place-summary-window-state', 'data'),
    State('place-summary-container', 'style'),
    prevent_initial_call=True
)
def resize_place_summary(store, window_state, current_style):
    style = _apply_size_to_style(store, 'place-summary', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('place-names-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('place-names-window-state', 'data'),
    State('place-names-container', 'style'),
    prevent_initial_call=True
)
def resize_places(store, window_state, current_style):
    style = _apply_size_to_style(store, 'places', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('corpus-controls-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('corpus-controls-window-state', 'data'),
    State('corpus-controls-container', 'style'),
    prevent_initial_call=True
)
def resize_corpus_controls(store, window_state, current_style):
    style = _apply_size_to_style(store, 'corpus-controls', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('visualization-controls-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('visualization-controls-window-state', 'data'),
    State('visualization-controls-container', 'style'),
    prevent_initial_call=True
)
def resize_visualization_controls(store, window_state, current_style):
    style = _apply_size_to_style(store, 'visualization-controls', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('corpus-builder-card', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('corpus-builder-window-state', 'data'),
    State('corpus-builder-card', 'style'),
    prevent_initial_call=True
)
def resize_corpus_builder(store, window_state, current_style):
    style = _apply_size_to_style(store, 'corpus-builder', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('collocation-card', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('collocation-card-window-state', 'data'),
    State('collocation-card', 'style'),
    prevent_initial_call=True
)
def resize_collocation_card(store, window_state, current_style):
    style = _apply_size_to_style(store, 'collocation-card', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('place-similarity-dialog', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('similarity-card-window-state', 'data'),
    State('place-similarity-dialog', 'style'),
    prevent_initial_call=True
)
def resize_similarity_card(store, window_state, current_style):
    style = _apply_size_to_style(store, 'similarity-card', current_style)
    return _enforce_minimized_dimensions(style, window_state)

# Add this callback to toggle the info modal

@app.callback(
    Output('info-modal', 'is_open'),
    [Input('info-button', 'n_clicks'),
     Input('close-info-modal', 'n_clicks')],
    [State('info-modal', 'is_open')]
)
def toggle_info_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


@app.callback(
    Output('place-names-container', 'style'),
    Output('place-names-window-state', 'data', allow_duplicate=True),
    Output('place-names-body', 'style', allow_duplicate=True),
    Input('card-chip-places', 'n_clicks'),
    State('place-names-container', 'style'),
    State('place-names-window-state', 'data'),
    State('place-names-body', 'style'),
    prevent_initial_call=True
)
def toggle_place_names_container(chip_btn, current_style, window_state, body_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id != 'card-chip-places':
        raise PreventUpdate

    new_style = dict(current_style or {})
    window_state = (window_state or {'minimized': False}).copy()
    body_style = dict(body_style or {})

    current_display = new_style.get('display', 'none')
    should_show = current_display == 'none'
    new_style['display'] = 'flex' if should_show else 'none'

    if should_show and window_state.get('minimized'):
        restored_state, restored_container, restored_body = _toggle_window_minimize(
            'places',
            window_state,
            new_style,
            body_style
        )
        window_state = restored_state
        if restored_container:
            new_style.update(restored_container)
        new_style['display'] = 'flex'
        body_style = restored_body
    elif should_show:
        window_state['minimized'] = False
        # ensure body props reset if they were collapsed previously
        for prop in MINIMIZE_BODY_PROPS:
            body_style.pop(prop, None)
        body_style.update({
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column'
        })

    return new_style, window_state, body_style

# Close button callback
app.clientside_callback(
    """
    function(n_clicks, currentStyle) {
        if (!n_clicks) return dash_clientside.no_update;
        
        const newStyle = {...currentStyle};
        newStyle.display = 'none';
        return newStyle;
    }
    """,
    Output('place-names-container', 'style', allow_duplicate=True),
    [Input('close-place-names', 'n_clicks')],
    [State('place-names-container', 'style')],
    prevent_initial_call=True
)


@app.callback(
    Output('collocation-card', 'style'),
    Input('card-chip-collocations', 'n_clicks'),
    Input('close-collocations', 'n_clicks'),
    State('collocation-card', 'style'),
    prevent_initial_call=True
)
def toggle_collocation_card(chip_clicks, close_clicks, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    new_style = dict(current_style or {})
    if trigger_id == 'close-collocations':
        new_style['display'] = 'none'
    elif trigger_id == 'card-chip-collocations':
        current_display = new_style.get('display', 'none')
        new_style['display'] = 'flex' if current_display == 'none' else 'none'
        new_style.pop('transform', None)
    else:
        raise PreventUpdate
    return new_style


@app.callback(
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    Output('current-filters', 'data', allow_duplicate=True),
    Output('select-all-loading', 'children'),
    Input('apply-similarity-corpus', 'n_clicks'),
    State('similarity-places-data', 'data'),
    State('corpus-operation', 'data'),
    State('current-dhlabids-store', 'data'),
    State('current-filters', 'data'),
    prevent_initial_call=True
)
def apply_similarity_to_corpus(n_clicks, places_json, operation, current_books, current_filters):
    if not n_clicks or not places_json:
        raise PreventUpdate
    try:
        places_df = pd.read_json(io.StringIO(places_json), orient='split')
    except ValueError:
        raise PreventUpdate
    tokens = places_df.get('token')
    if tokens is None or tokens.empty:
        raise PreventUpdate
    token_list = tokens.dropna().astype(str).tolist()
    if not token_list:
        raise PreventUpdate
    book_ids = fetch_books_for_tokens(token_list)
    if not book_ids:
        status = html.Span("Ingen bøker funnet for disse stedene", className="text-danger small")
        return dash.no_update, dash.no_update, status
    updated_books = apply_book_operation(current_books, book_ids, operation)
    new_filters = (current_filters or {}).copy()
    new_filters['books'] = updated_books
    new_filters['selected_tokens'] = token_list
    new_filters['corpus_source'] = 'Place Similarity'
    new_filters['last_operation'] = (operation or 'intersection')
    status = html.Span(f"Oppdatert korpus ({len(updated_books):,} bøker)", className="text-success small")
    return updated_books, new_filters, status


@app.callback(
    [Output('filtered-data', 'data', allow_duplicate=True),
     Output('current-dhlabids-store', 'data', allow_duplicate=True),
     Output('current-filters', 'data')],
    [Input('current-filters', 'data'),
     Input('upload-state', 'data'),
     Input('reset-corpus-confirm-modal', 'n_clicks')],
    [State('popup-upload-corpus', 'filename'),
     State('current-dhlabids-store', 'data')],
    prevent_initial_call=True
)
def update_filtered_data(filters, upload_state, reset_confirm_clicks, filename, current_books):
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    current_books = current_books or []
    if triggered_id == 'reset-corpus-confirm-modal' and reset_confirm_clicks:
        return pd.DataFrame().to_json(date_format='iso', orient='split'), [], {}
    if triggered_id == 'upload-state' and upload_state:
        try:
            if isinstance(upload_state, dict) and 'uploaded' in upload_state:
                pass
            else:
                return dash.no_update, dash.no_update, dash.no_update
        except Exception as e:
            return dash.no_update, dash.no_update, dash.no_update
    if not filters:
        return pd.DataFrame().to_json(date_format='iso', orient='split'), [], {}
    try:
        selected_tokens = filters.get('selected_tokens') if filters else None
        places_result = get_places_for_map(filters, books=current_books, selected_tokens=selected_tokens)
        if isinstance(places_result, tuple):
            places_df = places_result[0]
        else:
            places_df = places_result
        # Debug: Log the shape and content of places_df
        print(f"DEBUG: places_df shape: {places_df.shape}")
        print(f"DEBUG: places_df head: {places_df.head()}")
        json_output = places_df.to_json(date_format='iso', orient='split')
        return json_output, dash.no_update, filters
    except Exception as e:
        print(f"Error in update_filtered_data: {e}")
        return dash.no_update, dash.no_update, dash.no_update


@app.callback(
    Output('view-type', 'data'),
    Input('map-mode-map', 'n_clicks'),
    Input('map-mode-heat', 'n_clicks'),
    State('view-type', 'data'),
    prevent_initial_call=True
)
def set_map_view_mode(map_clicks, heat_clicks, current_view):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'map-mode-map':
        return 'points'
    if trigger == 'map-mode-heat':
        return 'heatmap'
    return current_view or 'points'


@app.callback(
    Output('map-mode-map', 'active'),
    Output('map-mode-heat', 'active'),
    Input('view-type', 'data')
)
def style_map_mode_buttons(view_type):
    is_heat = (view_type == 'heatmap')
    return (not is_heat), is_heat

@app.callback(
    Output('main-map', 'figure'),
    [Input('filtered-data', 'data'),
     Input('view-type', 'data'),
     Input('heatmap-intensity', 'value'),
     Input('heatmap-radius', 'value'),
     Input('heatmap-colorscale', 'value'),
     Input('top-cluster-toggle', 'value'),
     Input('selected-place', 'data'),
     Input('main-map', 'clickData'),
     Input('marker-size-slider', 'value'),
     Input('cluster-size-slider', 'value'),
     Input('cluster-radius-slider', 'value'),
     Input('collocation-highlight', 'data')],
    [State('all-places-store', 'data')],
    prevent_initial_call=True
)
def update_map(filtered_data_json, view_type, heatmap_intensity, heatmap_radius, heatmap_colorscale,
               cluster_toggle, selected_place, click_data, marker_size, cluster_size,
               cluster_radius, collocation_highlight, all_places_json):
    try:
        view_type = view_type or 'points'

        # Create base figure with default view of Norway
        fig = go.Figure()
        
        # Add a dummy trace to ensure the map displays
        fig.add_trace(go.Scattermap(
            lat=[60.5],
            lon=[9.0],
            mode='markers',
            marker=dict(size=1, color='rgba(0,0,0,0)'),
            hoverinfo='skip',
            showlegend=False,
            visible=(view_type == 'points')
        ))
        
        if filtered_data_json is None and not all_places_json:
            fig.update_layout(
                map=dict(
                    style='open-street-map',
                    center=dict(lat=60.5, lon=9.0),
                    zoom=4
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False,
                uirevision='constant'
            )
            return fig
        
        required_columns = ['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count']

        # Load cached (sampled) data
        places_df = pd.read_json(io.StringIO(filtered_data_json), orient='split') if filtered_data_json else pd.DataFrame(columns=required_columns)
        for col in required_columns:
            if col not in places_df.columns:
                places_df[col] = np.nan

        heatmap_df = None

        if all_places_json:
            try:
                heatmap_df = pd.read_json(io.StringIO(all_places_json), orient='split')
            except ValueError:
                heatmap_df = None

        if heatmap_df is not None:
            for col in required_columns:
                if col not in heatmap_df.columns:
                    heatmap_df[col] = np.nan

        # Clean datasets
        places_df = places_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude', 'frequency'])
        if heatmap_df is not None:
            heatmap_df = heatmap_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude', 'frequency'])
        else:
            heatmap_df = places_df.copy()

        sample_empty = places_df.empty
        heatmap_empty = heatmap_df.empty

        if sample_empty and (view_type != 'heatmap' or heatmap_empty):
            fig.update_layout(
                map=dict(
                    style='open-street-map',
                    center=dict(lat=60.5, lon=9.0),
                    zoom=4
                ),
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False,
                uirevision='constant'
            )
            return fig
        
        highlight_tokens = {str(t) for t in (collocation_highlight or []) if t}
        use_clustering = False
        if not sample_empty:
            # Logarithmic scale for marker sizes with constrained relative scaling
            sizes = places_df['frequency'].fillna(1).copy()
            sizes = np.log1p(sizes)  # Logarithmic transformation (log(1 + x))
            min_size, max_size = sizes.min(), sizes.max()
            base_size = marker_size if marker_size is not None else 8  # Use slider value as base size
            size_range = 15  # Reduced range for more relative consistency
            if min_size != max_size:
                sizes = base_size + (sizes - min_size) / (max_size - min_size) * size_range
            else:
                sizes = [base_size] * len(sizes)

            if not isinstance(sizes, pd.Series):
                sizes = pd.Series(sizes, index=places_df.index)

            # Aggregate data for tooltips
            places_df['hover_text'] = places_df.apply(
                lambda row: f"{row['token']} ({row['name']})<br>Mentions: {int(row['frequency'])}<br>Books: {int(row['book_count'])}",
                axis=1
            )

            # Determine if clustering is enabled
            use_clustering = cluster_toggle and 'cluster' in cluster_toggle

            clustered = pd.DataFrame()
            if use_clustering:
                # Convert cluster radius from km to degrees (approximate)
                radius_km = cluster_radius if cluster_radius is not None else 50
                radius_deg = radius_km / 111.32  # Convert km to degrees (approximate)

                clustered = places_df.copy()
                # Ensure we have valid numeric values for clustering
                clustered['latitude'] = pd.to_numeric(clustered['latitude'], errors='coerce')
                clustered['longitude'] = pd.to_numeric(clustered['longitude'], errors='coerce')
                clustered = clustered.dropna(subset=['latitude', 'longitude'])

                if not clustered.empty:
                    clustered['cluster'] = ((clustered['latitude'] / radius_deg).round() * 1000 +
                                            (clustered['longitude'] / radius_deg).round()).astype(int)

                    # Store original points for each cluster for polygon creation
                    cluster_points = {}
                    for _, row in clustered.iterrows():
                        cluster_id = row['cluster']
                        if cluster_id not in cluster_points:
                            cluster_points[cluster_id] = []
                        cluster_points[cluster_id].append((row['longitude'], row['latitude']))

                    # Aggregate clustered points with unique place names
                    cluster_data = clustered.groupby('cluster').agg({
                        'latitude': 'mean',
                        'longitude': 'mean',
                        'frequency': 'sum',
                        'book_count': 'sum',
                        'token': lambda x: '<br>'.join([str(t) for t in dict.fromkeys(x) if t is not None]),
                        'name': lambda x: '<br>'.join([str(n) for n in dict.fromkeys(x) if n is not None]),
                        'hover_text': 'first'
                    }).reset_index()
                    cluster_data['count'] = clustered.groupby('cluster').size().values
                    cluster_data['hover_text'] = cluster_data.apply(
                        lambda row: f"""Cluster of {row['count']} places<br>Total Mentions: {int(row['frequency'])}<br>Total Books: {int(row['book_count'])}<br>Example place: {row['token'].split('<br>')[0] if row['token'] else 'Unknown'}""",
                        axis=1
                    )

                    # Use cluster_size slider to control cluster marker size
                    base_cluster_size = cluster_size if cluster_size is not None else 3
                    cluster_data['size'] = np.log1p(cluster_data['count']) * base_cluster_size * 2  # Reduced multiplier for more reasonable sizes

                    # Add clustered markers
                    fig.add_trace(go.Scattermap(
                        lat=cluster_data['latitude'],
                        lon=cluster_data['longitude'],
                        mode='markers',
                        marker=dict(size=cluster_data['size'], color='#1E40AF', opacity=0.7, sizemode='diameter'),
                        text=cluster_data['hover_text'],
                        hoverinfo='text',
                        visible=(view_type == 'points'),
                        name='Clusters'
                    ))

                    # If a cluster is clicked, add a polygon showing its coverage area
                    if click_data and 'points' in click_data:
                        point = click_data['points'][0]
                        if 'Cluster of' in point.get('text', ''):
                            try:
                                # Find the clicked cluster
                                clicked_lat = point['lat']
                                clicked_lon = point['lon']

                                # Find the cluster ID that matches these coordinates
                                matching_clusters = cluster_data[
                                    (cluster_data['latitude'] == clicked_lat) &
                                    (cluster_data['longitude'] == clicked_lon)
                                ]

                                if not matching_clusters.empty:
                                    clicked_cluster = matching_clusters['cluster'].iloc[0]

                                    # Get the points for this cluster
                                    points = cluster_points[clicked_cluster]

                                    if len(points) == 2:
                                        # For two points, create an oval aligned with the points
                                        p1_lon, p1_lat = points[0]
                                        p2_lon, p2_lat = points[1]

                                        # Calculate center point
                                        center_lat = (p1_lat + p2_lat) / 2
                                        center_lon = (p1_lon + p2_lon) / 2

                                        # Calculate distance between points
                                        lat_diff = p2_lat - p1_lat
                                        lon_diff = p2_lon - p1_lon
                                        distance_km = math.sqrt(lat_diff**2 + lon_diff**2) * 111.32

                                        # Calculate bearing between points
                                        bearing = calculate_bearing(p1_lat, p1_lon, p2_lat, p2_lon)

                                        # Create rotated ellipse
                                        lats, lons = create_rotated_ellipse(
                                            center_lat, center_lon,
                                            distance_km/2,
                                            bearing,
                                            points=100
                                        )

                                        fig.add_trace(go.Scattermap(
                                            lat=lats,
                                            lon=lons,
                                            mode='lines',
                                            line=dict(color='#1E40AF', width=3),
                                            fill='toself',
                                            fillcolor='rgba(30, 64, 175, 0.3)',
                                            hoverinfo='skip',
                                            showlegend=False,
                                            visible=True
                                        ))

                                    elif len(points) >= 3:
                                        # For three or more points, use convex hull
                                        points_array = np.array(points)

                                        try:
                                            # Calculate convex hull
                                            hull = ConvexHull(points_array)

                                            # Get the hull vertices
                                            hull_points = points_array[hull.vertices]

                                            # Add some padding to make the hull slightly larger
                                            center = np.mean(hull_points, axis=0)
                                            padding = 0.05  # 5% padding
                                            padded_points = center + (1 + padding) * (hull_points - center)

                                            # Ensure the polygon is closed by adding the first point at the end
                                            padded_points = np.vstack([padded_points, padded_points[0]])

                                            # Add the polygon
                                            fig.add_trace(go.Scattermap(
                                                lat=padded_points[:, 1],
                                                lon=padded_points[:, 0],
                                                mode='lines',
                                                line=dict(color='#1E40AF', width=3),
                                                fill='toself',
                                                fillcolor='rgba(30, 64, 175, 0.3)',
                                                hoverinfo='skip',
                                                showlegend=False,
                                                visible=True
                                            ))
                                        except Exception as e:
                                            print(f"Error calculating convex hull: {e}")
                                            # Fallback to circle if convex hull fails
                                            radius_deg = radius_km / 111.32
                                            angles = np.linspace(0, 2*np.pi, 100)
                                            circle_lats = clicked_lat + radius_deg * np.cos(angles)
                                            circle_lons = clicked_lon + radius_deg * np.sin(angles)

                                            fig.add_trace(go.Scattermap(
                                                lat=circle_lats,
                                                lon=circle_lons,
                                                mode='lines',
                                                line=dict(color='#1E40AF', width=3),
                                                fill='toself',
                                                fillcolor='rgba(30, 64, 175, 0.3)',
                                                hoverinfo='skip',
                                                showlegend=False,
                                                visible=True
                                            ))
                                    else:
                                        # For single points, use a small circle
                                        radius_deg = radius_km / 111.32
                                        angles = np.linspace(0, 2*np.pi, 100)
                                        circle_lats = clicked_lat + radius_deg * np.cos(angles)
                                        circle_lons = clicked_lon + radius_deg * np.sin(angles)

                                        fig.add_trace(go.Scattermap(
                                            lat=circle_lats,
                                            lon=circle_lons,
                                            mode='lines',
                                            line=dict(color='#1E40AF', width=3),
                                            fill='toself',
                                            fillcolor='rgba(30, 64, 175, 0.3)',
                                            hoverinfo='skip',
                                            showlegend=False,
                                            visible=True
                                        ))
                            except Exception as e:
                                print(f"Error handling cluster click: {e}")
                                # Continue without showing the cluster polygon
                                pass
                else:
                    print("No valid data for clustering")

            # Add individual markers if not clustering or if clustering failed
            if not use_clustering or clustered.empty:
                if selected_place:
                    selected_df = places_df[places_df['token'] == selected_place]
                    unselected_df = places_df[places_df['token'] != selected_place]

                    # Add unselected places first
                    if not unselected_df.empty:
                        fig.add_trace(go.Scattermap(
                            lat=unselected_df['latitude'],
                            lon=unselected_df['longitude'],
                            mode='markers',
                            marker=dict(size=sizes[unselected_df.index], color='#3b82f6', opacity=0.7, sizemode='diameter'),
                            text=unselected_df['hover_text'],
                            hoverinfo='text',
                            customdata=unselected_df['token'].tolist(),
                            visible=(view_type == 'points'),
                            name='Places'
                        ))

                    # Add selected place with different color
                    if not selected_df.empty:
                        fig.add_trace(go.Scattermap(
                            lat=selected_df['latitude'],
                            lon=selected_df['longitude'],
                            mode='markers',
                            marker=dict(size=sizes[selected_df.index] * 1.2, color='#dc2626', opacity=0.9, sizemode='diameter'),
                            text=selected_df['hover_text'],
                            hoverinfo='text',
                            customdata=selected_df['token'].tolist(),
                            visible=(view_type == 'points'),
                            name='Selected Place'
                        ))
                else:
                    # No place selected, show all places normally
                    fig.add_trace(go.Scattermap(
                        lat=places_df['latitude'],
                        lon=places_df['longitude'],
                        mode='markers',
                        marker=dict(size=sizes, color='#3b82f6', opacity=0.7, sizemode='diameter'),
                        text=places_df['hover_text'],
                        hoverinfo='text',
                        customdata=places_df['token'].tolist(),
                        visible=(view_type == 'points'),
                        name='Places'
                    ))

            if highlight_tokens:
                highlight_df = places_df[places_df['token'].astype(str).isin(highlight_tokens)]
                if not highlight_df.empty:
                    highlight_sizes = (sizes.loc[highlight_df.index] * 1.4).tolist()
                    fig.add_trace(go.Scattermap(
                        lat=highlight_df['latitude'],
                        lon=highlight_df['longitude'],
                        mode='markers',
                        marker=dict(size=highlight_sizes, color='#ec4899', opacity=0.95, sizemode='diameter'),
                        text=highlight_df['hover_text'],
                        hoverinfo='text',
                        customdata=highlight_df['token'].tolist(),
                        visible=(view_type == 'points'),
                        name='Collocation places'
                    ))

        heatmap_visible = view_type == 'heatmap'
        if heatmap_visible and not heatmap_empty:
            try:
                x = heatmap_df['longitude'].values
                y = heatmap_df['latitude'].values
                z = heatmap_df['frequency'].fillna(1).values
                z = np.log1p(z)
                mask = (~np.isnan(x)) & (~np.isnan(y)) & (~np.isnan(z)) & (~np.isinf(x)) & (~np.isinf(y)) & (~np.isinf(z))
                x, y, z = x[mask], y[mask], z[mask]
                
                if len(x) < 2:
                    fig.add_trace(go.Densitymap(
                        lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap', showscale=False
                    ))
                else:
                    heatmap_actual_radius = (heatmap_radius ** 0.5) * 10
                    fig.add_trace(go.Densitymap(
                        lat=y,
                        lon=x,
                        z=z,
                        radius=heatmap_actual_radius,
                        colorscale=heatmap_colorscale,
                        opacity=0.8 * (heatmap_intensity / 10),
                        showscale=False,
                        visible=True,
                        name='Heatmap'
                    ))
            except Exception as e:
                print(f"Heatmap error: {e}")
                fig.add_trace(go.Densitymap(
                    lat=[60.5], lon=[9.0], z=[0], radius=10, opacity=0.1, visible=True, name='Heatmap', showscale=False
                ))
        else:
            fig.add_trace(go.Densitymap(visible=False, name='Heatmap', showscale=False))
        
        # Update layout
        fig.update_layout(
            map=dict(
                style='open-street-map',
                center=dict(lat=60.5, lon=9.0),
                zoom=4
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
            uirevision='constant',
            hovermode='closest',
            dragmode='pan',
            clickmode='event'
        )
        
        return fig
    except Exception as e:
        print(f"Error in update_map: {e}")
        return go.Figure()


# Add callback for place item clicks
@app.callback(
    [Output('selected-place', 'data', allow_duplicate=True),
     Output('main-map', 'clickData', allow_duplicate=True)],
    [Input({'type': 'place-item', 'index': dash.ALL}, 'n_clicks')],
    [State({'type': 'place-item', 'index': dash.ALL}, 'id'),
     State({'type': 'place-item', 'index': dash.ALL}, 'data-lat'),
     State({'type': 'place-item', 'index': dash.ALL}, 'data-lon'),
     State({'type': 'place-item', 'index': dash.ALL}, 'data-hover')],
    prevent_initial_call=True
)
def handle_place_click(n_clicks, ids, lats, lons, hovers):
    if not any(n_clicks):
        raise PreventUpdate
    
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    triggered_id = ctx.triggered[0]['prop_id']
    if not triggered_id:
        raise PreventUpdate
    
    # Get the index of the clicked item
    try:
        # Parse the triggered ID to get the place token
        triggered_id_dict = eval(triggered_id.split('.')[0])
        clicked_idx = next(i for i, id_dict in enumerate(ids) if id_dict['index'] == triggered_id_dict['index'])
    except (ValueError, SyntaxError, StopIteration):
        raise PreventUpdate
    
    # Get the place data from the clicked item's data attributes
    place_token = ids[clicked_idx]['index']
    lat = lats[clicked_idx]
    lon = lons[clicked_idx]
    hover_text = hovers[clicked_idx]
    
    # Create click data structure using the stored data
    click_data = {
        'points': [{
            'lat': lat,
            'lon': lon,
            'customdata': place_token,
            'text': hover_text
        }]
    }
    
    return place_token, click_data

# Callback to update place summary
@app.callback(
    [Output('place-summary-container', 'style'),
     Output('place-summary', 'children')],
    [Input('main-map', 'clickData'),
     Input('selected-place', 'data')],
    [State('place-summary-container', 'style'),
     State('current-dhlabids-store', 'data')],
    prevent_initial_call=True
)
def update_place_summary(click_data, selected_place, current_style, current_books):
    current_books = current_books or []
    ctx = callback_context
    triggered = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    # If triggered by map click
    if triggered == 'main-map':
        try:
            if not click_data or 'points' not in click_data or not click_data['points']:
                return current_style, dash.no_update
            point = click_data['points'][0]
            token = point.get('customdata') or point.get('text')
            # Try to extract modern name and hover text if available
            hover_text = point.get('text', '')
            modern_part = ''
            frequency = 0
            book_count = 0
            # Parse hover_text for modern name, frequency, and book count
            if '<br>' in hover_text:
                parts = hover_text.split('<br>')
                if len(parts) > 0:
                    token_part = parts[0]
                    if '(' in token_part and ')' in token_part:
                        token = token_part.split('(')[0].strip()
                        modern_part = token_part.split('(')[1].split(')')[0].strip()
                if len(parts) > 1 and 'Mentions:' in parts[1] and 'Books:' in parts[2]:
                    try:
                        frequency = int(parts[1].replace('Mentions:', '').strip())
                        book_count = int(parts[2].replace('Books:', '').strip())
                    except Exception:
                        pass
            # Get book details for the place
            books_df, total_books = get_place_details(token, current_books)
            if not books_df.empty:
                if 'total_mentions' in books_df.columns:
                    frequency = int(books_df.iloc[0]['total_mentions'])
                if 'total_books' in books_df.columns:
                    book_count = int(books_df.iloc[0]['total_books'])
                else:
                    book_count = len(books_df)
            summary = html.Div([
                html.Div([
                    html.H5(token, style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                    html.P(f"Appears in {book_count:,} books with {frequency:,} total mentions", style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                html.Div([
                    html.H6(f"Books mentioning this place (showing {len(books_df):,} of {book_count:,}):", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            html.A(
                                f"{row['title']} ({row['year']})",
                                href=f"https://www.nb.no/items/{row['urn']}?searchText=\"{token}\"",
                                target="_blank",
                                style={'fontWeight': '500', 'color': '#1a56db', 'textDecoration': 'none'}
                            ),
                            html.Div([
                                html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                                html.Span(f" • {int(row.get('mention_count', 1)):,} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between'})
                        ], style={'marginBottom': '10px', 'paddingBottom': '8px', 'borderBottom': '1px solid #eee'})
                        for i, row in books_df.iterrows() if pd.notna(row['title'])
                    ]) if not books_df.empty else html.Div("No book details available")
                ])
            ])
            new_style = dict(current_style)
            new_style['display'] = 'flex'
            return new_style, summary
        except Exception as e:
            print(f"Error updating place summary (map): {e}")
            return dash.no_update, dash.no_update
    # If triggered by list click
    elif triggered == 'selected-place':
        try:
            if not selected_place:
                return current_style, dash.no_update
            # Use selected_place (token) to fetch and display the place info
            token = selected_place
            # Get book details for the place
            books_df, total_books = get_place_details(token, current_books)
            # Fallbacks for summary info
            modern_part = ""
            frequency = 0
            book_count = 0
            # Try to get modern name, frequency, and book count from books_df if available
            if not books_df.empty:
                # Try to get modern name from the first row if present
                if 'modern' in books_df.columns:
                    modern_part = books_df.iloc[0]['modern']
                # Try to get total mentions and books from the columns if present
                if 'total_mentions' in books_df.columns:
                    frequency = int(books_df.iloc[0]['total_mentions'])
                if 'total_books' in books_df.columns:
                    book_count = int(books_df.iloc[0]['total_books'])
                else:
                    book_count = len(books_df)
            summary = html.Div([
                html.Div([
                    html.H5(token, style={'marginBottom': '5px'}),
                    html.P(f"Modern name: {modern_part}", style={'fontSize': '14px', 'color': '#666'}) if modern_part else None,
                    html.P(f"Appears in {book_count:,} books with {frequency:,} total mentions", style={'marginTop': '5px'}),
                    html.Hr(style={'margin': '10px 0'})
                ]),
                html.Div([
                    html.H6(f"Books mentioning this place (showing {len(books_df):,} of {book_count:,}):", style={'marginBottom': '10px'}),
                    html.Div([
                        html.Div([
                            html.A(
                                f"{row['title']} ({row['year']})",
                                href=f"https://www.nb.no/items/{row['urn']}?searchText=\"{token}\"",
                                target="_blank",
                                style={'fontWeight': '500', 'color': '#1a56db', 'textDecoration': 'none'}
                            ),
                            html.Div([
                                html.Span(f"by {row['author']}", style={'color': '#666', 'fontSize': '13px'}),
                                html.Span(f" • {int(row.get('mention_count', 1)):,} mentions", style={'color': '#666', 'fontSize': '13px', 'marginLeft': '10px'})
                            ], style={'display': 'flex', 'justifyContent': 'space-between'})
                        ], style={'marginBottom': '10px', 'paddingBottom': '8px', 'borderBottom': '1px solid #eee'})
                        for i, row in books_df.iterrows() if pd.notna(row['title'])
                    ]) if not books_df.empty else html.Div("No book details available")
                ])
            ])
            new_style = dict(current_style)
            new_style['display'] = 'flex'
            return new_style, summary
        except Exception as e:
            print(f"Error updating place summary (list): {e}")
            return dash.no_update, dash.no_update
    else:
        return dash.no_update, dash.no_update

# Callback for the close button on place summary
app.clientside_callback(
    """
    function(n_clicks, currentStyle) {
        if (!n_clicks) return dash_clientside.no_update;
        
        const newStyle = {...currentStyle};
        newStyle.display = 'none';
        return newStyle;
    }
    """,
    Output('place-summary-container', 'style', allow_duplicate=True),
    [Input('close-summary', 'n_clicks')],
    [State('place-summary-container', 'style')],
    prevent_initial_call=True
)

# Callback to update map view state
app.clientside_callback(
    """
    function(relayoutData) {
        if (relayoutData && relayoutData['map.zoom']) {
            return {'zoom': relayoutData['map.zoom']};
        }
        return dash_clientside.no_update;
    }
    """,
    Output('map-view-state', 'data'),
    [Input('main-map', 'relayoutData')],
    prevent_initial_call=True
)

# Update corpus stats callback to be more efficient
# Update corpus controls callback
@app.callback(
    Output('corpus-controls-container', 'style'),
    [Input('close-corpus', 'n_clicks'),
     Input('card-chip-corpus', 'n_clicks')],
    [State('corpus-controls-container', 'style')],
    prevent_initial_call=True
)
def toggle_corpus_controls(close_btn, chip_btn, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id not in ('close-corpus', 'card-chip-corpus'):
        raise PreventUpdate
    new_style = dict(current_style or {})
    if trigger_id == 'close-corpus':
        new_style['display'] = 'none'
    else:
        current_display = new_style.get('display', 'none')
        new_style['display'] = 'flex' if current_display == 'none' else 'none'
    return new_style

# Update visualization controls callback
@app.callback(
    Output('visualization-controls-container', 'style'),
    [Input('visualization-button', 'n_clicks'),
     Input('close-visualization', 'n_clicks'),
     Input('card-chip-visualization', 'n_clicks')],
    [State('visualization-controls-container', 'style')],
    prevent_initial_call=True
)
def toggle_visualization_controls(open_btn, close_btn, chip_btn, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id not in ('visualization-button', 'close-visualization', 'card-chip-visualization'):
        raise PreventUpdate
    new_style = dict(current_style or {})
    if trigger_id == 'close-visualization':
        new_style['display'] = 'none'
    else:
        current_display = new_style.get('display', 'none')
        new_style['display'] = 'flex' if current_display == 'none' else 'none'
    return new_style

# Update visualization button style callback
@app.callback(
    Output('visualization-button', 'style'),
    Input('visualization-controls-container', 'style'),
    State('visualization-button', 'style'),
    prevent_initial_call=True
)
def update_visualization_button_style(viz_style, current_style):
    base_style = {
        'padding': '8px',
        'backgroundColor': 'white',
        'color': '#475569',
        'border': 'none',
        'borderRadius': '50%',
        'cursor': 'pointer',
        'boxShadow': '0 1px 3px rgba(0,0,0,0.1)',
        'transition': 'all 0.2s',
        'width': '36px',
        'height': '36px',
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'center',
        'fontSize': '14px',
        'flexShrink': '0'
    }
    active_style = base_style.copy()
    active_style['backgroundColor'] = '#475569'
    active_style['color'] = 'white'
    return active_style if viz_style and viz_style.get('display') == 'block' else base_style


def _chip_class(base_class, style_dict):
    display_value = (style_dict or {}).get('display', 'none')
    is_open = display_value not in ('none', 'hidden')
    classes = [base_class]
    if is_open:
        classes.append('chip-open')
    return ' '.join(classes)


@app.callback(
    Output('card-chip-places', 'className'),
    Output('card-chip-corpus', 'className'),
    Output('card-chip-visualization', 'className'),
    Output('card-chip-builder', 'className'),
    Output('card-chip-collocations', 'className'),
    Output('card-chip-similarity', 'className'),
    Input('place-names-container', 'style'),
    Input('corpus-controls-container', 'style'),
    Input('visualization-controls-container', 'style'),
    Input('corpus-builder-card', 'style'),
    Input('collocation-card', 'style'),
    Input('place-similarity-dialog', 'style')
)
def refresh_card_chips(places_style, corpus_style, viz_style, builder_style, collocation_style, similarity_style):
    return (
        _chip_class('card-chip chip-option chip-places', places_style),
        _chip_class('card-chip chip-option chip-corpus', corpus_style),
        _chip_class('chip-pill chip-pill-visualization', viz_style),
        _chip_class('card-chip chip-option chip-builder', builder_style),
        _chip_class('card-chip chip-option chip-collocations', collocation_style),
        _chip_class('card-chip chip-option chip-similarity', similarity_style)
    )


def add_edge_points(points_array):
    """Add edge points to ensure the convex hull covers the entire cluster area."""
    if len(points_array) < 2:
        return points_array
    
    # Calculate the bounding box
    min_lon, min_lat = points_array.min(axis=0)
    max_lon, max_lat = points_array.max(axis=0)
    
    # Add corner points with some padding
    padding = 0.1  # 10% padding
    lon_range = max_lon - min_lon
    lat_range = max_lat - min_lat
    
    edge_points = np.array([
        [min_lon - padding * lon_range, min_lat - padding * lat_range],  # Bottom left
        [max_lon + padding * lon_range, min_lat - padding * lat_range],  # Bottom right
        [max_lon + padding * lon_range, max_lat + padding * lat_range],  # Top right
        [min_lon - padding * lon_range, max_lat + padding * lat_range]   # Top left
    ])
    
    # Combine original points with edge points
    return np.vstack([points_array, edge_points])

def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculate the bearing between two points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(y, x)
    return math.degrees(bearing)

def create_rotated_ellipse(center_lat, center_lon, radius_km, bearing, points=100):
    """Create a rotated ellipse around a center point."""
    # Convert radius from km to degrees (approximate)
    radius_deg = radius_km / 111.32
    
    # Create points for the ellipse
    angles = np.linspace(0, 2*np.pi, points)
    
    # Create the ellipse points
    x = radius_deg * np.cos(angles)
    y = radius_deg * np.sin(angles)
    
    # Rotate the points
    bearing_rad = math.radians(bearing)
    cos_bearing = math.cos(bearing_rad)
    sin_bearing = math.sin(bearing_rad)
    
    x_rot = x * cos_bearing - y * sin_bearing
    y_rot = x * sin_bearing + y * cos_bearing
    
    # Translate to center point
    lats = center_lat + y_rot
    lons = center_lon + x_rot
    
    return lats, lons

# Add callback for loading state
@app.callback(
    Output('loading-overlay', 'style'),
    [Input('build-corpus-btn', 'n_clicks'),  # Changed from apply-filters to build-corpus-btn
     Input('main-map', 'figure')],
    [State('loading-overlay', 'style')]
)
def update_loading_state(build_clicks, map_figure, current_style):
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # Show loading when build button is clicked
    if trigger_id == 'build-corpus-btn' and build_clicks:
        new_style = dict(current_style)
        new_style['display'] = 'flex'
        return new_style
    
    # Hide loading when map is updated
    if trigger_id == 'main-map' and map_figure:
        new_style = dict(current_style)
        new_style['display'] = 'none'
        return new_style
    
    return current_style

# Add download endpoint
@app.server.route('/download-map', methods=['GET'])
def download_map():
    try:
        # Get data from query parameters
        data_str = request.args.get('data')
        if not data_str:
            return 'No data provided', 400
            
        data = json.loads(data_str)
        figure = data.get('figure')
        format = data.get('format', 'png')
        width = data.get('width', 3840)
        height = data.get('height', 2160)
        scale = data.get('scale', 2)
        
        # Create figure from JSON
        fig = go.Figure(figure)
        
        # Update layout for download
        fig.update_layout(
            width=width,
            height=height,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        
        # Generate image
        if format == 'png':
            img_bytes = fig.to_image(format='png', scale=scale)
            mimetype = 'image/png'
            filename = 'imagination_map.png'
        elif format == 'pdf':
            img_bytes = fig.to_image(format='pdf', scale=scale)
            mimetype = 'application/pdf'
            filename = 'imagination_map.pdf'
        elif format == 'svg':
            img_bytes = fig.to_image(format='svg', scale=scale)
            mimetype = 'image/svg+xml'
            filename = 'imagination_map.svg'
        else:
            return 'Invalid format', 400
        
        return send_file(
            io.BytesIO(img_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error generating download: {e}")
        return str(e), 500

@app.callback(
    [Output('download-map-file', 'data'),
     Output('download-status', 'children'),
     Output('clear-download-status-interval', 'disabled'),
     Output('clear-download-status-interval', 'n_intervals')],
    [Input('download-map', 'n_clicks')],
    [State('download-format', 'value'),
     State('download-resolution', 'value'),
     State('main-map', 'figure')],
    prevent_initial_call=True
)
def trigger_download(n_clicks, format, resolution, figure):
    import dash
    from dash import dcc, html
    import plotly.graph_objects as go
    import io
    if not n_clicks:
        raise dash.exceptions.PreventUpdate
    # Set resolution based on selection
    resolution_map = {
        'standard': {'width': 1920, 'height': 1080},
        'high': {'width': 3840, 'height': 2160},
        'publication': {'width': 6000, 'height': 4000}
    }
    # Get the selected resolution
    dimensions = resolution_map.get(resolution, resolution_map['standard'])
    try:
        # Create figure from JSON
        fig = go.Figure(figure)
        fig.update_layout(
            width=dimensions['width'],
            height=dimensions['height'],
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        # Generate image bytes
        if format == 'png':
            img_bytes = fig.to_image(format='png', scale=2 if resolution in ['high', 'publication'] else 1)
            filename = 'imagination_map.png'
            mime = 'image/png'
        elif format == 'pdf':
            img_bytes = fig.to_image(format='pdf', scale=2 if resolution in ['high', 'publication'] else 1)
            filename = 'imagination_map.pdf'
            mime = 'application/pdf'
        elif format == 'svg':
            img_bytes = fig.to_image(format='svg', scale=2 if resolution in ['high', 'publication'] else 1)
            filename = 'imagination_map.svg'
            mime = 'image/svg+xml'
        else:
            return None, html.Div('Invalid format selected', style={'color': 'red'}), True, 0
        # Enable the interval to clear the message
        return dcc.send_bytes(lambda buf: buf.write(img_bytes), filename), html.Div('Download started...', style={'color': 'green', 'marginTop': '10px'}), False, 0
    except Exception as e:
        print(f"Error generating download: {e}")
        return None, html.Div(f'Error generating download: {e}', style={'color': 'red'}), True, 0

@app.callback(
    Output('download-status', 'children', allow_duplicate=True),
    [Input('clear-download-status-interval', 'n_intervals')],
    [State('clear-download-status-interval', 'disabled')],
    prevent_initial_call=True
)
def clear_download_status(n_intervals, disabled):
    if not disabled and n_intervals > 0:
        return ''
    raise dash.exceptions.PreventUpdate

@app.callback(
    Output('clear-download-status-interval', 'disabled', allow_duplicate=True),
    [Input('download-status', 'children')],
    prevent_initial_call=True
)
def disable_interval_on_clear(status):
    # Disable the interval if the status is cleared
    if not status:
        return True
    raise dash.exceptions.PreventUpdate

# Add new callback for data loading
@app.callback(
    Output('filtered-data', 'data'),
    Input('current-dhlabids-store', 'data'),
    State('current-filters', 'data'),
    prevent_initial_call=True
)
def load_filtered_data(books, filters):
    books = books or []
    filters = filters or {}
    if not books:
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count']).to_json(date_format='iso', orient='split')
    try:
        places = filters.get('selected_tokens')
        places_result = get_places_for_map(filters, books=books, selected_tokens=places)
        places_df = places_result[0] if isinstance(places_result, tuple) else places_result
        return places_df.to_json(date_format='iso', orient='split')
    except Exception as e:
        print(f"Error in load_filtered_data: {e}")
        return dash.no_update

# Global search surface -------------------------------------------------------

@app.callback(
    Output('global-search-results', 'children'),
    Output('global-search-results', 'style'),
    Input('global-place-search', 'value'),
    Input('global-search-filter-store', 'data'),
    prevent_initial_call=True
)
def update_global_search_results(search_term, filter_selection):
    term = (search_term or '').strip()
    if len(term) < 2:
        return [], _search_results_style(False)
    selection_set = set(filter_selection or ['places', 'books', 'authors'])
    selection_list = [cat for cat in ['places', 'books', 'authors'] if cat in selection_set]

    tokens = _normalize_search_tokens(term)

    try:
        conn = get_db_connection()
        search_pattern = f"%{term}%"

        # ----------------------
        place_clause, place_params = _build_like_clause(tokens, ['p.token', 'p.modern'])
        if not place_clause:
            place_clause = "(LOWER(p.token) LIKE LOWER(?) OR LOWER(p.modern) LIKE LOWER(?))"
            place_params = [search_pattern, search_pattern]
        places_query = f"""
            SELECT p.token, p.modern AS name
            FROM places p
            WHERE {place_clause}
            ORDER BY CASE 
                WHEN LOWER(p.token) = LOWER(?) THEN 0
                WHEN LOWER(p.modern) = LOWER(?) THEN 1
                ELSE 2
            END,
            p.modern
            LIMIT 5
        """
        places_df = pd.read_sql_query(
            places_query,
            conn,
            params=tuple(place_params + [term, term])
        )

        book_clause, book_params = _build_like_clause(tokens, ['title'])
        if not book_clause:
            book_clause = "LOWER(title) LIKE LOWER(?)"
            book_params = [search_pattern]
        books_query = f"""
            SELECT c.dhlabid, c.title, c.author, c.year, c.urn
            FROM corpus c
            WHERE c.title IS NOT NULL
              AND {book_clause}
            ORDER BY CASE WHEN LOWER(c.title) = LOWER(?) THEN 0 ELSE 1 END,
                     c.year DESC
            LIMIT 5
        """
        books_df = pd.read_sql_query(
            books_query,
            conn,
            params=tuple(book_params + [term])
        )
        author_clause, author_params = _build_like_clause(tokens, ['author'])
        if not author_clause:
            author_clause = "LOWER(author) LIKE LOWER(?)"
            author_params = [search_pattern]
        authors_query = f"""
            SELECT c.author, COUNT(DISTINCT c.dhlabid) AS book_count
            FROM corpus c
            WHERE c.author IS NOT NULL
              AND TRIM(c.author) != ''
              AND {author_clause}
            GROUP BY c.author
            ORDER BY CASE WHEN LOWER(c.author) = LOWER(?) THEN 0 ELSE 1 END,
                     c.author
            LIMIT 5
        """
        authors_df = pd.read_sql_query(
            authors_query,
            conn,
            params=tuple(author_params + [term])
        )
    except Exception as e:
        print(f"Error loading global search results: {e}")
        return dash.no_update, _search_results_style(False)
    finally:
        conn.close()

    sections = []

    def section(title, key, entries):
        return html.Div([
            html.Div(title, style={
                'fontSize': '11px',
                'letterSpacing': '0.08em',
                'textTransform': 'uppercase',
                'color': '#94a3b8',
                'marginBottom': '4px'
            }),
            html.Div(entries, style={'display': 'flex', 'flexDirection': 'column', 'gap': '6px'})
        ], style={
            'padding': '0.5rem',
            'borderRadius': '12px',
            'backgroundColor': '#f8fafc',
            'border': '1px solid rgba(148, 163, 184, 0.35)'
        }, id={'type': 'search-section', 'category': key})

    if 'places' in selection_set and not places_df.empty:
        items = []
        for _, place in places_df.iterrows():
            label = place.get('name') or place.get('token')
            token = place.get('token')
            items.append(
                html.Div([
                    html.Div([
                        html.Span(label, style={'fontWeight': 600, 'color': '#0f172a'}),
                        html.Span(token, style={'fontSize': '12px', 'color': '#94a3b8'})
                    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '2px'}),
                    html.Button(
                        "Vis på kartet",
                        id={'type': 'search-place-action', 'token': token},
                        n_clicks=0,
                        style={
                            'border': 'none',
                            'backgroundColor': '#e2e8f0',
                            'color': '#0f172a',
                            'fontSize': '12px',
                            'padding': '4px 10px',
                            'borderRadius': '999px',
                            'cursor': 'pointer'
                        }
                    )
                ], style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '8px 10px',
                    'backgroundColor': '#f8fafc',
                    'borderRadius': '8px'
                })
            )
        sections.append(section("Steder", 'places', items))

    if 'books' in selection_set and not books_df.empty:
        items = []
        for _, book in books_df.iterrows():
            title = book.get('title')
            year = book.get('year')
            author = book.get('author')
            dhlabid = int(book.get('dhlabid'))
            urn = book.get('urn')
            items.append(
                html.Div([
                    html.Div([
                        html.Span(f"{title} ({year})" if year else title, style={'fontWeight': 600}),
                        html.Span(author, style={'fontSize': '12px', 'color': '#94a3b8'})
                    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '2px'}),
                    html.Div([
                        html.A(
                            "Åpne NB",
                            href=f"https://www.nb.no/items/{urn}" if urn else "#",
                            target="_blank",
                            style={'fontSize': '12px', 'color': '#0284c7', 'textDecoration': 'none'}
                        ),
                        html.Button(
                            "Legg til korpus",
                            id={'type': 'search-book-action', 'dhlabid': dhlabid},
                            n_clicks=0,
                            style={
                                'border': 'none',
                                'backgroundColor': '#c7d2fe',
                                'color': '#1e1b4b',
                                'fontSize': '12px',
                                'padding': '4px 10px',
                                'borderRadius': '999px',
                                'cursor': 'pointer',
                                'marginLeft': '8px'
                            }
                        )
                    ], style={'display': 'flex', 'alignItems': 'center'})
                ], style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '8px 10px',
                    'backgroundColor': '#f8fafc',
                    'borderRadius': '8px'
                })
            )
        sections.append(section("Bøker", 'books', items))

    if 'authors' in selection_set and not authors_df.empty:
        items = []
        for _, author in authors_df.iterrows():
            name = author.get('author')
            count = int(author.get('book_count') or 0)
            items.append(
                html.Div([
                    html.Div([
                        html.Span(name, style={'fontWeight': 600}),
                        html.Span(f"{count} bøker", style={'fontSize': '12px', 'color': '#94a3b8'})
                    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '2px'}),
                    html.Button(
                        "Legg bøker til korpus",
                        id={'type': 'search-author-action', 'author': name},
                        n_clicks=0,
                        style={
                            'border': 'none',
                            'backgroundColor': '#fee2e2',
                            'color': '#7f1d1d',
                            'fontSize': '12px',
                            'padding': '4px 10px',
                            'borderRadius': '999px',
                            'cursor': 'pointer'
                        }
                    )
                ], style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '8px 10px',
                    'backgroundColor': '#f8fafc',
                    'borderRadius': '8px'
                })
            )
        sections.append(section("Forfattere", 'authors', items))

    if not sections:
        sections = [html.Div(f"Ingen treff for «{term}»", style={'fontSize': '13px', 'color': '#64748b'})]

    columns_wrapper = html.Div(
        sections,
        style={
            'display': 'grid',
            'gridTemplateColumns': 'repeat(auto-fit, minmax(220px, 1fr))',
            'gap': '12px',
            'marginTop': '12px',
            'maxHeight': '360px',
            'overflowY': 'auto',
            'paddingRight': '4px'
        }
    )

    section_header = html.Div([
        html.Span("Søketreff", style={'fontSize': '12px', 'color': '#64748b'}),
        dcc.Checklist(
            id='global-search-filter',
            options=[
                {'label': 'Steder', 'value': 'places'},
                {'label': 'Bøker', 'value': 'books'},
                {'label': 'Forfattere', 'value': 'authors'}
            ],
            value=selection_list,
            labelStyle={
                'display': 'inline-flex',
                'alignItems': 'center',
                'padding': '4px 10px',
                'borderRadius': '999px',
                'backgroundColor': '#e2e8f0',
                'fontSize': '11px',
                'textTransform': 'uppercase',
                'letterSpacing': '0.08em',
                'fontWeight': 600,
                'marginRight': '8px',
                'cursor': 'pointer'
            },
            inputStyle={'marginRight': '6px'}
        )
    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'})

    return [section_header, columns_wrapper], _search_results_style(True)


@app.callback(
    Output('main-map', 'figure', allow_duplicate=True),
    Output('place-summary-container', 'style', allow_duplicate=True),
    Output('place-summary', 'children', allow_duplicate=True),
    Output('global-search-results', 'style', allow_duplicate=True),
    Input({'type': 'search-place-action', 'token': ALL}, 'n_clicks'),
    State('main-map', 'figure'),
    State('place-summary-container', 'style'),
    prevent_initial_call=True
)
def show_place_from_search(_, current_figure, summary_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]
    if not trigger['value']:
        raise PreventUpdate
    trigger_id = json.loads(trigger['prop_id'].split('.')[0])
    token = trigger_id.get('token')
    place = _fetch_place_overview(token)
    if not place:
        raise PreventUpdate

    fig = go.Figure(current_figure or go.Figure())
    try:
        lat = float(place.get('latitude'))
        lon = float(place.get('longitude'))
        fig.update_layout(map=dict(center=dict(lat=lat, lon=lon), zoom=8))
    except (TypeError, ValueError):
        pass

    new_summary_style = dict(summary_style or {})
    new_summary_style['display'] = 'flex'
    new_summary_style.pop('transform', None)

    return (
        fig,
        new_summary_style,
        _render_place_summary_from_search(place),
        _search_results_style(False)
    )


@app.callback(
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    Output('global-search-results', 'style', allow_duplicate=True),
    Input({'type': 'search-book-action', 'dhlabid': ALL}, 'n_clicks'),
    State('current-dhlabids-store', 'data'),
    prevent_initial_call=True
)
def add_book_from_search(_, current_books):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]
    if not trigger['value']:
        raise PreventUpdate
    trigger_id = json.loads(trigger['prop_id'].split('.')[0])
    dhlabid = int(trigger_id.get('dhlabid'))
    books = set(current_books or [])
    books.add(dhlabid)
    return sorted(books), _search_results_style(False)


@app.callback(
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    Output('global-search-results', 'style', allow_duplicate=True),
    Input({'type': 'search-author-action', 'author': ALL}, 'n_clicks'),
    State('current-dhlabids-store', 'data'),
    prevent_initial_call=True
)
def add_author_books_from_search(_, current_books):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]
    if not trigger['value']:
        raise PreventUpdate
    trigger_id = json.loads(trigger['prop_id'].split('.')[0])
    author = trigger_id.get('author')
    dhlabids = _fetch_author_book_ids(author)
    if not dhlabids:
        raise PreventUpdate
    books = set(current_books or [])
    books.update(dhlabids)
    return sorted(books), _search_results_style(False)


@app.callback(
    Output('global-search-filter-store', 'data'),
    Input('global-search-filter', 'value'),
    prevent_initial_call=True
)
def persist_global_search_filter(selected):
    return selected or []


# Add a clientside callback for instant download status feedback
app.clientside_callback(
    """
    function(n_clicks) {
        if (n_clicks) {
            return 'Download started...';
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('download-status', 'children', allow_duplicate=True),
    [Input('download-map', 'n_clicks')],
    prevent_initial_call=True
)

@app.callback(
    [
        Output('corpus-info-books', 'children'),
        Output('corpus-info-authors', 'children'),
        Output('corpus-info-places', 'children'),
        Output('corpus-info-years', 'children'),
        Output('corpus-browse-table', 'children'),
    ],
    [Input('filtered-data', 'data'), Input('corpus-table-filter', 'data')],
    [State('current-dhlabids-store', 'data'),
     State('current-filters', 'data')],
    prevent_initial_call=True
)
def update_corpus_info_and_table(_, filter_data, current_books, current_filters):
    books = current_books or []
    selected_tokens = (current_filters or {}).get('selected_tokens', [])
    if not books:
        return "0", "0", "0", "", html.Div("No books in corpus.", style={'color': '#666'})
    import pandas as pd
    conn = get_db_connection()
    try:
        # Info section
        query = f"""
        SELECT COUNT(DISTINCT dhlabid) as book_count,
               COUNT(DISTINCT author) as author_count,
               MIN(year) as min_year,
               MAX(year) as max_year
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(books))})
        AND year IS NOT NULL
        """
        info = pd.read_sql_query(query, conn, params=tuple(books)).iloc[0]
        # Places count
        places_query = f"""
        SELECT COUNT(DISTINCT token) as place_count
        FROM books
        WHERE dhlabid IN ({','.join(['?'] * len(books))})
        """
        place_count = pd.read_sql_query(places_query, conn, params=tuple(books))['place_count'].iloc[0]
        # Year range
        if pd.notnull(info['min_year']) and pd.notnull(info['max_year']):
            years = f"{int(info['min_year'])}–{int(info['max_year'])}"
        else:
            years = ""
        # --- Build SQL filter for the table ---
        where_clauses = [f"c.dhlabid IN ({','.join(['?'] * len(books))})"]
        params = list(books)
        if filter_data and filter_data.get('column') and filter_data.get('value') is not None:
            col = filter_data['column']
            val = filter_data['value']
            if col == 'year':
                where_clauses.append("c.year <= ?")
                params.append(val)
            elif col == 'placename_count':
                # placename_count is a subquery, so filter after fetch
                pass
            elif col in ['title', 'author', 'category']:
                where_clauses.append(f"LOWER(c.{col}) LIKE ?")
                params.append(f"%{str(val).lower()}%")
        where_sql = ' AND '.join(where_clauses)
        table_query = f'''
        SELECT c.title, c.author, c.category, c.year, c.urn,
               (SELECT COUNT(DISTINCT b.token) FROM books b WHERE b.dhlabid = c.dhlabid) as placename_count
        FROM corpus c
        WHERE {where_sql}
        ORDER BY c.year DESC, c.title
        LIMIT 100
        '''
        df = pd.read_sql_query(table_query, conn, params=tuple(params))
        # placename_count filter (must be applied after fetch)
        if filter_data and filter_data.get('column') == 'placename_count' and filter_data.get('value') is not None:
            val = filter_data['value']
            df = df[df['placename_count'] <= val]
        if df.empty:
            table_section = html.Div("No books found in corpus.", style={'color': '#666'})
        else:
            table_rows = []
            for _, row in df.iterrows():
                title_text, full_title = truncate_text(row['title'] or '', 60)
                author_text, full_author = truncate_text(row['author'] or '', 40)
                title_cell = html.A(
                    title_text or "(Untitled)",
                    href=f"https://www.nb.no/items/{row['urn']}",
                    target="_blank",
                    title=full_title or "NB.no"
                )
                author_cell = html.Span(author_text, title=full_author) if full_author else ""
                table_rows.append({
                    'title': title_cell,
                    'author': author_cell,
                    'category': row['category'] or '',
                    'year': int(row['year']) if pd.notnull(row['year']) else '',
                    'placename_count': int(row['placename_count']) if pd.notnull(row['placename_count']) else ''
                })
            table_section = build_html_table(
                table_rows,
                [
                    ('title', 'Title'),
                    ('author', 'Author'),
                    ('category', '≡'),
                    ('year', '📅'),
                    ('placename_count', '◆')
                ],
                table_class="table table-sm table-striped table-hover",
                container_style={'flex': '1 1 auto', 'minHeight': 0, 'overflow': 'auto'}
            )

        return (
            f"{info['book_count']:,}",
            f"{info['author_count']:,}",
            f"{place_count:,}",
            years,
            table_section
        )
    except Exception as e:
        print(f"Error in update_corpus_info_and_table: {e}")
        return "0", "0", "0", "", html.Div("Error displaying corpus table.", style={'color': 'red'})
    finally:
        conn.close()



@app.callback(
    Output('corpus-download-unique', 'data'),
    [Input('corpus-download-btn-unique', 'n_clicks')],
    [State('current-dhlabids-store', 'data')],
    prevent_initial_call=True
)
def download_corpus_excel(n_clicks, dhlabids):
    if not n_clicks or not dhlabids:
        raise dash.exceptions.PreventUpdate
    print(f"Download triggered, first 5 dhlabids: {dhlabids[:5]}")
    import pandas as pd
    import io
    conn = get_db_connection()
    try:
        # Fetch metadata for current corpus
        query = f'''
        SELECT dhlabid, title, author, year, category, urn
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(dhlabids))})
        '''
        df = pd.read_sql_query(query, conn, params=tuple(dhlabids))
        if df.empty:
            raise dash.exceptions.PreventUpdate
        # Add URL column
        df['url'] = df['urn'].apply(lambda urn: f"https://www.nb.no/items/{urn}" if pd.notnull(urn) else '')
        # Reorder columns
        df = df[['dhlabid', 'title', 'author', 'year', 'category', 'url']]
        # Write to Excel in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Corpus')
        output.seek(0)
        return dcc.send_bytes(lambda buf: buf.write(output.getvalue()), filename='imagination_corpus.xlsx')
    except Exception as e:
        print(f"Download error: {e}")
        raise
    finally:
        conn.close()

def get_all_places_for_corpus(book_ids):
    """Return all valid places for a list of book IDs (no sampling, no limit)."""
    import pandas as pd
    if not book_ids:
        return pd.DataFrame(columns=['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count'])
    conn = get_db_connection()
    try:
        query = f'''
        SELECT 
            b.token,
            p.modern as name,
            p.latitude,
            p.longitude,
            SUM(b.book_count) as frequency,
            COUNT(DISTINCT b.dhlabid) as book_count
        FROM books b
        JOIN places p ON b.token = p.token
        WHERE b.dhlabid IN ({','.join(['?'] * len(book_ids))})
          AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
          AND p.latitude != '0' AND p.longitude != '0'
        GROUP BY b.token, p.modern, p.latitude, p.longitude
        '''
        df = pd.read_sql_query(query, conn, params=tuple(book_ids))
        df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
        df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
        return df
    finally:
        conn.close()

def sample_places(places_df, n=2000):
    """Return a random sample of n places from a DataFrame."""
    import pandas as pd
    if places_df is None or places_df.empty:
        return places_df
    n = min(n, len(places_df))
    return places_df.sample(n=n, random_state=None).reset_index(drop=True)

@app.callback(
    Output('all-places-store', 'data'),
    [Input('current-dhlabids-store', 'data'),
     Input('upload-state', 'data'),
     Input('reset-corpus-btn-main', 'n_clicks')],
    [State('all-places-store', 'data')],
    prevent_initial_call=True
)
def update_all_places_store(book_ids, upload_state, reset_n_clicks, current_data):
    import pandas as pd
    import io
    if not book_ids:
        return pd.DataFrame().to_json(date_format='iso', orient='split')
    df = get_all_places_for_corpus(book_ids)
    return df.to_json(date_format='iso', orient='split')


# Run Server
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8065, dev_tools_hot_reload=False)

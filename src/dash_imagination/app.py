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
from urllib.parse import quote

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

from dash_imagination.components.corpus import (
    create_corpus_controls,
    create_map_visuals_card,
    create_heatmap_visuals_card,
    create_corpus_builder_card
)
from dash_imagination.components.places.place_similarity_dialog import create_place_similarity_dialog
from dash_imagination.components.authors.author_list_card import create_author_list_card
from dash_imagination.components.authors.author_info_card import create_author_info_card
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
    if not search_term or not str(search_term).strip():
        return df
    import re
    term = str(search_term).strip().lower()

    if '*' in term:
        # support simple wildcard: * -> any suffix
        pattern = re.escape(term).replace(r'\*', '.*')
        regex = re.compile(rf"^{pattern}", re.IGNORECASE)
        mask = (
            df['token'].astype(str).str.match(regex, na=False) |
            df['name'].astype(str).str.match(regex, na=False)
        )
    else:
        mask = (
            df['token'].astype(str).str.lower().str.startswith(term, na=False) |
            df['name'].astype(str).str.lower().str.startswith(term, na=False)
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
    
    # Safe retrieval of dims with fallback to DEFAULT_CARD_SIZES
    default_dims = base.get(card_key, {'width': 400, 'height': 500})
    dims = store.get(card_key, default_dims).copy()
    
    limits = SIZE_LIMITS[axis]
    dims[axis] = max(limits['min'], min(limits['max'], dims[axis] + delta))
    store[card_key] = dims
    return store


def _apply_size_to_style(store, card_key, current_style):
    base = DEFAULT_CARD_SIZES
    # Safe retrieval of dims with fallback
    default_dims = base.get(card_key, {'width': 400, 'height': 500})
    dims = (store or base).get(card_key, default_dims)
    
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
    'opacity': '0',
    'pointerEvents': 'none',
    'overflow': 'hidden',
    'marginTop': '0',
    'marginBottom': '0',
    'paddingTop': '0',
    'paddingBottom': '0'
}


# Simple z-index bumping to bring active dialogs to front
Z_COUNTER = 3000
def _bump_z(style: dict | None) -> dict:
    global Z_COUNTER
    Z_COUNTER += 1
    new_style = dict(style or {})
    new_style['zIndex'] = Z_COUNTER
    return new_style


def _toggle_window_minimize(card_key, window_state, container_style, body_style):
    """
    Toggle minimized state for floating dialog cards. Keep header visible when minimized.
    """
    state = (window_state or {}).copy()
    container = (container_style or {}).copy()
    body = (body_style or {}).copy()

    is_minimized = state.get('minimized', False)
    default_size = DEFAULT_CARD_SIZES.get(card_key, {})
    default_h_val = default_size.get('height', 320)
    default_height = f"{default_h_val}px"

    if is_minimized:
        restored_height = state.get('stored_height') or default_height
        restored_min_height = state.get('stored_min_height')
        stored_body_styles = state.get('stored_body_styles', {})

        container['height'] = restored_height
        if restored_min_height is None:
            container.pop('minHeight', None)
        else:
            container['minHeight'] = restored_min_height

        # Restore body styles
        for prop in MINIMIZE_BODY_PROPS:
            if prop in stored_body_styles:
                value = stored_body_styles[prop]
                if value is None:
                    body.pop(prop, None)
                else:
                    body[prop] = value
            else:
                body.pop(prop, None)
        
        # Force body visible when restoring
        body['display'] = 'flex'
        if card_key == 'place-summary':
            body['flexDirection'] = 'column'
            body['flex'] = '1 1 auto'
            body['minHeight'] = 0
            body['overflow'] = 'hidden'
        if container.get('display') == 'none':
            container['display'] = 'flex'

        # Ensure restored body is visible and interactive
        body['opacity'] = '1'
        body['pointerEvents'] = 'auto'

        state['minimized'] = False
        state.pop('stored_height', None)
        state.pop('stored_min_height', None)
        state.pop('stored_body_styles', None)
        return state, container, body

    new_state = {
        'minimized': True,
        'stored_height': container.get('height', default_height),
        'stored_min_height': container.get('minHeight'),
        'stored_body_styles': {prop: body.get(prop) for prop in MINIMIZE_BODY_PROPS}
    }

    # Header-only: keep container visible but shrink; hide body
    container['display'] = 'flex'
    container['height'] = '36px'
    container['minHeight'] = '36px'

    for prop, value in MINIMIZED_BODY_VALUES.items():
        body[prop] = value
    body['display'] = 'none'
    
    return new_state, container, body



def _enforce_minimized_dimensions(style, window_state):
    minimized = (window_state or {}).get('minimized')
    if minimized:
        style['height'] = 'auto'
        style['minHeight'] = '0px'
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


from dash_imagination.utils.images import fetch_historical_images, hydrate_gallery_images


def _make_image_store_payload(source: str, label: str | None, subtitle: str | None, images: list[dict]) -> dict:
    return {
        'source': source,
        'label': label,
        'subtitle': subtitle,
        'images': images or []
    }


def _build_image_tile(
    image: dict,
    *,
    height: int = 100,
    show_caption: bool = False,
    context: str = "place",
    index: int = 0
) -> html.Div | None:
    """Create a clickable thumbnail with a source badge and optional caption."""
    if not image or not image.get('thumbnail'):
        return None

    source_label = (image.get('source') or "NB.no").upper()
    title = image.get('title') or "Historisk bilde"

    badge = html.Span(
        source_label,
        style={
            'position': 'absolute',
            'top': '6px',
            'left': '6px',
            'backgroundColor': 'rgba(15,23,42,0.85)',
            'color': '#f8fafc',
            'fontSize': '9px',
            'fontWeight': '600',
            'padding': '2px 8px',
            'borderRadius': '999px',
            'textTransform': 'uppercase',
            'letterSpacing': '0.08em',
            'pointerEvents': 'none'
        }
    )

    img = html.Img(
        src=image['thumbnail'],
        style={
            'height': f'{height}px',
            'width': 'auto',
            'objectFit': 'cover',
            'display': 'block'
        }
    )

    wrapper = html.Div(
        [img, badge],
        style={
            'position': 'relative',
            'border': '1px solid #e2e8f0',
            'borderRadius': '8px',
            'backgroundColor': '#ffffff',
            'display': 'inline-flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'padding': '4px',
            'minWidth': f'{int(height * 0.75)}px'
        }
    )

    children = [wrapper]
    if show_caption:
        year = (image.get('date') or '')[:4]
        caption = html.Div(
            year,
            style={
                'fontSize': '10px',
                'color': '#64748b',
                'marginTop': '4px',
                'textAlign': 'center'
            }
        )
        children.append(caption)

    href = image.get('view_url') or image.get('manifest') or "#"
    link = html.A(
        "Åpne kilde",
        href=href,
        target="_blank",
        className="image-thumb-link"
    )
    children.append(link)

    return html.Div(
        children,
        id={'type': 'image-thumb', 'context': context, 'index': index},
        n_clicks=0,
        role='button',
        tabIndex=0,
        className="image-thumb",
        title=f"{title} ({image.get('date') or 'ukjent dato'})"
    )


def _build_gallery_card(image: dict) -> html.Div | None:
    if not image:
        return None
    full_src = image.get('full') or image.get('thumbnail')
    if not full_src:
        return None
    title = image.get('title') or "Historisk bilde"
    date = image.get('date') or "ukjent"
    source_label = image.get('source') or "NB.no"
    description = image.get('description') or ''

    meta = html.Div([
        html.Strong(title),
        html.Span(f"{date}", style={'display': 'block', 'color': '#475569'}),
        html.Span(description, style={'display': 'block'}) if description else None
    ], className="image-meta")

    actions = html.Div([
        html.Span(source_label.upper(), className="source-badge"),
        html.A(
            "Åpne kilde",
            href=image.get('view_url') or image.get('manifest') or "#",
            target="_blank",
            className="image-gallery-link"
        )
    ], className="image-actions")

    return html.Div([
        html.Img(
            src=full_src,
            style={
                'width': '100%',
                'height': 'auto',
                'borderRadius': '8px',
                'backgroundColor': '#000'
            }
        ),
        meta,
        actions
    ], className="image-gallery-card")


def _render_place_summary_from_search(place: dict) -> tuple[html.Div, list[dict]]:
    books = place.get('books', [])
    
    # Fetch historical images
    images = []
    search_name = place.get('name') or place.get('token')
    if search_name:
        # Clean search name (remove 'i ', 'på ', etc if needed, but start simple)
        images = fetch_historical_images(search_name, limit=5)

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
    
    # Image gallery section
    gallery = html.Div()
    thumb_elements: list[html.Div] = []
    if images:
        for idx, img in enumerate(images):
            tile = _build_image_tile(
                img,
                height=100,
                show_caption=True,
                context='place',
                index=idx
            )
            if tile:
                thumb_elements.append(tile)
    if thumb_elements:
        gallery = html.Div([
            html.Div("Historiske bilder (IIIF)", style={
                'fontSize': '12px', 'fontWeight': '600', 'color': '#64748b', 
                'marginBottom': '8px', 'textTransform': 'uppercase', 'letterSpacing': '0.05em'
            }),
            html.Div(
                thumb_elements,
                style={
                    'display': 'flex', 'gap': '10px', 'overflowX': 'auto', 
                    'paddingBottom': '8px', 'scrollbarWidth': 'thin'
                }
            )
        ], style={'margin': '16px 0'})

    place_token = place.get('token') or ''
    token_query = quote(f'"{place_token}"') if place_token else ''

    total_books = place.get('book_count', 0)
    total_mentions = place.get('frequency', 0)
    page_size = 20
    book_list_caption = html.Div(
        f"Viser topp {min(page_size, len(books))} av {total_books:,} bøker (sortert på forekomster) · {total_mentions:,} totalt antall forekomster",
        style={'fontSize': '12px', 'color': '#475569', 'marginBottom': '6px'}
    ) if books else html.Div("Ingen bøker for dette stedet i aktivt korpus.", style={'fontSize': '12px', 'color': '#64748b'})

    book_rows = [
        html.Div([
            html.A(
                f"{row.get('title')} ({row.get('year')})",
                href=(
                    f"https://www.nb.no/items/{row.get('urn')}?searchText={token_query}"
                ) if row.get('urn') else "#",
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
    ]

    book_list = html.Div([book_list_caption] + book_rows) if books else html.Div(
        "No book details available", style={'color': '#475569'}
    )

    concordance_button = None
    if place_token:
        concordance_button = html.Button(
            "Konkordans",
            id={'type': 'open-concordance', 'token': place_token},
            n_clicks=0,
            style={
                'border': '1px solid #e2e8f0',
                'backgroundColor': '#f8fafc',
                'color': '#0f172a',
                'fontSize': '12px',
                'padding': '6px 10px',
                'borderRadius': '8px',
                'cursor': 'pointer',
                'alignSelf': 'flex-start'
            }
        )

    summary_children = [header, gallery, html.Hr(style={'margin': '10px 0'})]
    if concordance_button:
        summary_children.append(concordance_button)
    summary_children.append(book_list)

    summary = html.Div(summary_children)
    return summary, images


def _fetch_author_book_ids(author_key: str | None = None, author_name: str | None = None) -> list[int]:
    """
    Resolve a list of DHLab IDs for a given author.

    Prefer passing `author_key` (LOWER(TRIM(author))) so we have a stable lookup.
    `author_name` is kept for backwards compatibility and falls back to a LIKE query.
    """
    if not author_key and not author_name:
        return []
    conn = get_db_connection()
    try:
        if author_key:
            df = pd.read_sql_query(
                """
                SELECT DISTINCT dhlabid
                FROM corpus
                WHERE author IS NOT NULL
                  AND TRIM(author) != ''
                  AND LOWER(TRIM(author)) = ?
                """,
                conn,
                params=(author_key,)
            )
        else:
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
        ),
        dbc.Button(
            "Filter korpus med kollokasjon",
            id='filter-collocation-corpus',
            color='primary',
            outline=True,
            size='sm',
            className="mt-2"
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
                'label': 'View',
                'subtitle': 'List',
                'color_class': 'chip-corpus',
                'title': 'Toggle Corpus View'
            },
            {
                'chip_id': 'card-chip-builder',
                'label': 'Build',
                'subtitle': 'Modify',
                'color_class': 'chip-builder',
                'title': 'Toggle Corpus Build/Modify'
            }
        ]
    },
    {
        'group_id': 'authors',
        'label': 'Authors',
        'pill_class': 'chip-pill-authors',
        'children': [
            {
                'chip_id': 'card-chip-author-list',
                'label': 'Authors',
                'subtitle': 'List',
                'color_class': 'chip-author-list',
                'title': 'View Author List'
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
    },
    {
        'group_id': 'visuals',
        'label': 'Visuals',
        'pill_class': 'chip-pill-visualization',
        'children': [
            {
                'chip_id': 'card-chip-map-visuals',
                'label': 'Map',
                'subtitle': 'Visuals',
                'color_class': 'chip-visuals-map',
                'title': 'Toggle Map Visuals'
            },
            {
                'chip_id': 'card-chip-heatmap-visuals',
                'label': 'Heatmap',
                'subtitle': 'Visuals',
                'color_class': 'chip-visuals-heat',
                'title': 'Toggle Heatmap Visuals'
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
        'card_key': 'map-visuals',
        'store_id': 'map-visuals-window-state',
        'container_id': 'map-visuals-container',
        'body_id': 'map-visuals-body',
        'minimize_id': 'minimize-map-visuals',
        'close_id': 'close-map-visuals'
    },
    {
        'card_key': 'heatmap-visuals',
        'store_id': 'heatmap-visuals-window-state',
        'container_id': 'heatmap-visuals-container',
        'body_id': 'heatmap-visuals-body',
        'minimize_id': 'minimize-heatmap-visuals',
        'close_id': 'close-heatmap-visuals'
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
    },
    {
        'card_key': 'author-list',
        'store_id': 'author-list-window-state',
        'container_id': 'author-list-container',
        'body_id': 'author-list-body',
        'minimize_id': 'minimize-author-list',
        'close_id': 'close-author-list'
    },
    {
        'card_key': 'author-info',
        'store_id': 'author-info-window-state',
        'container_id': 'author-info-container',
        'body_id': 'author-info-body',
        'minimize_id': 'minimize-author-info',
        'close_id': 'close-author-info'
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
            Output(store_id, 'data', allow_duplicate=True),
            Output(container_id, 'style', allow_duplicate=True),
            Output(body_id, 'style', allow_duplicate=True),
            Output(close_id, 'disabled', allow_duplicate=True),
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
                    restored_body = restored_body or {}
                    restored_body['opacity'] = '1'
                    restored_body['pointerEvents'] = 'auto'
                    return restored_state, dash.no_update, restored_body, False
                normalized_body = dict(body_style or {})
                normalized_body['opacity'] = '1'
                normalized_body['pointerEvents'] = 'auto'
                return {'minimized': False}, dash.no_update, normalized_body, False
            if trigger == cfg['minimize_id']:
                new_state, new_container_style, new_body_style = _toggle_window_minimize(
                    card_key,
                    state,
                    container_style,
                    body_style
                )
                # disable close button only while minimized; re-enable when restored
                disabled = new_state.get('minimized', False)
                return new_state, new_container_style, new_body_style, disabled
            raise PreventUpdate


_register_window_callbacks()

# Reflect minimized state on minimize button class/style for styling
for cfg in WINDOW_CONTROL_CONFIG:
    minimize_id = cfg['minimize_id']
    store_id = cfg['store_id']

    @app.callback(
        Output(minimize_id, 'className', allow_duplicate=True),
        Output(minimize_id, 'style', allow_duplicate=True),
        Input(store_id, 'data'),
        prevent_initial_call=True
    )
    def _set_minimize_state(window_state, base_class="card-window-btn window-minimize"):
        state = window_state or {}
        is_min = state.get('minimized')
        cls = f"{base_class} minimized-active" if is_min else base_class
        style = {'color': '#22c55e'} if is_min else {'color': '#f59e0b'}
        return cls, style

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
        cur = conn.cursor()
        # Temp table for books to avoid SQLite 999-parameter limit
        cur.execute("DROP TABLE IF EXISTS tmp_books")
        cur.execute("CREATE TEMP TABLE tmp_books (dhlabid INTEGER)")
        cur.executemany("INSERT INTO tmp_books (dhlabid) VALUES (?)", [(int(b),) for b in books])

        if tokens:
            cur.execute("DROP TABLE IF EXISTS tmp_tokens")
            cur.execute("CREATE TEMP TABLE tmp_tokens (token TEXT)")
            cur.executemany("INSERT INTO tmp_tokens (token) VALUES (?)", [(t,) for t in tokens])

        if tokens:
            query = """
            WITH selected_places AS (
                SELECT 
                    p.token,
                    p.modern as name,
                    p.latitude,
                    p.longitude
                FROM places p
                JOIN tmp_tokens tt ON p.token = tt.token
                WHERE p.latitude IS NOT NULL 
                  AND p.longitude IS NOT NULL
                  AND CAST(p.latitude AS REAL) != 0
                  AND CAST(p.longitude AS REAL) != 0
            ),
            selected_books AS (
                SELECT dhlabid FROM tmp_books
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
            JOIN selected_books sb ON b.dhlabid = sb.dhlabid
            GROUP BY sp.token, sp.name, sp.latitude, sp.longitude
            ORDER BY frequency DESC
            """
            places_df = pd.read_sql_query(query, conn)
        else:
            query = """
            WITH selected_books AS (
                SELECT dhlabid FROM tmp_books
            )
            SELECT 
                b.token,
                p.modern as name,
                p.latitude,
                p.longitude,
                SUM(b.book_count) as frequency,
                COUNT(DISTINCT b.dhlabid) as book_count
            FROM books b
            JOIN selected_books sb ON b.dhlabid = sb.dhlabid
            JOIN places p ON b.token = p.token
            WHERE p.latitude IS NOT NULL 
              AND p.longitude IS NOT NULL
              AND CAST(p.latitude AS REAL) != 0
              AND CAST(p.longitude AS REAL) != 0
            GROUP BY b.token, p.modern, p.latitude, p.longitude
            ORDER BY frequency DESC
            """
            places_df = pd.read_sql_query(query, conn)

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
        ORDER BY bm.mention_count DESC, c.year DESC, c.title
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

def get_corpus_authors(book_ids: list[int], filter_text: str = None) -> pd.DataFrame:
    if not book_ids:
        return pd.DataFrame()
    conn = get_db_connection()
    try:
        query = f"""
        SELECT 
            LOWER(TRIM(author)) as author_key,
            MIN(TRIM(author)) as display_name,
            COUNT(DISTINCT dhlabid) as book_count,
            MIN(year) as min_year,
            MAX(year) as max_year
        FROM corpus
        WHERE dhlabid IN ({','.join(['?'] * len(book_ids))})
        AND author IS NOT NULL 
        AND TRIM(author) != ''
        """
        params = list(book_ids)
        
        if filter_text:
            query += " AND LOWER(author) LIKE ?"
            params.append(f"%{filter_text.lower()}%")
            
        query += """
        GROUP BY LOWER(TRIM(author))
        ORDER BY book_count DESC, display_name ASC
        """
        return pd.read_sql_query(query, conn, params=tuple(params))
    finally:
        conn.close()

@app.callback(
    Output('author-list-container', 'style', allow_duplicate=True),
    Input('card-chip-author-list', 'n_clicks'),
    Input('close-author-list', 'n_clicks'),
    State('author-list-container', 'style'),
    State('chip-group-open', 'data'),
    prevent_initial_call=True
)
def toggle_author_list(n_open, n_close, current_style, group_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    style = dict(current_style or {})
    
    if trigger_id == 'close-author-list':
        style['display'] = 'none'
        return style
        
    if trigger_id == 'card-chip-author-list':
        # Reset minimize if hidden
        if style.get('display') == 'none':
             # Reset minimize logic if needed, but standard toggle behavior:
             style['display'] = 'flex'
             # Position it nicely if first open
             if 'top' not in style: style['top'] = '80px'
             if 'left' not in style: style['left'] = '400px'
        else:
            style['display'] = 'none'
        return style
        
    return style

@app.callback(
    Output('author-list-content', 'children'),
    Output('author-count-badge', 'children'),
    Input('current-dhlabids-store', 'data'),
    Input('author-list-filter', 'value'),
    prevent_initial_call=True
)
def update_author_list(book_ids, filter_text):
    if not book_ids:
        return html.Div("No corpus selected.", style={'padding': '10px', 'color': '#666'}), "0 authors"
        
    df = get_corpus_authors(book_ids, filter_text)
    
    if df.empty:
         return html.Div("No authors found.", style={'padding': '10px', 'color': '#666'}), "0 authors"

    items = []
    for _, row in df.iterrows():
        author_key = row['author_key']
        author = row['display_name']
        count = row['book_count']
        years = f"({int(row['min_year'])}–{int(row['max_year'])})" if pd.notnull(row['min_year']) else ""
        
        items.append(
            html.Button(
                [
                    html.Div([
                        html.Span(author, style={'fontWeight': '500', 'color': '#334155'}),
                        html.Span(years, style={'fontSize': '12px', 'color': '#94a3b8', 'marginLeft': '6px'})
                    ]),
                    html.Div([
                        html.Span(f"{count} books", style={'fontSize': '12px', 'color': '#64748b', 'marginRight': '10px'}),
                        html.I(className="fas fa-chevron-right", style={'color': '#94a3b8'})
                    ], style={'display': 'flex', 'alignItems': 'center'})
                ],
                id={'type': 'author-select-row', 'author_key': author_key, 'display_name': author},
                n_clicks=0,
                type='button',
                className="author-list-item",
                style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'padding': '8px 12px',
                    'borderBottom': '1px solid #f1f5f9',
                    'cursor': 'pointer',
                    'transition': 'background-color 0.2s'
                }
            )
        )
        
    return html.Div(items), f"{len(df):,} authors"

@app.callback(
    Output('selected-author-store', 'data'),
    Input({'type': 'author-select-row', 'author_key': ALL, 'display_name': ALL}, 'n_clicks_timestamp'),
    prevent_initial_call=True
)
def set_selected_author(n_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
        
    # Find which button was clicked
    trigger = ctx.triggered[0]
    trigger_timestamp = trigger.get('value')

    # Ignore render/list-change events; only act on real clicks
    if not trigger_timestamp or trigger_timestamp <= 0:
        raise PreventUpdate

    trigger_id = getattr(ctx, "triggered_id", None)
    prop_id = None
    if isinstance(trigger_id, dict):
        prop_id = trigger_id
    else:
        raw_id = trigger['prop_id'].split('.', 1)[0]
        try:
            prop_id = json.loads(raw_id)
        except Exception as exc:
            print(f"[AuthorDetails] Unable to parse trigger id: {exc} (raw={raw_id})")
            raise PreventUpdate

    author_key = prop_id.get('author_key')
    display_name = prop_id.get('display_name')
    print(f"[AuthorDetails] Button click captured for key={author_key} ({display_name}) ts={trigger_timestamp}")
    return prop_id


@app.callback(
    Output('author-info-container', 'style', allow_duplicate=True),
    Output('author-info-content', 'children'),
    Output('author-images-store', 'data'),
    Input('selected-author-store', 'data'),
    State('author-info-container', 'style'),
    State('current-dhlabids-store', 'data'),
    prevent_initial_call=True
)
def show_author_details(selected_author, current_style, current_books):
    if not selected_author:
        raise PreventUpdate

    author_key = selected_author.get('author_key')
    author_display = selected_author.get('display_name') or author_key
    if not author_key:
        raise PreventUpdate

    current_books = current_books or []
    print(f"[AuthorDetails] Requested key={author_key} ({author_display}), corpus_size={len(current_books)}")

    # Fetch details
    # 1. Images (fetch multiple, like for places)
    try:
        images = fetch_historical_images(author_display, limit=5)
    except Exception as exc:
        print(f"[AuthorDetails] Image fetch failed for {author_display}: {exc}")
        images = []
    image_section = html.Div()
    if images:
        thumb_elements = []
        for idx, img in enumerate(images):
            tile = _build_image_tile(
                img,
                height=120,
                show_caption=True,
                context='author',
                index=idx
            )
            if tile:
                thumb_elements.append(tile)
        image_section = html.Div([
            html.Div("Historiske bilder (IIIF)", style={
                'fontSize': '12px', 'fontWeight': '600', 'color': '#64748b', 
                'marginBottom': '8px', 'textTransform': 'uppercase', 'letterSpacing': '0.05em'
            }),
            html.Div(
                thumb_elements,
                style={
                    'display': 'flex', 'gap': '10px', 'overflowX': 'auto', 
                    'paddingBottom': '8px', 'scrollbarWidth': 'thin'
                }
            )
        ], style={'marginBottom': '16px'})
    else:
        # Placeholder or empty
        image_section = html.Div([
            html.I(className="fas fa-user", style={'fontSize': '48px', 'color': '#cbd5e1'}),
            html.Div("No image found", style={'marginTop': '8px', 'fontSize': '12px', 'color': '#94a3b8'})
        ], style={'width': '100%', 'height': '120px', 'display': 'flex', 'flexDirection': 'column', 'alignItems': 'center', 'justifyContent': 'center', 'backgroundColor': '#f8fafc', 'borderRadius': '8px', 'marginBottom': '12px'})

    # 2. Books in corpus
    books_df = pd.DataFrame()
    if current_books:
        conn = get_db_connection()
        try:
            books_query = f"""
            SELECT title, year, urn, author
            FROM corpus
            WHERE dhlabid IN ({','.join(['?'] * len(current_books))})
            AND LOWER(TRIM(author)) = ?
            ORDER BY year ASC
            """
            params = tuple(list(current_books) + [author_key])
            books_df = pd.read_sql_query(books_query, conn, params=params)
        finally:
            conn.close()
    else:
        print("[AuthorDetails] current_books is empty – no corpus loaded")

    print(f"[AuthorDetails] Book rows for key={author_key}: {len(books_df)}")
        
    book_list = html.Div([
        html.Div([
            html.A(
                f"{row['title']} ({int(row['year']) if pd.notnull(row['year']) else '?'})",
                href=f"https://www.nb.no/items/{row['urn']}" if row['urn'] else "#",
                target="_blank",
                style={'color': '#3b82f6', 'textDecoration': 'none', 'fontWeight': '500', 'fontSize': '13px'}
            )
        ], style={'padding': '6px 0', 'borderBottom': '1px solid #f1f5f9'})
        for _, row in books_df.iterrows()
    ], style={'maxHeight': '200px', 'overflowY': 'auto'})

    content = html.Div([
        html.H4(author_display, style={'marginBottom': '16px', 'color': '#1e293b'}),
        image_section,
        html.H6(f"Books in Corpus ({len(books_df)})", style={'marginTop': '16px', 'marginBottom': '8px', 'color': '#64748b', 'fontSize': '12px', 'textTransform': 'uppercase'}),
        book_list
    ])

    style = dict(current_style or {})
    style['display'] = 'flex'
    style = _bump_z(style)
    
    image_payload = _make_image_store_payload('author', author_display, None, images)
    return style, content, image_payload

@app.callback(
    Output('author-info-container', 'style', allow_duplicate=True),
    Input('close-author-info', 'n_clicks'),
    State('author-info-container', 'style'),
    prevent_initial_call=True
)
def close_author_info(n_clicks, current_style):
    if not n_clicks:
        raise PreventUpdate
    style = dict(current_style or {})
    style['display'] = 'none'
    return style

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
    create_map_visuals_card(),
    create_heatmap_visuals_card(),
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
    
    # Concordance modal (opens from Place Details)
    dbc.Modal(
        [
            dbc.ModalHeader("Konkordans"),
            dbc.ModalBody([
                dbc.Input(id='concordance-query', type='text', placeholder='Søkestreng', size='sm'),
                dbc.Input(id='concordance-window', type='number', min=1, max=200, step=1, value=25, size='sm', className='mt-2'),
                dbc.Button("Hent konkordanser", id='run-concordance', color='secondary', size='sm', className='mt-2'),
                html.Div(id='concordance-output', style={'marginTop': '8px', 'maxHeight': '260px', 'overflowY': 'auto', 'fontSize': '13px'})
            ]),
            dbc.ModalFooter([
                dbc.Button("Last ned CSV", id='download-concordance-btn', color='light', className='me-2'),
                dbc.Button("Lukk", id='close-concordance', className='ms-auto')
            ])
        ],
        id='concordance-modal',
        is_open=False,
        size='lg'
    ),
    dcc.Download(id='download-concordance'),

    # Place summary container
    dbc.Card([
        dbc.CardHeader(
            card_title_bar(
                'place-summary',
                'fa fa-grip-horizontal',
                "Place Details",
                close_button_id='close-summary',
                close_button_title="Hide place details"
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
    ], id='place-summary-container', className="position-absolute dialog-card place-summary-card", style={
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
                    html.Div([
                        dcc.Input(
                            id='place-search',
                            type='text',
                            placeholder='Type to search...',
                            className="form-control ps-4",
                            debounce=True,
                            style={
                                'position': 'relative',
                                'paddingLeft': '30px'
                            }
                        ),
                        html.Button(
                            html.I(className="fas fa-search"),
                            id='place-search-icon',
                            n_clicks=0,
                            title="Søk i korpuset. Bruk * som jokertegn (f.eks. *on*).",
                            style={
                                'position': 'absolute',
                                'left': '6px',
                                'top': '50%',
                                'transform': 'translateY(-50%)',
                                'color': '#94a3b8',
                                'fontSize': '0.85rem',
                                'background': 'transparent',
                                'border': 'none',
                                'padding': 0,
                                'margin': 0,
                                'lineHeight': '1',
                                'cursor': 'pointer'
                            }
                        )
                    ], style={'position': 'relative'})
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
            ], className="mb-2 d-flex flex-column flex-md-row"),
            html.Div([
                html.Button("←", id="places-page-prev", n_clicks=0, className="btn btn-outline-secondary btn-sm"),
                html.Span(id="places-page-label", style={'minWidth': '160px', 'textAlign': 'center', 'fontSize': '0.9rem'}),
                html.Button("→", id="places-page-next", n_clicks=0, className="btn btn-outline-secondary btn-sm"),
                dcc.Input(
                    id='places-page-jump',
                    type='number',
                    placeholder='Gå til side',
                    min=1,
                    debounce=True,
                    style={'width': '110px', 'height': '32px', 'fontSize': '0.9rem'}
                ),
                dbc.Button(
                    "Oppdater kart",
                    id='update-map-from-page',
                    n_clicks=0,
                    color='secondary',
                    size='sm',
                    className='ms-2'
                ),
                dbc.Button(
                    html.I(className="fas fa-eraser"),
                    id='clear-selected-place',
                    color='link',
                    size='sm',
                    className='mb-2',
                    style={
                        'fontSize': '12px',
                        'padding': '6px 8px',
                        'color': '#475569',
                        'border': 'none',
                        'flex': '0 0 auto'
                    },
                    title="Nullstill markering"
                ),
                html.Div([
                    dbc.Checklist(
                        options=[{"label": "Bruk underliste i heatmap", "value": "subset"}],
                        value=[],
                        id='heatmap-subset-checkbox',
                        switch=True,
                        persistence=True
                    )
                ], className="ms-3", style={'fontSize': '0.85rem', 'flex': '0 0 auto'})
            ], className="mb-2 d-flex flex-row align-items-center gap-2 flex-wrap"),
            html.Div([
                html.Div([
                    html.Div([
                        html.Div(
                            build_places_tab(
                                'places-frequency-summary',
                                'places-frequency-table',
                                'download-places-frequency-btn',
                                'download-places-frequency',
                                None,
                                action_prefix=None,
                                activate_btn_id=None,
                                source_key='frequency',
                                activate_title=None
                            ),
                            id='places-frequency-panel',
                            style={'flex': '1 1 auto', 'minHeight': 0, 'display': 'flex'}
                        )
                    ], className="places-mode-panels flex-grow-1 d-flex flex-column", style={'minHeight': 0, 'gap': '0.75rem'}),
                    dbc.Button(id='activate-places-frequency', style={'display': 'none'}, color='light')
                ], className="flex-grow-1 d-flex flex-column", style={'minHeight': 0, 'gap': '0.75rem'}),
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
    create_author_list_card(),
    create_author_info_card(),
    dbc.Modal(
        [
            dbc.ModalHeader(
                html.Div(
                    [
                        dbc.ModalTitle("Historiske bilder", id='image-gallery-title'),
                        html.Button(
                            html.Span(className="visually-hidden", children="Lukk"),
                            id='image-gallery-dismiss',
                            className='btn-close',
                            n_clicks=0,
                            type='button'
                        )
                    ],
                    className='d-flex align-items-center justify-content-between w-100'
                ),
                close_button=False
            ),
            dbc.ModalBody(
                dcc.Loading(
                    html.Div(id='image-gallery-grid', className='image-gallery-grid'),
                    type='default'
                )
            ),
            dbc.ModalFooter(
                dbc.Button("Lukk", id='image-gallery-close', color='secondary', n_clicks=0)
            )
        ],
        id='image-gallery-modal',
        is_open=False,
        backdrop='static',
        size='xl',
        scrollable=True,
        centered=True,
        className='image-gallery-modal'
    ),

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
    dcc.Store(id='collocation-place-counts', data={}),
    dcc.Store(id='places-mode', data='basis'),
    dcc.Store(id='places-sort-field', data='frequency'),
    dcc.Store(id='places-sort-dir', data='desc'),
    dcc.Store(id='places-page', data=0),
    dcc.Store(id='heatmap-subset-mode', data='all'),
    dcc.Store(id='dialog-size-store', data=copy.deepcopy(DEFAULT_CARD_SIZES)),
    dcc.Store(id='place-summary-window-state', data={'minimized': False}),
    dcc.Store(id='place-names-window-state', data={'minimized': False}),
    dcc.Store(id='corpus-controls-window-state', data={'minimized': False}),
    dcc.Store(id='map-visuals-window-state', data={'minimized': False}),
    dcc.Store(id='heatmap-visuals-window-state', data={'minimized': False}),
    dcc.Store(id='corpus-builder-window-state', data={'minimized': False}),
    dcc.Store(id='collocation-card-window-state', data={'minimized': False}),
    dcc.Store(id='similarity-card-window-state', data={'minimized': False}),
    dcc.Store(id='global-search-filter-store', data=['places', 'books', 'authors']),
    dcc.Store(id='similarity-places-data'),
    dcc.Store(id='place-images-store', data={'source': 'place', 'label': None, 'subtitle': None, 'images': []}),
    dcc.Store(id='author-images-store', data={'source': 'author', 'label': None, 'subtitle': None, 'images': []}),
    dcc.Store(id='image-gallery-store'),

    # Add the new corpus builder card
    create_corpus_builder_card(categories_list=categories_list, authors_list=authors_list, titles_list=titles_list),
    # Add intervals for clearing download status messages
    dcc.Interval(id='clear-download-status-interval', interval=6000, n_intervals=0, disabled=True),
    dcc.Interval(id='clear-heatmap-download-status-interval', interval=6000, n_intervals=0, disabled=True),
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
                    '#map-visuals-container',
                    '#heatmap-visuals-container',
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
    Output('collocation-place-counts', 'data'),
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
        return html.Div("Enter one or more keywords to analyse collocations.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), [], {}
    if not current_books:
        return html.Div("Corpus is empty. Build or upload a corpus first.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), [], {}

    words = [w.strip() for w in words_value.split(',') if w.strip()]
    if not words:
        return html.Div("No valid keywords provided.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), [], {}

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
        return html.Div("No URNs found for the current corpus; collocations require identifiable texts.", style={'color': '#dc2626', 'fontSize': '0.8rem'}), [], {}

    sample_size = min(len(urns), 5000)

    try:
        coll = dh.Collocations(urns, words, before=before, after=after, samplesize=sample_size)
        coll_df = coll.frame.copy()
    except Exception as err:
        return html.Div(f"Error retrieving collocations: {err}", style={'color': '#dc2626', 'fontSize': '0.8rem'}), [], {}

    if coll_df is None or coll_df.empty:
        return html.Div("No collocations found for the selected keywords.", style={'color': '#475569', 'fontSize': '0.8rem'}), [], {}

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
        return message, [], {}

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
        .head(23000)
    )
    tokens = match_df['Token'].dropna().astype(str).unique().tolist()
    summary = html.Div(
        f"Fant {len(tokens)} steder. Listen kan avkortes av Max places i stedsvisningen.",
        style={'color': '#0f172a', 'fontSize': '0.85rem'}
    )
    count_map = match_df.set_index('Token')['Total count'].to_dict()
    return summary, tokens, count_map

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
    Output('places-collocation-data', 'data'),
    Input('filtered-data', 'data'),
    Input('corpus-max-places-slider', 'value'),
    Input('collocation-place-tokens', 'data'),
    Input('collocation-place-counts', 'data'),
    Input('current-dhlabids-store', 'data'),
    State('all-places-store', 'data')
)
def update_places_datasets(filtered_data_json, max_places, collocation_tokens, collocation_counts, current_books, all_places_json):
    import pandas as pd
    ctx = dash.callback_context
    triggered = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    max_places = max_places or 500
    base_columns = ['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count']
    empty_json = pd.DataFrame(columns=base_columns).to_json(date_format='iso', orient='split')

    if not filtered_data_json:
        return empty_json, empty_json

    df = load_places_frame(filtered_data_json)
    df['frequency'] = pd.to_numeric(df.get('frequency'), errors='coerce')
    df['book_count'] = pd.to_numeric(df.get('book_count'), errors='coerce')
    print(f"[places] source={triggered} rows={len(df)} max_places={max_places}")
    if df.empty:
        return empty_json, empty_json

    freq_df = (
        df.sort_values(by='frequency', ascending=False)
        .head(max_places)
        .reset_index(drop=True)
    )

    tokens = set(collocation_tokens or [])
    count_map = collocation_counts or {}
    if tokens:
        base_colloc_df = df
        if all_places_json:
            try:
                base_colloc_df = load_places_frame(all_places_json)
            except Exception:
                base_colloc_df = df
        colloc_df = (
            base_colloc_df[base_colloc_df['token'].isin(tokens)]
            .sort_values(by='frequency', ascending=False)
            .reset_index(drop=True)
        )
        if not colloc_df.empty:
            colloc_df['collocation_count'] = colloc_df['token'].astype(str).map(count_map).fillna(0).astype(int)
    else:
        colloc_df = pd.DataFrame(columns=base_columns)

    print(f"[places] freq={len(freq_df)} colloc={len(colloc_df)}")
    return (
        freq_df.to_json(date_format='iso', orient='split'),
        colloc_df.to_json(date_format='iso', orient='split')
    )


@app.callback(
    Output('places-frequency-summary', 'children'),
    Output('places-frequency-table', 'children'),
    Output('filtered-data', 'data', allow_duplicate=True),
    Output('places-page-label', 'children'),
    Output('update-map-from-page', 'color'),
    Input('places-frequency-data', 'data'),
    Input('place-search', 'value'),
    Input('place-search-icon', 'n_clicks'),
    Input('places-collocation-data', 'data'),
    Input('similarity-places-data', 'data'),
    Input('places-mode', 'data'),
    Input('places-sort-field', 'data'),
    Input('places-sort-dir', 'data'),
    Input('corpus-max-places-slider', 'value'),
    Input('all-places-store', 'data'),
    Input('places-page', 'data'),
    Input('update-map-from-page', 'n_clicks'),
    State('selected-place', 'data'),
    prevent_initial_call=True
)
def display_frequency_places(freq_json, search_term, search_clicks, colloc_json, sim_json, mode_value, sort_field, sort_dir, max_places, all_places_json, page, update_map_clicks, selected_place):
    max_places = max_places or 500
    sort_field = sort_field or 'frequency'
    sort_dir = sort_dir or 'desc'
    page = page or 0
    required_columns = ['token', 'name', 'latitude', 'longitude', 'frequency', 'book_count']

    df_all = load_places_frame(all_places_json) if all_places_json else load_places_frame(freq_json)
    if df_all is None or df_all.empty:
        df_all = pd.DataFrame(columns=required_columns)
    for col in required_columns:
        if col not in df_all.columns:
            df_all[col] = pd.NA
    df_all['frequency'] = pd.to_numeric(df_all.get('frequency'), errors='coerce')
    df_all['book_count'] = pd.to_numeric(df_all.get('book_count'), errors='coerce')

    mode_value = mode_value or 'basis'
    mode_label = None

    if mode_value == 'sample':
        df_filtered = df_all.sample(
            n=min(max_places, len(df_all)),
            replace=False,
            random_state=None
        )
        page = 0
        mode_label = "Sample"
        print(f"[places] sample mode (toggle): {len(df_filtered)} rows (max_places={max_places})")
    elif mode_value == 'coll':
        coll_df = load_places_frame(colloc_json) if colloc_json else pd.DataFrame(columns=required_columns)
        if coll_df is None or coll_df.empty:
            df_filtered = df_all
            mode_label = "Kollokasjon (tom)"
            print(f"[places] collocation mode (toggle) empty -> fallback to base: {len(df_filtered)} rows")
        else:
            df_filtered = coll_df
            mode_label = "Kollokasjon"
            print(f"[places] collocation mode (toggle): {len(df_filtered)} rows")
        page = 0
    elif mode_value == 'sim':
        sim_df = load_places_frame(sim_json) if sim_json else pd.DataFrame(columns=required_columns)
        if sim_df is None or sim_df.empty:
            df_filtered = df_all
            mode_label = "Similarity (tom)"
            print(f"[places] similarity mode (toggle) empty -> fallback to base: {len(df_filtered)} rows")
        else:
            df_filtered = sim_df
            mode_label = "Similarity"
            print(f"[places] similarity mode (toggle): {len(df_filtered)} rows")
        page = 0
    else:
        if search_term:
            search_trim = search_term.strip()
            search_lower = search_trim.lower()
            if search_lower.startswith('#sample'):
                df_filtered = df_all.sample(
                    n=min(max_places, len(df_all)),
                    replace=False,
                    random_state=None
                )
                page = 0
                mode_label = "Sample"
                print(f"[places] sample mode: {len(df_filtered)} rows (max_places={max_places})")
            elif search_lower.startswith('#coll'):
                coll_df = load_places_frame(colloc_json) if colloc_json else pd.DataFrame(columns=required_columns)
                df_filtered = coll_df
                page = 0
                mode_label = "Kollokasjon"
                print(f"[places] collocation mode: {len(df_filtered)} rows")
            elif search_lower.startswith('#sim'):
                sim_df = load_places_frame(sim_json) if sim_json else pd.DataFrame(columns=required_columns)
                df_filtered = sim_df
                page = 0
                mode_label = "Similarity"
                print(f"[places] similarity mode: {len(df_filtered)} rows")
            else:
                df_filtered = filter_places_search(df_all, search_term)
                print(f"[places] freq table search '{search_term}': hits={len(df_filtered)}")
        else:
            df_filtered = df_all
            print(f"[places] freq table reset to base: {len(df_filtered)} rows")

    if mode_value == 'coll' and 'collocation_count' in df_filtered.columns:
        sort_field = 'collocation_count'
    if sort_field not in df_filtered.columns:
        sort_field = 'frequency'
    ascending_main = (sort_dir == 'asc')
    df_filtered = df_filtered.sort_values(
        by=[sort_field, 'frequency', 'book_count', 'token'],
        ascending=[ascending_main, False, False, True]
    )

    total_count = len(df_filtered)
    page_size = max_places
    total_pages = max(1, math.ceil(total_count / page_size))
    page = min(page, total_pages - 1)
    offset = page * page_size
    df_page = df_filtered.iloc[offset:offset + page_size]
    page_label = f"Side {page + 1} / {total_pages} – viser {len(df_page)} av {total_count}"

    filtered_payload = df_page.to_json(date_format='iso', orient='split')
    update_btn_color = 'secondary' if max_places <= 500 else 'primary'

    summary, table = render_place_preview(
        df_page,
        selected_place,
        empty_message="Ingen steder tilgjengelig ennå.",
        sort_field=sort_field,
        sort_dir=sort_dir,
        total_count=total_count,
        show_mode_toggle=True,
        mode_value=mode_value
    )
    return summary, table, filtered_payload, page_label, update_btn_color


@app.callback(
    Output('places-mode', 'data'),
    Output('place-search', 'value'),
    Output('places-page', 'data', allow_duplicate=True),
    Input('places-mode-radio', 'value'),
    State('places-mode', 'data'),
    prevent_initial_call=True
)
def set_places_mode(new_mode, current_mode):
    if not new_mode:
        raise PreventUpdate
    if new_mode == current_mode:
        raise PreventUpdate
    return new_mode, '', 0


@app.callback(
    Output('places-page', 'data'),
    Input('places-page-prev', 'n_clicks'),
    Input('places-page-next', 'n_clicks'),
    Input('place-search-icon', 'n_clicks'),
    Input('places-page-jump', 'value'),
    Input('places-frequency-data', 'data'),
    Input('place-search', 'value'),
    Input('corpus-max-places-slider', 'value'),
    Input('all-places-store', 'data'),
    State('places-page', 'data'),
    prevent_initial_call=True
)
def update_places_page(prev_clicks, next_clicks, search_clicks, jump_value, freq_json, search_term, max_places, all_places_json, current_page):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    current_page = current_page or 0
    max_places = max_places or 500

    # Compute total pages for clamping
    df = load_places_frame(all_places_json) if all_places_json else load_places_frame(freq_json)
    if df is None:
        df = pd.DataFrame()
    if search_term:
        try:
            df = filter_places_search(df, search_term)
        except Exception:
            pass
    total_pages = max(1, math.ceil(len(df) / max_places)) if max_places else 1

    if trigger in ('places-frequency-data', 'place-search', 'place-search-icon', 'corpus-max-places-slider', 'all-places-store'):
        return 0
    if trigger == 'places-page-prev':
        return max(0, current_page - 1)
    if trigger == 'places-page-next':
        return min(total_pages - 1, current_page + 1)
    if trigger == 'places-page-jump':
        if jump_value is None:
            raise PreventUpdate
        try:
            target = int(jump_value) - 1
        except (TypeError, ValueError):
            raise PreventUpdate
        target = max(0, min(total_pages - 1, target))
        return target
    return current_page

@app.callback(
    Output('clear-selected-place', 'style'),
    Input('selected-place', 'data')
)
def style_clear_button(selected_place):
    base_style = {
        'fontSize': '12px',
        'padding': '6px 8px',
        'color': '#475569',
        'border': 'none',
        'flex': '0 0 auto'
    }
    if selected_place:
        base_style['color'] = '#dc2626'
    return base_style


@app.callback(
    Output('places-sort-field', 'data'),
    Output('places-sort-dir', 'data'),
    Input({'type': 'places-sort-header', 'key': dash.ALL}, 'n_clicks'),
    State('places-sort-field', 'data'),
    State('places-sort-dir', 'data'),
    prevent_initial_call=True
)
def sort_places_table(n_clicks, current_field, current_dir):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    try:
        trigger_id = eval(trigger)
    except Exception:
        raise PreventUpdate
    key = trigger_id.get('key')
    if not key:
        raise PreventUpdate
    current_field = current_field or 'frequency'
    current_dir = current_dir or 'desc'
    new_dir = 'asc' if (current_field == key and current_dir == 'desc') else 'desc'
    return key, new_dir


@app.callback(
    Output('places-sort-field', 'data', allow_duplicate=True),
    Output('places-sort-dir', 'data', allow_duplicate=True),
    Input('places-frequency-data', 'data'),
    Input('place-search', 'value'),
    Input('corpus-max-places-slider', 'value'),
    prevent_initial_call=True
)
def reset_places_sort_on_data(_, search_term, max_places):
    # Reset sort to frequency/desc on data refresh, search change, or max-places change
    return 'frequency', 'desc'


@app.callback(
    Output('current-filters', 'data', allow_duplicate=True),
    Input('corpus-max-places-slider', 'value'),
    State('current-filters', 'data'),
    prevent_initial_call=True
)
def set_max_places_filter(max_places, current_filters):
    filters = (current_filters or {}).copy()
    filters['max_places'] = max_places or 500
    return filters


@app.callback(
    Output('places-collocation-summary', 'children'),
    Output('places-collocation-table', 'children'),
    Input('places-collocation-data', 'data'),
    State('selected-place', 'data')
)
def display_collocation_places(colloc_json, selected_place):
    df = load_places_frame(colloc_json)
    if df.empty:
        return (
            html.Div("Kjør et kollokasjonssøk for å fylle denne fanen.", style={'fontSize': '0.85rem'}),
            html.Div("Ingen kollokasjoner funnet.", className="text-muted")
        )
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
    State('all-places-store', 'data'),
    State('places-frequency-data', 'data'),
    prevent_initial_call=True
)
def download_frequency_places(n_clicks, all_places_json, freq_json):
    payload = all_places_json or freq_json
    return _download_places_frame(payload, "places_frequency_all")


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
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    Input('activate-places-frequency', 'n_clicks'),
    Input('activate-places-collocations', 'n_clicks'),
    Input('filter-collocation-corpus', 'n_clicks'),
    State('places-frequency-data', 'data'),
    State('places-collocation-data', 'data'),
    State('heatmap-subset-checkbox', 'value'),
    State('place-search', 'value'),
    State('corpus-max-places-slider', 'value'),
    State('collocation-words-input', 'value'),
    State('current-dhlabids-store', 'data'),
    State('current-filters', 'data'),
    prevent_initial_call=True
)
def apply_places_to_map(freq_lamp_clicks, colloc_lamp_clicks,
                        filter_colloc_clicks,
                        freq_json, colloc_json,
                        heatmap_subset_value,
                        search_term, max_places, colloc_words_value, current_books, current_filters):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'activate-places-frequency':
        mode = 'frequency'
        df = load_places_frame(freq_json)
    elif trigger in ('activate-places-collocations', 'filter-collocation-corpus'):
        mode = 'collocations'
        df = load_places_frame(colloc_json)
    else:
        raise PreventUpdate

    if mode == 'collocations':
        # Do not filter collocation corpus by place search; use full collocation set
        filtered_df = df
    else:
        filtered_df = filter_places_search(df, search_term)
    if filtered_df.empty:
        raise PreventUpdate

    tokens = filtered_df['token'].dropna().astype(str).tolist()
    new_filters = (current_filters or {}).copy()
    new_filters['selected_tokens'] = tokens
    new_filters['max_places'] = max_places or len(tokens)
    new_filters['places_source'] = mode

    # For collocations: filter books to those containing BOTH the collocation words and one of the selected place tokens
    updated_books = current_books or []

    if mode == 'collocations':
        words = [w.strip() for w in (colloc_words_value or "").split(',') if w.strip()]
        filtered_books = updated_books
        if words and filtered_books:
            from dash_imagination.utils.corpus_build import count_words
            try:
                counts_df = count_words(filtered_books, words)
                if not counts_df.empty:
                    sums = counts_df.sum(axis=0)
                    filtered_books = [int(d) for d, total in sums.items() if total >= 1]
            except Exception as e:
                print(f"[collocation] count_words error: {e}")
        # also require the book to contain one of the selected place tokens
        if tokens and filtered_books:
            try:
                conn = get_db_connection()
                placeholders = ','.join(['?'] * len(tokens))
                book_place_query = f"""
                    SELECT DISTINCT dhlabid
                    FROM books
                    WHERE token IN ({placeholders})
                """
                place_books_df = pd.read_sql_query(book_place_query, conn, params=tuple(tokens))
                place_books = set(place_books_df['dhlabid'].dropna().astype(int).tolist())
                filtered_books = [b for b in filtered_books if b in place_books]
            except Exception as e:
                print(f"[collocation] place/book filter error: {e}")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        if filtered_books:
            updated_books = filtered_books
            new_filters['books'] = filtered_books
            new_filters['corpus_source'] = 'Collocations'
        else:
            new_filters['corpus_source'] = 'Places'
    else:
        new_filters['corpus_source'] = 'Places'
    subset_mode = 'subset' if heatmap_subset_value else 'all'
    return new_filters, subset_mode, updated_books


@app.callback(
    Output('heatmap-subset-mode', 'data'),
    Input('heatmap-subset-checkbox', 'value')
)
def sync_heatmap_subset_mode(checkbox_value):
    return 'subset' if checkbox_value else 'all'


@app.callback(
    Output('activate-places-frequency', 'children'),
    Output('activate-places-frequency', 'color'),
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
    colloc_icon, colloc_color = lamp_props('collocations')
    return freq_icon, freq_color, colloc_icon, colloc_color


@app.callback(
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    Output('current-filters', 'data', allow_duplicate=True),
    Output('filtered-data', 'data', allow_duplicate=True),
    Input('reset-corpus-btn-builder', 'n_clicks'),
    prevent_initial_call=True
)
def quick_reset_corpus(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    empty_df = pd.DataFrame().to_json(date_format='iso', orient='split')
    return [], {}, empty_df


@app.callback(
    Output('author-list-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('author-list-window-state', 'data'),
    State('author-list-container', 'style'),
    prevent_initial_call=True
)
def resize_author_list(store, window_state, current_style):
    style = _apply_size_to_style(store, 'author-list', current_style)
    return _enforce_minimized_dimensions(style, window_state)

@app.callback(
    Output('author-info-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('author-info-window-state', 'data'),
    State('author-info-container', 'style'),
    prevent_initial_call=True
)
def resize_author_info(store, window_state, current_style):
    style = _apply_size_to_style(store, 'author-info', current_style)
    return _enforce_minimized_dimensions(style, window_state)

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
    Output('map-visuals-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('map-visuals-window-state', 'data'),
    State('map-visuals-container', 'style'),
    prevent_initial_call=True
)
def resize_map_visuals(store, window_state, current_style):
    style = _apply_size_to_style(store, 'map-visuals', current_style)
    return _enforce_minimized_dimensions(style, window_state)


@app.callback(
    Output('heatmap-visuals-container', 'style', allow_duplicate=True),
    Input('dialog-size-store', 'data'),
    State('heatmap-visuals-window-state', 'data'),
    State('heatmap-visuals-container', 'style'),
    prevent_initial_call=True
)
def resize_heatmap_visuals(store, window_state, current_style):
    style = _apply_size_to_style(store, 'heatmap-visuals', current_style)
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
        body_style = restored_body or {}
        body_style['display'] = 'flex'
        body_style['opacity'] = '1'
        body_style['pointerEvents'] = 'auto'
    elif should_show:
        window_state['minimized'] = False
        # ensure body props reset if they were collapsed previously
        for prop in MINIMIZE_BODY_PROPS:
            body_style.pop(prop, None)
        body_style.update({
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'opacity': '1',
            'pointerEvents': 'auto'
        })
        body_style['display'] = 'flex'

    return new_style, window_state, body_style


@app.callback(
    Output('corpus-builder-card', 'style', allow_duplicate=True),
    Output('corpus-builder-window-state', 'data', allow_duplicate=True),
    Output('corpus-builder-body', 'style', allow_duplicate=True),
    Input('card-chip-builder', 'n_clicks'),
    State('corpus-builder-card', 'style'),
    State('corpus-builder-window-state', 'data'),
    State('corpus-builder-body', 'style'),
    prevent_initial_call=True
)
def toggle_corpus_builder_from_chip(chip_clicks, current_style, window_state, body_style):
    if not chip_clicks:
        raise PreventUpdate
    new_style = dict(current_style or {})
    window_state = (window_state or {'minimized': False}).copy()
    body_style = dict(body_style or {})

    current_display = new_style.get('display', 'none')
    should_show = current_display == 'none'
    new_style['display'] = 'flex' if should_show else 'none'

    if should_show:
        window_state['minimized'] = False
        for prop in MINIMIZE_BODY_PROPS:
            body_style.pop(prop, None)
        body_style.update({
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'opacity': '1',
            'pointerEvents': 'auto'
        })
        body_style['display'] = 'flex'

    return new_style, window_state, body_style

# Close button callback
@app.callback(
    Output('place-names-container', 'style', allow_duplicate=True),
    Input('close-place-names', 'n_clicks'),
    State('place-names-container', 'style'),
    State('place-names-window-state', 'data'),
    prevent_initial_call=True
)
def close_place_names(n_clicks, current_style, window_state):
    # Disable close while minimized to avoid reopening with hidden body styles.
    if not n_clicks:
        raise PreventUpdate
    if window_state and window_state.get('minimized'):
        raise PreventUpdate
    new_style = dict(current_style or {})
    new_style['display'] = 'none'
    return new_style


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
     Input('collocation-highlight', 'data'),
     Input('heatmap-subset-mode', 'data'),
     Input('places-mode', 'data')],
    [State('all-places-store', 'data')],
    prevent_initial_call=True
)
def update_map(filtered_data_json, view_type, heatmap_intensity, heatmap_radius, heatmap_colorscale,
               cluster_toggle, selected_place, click_data, marker_size, cluster_size,
               cluster_radius, collocation_highlight, heatmap_subset_mode, places_mode, all_places_json):
    try:
        view_type = view_type or 'points'
        # Debug: log incoming sizes
        try:
            dbg_len = len(pd.read_json(io.StringIO(filtered_data_json), orient='split')) if filtered_data_json else 0
        except Exception:
            dbg_len = 0
        print(f"[map] filtered len={dbg_len} all_places={'yes' if all_places_json else 'no'} subset={heatmap_subset_mode}")

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

        # Ensure we can highlight selected place even if it's not in current page
        if selected_place:
            token_str = str(selected_place)
            if token_str not in places_df['token'].astype(str).values:
                extra_source = heatmap_df if heatmap_df is not None else places_df
                extra_row = extra_source[extra_source['token'].astype(str) == token_str] if extra_source is not None else pd.DataFrame(columns=required_columns)
                if extra_row is not None and not extra_row.empty:
                    places_df = pd.concat([places_df, extra_row], ignore_index=True)

        # Clean datasets
        metric_field = 'collocation_count' if (places_mode == 'coll' and 'collocation_count' in places_df.columns) else 'frequency'
        places_df = places_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude'])
        if heatmap_df is not None:
            heatmap_df = heatmap_df.replace([np.inf, -np.inf], np.nan).dropna(subset=['latitude', 'longitude'])
        else:
            heatmap_df = places_df.copy()

        # If subset mode is on, build heatmap from current subset/page
        if (heatmap_subset_mode or 'all') == 'subset':
            heatmap_df = places_df.copy()

        sample_empty = places_df.empty
        heatmap_empty = heatmap_df.empty

        # If current mode produced an empty sample but we still have heatmap data, fall back to that to avoid blank map
        if sample_empty and not heatmap_empty:
            places_df = heatmap_df.copy()
            sample_empty = places_df.empty

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
            # Logarithmic scale normalized globally (all places) for consistent sizing
            metric_vals = places_df[metric_field].fillna(1).copy()
            base_size = marker_size if marker_size is not None else 8  # slider base
            size_range = 40  # spread relative to global range

            # Derive global min/max from all places (fallback to current page)
            try:
                if all_places_json:
                    all_df = pd.read_json(io.StringIO(all_places_json), orient='split')
                    all_log = np.log1p(all_df[metric_field].fillna(1)) if metric_field in all_df.columns else np.log1p(all_df['frequency'].fillna(1))
                    log_min, log_max = all_log.min(), all_log.max()
                else:
                    log_vals = np.log1p(metric_vals)
                    log_min, log_max = log_vals.min(), log_vals.max()
            except Exception:
                log_vals = np.log1p(metric_vals)
                log_min, log_max = log_vals.min(), log_vals.max()

            if log_max == log_min:
                sizes = pd.Series(base_size + size_range / 2, index=places_df.index)
            else:
                page_log = np.log1p(metric_vals)
                norm = (page_log - log_min) / (log_max - log_min)
                sizes = base_size + norm * size_range

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
                z_raw = heatmap_df[metric_field].fillna(1).values if metric_field in heatmap_df.columns else heatmap_df['frequency'].fillna(1).values
                z = np.log1p(z_raw)
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

# Clear selected place
@app.callback(
    Output('selected-place', 'data'),
    Input('clear-selected-place', 'n_clicks'),
    prevent_initial_call=True
)
def clear_selected_place(n):
    if not n:
        raise PreventUpdate
    return None

# Callback to update place summary
@app.callback(
    Output('place-summary-container', 'style'),
    Output('place-summary', 'children'),
    Output('place-images-store', 'data', allow_duplicate=True),
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
                return current_style, dash.no_update, dash.no_update
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

            # Convert books_df to list of dicts for unified rendering
            books_list = []
            if not books_df.empty:
                for _, row in books_df.iterrows():
                    if pd.notna(row['title']):
                        books_list.append({
                            'title': row['title'],
                            'year': row['year'],
                            'urn': row['urn'],
                            'author': row['author'],
                            'mentions': int(row.get('mention_count', 1))
                        })

            # Construct place dict
            place_data = {
                'token': token,
                'name': modern_part if modern_part else None,
                'book_count': book_count,
                'frequency': frequency,
                'books': books_list
            }

            summary, images = _render_place_summary_from_search(place_data)
            
            new_style = dict(current_style)
            new_style['display'] = 'flex'
            new_style = _bump_z(new_style)
            image_payload = _make_image_store_payload(
                'place',
                place_data.get('name') or place_data.get('token'),
                place_data.get('token'),
                images
            )
            return new_style, summary, image_payload
        except Exception as e:
            print(f"Error updating place summary (map): {e}")
            return dash.no_update, dash.no_update, dash.no_update
    # If triggered by list click
    elif triggered == 'selected-place':
        try:
            if not selected_place:
                return current_style, dash.no_update, dash.no_update
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

            # Convert books_df to list of dicts for unified rendering
            books_list = []
            if not books_df.empty:
                for _, row in books_df.iterrows():
                    if pd.notna(row['title']):
                        books_list.append({
                            'title': row['title'],
                            'year': row['year'],
                            'urn': row['urn'],
                            'author': row['author'],
                            'mentions': int(row.get('mention_count', 1))
                        })

            # Construct place dict
            place_data = {
                'token': token,
                'name': modern_part if modern_part else None,
                'book_count': book_count,
                'frequency': frequency,
                'books': books_list
            }

            summary, images = _render_place_summary_from_search(place_data)

            new_style = dict(current_style)
            new_style['display'] = 'flex'
            new_style = _bump_z(new_style)
            image_payload = _make_image_store_payload(
                'place',
                place_data.get('name') or place_data.get('token'),
                place_data.get('token'),
                images
            )
            return new_style, summary, image_payload
        except Exception as e:
            print(f"Error updating place summary (list): {e}")
            return dash.no_update, dash.no_update, dash.no_update
    else:
        return dash.no_update, dash.no_update, dash.no_update


@app.callback(
    Output('concordance-modal', 'is_open'),
    Output('concordance-query', 'value'),
    Output('concordance-output', 'children'),
    Input({'type': 'open-concordance', 'token': dash.ALL}, 'n_clicks'),
    Input('close-concordance', 'n_clicks'),
    State('concordance-modal', 'is_open'),
    prevent_initial_call=True
)
def toggle_concordance_modal(open_clicks, close_clicks, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger == 'close-concordance':
        return False, '', dash.no_update
    # open
    try:
        trigger_id = json.loads(trigger)
    except Exception:
        raise PreventUpdate
    token = trigger_id.get('token')
    if not token:
        raise PreventUpdate
    return True, token, ''


@app.callback(
    Output('concordance-output', 'children', allow_duplicate=True),
    Output('download-concordance', 'data', allow_duplicate=True),
    Input('run-concordance', 'n_clicks'),
    State('concordance-query', 'value'),
    State('concordance-window', 'value'),
    State('current-dhlabids-store', 'data'),
    prevent_initial_call=True
)
def run_concordance(n_clicks, query, window, current_books):
    if not n_clicks:
        raise PreventUpdate
    query = (query or "").strip()
    if not query:
        return html.Div("Tom søkestreng."), dash.no_update
    window = int(window or 25)
    current_books = current_books or []
    if not current_books:
        return html.Div("Ingen bøker i korpus; kan ikke hente konkordanser.", style={'color': '#64748b'}), dash.no_update

    conn = get_db_connection()
    try:
        placeholders = ','.join(['?'] * len(current_books))
        urn_df = pd.read_sql_query(
            f"""
            SELECT DISTINCT c.urn
            FROM corpus c
            JOIN books b ON c.dhlabid = b.dhlabid
            WHERE c.dhlabid IN ({placeholders})
              AND c.urn IS NOT NULL
            """,
            conn,
            params=tuple(current_books)
        )
    finally:
        conn.close()

    urns = urn_df['urn'].dropna().unique().tolist() if not urn_df.empty else []
    if not urns:
        return html.Div("Ingen URNs i korpuset; kan ikke hente konkordanser.", style={'color': '#64748b'}), dash.no_update

    try:
        conc = dh.Concordance(urns, query, window=window, limit=500)
        conc_df = conc.frame.copy()
    except Exception as e:
        return html.Div(f"Feil ved henting av konkordanser: {e}", style={'color': '#dc2626'}), dash.no_update

    if conc_df is None or conc_df.empty:
        return html.Div("Ingen konkordanser funnet.", style={'color': '#64748b'}), dash.no_update

    preview = conc_df.head(10)
    rows = []
    for _, row in preview.iterrows():
        rows.append(html.Div([
            html.Span(row.get('left', ''), style={'color': '#475569'}),
            html.Span(row.get('keyword', ''), style={'fontWeight': 700, 'margin': '0 4px'}),
            html.Span(row.get('right', ''), style={'color': '#475569'}),
            html.Span(row.get('urn', ''), style={'color': '#94a3b8', 'fontSize': '12px', 'marginLeft': '6px'})
        ], style={'padding': '4px 0', 'borderBottom': '1px solid #eee'}))

    table = html.Div(rows, style={'maxHeight': '260px', 'overflowY': 'auto', 'fontSize': '13px'})
    download = dcc.send_data_frame(conc_df.to_csv, f"concordance_{query}.csv", index=False)
    return table, download


@app.callback(
    Output('place-concordance-output', 'children'),
    Output('download-place-concordance', 'data'),
    Input({'type': 'place-concordance', 'token': dash.ALL}, 'n_clicks'),
    State('current-dhlabids-store', 'data'),
    prevent_initial_call=True
)
def fetch_place_concordance(n_clicks, current_books):
    if not n_clicks or not any(n_clicks):
        raise PreventUpdate
    ctx = dash.callback_context
    trigger = ctx.triggered[0] if ctx.triggered else None
    if not trigger or not trigger.get('value'):
        raise PreventUpdate
    try:
        trigger_id = json.loads(trigger['prop_id'].split('.')[0])
    except Exception:
        raise PreventUpdate
    token = trigger_id.get('token')
    if not token:
        raise PreventUpdate

    current_books = current_books or []
    if not current_books:
        return html.Div("Ingen bøker i korpus; kan ikke hente konkordanser.", style={'color': '#64748b'}), dash.no_update

    conn = get_db_connection()
    try:
        placeholders = ','.join(['?'] * len(current_books))
        urn_df = pd.read_sql_query(
            f"""
            SELECT DISTINCT c.urn
            FROM corpus c
            JOIN books b ON c.dhlabid = b.dhlabid
            WHERE c.dhlabid IN ({placeholders})
              AND b.token = ?
              AND c.urn IS NOT NULL
            """,
            conn,
            params=tuple(current_books + [token])
        )
    finally:
        conn.close()

    urns = urn_df['urn'].dropna().unique().tolist() if not urn_df.empty else []
    if not urns:
        return html.Div("Ingen URNs for denne plassen i korpuset; kan ikke hente konkordanser.", style={'color': '#64748b'}), dash.no_update

    try:
        conc = dh.Concordance(urns, [token], before=25, after=25)
        conc_df = conc.frame.copy()
    except Exception as e:
        return html.Div(f"Feil ved henting av konkordanser: {e}", style={'color': '#dc2626'}), dash.no_update

    if conc_df is None or conc_df.empty:
        return html.Div("Ingen konkordanser funnet.", style={'color': '#64748b'}), dash.no_update

    preview = conc_df.head(10)
    rows = []
    for _, row in preview.iterrows():
        rows.append(html.Div([
            html.Span(row.get('left', ''), style={'color': '#475569'}),
            html.Span(row.get('keyword', ''), style={'fontWeight': 700, 'margin': '0 4px'}),
            html.Span(row.get('right', ''), style={'color': '#475569'}),
            html.Span(row.get('urn', ''), style={'color': '#94a3b8', 'fontSize': '12px', 'marginLeft': '6px'})
        ], style={'padding': '4px 0', 'borderBottom': '1px solid #eee'}))

    table = html.Div(rows, style={'maxHeight': '260px', 'overflowY': 'auto', 'fontSize': '13px'})
    download = dcc.send_data_frame(conc_df.to_csv, f"concordance_{token}.csv", index=False)
    return table, download

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

# Map visuals toggle (button + chip)
@app.callback(
    Output('map-visuals-container', 'style'),
    Output('map-visuals-window-state', 'data', allow_duplicate=True),
    Output('map-visuals-body', 'style', allow_duplicate=True),
    Input('visualization-button', 'n_clicks'),
    Input('card-chip-map-visuals', 'n_clicks'),
    Input('close-map-visuals', 'n_clicks'),
    State('map-visuals-container', 'style'),
    State('map-visuals-window-state', 'data'),
    State('map-visuals-body', 'style'),
    prevent_initial_call=True
)
def toggle_map_visuals(button_clicks, chip_clicks, close_clicks, current_style, window_state, body_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id not in ('visualization-button', 'card-chip-map-visuals', 'close-map-visuals'):
        raise PreventUpdate

    new_style = dict(current_style or {})
    window_state = (window_state or {'minimized': False}).copy()
    body_style = dict(body_style or {})

    if trigger_id == 'close-map-visuals':
        new_style['display'] = 'none'
        return new_style, window_state, body_style

    should_show = new_style.get('display', 'none') == 'none'
    new_style['display'] = 'flex' if should_show else 'none'

    if should_show:
        window_state['minimized'] = False
        for prop in MINIMIZE_BODY_PROPS:
            body_style.pop(prop, None)
        body_style.update({
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'opacity': '1',
            'pointerEvents': 'auto'
        })
        body_style['display'] = 'flex'

    return new_style, window_state, body_style


@app.callback(
    Output('heatmap-visuals-container', 'style'),
    Output('heatmap-visuals-window-state', 'data', allow_duplicate=True),
    Output('heatmap-visuals-body', 'style', allow_duplicate=True),
    Input('card-chip-heatmap-visuals', 'n_clicks'),
    Input('close-heatmap-visuals', 'n_clicks'),
    State('heatmap-visuals-container', 'style'),
    State('heatmap-visuals-window-state', 'data'),
    State('heatmap-visuals-body', 'style'),
    prevent_initial_call=True
)
def toggle_heatmap_visuals(chip_clicks, close_clicks, current_style, window_state, body_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id not in ('card-chip-heatmap-visuals', 'close-heatmap-visuals'):
        raise PreventUpdate

    new_style = dict(current_style or {})
    window_state = (window_state or {'minimized': False}).copy()
    body_style = dict(body_style or {})

    if trigger_id == 'close-heatmap-visuals':
        new_style['display'] = 'none'
        return new_style, window_state, body_style

    should_show = new_style.get('display', 'none') == 'none'
    new_style['display'] = 'flex' if should_show else 'none'

    if should_show:
        window_state['minimized'] = False
        for prop in MINIMIZE_BODY_PROPS:
            body_style.pop(prop, None)
        body_style.update({
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'opacity': '1',
            'pointerEvents': 'auto'
        })
        body_style['display'] = 'flex'

    return new_style, window_state, body_style


@app.callback(
    Output('visualization-button', 'style'),
    Input('map-visuals-container', 'style'),
    State('visualization-button', 'style'),
    prevent_initial_call=True
)
def update_visualization_button_style(map_style, current_style):
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
    return active_style if map_style and map_style.get('display') not in ('none', 'hidden') else base_style



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
    Output('card-chip-map-visuals', 'className'),
    Output('card-chip-heatmap-visuals', 'className'),
    Output('card-chip-builder', 'className'),
    Output('card-chip-collocations', 'className'),
    Output('card-chip-similarity', 'className'),
    Input('place-names-container', 'style'),
    Input('corpus-controls-container', 'style'),
    Input('map-visuals-container', 'style'),
    Input('heatmap-visuals-container', 'style'),
    Input('corpus-builder-card', 'style'),
    Input('collocation-card', 'style'),
    Input('place-similarity-dialog', 'style')
)
def refresh_card_chips(
    places_style,
    corpus_style,
    map_visuals_style,
    heatmap_visuals_style,
    builder_style,
    collocation_style,
    similarity_style
):
    return (
        _chip_class('card-chip chip-option chip-places', places_style),
        _chip_class('card-chip chip-option chip-corpus', corpus_style),
        _chip_class('card-chip chip-option chip-visuals-map', map_visuals_style),
        _chip_class('card-chip chip-option chip-visuals-heat', heatmap_visuals_style),
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
    [Output('download-heatmap-file', 'data'),
     Output('heatmap-download-status', 'children'),
     Output('clear-heatmap-download-status-interval', 'disabled'),
     Output('clear-heatmap-download-status-interval', 'n_intervals')],
    [Input('download-heatmap', 'n_clicks')],
    [State('heatmap-download-format', 'value'),
     State('heatmap-download-resolution', 'value'),
     State('main-map', 'figure')],
    prevent_initial_call=True
)
def trigger_heatmap_download(n_clicks, format_value, resolution_value, figure):
    import dash
    from dash import dcc, html
    import plotly.graph_objects as go
    import io
    if not n_clicks:
        raise dash.exceptions.PreventUpdate

    resolution_map = {
        'standard': {'width': 1920, 'height': 1080},
        'high': {'width': 3840, 'height': 2160},
        'publication': {'width': 6000, 'height': 4000}
    }
    dimensions = resolution_map.get(resolution_value, resolution_map['standard'])
    try:
        fig = go.Figure(figure)
        fig.update_layout(
            width=dimensions['width'],
            height=dimensions['height'],
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False
        )
        if format_value == 'png':
            img_bytes = fig.to_image(format='png', scale=2 if resolution_value in ['high', 'publication'] else 1)
            filename = 'imagination_heatmap.png'
        elif format_value == 'pdf':
            img_bytes = fig.to_image(format='pdf', scale=2 if resolution_value in ['high', 'publication'] else 1)
            filename = 'imagination_heatmap.pdf'
        elif format_value == 'svg':
            img_bytes = fig.to_image(format='svg', scale=2 if resolution_value in ['high', 'publication'] else 1)
            filename = 'imagination_heatmap.svg'
        else:
            return None, html.Div('Invalid format selected', style={'color': 'red'}), True, 0
        return (
            dcc.send_bytes(lambda buf: buf.write(img_bytes), filename),
            html.Div('Heatmap download started...', style={'color': 'green', 'marginTop': '10px'}),
            False,
            0
        )
    except Exception as e:
        print(f"Error generating heatmap download: {e}")
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


@app.callback(
    Output('heatmap-download-status', 'children', allow_duplicate=True),
    [Input('clear-heatmap-download-status-interval', 'n_intervals')],
    [State('clear-heatmap-download-status-interval', 'disabled')],
    prevent_initial_call=True
)
def clear_heatmap_download_status(n_intervals, disabled):
    if not disabled and n_intervals > 0:
        return ''
    raise dash.exceptions.PreventUpdate


@app.callback(
    Output('clear-heatmap-download-status-interval', 'disabled', allow_duplicate=True),
    [Input('heatmap-download-status', 'children')],
    prevent_initial_call=True
)
def disable_heatmap_interval_on_clear(status):
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
    Output('global-search-results', 'style', allow_duplicate=True),
    Input('global-place-search', 'n_blur'),
    Input('global-place-search', 'n_submit'),
    State('global-place-search', 'value'),
    State('global-search-results', 'style'),
    prevent_initial_call=True
)
def manage_search_results_visibility(n_blur, n_submit, search_value, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    # If blurred, hide
    if trigger_id == 'global-place-search' and 'n_blur' in ctx.triggered[0]['prop_id']:
        if not n_blur:
            raise PreventUpdate
        # Small delay to allow click events to propagate
        import time
        time.sleep(0.1)
        style = dict(current_style or _search_results_style(False))
        style['display'] = 'none'
        return style

    # If submit and term is long enough, show
    if trigger_id == 'global-place-search' and 'n_submit' in ctx.triggered[0]['prop_id']:
        term = (search_value or '').strip()
        style = dict(current_style or _search_results_style(False))
        if len(term) >= 2:
            style['display'] = 'block'
        else:
            style['display'] = 'none'
        return style

    raise PreventUpdate

app.clientside_callback(
    """
    function(id) {
        var el = document.getElementById(id);
        if (el) {
            el.addEventListener('mousedown', function(e) {
                // Prevent input blur when clicking inside results
                // We use mousedown because it fires before blur
                e.preventDefault();
            });
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('global-search-results', 'title'),
    Input('global-search-results', 'id')
)

# Client-side scroll to sections for omniboks
app.clientside_callback(
    """
    function(btnClicks, btnIds) {
        // Find which button was clicked
        if (!btnClicks || !btnIds) { return window.dash_clientside.no_update; }
        for (let i = 0; i < btnClicks.length; i++) {
            if (btnClicks[i]) {
                const target = btnIds[i].target;
                const el = document.getElementById('search-section-' + target);
                if (el) {
                    el.scrollIntoView({behavior: 'smooth', block: 'start'});
                }
                break;
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('global-search-results', 'role'),
    Input({'type': 'search-scroll', 'target': ALL}, 'n_clicks'),
    State({'type': 'search-scroll', 'target': ALL}, 'id')
)

@app.callback(
    Output('global-search-results', 'children'),
    Output('global-search-results', 'style'),
    Input('global-place-search', 'n_submit'),
    State('global-place-search', 'value'),
    prevent_initial_call=True
)
def update_global_search_results(n_submit, search_term):
    if not n_submit:
        raise PreventUpdate
    term = (search_term or '').strip()
    if len(term) < 2:
        return [], _search_results_style(False)
    selection_set = {'places', 'books', 'authors'}

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
            SELECT 
                LOWER(TRIM(c.author)) as author_key,
                c.author,
                COUNT(DISTINCT c.dhlabid) AS book_count
            FROM corpus c
            WHERE c.author IS NOT NULL
              AND TRIM(c.author) != ''
              AND {author_clause}
            GROUP BY c.author, author_key
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
        }, id=f"search-section-{key}", **{'data-target': f"search-section-{key}"})

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
            author_key = author.get('author_key')
            items.append(
                html.Div([
                    html.Div([
                        html.Span(name, style={'fontWeight': 600}),
                        html.Span(f"{count} bøker", style={'fontSize': '12px', 'color': '#94a3b8'})
                    ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '2px'}),
                    html.Button(
                        "Legg bøker til korpus",
                        id={'type': 'search-author-action', 'author_key': author_key, 'display_name': name},
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
        html.Div([
            html.Button("Steder", id={'type': 'search-scroll', 'target': 'places'}, n_clicks=0, style={
                'border': 'none', 'backgroundColor': '#e2e8f0', 'color': '#0f172a',
                'fontSize': '11px', 'padding': '4px 10px', 'borderRadius': '12px', 'cursor': 'pointer', 'marginRight': '6px'
            }),
            html.Button("Bøker", id={'type': 'search-scroll', 'target': 'books'}, n_clicks=0, style={
                'border': 'none', 'backgroundColor': '#e2e8f0', 'color': '#0f172a',
                'fontSize': '11px', 'padding': '4px 10px', 'borderRadius': '12px', 'cursor': 'pointer', 'marginRight': '6px'
            }),
            html.Button("Forfattere", id={'type': 'search-scroll', 'target': 'authors'}, n_clicks=0, style={
                'border': 'none', 'backgroundColor': '#e2e8f0', 'color': '#0f172a',
                'fontSize': '11px', 'padding': '4px 10px', 'borderRadius': '12px', 'cursor': 'pointer'
            })
        ], style={'display': 'flex', 'alignItems': 'center'})
    ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'})

    return [section_header, columns_wrapper], _search_results_style(True)


@app.callback(
    Output('main-map', 'figure', allow_duplicate=True),
    Output('place-summary-container', 'style', allow_duplicate=True),
    Output('place-summary', 'children', allow_duplicate=True),
    Output('place-images-store', 'data', allow_duplicate=True),
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
    # Remove previous search selection trace
    try:
        fig.data = tuple(tr for tr in fig.data if getattr(tr, 'name', None) != 'Search selection')
    except Exception:
        pass
    # Add green marker without changing viewport
    try:
        lat = float(place.get('latitude'))
        lon = float(place.get('longitude'))
        fig.add_trace(go.Scattermap(
            lat=[lat],
            lon=[lon],
            mode='markers',
            marker=dict(size=14, color='#10b981', opacity=0.95, sizemode='diameter'),
            hoverinfo='text',
            text=[place.get('token') or place.get('name') or 'Sted'],
            name='Search selection'
        ))
    except (TypeError, ValueError):
        pass

    new_summary_style = dict(summary_style or {})
    new_summary_style['display'] = 'flex'
    new_summary_style.pop('transform', None)

    summary, images = _render_place_summary_from_search(place)
    image_payload = _make_image_store_payload(
        'place',
        place.get('name') or place.get('token'),
        place.get('token'),
        images
    )

    return (
        fig,
        new_summary_style,
        summary,
        image_payload,
        _search_results_style(False)
    )


@app.callback(
    Output('image-gallery-modal', 'is_open'),
    Output('image-gallery-title', 'children'),
    Output('image-gallery-grid', 'children'),
    Output('image-gallery-store', 'data'),
    Input({'type': 'image-thumb', 'context': ALL, 'index': ALL}, 'n_clicks'),
    Input('image-gallery-close', 'n_clicks'),
    Input('image-gallery-dismiss', 'n_clicks'),
    State('place-images-store', 'data'),
    State('author-images-store', 'data'),
    prevent_initial_call=True
)
def toggle_image_gallery(_, close_clicks, dismiss_clicks, place_images, author_images):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate

    trigger = ctx.triggered[0]
    trigger_id = getattr(ctx, 'triggered_id', None)

    if trigger_id in ('image-gallery-close', 'image-gallery-dismiss'):
        if not trigger.get('value'):
            raise PreventUpdate
        return False, dash.no_update, dash.no_update, None

    if isinstance(trigger_id, dict) and trigger_id.get('type') == 'image-thumb':
        if not trigger.get('value'):
            raise PreventUpdate
        context_key = trigger_id.get('context')
        index = trigger_id.get('index') or 0
        source_data = place_images if context_key == 'place' else author_images if context_key == 'author' else None
        if not source_data or not source_data.get('images'):
            raise PreventUpdate
        raw_images = source_data.get('images') or []
        if not raw_images:
            raise PreventUpdate
        try:
            index = int(index)
        except (ValueError, TypeError):
            index = 0
        index = max(0, min(index, len(raw_images) - 1))
        ordered = raw_images[index:] + raw_images[:index]
        hydrated = hydrate_gallery_images(ordered, max_items=8, max_px=1400)
        cards = [card for card in (_build_gallery_card(img) for img in hydrated) if card]
        if not cards:
            cards = [html.Div("Ingen IIIF-bilder kunne lastes", className="text-muted")]
        label = source_data.get('label') or source_data.get('subtitle') or "Uten navn"
        title = f"Historiske bilder – {label}"
        payload = {
            'context': context_key,
            'label': label,
            'subtitle': source_data.get('subtitle'),
            'images': hydrated
        }
        return True, title, cards, payload

    raise PreventUpdate


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
    if not trigger or not trigger.get('value'):
        raise PreventUpdate
    prop = trigger['prop_id'].split('.')[0]
    if not prop:
        raise PreventUpdate
    try:
        trigger_id = json.loads(prop)
    except (json.JSONDecodeError, TypeError):
        raise PreventUpdate
    dhlabid = int(trigger_id.get('dhlabid'))
    books = set(current_books or [])
    books.add(dhlabid)
    return sorted(books), _search_results_style(False)


@app.callback(
    Output('current-dhlabids-store', 'data', allow_duplicate=True),
    Output('global-search-results', 'style', allow_duplicate=True),
    Input({'type': 'search-author-action', 'author_key': ALL, 'display_name': ALL}, 'n_clicks'),
    State('current-dhlabids-store', 'data'),
    prevent_initial_call=True
)
def add_author_books_from_search(_, current_books):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise PreventUpdate
    trigger = ctx.triggered[0]
    if not trigger or not trigger.get('value'):
        raise PreventUpdate
    prop = trigger['prop_id'].split('.')[0]
    if not prop:
        raise PreventUpdate
    try:
        trigger_id = json.loads(prop)
    except (json.JSONDecodeError, TypeError):
        raise PreventUpdate
    author_key = trigger_id.get('author_key')
    display_name = trigger_id.get('display_name')
    dhlabids = _fetch_author_book_ids(author_key=author_key, author_name=display_name)
    if not dhlabids:
        raise PreventUpdate
    books = set(current_books or [])
    books.update(dhlabids)
    return sorted(books), _search_results_style(False)


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
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS tmp_corpus_view")
        cur.execute("CREATE TEMP TABLE tmp_corpus_view (dhlabid INTEGER)")
        cur.executemany("INSERT INTO tmp_corpus_view (dhlabid) VALUES (?)", [(int(b),) for b in books])

        # Info section
        query = """
        SELECT COUNT(DISTINCT c.dhlabid) as book_count,
               COUNT(DISTINCT c.author) as author_count,
               MIN(c.year) as min_year,
               MAX(c.year) as max_year
        FROM corpus c
        JOIN tmp_corpus_view t ON c.dhlabid = t.dhlabid
        WHERE c.year IS NOT NULL
        """
        info = pd.read_sql_query(query, conn).iloc[0]
        # Places count
        places_query = """
        SELECT COUNT(DISTINCT b.token) as place_count
        FROM books b
        JOIN tmp_corpus_view t ON b.dhlabid = t.dhlabid
        JOIN places p ON b.token = p.token
        WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL
          AND CAST(p.latitude AS REAL) != 0
          AND CAST(p.longitude AS REAL) != 0
        """
        place_count = pd.read_sql_query(places_query, conn)['place_count'].iloc[0]
        # Year range
        if pd.notnull(info['min_year']) and pd.notnull(info['max_year']):
            years = f"{int(info['min_year'])}–{int(info['max_year'])}"
        else:
            years = ""
        # --- Build SQL filter for the table ---
        where_clauses = ["t.dhlabid = c.dhlabid"]
        params = []
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
        JOIN tmp_corpus_view t ON c.dhlabid = t.dhlabid
        WHERE {where_sql}
        ORDER BY c.year DESC, c.title
        LIMIT 100
        '''
        df = pd.read_sql_query(table_query, conn, params=tuple(params) if params else None)
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
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS tmp_books_all")
        cur.execute("CREATE TEMP TABLE tmp_books_all (dhlabid INTEGER)")
        cur.executemany("INSERT INTO tmp_books_all (dhlabid) VALUES (?)", [(int(b),) for b in book_ids])
        query = '''
        WITH selected_books AS (
            SELECT dhlabid FROM tmp_books_all
        )
        SELECT 
            b.token,
            p.modern as name,
            p.latitude,
            p.longitude,
            SUM(b.book_count) as frequency,
            COUNT(DISTINCT b.dhlabid) as book_count
        FROM books b
        JOIN selected_books sb ON b.dhlabid = sb.dhlabid
        JOIN places p ON b.token = p.token
        WHERE p.latitude IS NOT NULL AND p.longitude IS NOT NULL
          AND CAST(p.latitude AS REAL) != 0
          AND CAST(p.longitude AS REAL) != 0
        GROUP BY b.token, p.modern, p.latitude, p.longitude
        '''
        df = pd.read_sql_query(query, conn)
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

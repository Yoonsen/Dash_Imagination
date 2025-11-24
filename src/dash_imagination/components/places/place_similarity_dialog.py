from dash import dcc, html, callback, no_update, callback_context
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State
from .word_similarity import WordSimilarityAPI
import pandas as pd
from dash_imagination.utils.db import get_db_connection
from dash_imagination.components.common.places_table import render_place_preview
from dash_imagination.components.common.size_controls import card_title_bar, DEFAULT_CARD_SIZES
import dash


DEFAULT_SIMILARITY_POSITION = {
    'top': 100,
    'left': 360,
}


def _ensure_similarity_position(style: dict | None) -> dict:
    style = (style or {}).copy()

    def _normalize_axis(axis: str, minimum: int):
        value = style.get(axis)
        try:
            if isinstance(value, str) and value.endswith('px'):
                numeric = float(value[:-2])
            elif value is not None:
                numeric = float(value)
            else:
                numeric = DEFAULT_SIMILARITY_POSITION[axis]
        except (ValueError, TypeError):
            numeric = DEFAULT_SIMILARITY_POSITION[axis]
        if numeric < minimum:
            numeric = DEFAULT_SIMILARITY_POSITION[axis]
        style[axis] = f"{numeric}px"

    _normalize_axis('top', 40)
    _normalize_axis('left', 140)
    return style

def create_place_similarity_dialog():
    """Create the place similarity dialog."""
    return dbc.Card([
        dbc.CardHeader(
            card_title_bar(
                'similarity-card',
                'fa fa-search',
                "Place Similarity",
                close_button_id='close-similarity',
                close_button_title="Hide similarity card",
                minimize_button_id='minimize-similarity-card',
                minimize_button_title="Minimize similarity card"
            ),
            className="bg-info-subtle text-dark",
            id='similarity-header'
        ),
        dbc.CardBody([
            # Input section
            html.Div([
                html.Label("Place Name", className="form-label"),
                dbc.InputGroup([
                    dcc.Input(
                        id='similar-place-input',
                        type='text',
                        placeholder='Enter a place name...',
                        className="form-control"
                    ),
                    dbc.Button(
                        html.I(className="fas fa-search"),
                        id='find-similar',
                        color="primary"
                    )
                ], className="mb-3"),
                html.Label("Similarity Threshold", className="form-label"),
                dcc.Slider(
                    id='similarity-threshold',
                    min=0,
                    max=1,
                    step=0.1,
                    value=0.7,
                    marks={i/10: f"{i/10:.1f}" for i in range(0, 11, 2)},
                    className="mb-3"
                ),
                html.Div([
                    html.Label("Max Places", className="form-label"),
                    dcc.Input(
                        id='max-places',
                        type='number',
                        min=1,
                        max=500,
                        value=100,
                        className="form-control"
                    )
                ], className="mb-3")
            ], className="similarity-inputs", style={'flex': '0 0 auto'}),
            
            # Results section
            html.Div([
                html.Div("Results", className="text-uppercase fw-semibold small text-muted"),
                html.Div(
                    id='similar-places-results',
                    className="flex-grow-1 d-flex flex-column",
                    style={'flex': '1 1 auto', 'minHeight': 0, 'overflow': 'hidden'},
                    children=[
                        html.P("Enter a place name and click 'Find Similar Places' to see results", className="text-muted")
                    ]
                ),
                html.Div([
                    html.Div([
                        html.Span("Kombiner med korpus", className="text-muted small me-2"),
                        dbc.ButtonGroup([
                            dbc.Button("+", id='corpus-op-union-similarity', n_clicks=0,
                                       color="secondary", size="sm", outline=True,
                                       title="Legg til treffene i korpuset"),
                            dbc.Button("&", id='corpus-op-intersection-similarity', n_clicks=0,
                                       color="secondary", size="sm", outline=True,
                                       title="Behold kun overlapp"),
                            dbc.Button("-", id='corpus-op-diff-similarity', n_clicks=0,
                                       color="secondary", size="sm", outline=True,
                                       title="Fjern treffene fra korpuset")
                        ], size="sm", className="similarity-operation-buttons"),
                        dbc.Button(
                            html.Span("Oppdater", className="px-2"),
                            id='apply-similarity-corpus',
                            color="primary",
                            size="sm",
                            className="ms-2 similarity-apply-btn",
                            disabled=True
                        )
                    ], className="d-flex align-items-center flex-wrap gap-2"),
                    dbc.Spinner(
                        html.Div(id="select-all-loading"),
                        color="primary",
                        type="grow",
                        fullscreen=False,
                        spinner_style={"width": "1rem", "height": "1rem"}
                    )
                ], id="select-all-container", style={'display': 'none', 'marginBottom': '8px'})
            ], className="flex-grow-1 d-flex flex-column gap-2", style={'minHeight': 0, 'overflow': 'hidden'})
        ], id='place-similarity-body', style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '1rem',
            'overflow': 'hidden'
        })
    ], id='place-similarity-dialog', className="position-absolute dialog-card", style={
        'width': f"{DEFAULT_CARD_SIZES['similarity-card']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['similarity-card']['height']}px",
        'zIndex': 800,
        'display': 'none',
        'top': '100px',  # Position below the top button container
        'left': '360px',   # Align just to the right of launcher column
        'cursor': 'grab',
        'flexDirection': 'column'
    })

@callback(
    Output('place-similarity-dialog', 'style', allow_duplicate=True),
    [Input('close-similarity', 'n_clicks'),
     Input('find-similar', 'n_clicks'),
     Input('card-chip-similarity', 'n_clicks')],
    [State('place-similarity-dialog', 'style')],
    prevent_initial_call=True
)
def toggle_similarity_dialog(n_clicks_close, n_clicks_show, chip_clicks, current_style):
    ctx = callback_context
    if not ctx.triggered:
        return current_style
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id == 'close-similarity':
        return {'display': 'none'}
    elif trigger_id == 'find-similar':
        new_style = _ensure_similarity_position(current_style)
        new_style['display'] = 'flex'
        new_style.pop('transform', None)
        return new_style
    elif trigger_id == 'card-chip-similarity':
        new_style = _ensure_similarity_position(current_style)
        current_display = new_style.get('display', 'none')
        new_style['display'] = 'flex' if current_display == 'none' else 'none'
        new_style.pop('transform', None)
        return new_style
    return current_style

@callback(
    Output('form-submit-trigger', 'children'),
    Input('similar-place-form', 'submit'),
    prevent_initial_call=True
)
def handle_form_submit(submit):
    if submit:
        return 'submitted'
    return no_update

@callback(
    Output('similar-places-results', 'children'),
    Output('similar-places-results', 'style'),
    Output('similarity-places-data', 'data'),
    Input('find-similar', 'n_clicks'),
    State('similar-place-input', 'value'),
    State('similarity-threshold', 'value'),
    State('max-places', 'value'),
    prevent_initial_call=True
)
def handle_similar_places(n_clicks, search_word, threshold, max_places):
    if not n_clicks:
        return no_update, no_update, no_update
        
    if not search_word:
        return html.Div("Please enter a search term"), {'display': 'block'}, None
    
    conn = None
    try:
        # Get similar words from API with limit
        api = WordSimilarityAPI()
        similar_words = api.find_similar_words(search_word, collection_name="vss_1850_cos", limit=max_places)
        
        if not similar_words:
            return html.Div("No similar places found"), {'display': 'block'}, None
        
        # Filter similar words based on threshold
        filtered_words = [word for word, score in similar_words if score >= threshold]
        
        if not filtered_words:
            return html.Div("No places meet the similarity threshold"), {'display': 'block'}, None
        
        # Connect to database and get place information
        conn = get_db_connection()
        
        # Get place information in a single query with CTE
        query = """
        WITH valid_tokens AS (
            SELECT DISTINCT token 
            FROM books 
            WHERE token IN ({})
        )
        SELECT DISTINCT 
            p.token,
            p.modern as name,
            p.latitude,
            p.longitude,
            COUNT(DISTINCT b.dhlabid) as book_count,
            SUM(b.book_count) as frequency
        FROM places p
        JOIN books b ON p.token = b.token
        JOIN valid_tokens vt ON p.token = vt.token
        WHERE p.latitude IS NOT NULL 
        AND p.longitude IS NOT NULL
        AND p.latitude != '0'
        AND p.longitude != '0'
        GROUP BY p.token, p.modern, p.latitude, p.longitude
        ORDER BY frequency DESC
        LIMIT ?
        """.format(','.join(['?'] * len(filtered_words)))
        
        places_df = pd.read_sql_query(query, conn, params=tuple(filtered_words + [max_places]))
        
        if places_df.empty:
            return html.Div("No matching places found in the database"), {'display': 'block'}, None
        
        summary, table = render_place_preview(
            places_df,
            selected_place=None,
            empty_message="Ingen steder tilgjengelig ennå.",
            body_max_height=None
        )
        panel = html.Div(
            [
                html.Div(
                    [summary],
                    className="places-tab-toolbar d-flex align-items-center justify-content-between"
                ),
                table
            ],
            className="places-tab-panel similarity-results-panel",
            style={
                'display': 'flex',
                'flexDirection': 'column',
                'flex': '1 1 auto',
                'minHeight': 0,
                'gap': '0.5rem'
            }
        )
        return (
            panel,
            {'display': 'flex', 'flexDirection': 'column', 'flex': '1 1 auto', 'minHeight': 0},
            places_df.to_json(date_format='iso', orient='split')
        )
        
    except Exception as e:
        print(f"Error in handle_similar_places: {e}")
        return html.Div(f"Error: {str(e)}"), {'display': 'block'}, None
    finally:
        if conn:
            conn.close() 

@callback(
    Output('select-all-container', 'style'),
    Input('similarity-places-data', 'data')
)
def toggle_similarity_action_bar(data):
    if data:
        return {'display': 'block', 'marginBottom': '8px'}
    return {'display': 'none'}


@callback(
    Output('apply-similarity-corpus', 'disabled'),
    Input('similarity-places-data', 'data')
)
def toggle_similarity_apply_button(data):
    return not bool(data)
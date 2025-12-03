from dash import html, dcc
import dash_bootstrap_components as dbc
from dash_imagination.components.common.size_controls import card_title_bar

DEFAULT_CARD_SIZES = {
    'places': {'width': 380, 'height': 520},
    'corpus-controls': {'width': 360, 'height': 260},
    'corpus-builder': {'width': 800, 'height': 600},
    'place-summary': {'width': 340, 'height': 400},
    'map-visuals': {'width': 300, 'height': 340},
    'heatmap-visuals': {'width': 300, 'height': 340},
    'collocation': {'width': 400, 'height': 500},
    'place-similarity': {'width': 400, 'height': 500},
    'author-list': {'width': 400, 'height': 600},
    'author-info': {'width': 450, 'height': 500},
}

def create_author_list_card():
    """
    Create the floating card that lists authors in the current corpus.
    """
    return html.Div([
        # Window state store
        dcc.Store(id='author-list-window-state', data={'minimized': False, 'restored_style': None}),
        
        dbc.Card([
            # Title bar
            dbc.CardHeader(
                card_title_bar(
                    "author-list", 
                    "fas fa-users", 
                    "Authors in Corpus", 
                    minimize_button_id="minimize-author-list",
                    close_button_id="close-author-list"
                ),
                id="author-list-header",
                className="bg-info-subtle text-dark",
                style={'cursor': 'grab'}
            ),
            
            # Content Body
            dbc.CardBody([
                # Controls / Filter
                html.Div([
                    dcc.Input(
                        id="author-list-filter",
                        type="text",
                        placeholder="Filter authors...",
                        className="form-control form-control-sm",
                        style={'marginBottom': '10px'}
                    ),
                    html.Div(id="author-count-badge", style={'fontSize': '12px', 'color': '#666', 'textAlign': 'right'})
                ], style={'padding': '0 0 10px 0'}),

                # The List
                html.Div(id="author-list-content", style={
                    'flex': '1 1 auto',
                    'overflowY': 'auto',
                    'minHeight': 0,
                    'border': '1px solid #eee',
                    'borderRadius': '4px'
                })
            ], id='author-list-body', style={
                'flex': '1 1 auto',
                'display': 'flex',
                'flexDirection': 'column',
                'padding': '10px',
                'minHeight': 0
            })
        ], style={'height': '100%', 'display': 'flex', 'flexDirection': 'column'})
    ], id='author-list-container', className="position-absolute dialog-card", style={
        'width': f"{DEFAULT_CARD_SIZES['author-list']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['author-list']['height']}px",
        'minWidth': '300px',
        'minHeight': '200px',
        'zIndex': 1050, # Above corpus/places
        'display': 'none',
        'top': '80px',
        'left': '400px',
        'cursor': 'grab',
        'flexDirection': 'column'
    })

from dash import html, dcc
import dash_bootstrap_components as dbc
from dash_imagination.components.common.size_controls import card_title_bar
from dash_imagination.components.authors.author_list_card import DEFAULT_CARD_SIZES

def create_author_info_card():
    """
    Create the floating card that shows details for a selected author.
    """
    return html.Div([
        # Window state store
        dcc.Store(id='author-info-window-state', data={'minimized': False, 'restored_style': None}),
        
        # Store for selected author
        dcc.Store(id='selected-author-store', data=None),

        dbc.Card([
            # Title bar
            dbc.CardHeader(
                card_title_bar(
                    "author-info",
                    "fas fa-user",
                    "Author Details",
                    minimize_button_id="minimize-author-info",
                    close_button_id="close-author-info"
                ),
                id="author-info-header",
                className="bg-info-subtle text-dark",
                style={'cursor': 'grab'}
            ),
            
            # Content Body
            dbc.CardBody([
                html.Div(id="author-info-content", style={
                    'flex': '1 1 auto',
                    'overflowY': 'auto',
                    'minHeight': 0
                })
            ], id='author-info-body', style={
                'flex': '1 1 auto',
                'display': 'flex',
                'flexDirection': 'column',
                'padding': '16px',
                'minHeight': 0
            })
        ], style={'height': '100%', 'display': 'flex', 'flexDirection': 'column'})
    ], id='author-info-container', className="position-absolute dialog-card", style={
        'width': f"{DEFAULT_CARD_SIZES['author-info']['width']}px",
        'height': f"{DEFAULT_CARD_SIZES['author-info']['height']}px",
        'minWidth': '300px',
        'minHeight': '300px',
        'zIndex': 1100, # Top most
        'display': 'none',
        'top': '100px',
        'left': '500px',
        'cursor': 'grab',
        'flexDirection': 'column'
    })

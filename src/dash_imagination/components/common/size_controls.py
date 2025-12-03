from dash import html
import dash_bootstrap_components as dbc

SIZE_PRESETS = {
    'compact': {'width': 320, 'height': 420},
    'standard': {'width': 380, 'height': 500},
    'wide': {'width': 480, 'height': 600},
}

CARD_DEFAULT_PRESET = {
    'place-summary': 'standard',
    'places': 'wide',
    'corpus-controls': 'standard',
    'map-visuals': 'standard',
    'heatmap-visuals': 'standard',
    'corpus-builder': 'standard',
    'collocation-card': 'standard',
    'similarity-card': 'standard',
    'author-list': 'standard',
    'author-info': 'standard'
}

DEFAULT_CARD_SIZES = {key: SIZE_PRESETS[value].copy() for key, value in CARD_DEFAULT_PRESET.items()}

# Fine-tune initial dimensions (simulate manual W+/H+ adjustments)
DEFAULT_CARD_SIZES['corpus-controls']['width'] += 80  # One W+ click
DEFAULT_CARD_SIZES['corpus-builder']['height'] += 160  # Two H+ clicks
DEFAULT_CARD_SIZES['places']['height'] += 160  # Two H+ clicks
DEFAULT_CARD_SIZES['similarity-card']['height'] += 160  # Two H+ clicks


def size_control_buttons(component_id: str):
    return html.Div(
        html.Div(
            [
                html.Span(className="size-circle-indicator"),
                html.Button(
                    "+",
                    id={'type': 'size-btn', 'card': component_id, 'axis': 'height', 'delta': 80},
                    className="size-circle-hotspot size-circle-hotspot--up size-circle-hotspot--plus",
                    title="Øk høyde",
                    type="button",
                    tabIndex=-1
                ),
                html.Button(
                    "+",
                    id={'type': 'size-btn', 'card': component_id, 'axis': 'width', 'delta': 80},
                    className="size-circle-hotspot size-circle-hotspot--right size-circle-hotspot--plus",
                    title="Øk bredde",
                    type="button",
                    tabIndex=-1
                ),
                html.Button(
                    "−",
                    id={'type': 'size-btn', 'card': component_id, 'axis': 'height', 'delta': -80},
                    className="size-circle-hotspot size-circle-hotspot--down size-circle-hotspot--minus",
                    title="Minsk høyde",
                    type="button",
                    tabIndex=-1
                ),
                html.Button(
                    "−",
                    id={'type': 'size-btn', 'card': component_id, 'axis': 'width', 'delta': -80},
                    className="size-circle-hotspot size-circle-hotspot--left size-circle-hotspot--minus",
                    title="Minsk bredde",
                    type="button",
                    tabIndex=-1
                )
            ],
            className="size-resize-circle",
            title="Justér kortstørrelse"
        ),
        className="size-control-wrapper"
    )


def card_title_bar(
    component_id,
    icon_class,
    title,
    *,
    close_button_id=None,
    close_button_title=None,
    minimize_button_id=None,
    minimize_button_title=None
):
    """
    Shared header layout for floating dialog cards.
    """
    window_controls = []
    if close_button_id:
        window_controls.append(
            html.Button(
                html.Span("×", className="card-window-icon"),
            id=close_button_id,
            title=close_button_title or "Hide card",
                className="card-window-btn window-close",
                type="button"
            )
        )
    if minimize_button_id:
        window_controls.append(
            html.Button(
                html.Span("–", className="card-window-icon"),
                id=minimize_button_id,
                title=minimize_button_title or "Minimize card",
                className="card-window-btn window-minimize",
            type="button"
            )
        )

    title_children = []
    if window_controls:
        title_children.append(
            html.Div(window_controls, className="card-window-controls")
        )
    title_children.extend([
        html.I(className=f"{icon_class} card-title-icon"),
        html.H5(title, className="card-title-text mb-0")
    ])

    action_children = [size_control_buttons(component_id)]

    return html.Div(
        [
            html.Div(title_children, className="card-title-main"),
            html.Div(action_children, className="card-title-actions")
        ],
        className="card-title-bar"
    )


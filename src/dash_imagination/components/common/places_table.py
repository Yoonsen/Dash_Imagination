from dash import html, dcc


def render_place_preview(
    df,
    selected_place,
    empty_message="Ingen steder tilgjengelig.",
    *,
    body_max_height=360,
    sort_field=None,
    sort_dir='desc',
    total_count=None,
    show_mode_toggle=False,
    mode_value='basis'
):
    """
    Shared helper that renders a summary + scrollable table for place lists.
    """
    if df is None or df.empty:
        return html.Div(empty_message, className="text-muted"), html.Div()

    if sort_field:
        ascending = (sort_dir == 'asc')
        if sort_field in df.columns:
            df = df.sort_values(by=sort_field, ascending=ascending)

    df = df.copy()
    df['hover_text'] = df.apply(
        lambda row: (
            f"{row.get('token', '')} ({row.get('name', '')})<br>"
            f"Modern name: {row.get('name', '')}<br>"
            f"Mentions: {int(row.get('frequency', 0))}<br>"
            f"Books: {int(row.get('book_count', 0))}"
        ),
        axis=1
    )

    count_text = f"{len(df):,} steder".replace(',', ' ')
    if total_count is not None:
        count_text = f"{len(df):,} av {total_count:,} steder".replace(',', ' ')
    summary_children = [html.Span(count_text, style={'fontSize': '0.85rem', 'fontWeight': 600, 'color': '#0f172a'})]
    if show_mode_toggle:
        summary_children.append(
            dcc.RadioItems(
                id='places-mode-radio',
                options=[
                    {'label': 'Basis', 'value': 'basis'},
                    {'label': 'Sample', 'value': 'sample'},
                    {'label': 'Coll', 'value': 'coll'},
                    {'label': 'Sim', 'value': 'sim'},
                ],
                value=mode_value or 'basis',
                labelStyle={'marginRight': '10px', 'fontSize': '0.8rem', 'display': 'inline-flex', 'alignItems': 'center'},
                style={'marginLeft': '12px'}
            )
        )
    summary = html.Div(
        summary_children,
        style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'flexWrap': 'wrap'}
    )

    def header_cell(label, key, flex=None):
        return html.Span(
            label,
            style={
                'flex': flex if flex is not None else ('1.2' if key in ('token', 'name') else '0.7'),
                'fontWeight': '600',
                'padding': '8px',
                'cursor': 'pointer',
                'border': 'none',
                'background': 'transparent',
                'textAlign': 'left',
                'display': 'inline-block'
            },
            className="places-sort-header",
            **{'data-key': key, 'role': 'button', 'tabIndex': 0, 'aria-label': f"Sorter {label}"}
        )

    rows = []
    for _, row in df.iterrows():
        cells = [
            html.Div(
                f"{row.get('token', '')}",
                style={'flex': '1.2', 'padding': '8px', 'fontWeight': '500', 'fontSize': '0.9rem'}
            ),
            html.Div(
                f"{row.get('name', '') or '—'}",
                style={
                    'flex': '1.2',
                    'padding': '8px',
                    'color': '#475569',
                    'fontSize': '0.85rem',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'whiteSpace': 'nowrap'
                }
            ),
            html.Div(
                f"{int(row.get('book_count', 0))}",
                style={'flex': '0.7', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'}
            ),
            html.Div(
                f"{int(row.get('frequency', 0))}",
                style={'flex': '0.7', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'}
            )
        ]
        if 'collocation_count' in df.columns:
            cells.append(
                html.Div(
                    f"{int(row.get('collocation_count', 0))}",
                    style={'flex': '0.7', 'padding': '8px', 'textAlign': 'center', 'fontSize': '0.9rem'}
                )
            )
        rows.append(
            html.Div(
                cells,
                style={
                    'display': 'flex',
                    'borderBottom': '1px solid #eee',
                    'transition': 'background-color 0.2s',
                    'cursor': 'pointer',
                    'backgroundColor': '#fff7ed' if selected_place == row['token'] else 'transparent'
                },
                className='place-item',
                id={'type': 'place-item', 'index': row['token']},
                **{
                    'data-lat': row.get('latitude'),
                    'data-lon': row.get('longitude'),
                    'data-hover': row['hover_text']
                }
            )
        )

    table_body_style = {
        'flex': '1 1 auto',
        'minHeight': 0,
        'overflowY': 'auto'
    }
    if body_max_height is not None:
        table_body_style['maxHeight'] = body_max_height

    table = html.Div(
        [
            html.Div(
                [c for c in [
                    header_cell("Historisk", 'token'),
                    header_cell("Moderne", 'name'),
                    header_cell("📚", 'book_count'),
                    header_cell("📝", 'frequency'),
                    header_cell("Coll", 'collocation_count') if 'collocation_count' in df.columns else None
                ] if c is not None],
                style={
                    'display': 'flex',
                    'borderBottom': '2px solid #eee',
                    'marginBottom': '4px',
                    'fontSize': '0.9rem'
                }
            ),
            html.Div(rows, style=table_body_style)
        ],
        style={
            'border': '1px solid #eee',
            'borderRadius': '4px',
            'padding': '4px',
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'column'
        }
    )

    return summary, table


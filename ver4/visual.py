import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, State, dash_table
import numpy as np

from utils import timestamp_to_utc, format_timestamp_with_nanoseconds


# словари для преобразования категорий в метры и проценты
NIC_TO_HIL = {
    11: 7.5, 10: 25.0, 9: 75.0, 8: 185.2, 7: 370.4, 6: 1111.2,
    5: 1852.0, 4: 3704.0, 3: 7408.0, 2: 14816.0, 1: 37040.0, 0: 40000.0
}

NACP_TO_HFOM = {
    11: 3.0, 10: 10.0, 9: 30.0, 8: 92.6, 7: 185.2, 6: 555.6,
    5: 926.0, 4: 1852.0, 3: 3704.0, 2: 7408.0, 1: 18520.0, 0: 20000.0
}

GVA_TO_VFOM = {
    2: 45.0, 1: 150.0, 0: 500.0, 3: 0.0
}

NIC_TO_PERCENT = {
    11: 100, 10: 86, 9: 73, 8: 62, 7: 54, 6: 41,
    5: 35, 4: 27, 3: 19, 2: 11, 1: 0, 0: 0
}

NACP_TO_PERCENT = {
    11: 100, 10: 86, 9: 74, 8: 61, 7: 53, 6: 40,
    5: 34, 4: 26, 3: 18, 2: 10, 1: 0, 0: 0
}

GVA_TO_PERCENT = {
    2: 100, 1: 0, 0: 0, 3: 0
}


class IcaoGraphs:
    def __init__(self, alt_dict, spd_dict, pos_dict, course_dict, adsb_icao_list, icao_callsigns,
                 icao_sel_alt, icao_alt_diff, icao_baro_correction, icao_gnss_alt,
                 icao_nic, icao_nacp, icao_gva, icao_sil, icao_nacv, icao_anomalies,
                 messages_dict):
        icao_with_data = set(alt_dict.keys()) | set(spd_dict.keys()) | set(pos_dict.keys()) | set(course_dict.keys()) | set(icao_gnss_alt.keys())
        self.icao_list = sorted(list(icao_with_data.intersection(adsb_icao_list)))

        if not self.icao_list:
            print("нет данных для построения графиков")
            return

        self.alt_dict = alt_dict
        self.spd_dict = spd_dict
        self.pos_dict = pos_dict
        self.course_dict = course_dict
        self.icao_callsigns = icao_callsigns
        self.sel_alt_dict = icao_sel_alt if icao_sel_alt else {}
        self.alt_diff_dict = icao_alt_diff if icao_alt_diff else {}
        self.baro_correction_dict = icao_baro_correction if icao_baro_correction else {}
        self.gnss_alt_dict = icao_gnss_alt if icao_gnss_alt else {}

        self.nic_dict = icao_nic if icao_nic else {}
        self.nacp_dict = icao_nacp if icao_nacp else {}
        self.gva_dict = icao_gva if icao_gva else {}
        self.sil_dict = icao_sil if icao_sil else {}
        self.nacv_dict = icao_nacv if icao_nacv else {}

        self.anomalies_dict = icao_anomalies if icao_anomalies else {}
        self.messages_dict = messages_dict if messages_dict else {}

        self.app = dash.Dash(__name__, title='Авиационный Дашборд')
        self.setup_layout()
        self.setup_callbacks()

        print("\nзапуск веб-интерфейса. откройте в браузере: http://127.0.0.1:8050")
        self.app.run(debug=False, use_reloader=False)

    def get_display_id(self, icao):
        callsign = self.icao_callsigns.get(icao, "N/A")
        squawk = self.icao_callsigns.get(f"{icao}_sq", "")
        if squawk:
            callsign += f" (SQ:{squawk})"
        modes_key = f"{icao}_modes"
        active_modes = self.icao_callsigns.get(modes_key, set())
        mode_str = f" ({', '.join(sorted(active_modes))})" if active_modes else ""
        return f"{callsign} ({icao}){mode_str}" if callsign != "N/A" else f"{icao}{mode_str}"

    def get_times_values(self, data):
        if not data:
            return [], []
        sorted_data = sorted(data)
        return [timestamp_to_utc(t) for t, v in sorted_data], [v for t, v in sorted_data]

    def generate_styled_table(self):
        table_rows = []
        for icao in self.icao_list:
            callsign = self.icao_callsigns.get(icao, "N/A")
            alt_data = self.alt_dict.get(icao, [[0, 0]])
            spd_data = self.spd_dict.get(icao, [[0, 0]])
            alt = alt_data[-1][1] if alt_data else 0
            spd = spd_data[-1][1] if spd_data else 0
            status_text = "аномалия" if icao in self.anomalies_dict else "норма"
            table_rows.append({
                "ICAO": icao,
                "Позывной": callsign,
                "Высота (фт)": f"{int(alt):,}",
                "Скорость (уз)": f"{int(spd):,}",
                "Статус": status_text
            })
        return dash_table.DataTable(
            data=table_rows,
            columns=[{"name": i, "id": i} for i in ["ICAO", "Позывной", "Высота (фт)", "Скорость (уз)", "Статус"]],
            sort_action="native",
            style_as_list_view=True,
            style_header={'backgroundColor': '#f1f1f1', 'fontWeight': 'bold', 'borderBottom': '2px solid #007bff'},
            style_cell={'padding': '12px', 'textAlign': 'left', 'fontFamily': 'Arial, sans-serif'},
            style_data_conditional=[
                {'if': {'row_index': 'odd'}, 'backgroundColor': '#f9f9f9'},
                {'if': {'column_id': 'Статус', 'filter_query': '{Статус} contains "аномалия"'}, 'color': 'red', 'fontWeight': 'bold'}
            ]
        )

    def _finalize_group(self, group, grouped):
        """завершает группу аномалий и добавляет в список grouped"""
        if group['type'] == 'SPOOFING':
            avg_diff = sum(group['values']) / len(group['values']) if group['values'] else 0
            desc = f"аномальная разница высот: с {format_timestamp_with_nanoseconds(group['start_time'])} по {format_timestamp_with_nanoseconds(group['end_time'])} (средняя разница {avg_diff:.0f} фт)"
        else:
            desc = f"падение nic: с {format_timestamp_with_nanoseconds(group['start_time'])} по {format_timestamp_with_nanoseconds(group['end_time'])}"
        grouped.append({
            'type': group['type'],
            'desc': desc,
            'start': group['start_time'],
            'end': group['end_time']
        })

    def _group_anomalies(self, anomalies):
        if not anomalies:
            return []
        grouped = []
        current_group = None
        for a in anomalies:
            if current_group is None:
                current_group = {
                    'type': a['type'],
                    'start_time': a['time'],
                    'end_time': a['time'],
                    'desc_list': [a['desc']],
                    'values': []
                }
                if a['type'] == 'SPOOFING':
                    import re
                    match = re.search(r'(\d+) фт', a['desc'])
                    if match:
                        current_group['values'].append(int(match.group(1)))
            else:
                if current_group['type'] == a['type'] and (a['time'] - current_group['end_time']) <= 10:
                    current_group['end_time'] = a['time']
                    current_group['desc_list'].append(a['desc'])
                    if a['type'] == 'SPOOFING':
                        import re
                        match = re.search(r'(\d+) фт', a['desc'])
                        if match:
                            current_group['values'].append(int(match.group(1)))
                else:
                    self._finalize_group(current_group, grouped)
                    current_group = {
                        'type': a['type'],
                        'start_time': a['time'],
                        'end_time': a['time'],
                        'desc_list': [a['desc']],
                        'values': []
                    }
                    if a['type'] == 'SPOOFING':
                        import re
                        match = re.search(r'(\d+) фт', a['desc'])
                        if match:
                            current_group['values'].append(int(match.group(1)))
        if current_group:
            self._finalize_group(current_group, grouped)
        return grouped

    def _get_anomaly_time_ranges(self, icao):
        """возвращает список кортежей (start_ts, end_ts) для аномалий данного борта"""
        if icao not in self.anomalies_dict:
            return []
        grouped = self._group_anomalies(self.anomalies_dict[icao])
        return [(g['start'], g['end']) for g in grouped]

    def _add_anomaly_vrects(self, fig, icao, xaxis_ref='x'):
        """добавляет вертикальные красные прямоугольники на график по временным интервалам аномалий"""
        ranges = self._get_anomaly_time_ranges(icao)
        for start, end in ranges:
            start_utc = timestamp_to_utc(start)
            end_utc = timestamp_to_utc(end)
            fig.add_vrect(
                x0=start_utc, x1=end_utc,
                fillcolor="red", opacity=0.2, layer="below", line_width=0,
                annotation_text="аномалия", annotation_position="top left",
                annotation_font_size=10, annotation_font_color="red"
            )

    def _compute_ground_speed_from_positions(self, pos_data):
        """рассчитывает скорость по координатам (узлы) для каждой пары соседних точек"""
        if not pos_data or len(pos_data) < 2:
            return []
        sorted_pos = sorted(pos_data, key=lambda x: x[0])
        speeds = []
        for i in range(1, len(sorted_pos)):
            t1, lat1, lon1 = sorted_pos[i-1]
            t2, lat2, lon2 = sorted_pos[i]
            dt = t2 - t1
            if dt <= 0:
                continue
            R = 6371000
            phi1 = np.radians(lat1)
            phi2 = np.radians(lat2)
            dphi = np.radians(lat2 - lat1)
            dlambda = np.radians(lon2 - lon1)
            a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            dist_m = R * c
            speed_mps = dist_m / dt
            speed_kts = speed_mps * 1.94384
            speeds.append((t2, speed_kts))
        return speeds

    def setup_layout(self):
        self.app.layout = html.Div(
            style={'font-family': 'sans-serif', 'padding': '20px', 'backgroundColor': '#f4f6f8', 'minHeight': '100vh'},
            children=[
                html.H2("Авиационный Навигационный Дашборд", style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '30px'}),
                dcc.Store(id='zoom-store', data={}),
                html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px', 'flexWrap': 'wrap', 'justifyContent': 'center'}, children=[
                    html.Div([
                        html.Label("Борт (ICAO):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(id='icao-dropdown', options=[{'label': self.get_display_id(i), 'value': i} for i in self.icao_list], value=self.icao_list[0] if self.icao_list else None, style={'width': '300px'})
                    ]),
                    html.Div([
                        html.Label("Режим экрана:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(id='mode-dropdown', options=[
                            {'label': 'Схема трека (2D карта)', 'value': 'track'},
                            {'label': 'Трек борта с качеством NIC', 'value': 'nic_track'},
                            {'label': 'Кинематика (высота, скорость, курс)', 'value': 'kinematics'},
                            {'label': 'Категории целостности (NIC/SIL, NAC)', 'value': 'integrity_and_accuracy'},
                            {'label': 'Физические метрики (HIL, FOM)', 'value': 'quality_metrics'},
                            {'label': 'Барометрический анализ', 'value': 'baro_analysis'},
                            {'label': 'Качество данных в % (HIL/HFOM/VFOM)', 'value': 'quality_percentages'},
                            {'label': 'Спуфинг-анализ: кинематика (GS vs скорость по координатам)', 'value': 'spoofing_kinematics'},
                            {'label': 'Джамминг-анализ: активность пакетов (DF)', 'value': 'jamming_activity'},
                            {'label': 'Интенсивность сообщений (Message Rate) – Jamming', 'value': 'message_rate'}
                        ], value='track', style={'width': '300px'})
                    ]),
                    html.Div(id='mapbox-toggle-container', children=[
                        html.Label("Реальная карта (Mapbox):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Checklist(id='mapbox-toggle', options=[{'label': 'Включить', 'value': 'mapbox'}], value=[])
                    ])
                ]),
                html.Div(style={'backgroundColor': '#ffffff', 'padding': '15px', 'borderRadius': '10px', 'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.1)'}, children=[
                    dcc.Graph(id='main-graph', style={'height': '90vh'}, config={'displayModeBar': True})
                ]),
                html.Div(id='tables-container', style={'display': 'flex', 'gap': '20px', 'marginTop': '20px'}, children=[
                    html.Div(style={'flex': '1', 'backgroundColor': '#ffffff', 'borderRadius': '10px', 'padding': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
                        html.H3("Сводная информация по всем бортам", style={'textAlign': 'center'}),
                        html.Div(id='table-container')
                    ]),
                    html.Div(style={'flex': '1', 'backgroundColor': '#ffffff', 'borderRadius': '10px', 'padding': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
                        html.H3("Журнал безопасности (обнаруженные аномалии)", style={'textAlign': 'center', 'color': '#c0392b'}),
                        dash_table.DataTable(
                            id='anomaly-table',
                            columns=[
                                {'name': 'Период (UTC)', 'id': 'period'},
                                {'name': 'Тип', 'id': 'type'},
                                {'name': 'Уровень', 'id': 'severity'},
                                {'name': 'Описание', 'id': 'description'}
                            ],
                            data=[],
                            style_cell={'textAlign': 'left', 'padding': '8px'},
                            style_header={'backgroundColor': '#f1f1f1', 'fontWeight': 'bold'},
                            style_data_conditional=[
                                {'if': {'filter_query': '{severity} eq "critical"'}, 'backgroundColor': '#ffcccc', 'color': '#a00'},
                                {'if': {'filter_query': '{severity} eq "high"'}, 'backgroundColor': '#ffe0b3', 'color': '#c60'},
                                {'if': {'filter_query': '{severity} eq "warning"'}, 'backgroundColor': '#ffffcc', 'color': '#aa0'},
                            ],
                            row_selectable=False,
                            active_cell=None,
                            hidden_columns=['start_ts', 'end_ts']
                        )
                    ])
                ])
            ]
        )

    def _get_color_from_nic(self, nic):
        if nic is None:
            return 'lightgray'
        if nic >= 10:
            return 'green'
        elif nic >= 7:
            return 'orange'
        else:
            return 'red'

    def _get_closest_nic(self, timestamp, nic_list):
        if not nic_list:
            return None
        lo, hi = 0, len(nic_list) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            ts_mid, nic_mid = nic_list[mid]
            if ts_mid < timestamp:
                best = (ts_mid, nic_mid)
                lo = mid + 1
            elif ts_mid > timestamp:
                hi = mid - 1
            else:
                return nic_mid
        if best is None:
            return nic_list[0][1] if nic_list else None
        next_idx = best[0] + 1
        if next_idx < len(nic_list) and abs(nic_list[next_idx][0] - timestamp) < abs(best[0] - timestamp):
            return nic_list[next_idx][1]
        return best[1]

    def setup_callbacks(self):
        @self.app.callback(
            [Output('main-graph', 'figure'),
             Output('table-container', 'children'),
             Output('anomaly-table', 'data'),
             Output('tables-container', 'style'),
             Output('mapbox-toggle-container', 'style')],
            [Input('icao-dropdown', 'value'),
             Input('mode-dropdown', 'value'),
             Input('mapbox-toggle', 'value')]
        )
        def update_graph(icao, mode, mapbox_toggle):
            if mode in ('track', 'nic_track'):
                tables_style = {'display': 'flex', 'gap': '20px', 'marginTop': '20px'}
                mapbox_style = {'display': 'block'}
            else:
                tables_style = {'display': 'none'}
                mapbox_style = {'display': 'none'}

            full_table = self.generate_styled_table()

            # подготовка данных для таблицы аномалий
            anomaly_rows = []
            if icao and icao in self.anomalies_dict:
                for anom in self.anomalies_dict[icao]:
                    start_ts = anom['time']
                    end_ts = start_ts
                    severity = anom.get('severity', 'info')
                    anomaly_rows.append({
                        'period': format_timestamp_with_nanoseconds(start_ts),
                        'type': anom['type'],
                        'severity': severity,
                        'description': anom['desc'],
                        'start_ts': start_ts,
                        'end_ts': end_ts
                    })

            if not icao:
                return go.Figure(), full_table, anomaly_rows, tables_style, mapbox_style

            display_id = self.get_display_id(icao)

            # режим nic_track (цветной трек) с выделением аномальных сегментов
            if mode == 'nic_track':
                pos_data = self.pos_dict.get(icao)
                if not pos_data or len(pos_data) < 2:
                    fig = go.Figure().add_annotation(text="недостаточно данных координат", showarrow=False)
                    return fig, full_table, anomaly_rows, tables_style, mapbox_style
                nic_data = self.nic_dict.get(icao, [])
                pos_sorted = sorted(pos_data, key=lambda x: x[0])
                use_mapbox = 'mapbox' in mapbox_toggle
                # подготовка точек с nic
                points = [(t, lat, lon, self._get_closest_nic(t, nic_data)) for t, lat, lon in pos_sorted]
                # интервалы аномалий
                anomaly_ranges = self._get_anomaly_time_ranges(icao)
                fig = go.Figure()
                # функция для проверки принадлежности времени аномалии
                def is_time_in_anomaly(t):
                    for start, end in anomaly_ranges:
                        if start <= t <= end:
                            return True
                    return False
                # разбиваем на сегменты по цвету NIC и аномалиям
                i = 0
                while i < len(points) - 1:
                    j = i + 1
                    # определяем цвет по NIC для текущего сегмента
                    current_nic_color = self._get_color_from_nic(points[i][3])
                    # также проверяем, является ли сегмент аномальным (хотя бы одна точка)
                    is_anomaly_segment = any(is_time_in_anomaly(points[k][0]) for k in range(i, j))
                    while j < len(points):
                        next_nic_color = self._get_color_from_nic(points[j][3])
                        if next_nic_color == current_nic_color:
                            j += 1
                        else:
                            break
                    # цвет линии: если сегмент аномальный - красный, иначе цвет NIC
                    line_color = 'red' if is_anomaly_segment else current_nic_color
                    lats = [p[1] for p in points[i:j]]
                    lons = [p[2] for p in points[i:j]]
                    times_seg = [p[0] for p in points[i:j]]
                    # hovertext
                    hover_text = [f"время: {timestamp_to_utc(t).strftime('%H:%M:%S')}<br>nic: {nic}" for t,lat,lon,nic in points[i:j]]
                    if use_mapbox:
                        fig.add_trace(go.Scattermapbox(
                            lat=lats, lon=lons, mode='lines',
                            line=dict(width=3, color=line_color),
                            hoverinfo='text', text=hover_text, showlegend=False
                        ))
                    else:
                        fig.add_trace(go.Scatter(
                            x=lons, y=lats, mode='lines',
                            line=dict(width=3, color=line_color),
                            hoverinfo='text', text=hover_text, showlegend=False
                        ))
                    i = j
                # добавляем маркеры
                for t, lat, lon, nic in points:
                    color = self._get_color_from_nic(nic)
                    if is_time_in_anomaly(t):
                        color = 'red'
                    hover = f"время: {timestamp_to_utc(t).strftime('%H:%M:%S')}<br>nic: {nic if nic is not None else 'нет данных'}"
                    if use_mapbox:
                        fig.add_trace(go.Scattermapbox(
                            lat=[lat], lon=[lon], mode='markers',
                            marker=dict(size=6, color=color),
                            text=hover, hoverinfo='text', showlegend=False
                        ))
                    else:
                        fig.add_trace(go.Scatter(
                            x=[lon], y=[lat], mode='markers',
                            marker=dict(size=6, color=color),
                            text=hover, hoverinfo='text', showlegend=False
                        ))
                if use_mapbox:
                    center = (sum(p[1] for p in points)/len(points), sum(p[2] for p in points)/len(points))
                    fig.update_layout(
                        title=f"трек борта {display_id} с цветовой индикацией nic (красный – аномалия)",
                        mapbox=dict(style="open-street-map", center=dict(lat=center[0], lon=center[1]), zoom=9),
                        margin=dict(l=0, r=150, t=40, b=0),
                        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
                    )
                else:
                    fig.update_layout(
                        title=f"трек борта {display_id} с цветовой индикацией nic (красный – аномалия)",
                        xaxis_title="долгота", yaxis_title="широта",
                        yaxis=dict(scaleanchor="x", scaleratio=1),
                        template="plotly_white", hovermode='closest', margin=dict(r=150),
                        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
                    )
                # легенда
                for item in [go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='green'), name='nic ≥ 10 (отлично)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='orange'), name='nic 7–9 (средне)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='red'), name='nic ≤ 6 или аномалия'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='lightgray'), name='nic нет данных')]:
                    fig.add_trace(item)
                return fig, full_table, anomaly_rows, tables_style, mapbox_style

            # режим общей карты с выделением аномальных сегментов
            if mode == 'track':
                if not self.pos_dict:
                    return go.Figure().add_annotation(text="нет данных координат", showarrow=False), full_table, anomaly_rows, tables_style, mapbox_style
                use_mapbox = 'mapbox' in mapbox_toggle
                anomaly_ranges = self._get_anomaly_time_ranges(icao)
                def is_time_in_anomaly(t):
                    for start, end in anomaly_ranges:
                        if start <= t <= end:
                            return True
                    return False
                if use_mapbox:
                    fig = go.Figure()
                    # другие борта
                    for track_icao, track_data in self.pos_dict.items():
                        if track_icao not in self.icao_list or track_icao == icao:
                            continue
                        lats = [lat for t, lat, lon in track_data]
                        lons = [lon for t, lat, lon in track_data]
                        fig.add_trace(go.Scattermapbox(
                            lat=lats, lon=lons, mode='lines', line=dict(width=2, color='#a0a0a0'),
                            opacity=0.8, hoverinfo='text', text=[f"борт: {track_icao}"]*len(lons), showlegend=False
                        ))
                    # текущий борт с разбивкой на аномальные/нормальные сегменты
                    curr_data = self.pos_dict.get(icao)
                    if curr_data:
                        curr_sorted = sorted(curr_data, key=lambda x: x[0])
                        i = 0
                        while i < len(curr_sorted) - 1:
                            j = i + 1
                            # определяем, является ли сегмент аномальным (хотя бы одна точка)
                            is_anomaly = any(is_time_in_anomaly(curr_sorted[k][0]) for k in range(i, j))
                            while j < len(curr_sorted):
                                # проверяем, не изменился ли статус аномальности на следующей точке
                                next_anomaly = any(is_time_in_anomaly(curr_sorted[j][0]) for kk in [j])
                                if next_anomaly == is_anomaly:
                                    j += 1
                                else:
                                    break
                            lats = [lat for t, lat, lon in curr_sorted[i:j]]
                            lons = [lon for t, lat, lon in curr_sorted[i:j]]
                            times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in curr_sorted[i:j]]
                            line_color = 'red' if is_anomaly else '#d62728'
                            fig.add_trace(go.Scattermapbox(
                                lat=lats, lon=lons, mode='lines+markers',
                                marker=dict(size=6, color=line_color),
                                line=dict(width=3, color=line_color),
                                text=times, name=display_id if not is_anomaly else f"{display_id} (аномалия)"
                            ))
                            i = j
                    all_lats = [lat for tdata in self.pos_dict.values() for t, lat, lon in tdata]
                    all_lons = [lon for tdata in self.pos_dict.values() for t, lat, lon in tdata]
                    center_lat, center_lon = sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)
                    fig.update_layout(
                        title="общая карта (все обнаруженные треки) — реальная карта, красный – аномалия",
                        mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=8),
                        margin=dict(l=0, r=0, t=40, b=0),
                        legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99),
                        modebar=dict(orientation='v')
                    )
                else:
                    fig = go.Figure()
                    # другие борта
                    for track_icao, track_data in self.pos_dict.items():
                        if track_icao not in self.icao_list or track_icao == icao:
                            continue
                        lats = [lat for t, lat, lon in track_data]
                        lons = [lon for t, lat, lon in track_data]
                        fig.add_trace(go.Scatter(
                            x=lons, y=lats, mode='lines', line=dict(width=2, color='#a0a0a0'),
                            opacity=0.8, hoverinfo='text', text=[f"борт: {track_icao}"]*len(lons), showlegend=False
                        ))
                    # текущий борт с разбивкой
                    curr_data = self.pos_dict.get(icao)
                    if curr_data:
                        curr_sorted = sorted(curr_data, key=lambda x: x[0])
                        i = 0
                        while i < len(curr_sorted) - 1:
                            j = i + 1
                            is_anomaly = any(is_time_in_anomaly(curr_sorted[k][0]) for k in range(i, j))
                            while j < len(curr_sorted):
                                next_anomaly = any(is_time_in_anomaly(curr_sorted[j][0]) for kk in [j])
                                if next_anomaly == is_anomaly:
                                    j += 1
                                else:
                                    break
                            lats = [lat for t, lat, lon in curr_sorted[i:j]]
                            lons = [lon for t, lat, lon in curr_sorted[i:j]]
                            times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in curr_sorted[i:j]]
                            line_color = 'red' if is_anomaly else '#d62728'
                            fig.add_trace(go.Scatter(
                                x=lons, y=lats, mode='lines+markers', marker=dict(size=5, color=line_color),
                                line=dict(width=3, color=line_color), text=times, name=display_id if not is_anomaly else f"{display_id} (аномалия)"
                            ))
                            i = j
                    fig.update_layout(
                        title="общая карта (все обнаруженные треки), красный – аномалия",
                        xaxis_title="долгота", yaxis_title="широта", yaxis=dict(scaleanchor="x", scaleratio=1),
                        template="plotly_white", hovermode='closest'
                    )
                return fig, full_table, anomaly_rows, tables_style, mapbox_style

            # остальные режимы строятся через _build_normal_figure (с добавлением vrect)
            fig = self._build_normal_figure(icao, mode, display_id)
            return fig, full_table, anomaly_rows, tables_style, mapbox_style

        # callback для зума по клику на строку аномалии
        @self.app.callback(
            Output('main-graph', 'relayoutData'),
            Input('anomaly-table', 'active_cell'),
            State('anomaly-table', 'data'),
            prevent_initial_call=True
        )
        def zoom_to_anomaly(active_cell, table_data):
            if not active_cell or not table_data:
                raise dash.exceptions.PreventUpdate
            row_idx = active_cell['row']
            if row_idx >= len(table_data):
                raise dash.exceptions.PreventUpdate
            anomaly = table_data[row_idx]
            start_ts = anomaly.get('start_ts')
            end_ts = anomaly.get('end_ts')
            if start_ts is not None and end_ts is not None:
                start_utc = timestamp_to_utc(start_ts)
                end_utc = timestamp_to_utc(end_ts)
                return {'xaxis.range': [start_utc, end_utc]}
            return {}

    def _build_normal_figure(self, icao, mode, display_id):
        # режим кинематики
        if mode == 'kinematics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=("высота (фт)", "скорость (узлы)", "курс (°)"))
            times, vals = self.get_times_values(self.alt_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='baro alt', marker=dict(size=4, color='blue')), row=1, col=1)
            times, vals = self.get_times_values(self.gnss_alt_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='gnss alt', marker=dict(size=4, color='magenta')), row=1, col=1)
            times, vals = self.get_times_values(self.sel_alt_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='selected alt', line=dict(color='red', dash='dash', shape='vh')), row=1, col=1)
            times, vals = self.get_times_values(self.spd_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='gs', marker=dict(size=4, color='green')), row=2, col=1)
            times, vals = self.get_times_values(self.course_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='курс', marker=dict(size=4, color='purple')), row=3, col=1)
            fig.update_yaxes(range=[-10, 370], tickvals=[0,90,180,270,360], row=3, col=1)
            fig.update_layout(title=f"кинематика полета: {display_id}", template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # категории целостности и точности
        if mode == 'integrity_and_accuracy':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=("nic / sil", "nacp / gva", "nacv"))
            times, vals = self.get_times_values(self.nic_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='nic (0-11)', line=dict(color='darkcyan', width=2, shape='vh'), fill='tozeroy', fillcolor='rgba(0,255,255,0.1)'), row=1, col=1)
            times, vals = self.get_times_values(self.sil_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='sil (0-3)', line=dict(color='darkorange', dash='dash', shape='vh')), row=1, col=1)
            times, vals = self.get_times_values(self.nacp_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='nacp (0-11)', line=dict(color='green', width=2, shape='vh')), row=2, col=1)
            times, vals = self.get_times_values(self.gva_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='gva (0-3)', line=dict(color='purple', dash='dash', shape='vh')), row=2, col=1)
            times, vals = self.get_times_values(self.nacv_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='nacv (0-4)', line=dict(color='brown', width=2, shape='vh')), row=3, col=1)
            fig.update_yaxes(range=[0,12], tickvals=list(range(0,13,2)), row=1, col=1)
            fig.update_yaxes(range=[0,12], tickvals=list(range(0,13,2)), row=2, col=1)
            fig.update_yaxes(range=[0,4], tickvals=list(range(0,5)), row=3, col=1)
            fig.update_layout(title=f"категории качества сигналов: {display_id}", template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # метрики в метрах (hil, hfom, vfom)
        if mode == 'quality_metrics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, subplot_titles=("hil (nic)", "hfom (nacp)", "vfom (gva)"))
            def add_metric(data_dict, mapping, zero_label, row, color):
                data = data_dict.get(icao)
                if not data:
                    return
                times, vals, texts = [], [], []
                for t, val in sorted(data):
                    times.append(timestamp_to_utc(t))
                    if val == 0:
                        vals.append(None)
                        texts.append(zero_label)
                    else:
                        v_m = mapping.get(val, 0)
                        vals.append(v_m)
                        texts.append(f"{v_m} м")
                fig.add_trace(go.Scatter(x=times, y=vals, hovertext=texts, mode='lines+markers', name=color, line=dict(color=color)), row=row, col=1)
            add_metric(self.nic_dict, NIC_TO_HIL, "≥ 20 nm (37.04 км) или неизвестно", 1, 'red')
            add_metric(self.nacp_dict, NACP_TO_HFOM, "hfom ≥ 18.52 км", 2, 'blue')
            add_metric(self.gva_dict, GVA_TO_VFOM, "неизвестно или ≥10 м/с", 3, 'green')
            fig.update_layout(height=800, title_text=f"параметры точности: {display_id}", template="plotly_white")
            self._add_anomaly_vrects(fig, icao)
            return fig

        # барометрический анализ
        if mode == 'baro_analysis':
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("разница высот gnss vs baro (фт)", "барокоррекция (гПа)"))
            times, vals = self.get_times_values(self.alt_diff_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='разница (фт)', marker=dict(size=4, color='red')), row=1, col=1)
                fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)
            times, vals = self.get_times_values(self.baro_correction_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='давление', marker=dict(size=4, color='brown')), row=2, col=1)
            fig.update_layout(title=f"барометрический анализ: {display_id}", template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # проценты качества
        if mode == 'quality_percentages':
            fig = go.Figure()
            if icao in self.nic_dict:
                times, vals = self.get_times_values(self.nic_dict[icao])
                percent_vals = [NIC_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers', name='hil (%)', line=dict(color='red', width=2, shape='hv')))
            if icao in self.nacp_dict:
                times, vals = self.get_times_values(self.nacp_dict[icao])
                percent_vals = [NACP_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers', name='hfom (%)', line=dict(color='blue', width=2, shape='hv')))
            if icao in self.gva_dict:
                times, vals = self.get_times_values(self.gva_dict[icao])
                percent_vals = [GVA_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers', name='vfom (%)', line=dict(color='purple', width=2, dash='dash')))
            fig.update_layout(title=f"качество данных в процентах: {display_id}", yaxis_title="качество (%)", yaxis_range=[-5, 105], template="plotly_white", hovermode='x unified')
            fig.add_annotation(text="hil: <7.5м → 37км\nhfom: <3м → >18.5км\nvfom: ≤45м → ≥150м", xref="paper", yref="paper", x=0.02, y=0.05, showarrow=False, font=dict(size=10), bgcolor="white", bordercolor="gray", borderwidth=1)
            self._add_anomaly_vrects(fig, icao)
            return fig

        # спуфинг-анализ, сравнение скоростей
        if mode == 'spoofing_kinematics':
            fig = go.Figure()
            times, gs_vals = self.get_times_values(self.spd_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=gs_vals, mode='lines+markers', name='заявленная gs (узлы)', line=dict(color='green', width=2), marker=dict(size=4)))
            pos_data = self.pos_dict.get(icao)
            if pos_data and len(pos_data) >= 2:
                calc_speeds = self._compute_ground_speed_from_positions(pos_data)
                if calc_speeds:
                    calc_times, calc_vals = zip(*calc_speeds)
                    calc_times_utc = [timestamp_to_utc(t) for t in calc_times]
                    fig.add_trace(go.Scatter(x=calc_times_utc, y=calc_vals, mode='lines+markers', name='скорость по координатам (узлы)', line=dict(color='red', width=2, dash='dash'), marker=dict(size=4)))
            fig.update_layout(title=f"сравнение скоростей (спуфинг-анализ): {display_id}", xaxis_title="время (utc)", yaxis_title="скорость (узлы)", template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # джамминг-анализ: активность пакетов df
        if mode == 'jamming_activity':
            messages = self.messages_dict.get(icao, [])
            if not messages:
                fig = go.Figure().add_annotation(text="нет данных о сообщениях df", showarrow=False)
                return fig
            df_messages = {}
            for ts, df in messages:
                df_messages.setdefault(df, []).append(ts)
            fig = go.Figure()
            df_order = sorted(df_messages.keys())
            for df in df_order:
                timestamps = df_messages[df]
                times_utc = [timestamp_to_utc(ts) for ts in timestamps]
                fig.add_trace(go.Scatter(
                    x=times_utc,
                    y=[df] * len(timestamps),
                    mode='markers',
                    name=f'df{df}',
                    marker=dict(size=8, opacity=0.7),
                    text=[f'df{df}<br>{timestamp_to_utc(ts).strftime("%H:%M:%S.%f")[:-3]}' for ts in timestamps],
                    hoverinfo='text'
                ))
            fig.update_layout(
                title=f"активность сообщений по типам df: {display_id}",
                xaxis_title="время (utc)",
                yaxis_title="тип сообщения (df)",
                yaxis=dict(tickmode='array', tickvals=df_order, ticktext=[f'df{df}' for df in df_order]),
                template="plotly_white",
                hovermode='closest'
            )
            self._add_anomaly_vrects(fig, icao)
            return fig

        # интенсивность сообщений (Message Rate)
        if mode == 'message_rate':
            messages = self.messages_dict.get(icao, [])
            if not messages:
                fig = go.Figure().add_annotation(text="нет данных о сообщениях", showarrow=False)
                return fig
            messages_sorted = sorted(messages, key=lambda x: x[0])
            timestamps = [ts for ts, _ in messages_sorted]
            start_time = timestamps[0]
            end_time = timestamps[-1]
            bin_width = 1.0
            bins = np.arange(start_time, end_time + bin_width, bin_width)
            hist_total, _ = np.histogram(timestamps, bins=bins)
            coord_timestamps = [ts for ts, df in messages_sorted if df in (17, 18)]
            hist_coord, _ = np.histogram(coord_timestamps, bins=bins)
            bin_centers = (bins[:-1] + bins[1:]) / 2
            bin_centers_utc = [timestamp_to_utc(bc) for bc in bin_centers]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=bin_centers_utc, y=hist_total,
                mode='lines+markers', name='Все сообщения (1/сек)',
                line=dict(color='blue', width=2), marker=dict(size=4)
            ))
            fig.add_trace(go.Scatter(
                x=bin_centers_utc, y=hist_coord,
                mode='lines+markers', name='DF17+18 (координаты)',
                line=dict(color='red', width=2, dash='dash'), marker=dict(size=4)
            ))
            fig.update_layout(
                title=f"Интенсивность сообщений (Message Rate) – {display_id}",
                xaxis_title="время (UTC)",
                yaxis_title="Сообщений в секунду",
                template="plotly_white",
                hovermode='x unified'
            )
            fig.add_annotation(
                text="Резкое падение красной линии (DF17/18) при сохранении синей – признак подавления GNSS (jamming)",
                xref="paper", yref="paper", x=0.02, y=0.95, showarrow=False,
                font=dict(size=11, color="gray"), bgcolor="white", bordercolor="lightgray", borderwidth=1
            )
            self._add_anomaly_vrects(fig, icao)
            return fig

        # если режим не распознан
        fig = go.Figure()
        fig.add_annotation(text=f"режим {mode} не реализован", showarrow=False)
        return fig
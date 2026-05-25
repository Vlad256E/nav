import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output
from utils import timestamp_to_utc, format_timestamp_with_nanoseconds
from dash import dash_table

# ------------------------------------------------------------
# Словари для преобразования категорий в метры и проценты
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# Основной класс визуализации
# ------------------------------------------------------------
class IcaoGraphs:
    def __init__(self, alt_dict, spd_dict, pos_dict, course_dict, adsb_icao_list, icao_callsigns, 
                 icao_sel_alt, icao_alt_diff, icao_baro_correction, icao_gnss_alt,
                 icao_nic, icao_nacp, icao_gva, icao_sil, icao_nacv, icao_anomalies):
        
        icao_with_data = set(alt_dict.keys()) | set(spd_dict.keys()) | set(pos_dict.keys()) | set(course_dict.keys()) | set(icao_gnss_alt.keys())
        self.icao_list = sorted(list(icao_with_data.intersection(adsb_icao_list)))
        
        if not self.icao_list:
            print("Нет данных для построения графиков")
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

        self.app = dash.Dash(__name__, title='Авиационный Дашборд')
        self.setup_layout()
        self.setup_callbacks()
        
        print("\nЗапуск веб-интерфейса. Откройте в браузере: http://127.0.0.1:8050")
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
            
            status_text = "Аномалия" if icao in self.anomalies_dict else "Норма"
            
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
                {'if': {'column_id': 'Статус', 'filter_query': '{Статус} contains "Аномалия"'}, 'color': 'red', 'fontWeight': 'bold'}
            ]
        )
    
    # --- Исправленный метод группировки аномалий (DRY) ---
    def _finalize_group(self, group, grouped):
        """Завершает группу аномалий и добавляет в список grouped."""
        if group['type'] == 'SPOOFING':
            avg_diff = sum(group['values']) / len(group['values']) if group['values'] else 0
            desc = f"Аномальная разница высот: с {format_timestamp_with_nanoseconds(group['start_time'])} по {format_timestamp_with_nanoseconds(group['end_time'])} (средняя разница {avg_diff:.0f} фт)"
        else:
            desc = f"Падение NIC: с {format_timestamp_with_nanoseconds(group['start_time'])} по {format_timestamp_with_nanoseconds(group['end_time'])}"
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

    # ------------------------- Layout -------------------------
    def setup_layout(self):
        self.app.layout = html.Div(
            style={'font-family': 'sans-serif', 'padding': '20px', 'backgroundColor': '#f4f6f8', 'minHeight': '100vh'},
            children=[
                html.H2("Авиационный Навигационный Дашборд", style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '30px'}),
                html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px', 'flexWrap': 'wrap', 'justifyContent': 'center'}, children=[
                    html.Div([
                        html.Label("Борт (ICAO):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(id='icao-dropdown', options=[{'label': self.get_display_id(i), 'value': i} for i in self.icao_list], value=self.icao_list[0] if self.icao_list else None, style={'width': '300px'})
                    ]),
                    html.Div([
                        html.Label("Режим экрана:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(id='mode-dropdown', options=[
                            {'label': 'Схема трека (2D Карта)', 'value': 'track'},
                            {'label': 'Трек борта с качеством NIC', 'value': 'nic_track'},
                            {'label': 'Кинематика (Высота, Скорость, Курс)', 'value': 'kinematics'},
                            {'label': 'Категории целостности (NIC/SIL, NAC)', 'value': 'integrity_and_accuracy'},
                            {'label': 'Физические метрики (HIL, FOM)', 'value': 'quality_metrics'},
                            {'label': 'Барометрический анализ', 'value': 'baro_analysis'},
                            {'label': 'Качество данных в % (HIL/HFOM/VFOM)', 'value': 'quality_percentages'}
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
                        html.H3("Сводная информация по всем бортам", style={'textAlign': 'center'}), html.Div(id='table-container')
                    ]),
                    html.Div(style={'flex': '1', 'backgroundColor': '#ffffff', 'borderRadius': '10px', 'padding': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
                        html.H3("Журнал безопасности (Обнаруженные аномалии)", style={'textAlign': 'center', 'color': '#c0392b'}), html.Div(id='anomaly-table-content')
                    ])
                ])
            ]
        )

    # --- Функции для цветового кодирования NIC ---
    def _get_color_from_nic(self, nic):
        if nic is None: return 'lightgray'
        if nic >= 10: return 'green'
        elif nic >= 7: return 'orange'
        else: return 'red'

    def _get_closest_nic(self, timestamp, nic_list):
        if not nic_list: return None
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
        if best is None: return nic_list[0][1] if nic_list else None
        next_idx = best[0] + 1
        if next_idx < len(nic_list) and abs(nic_list[next_idx][0] - timestamp) < abs(best[0] - timestamp):
            return nic_list[next_idx][1]
        return best[1]

    # ------------------------- Callbacks -------------------------
    def setup_callbacks(self):
        @self.app.callback(
            [Output('main-graph', 'figure'),
             Output('table-container', 'children'),
             Output('anomaly-table-content', 'children'),
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
            anomaly_log = "Аномалий не обнаружено"
            if icao and icao in self.anomalies_dict:
                grouped_anomalies = self._group_anomalies(self.anomalies_dict[icao])
                if grouped_anomalies:
                    rows = []
                    for anom in grouped_anomalies:
                        rows.append(html.Tr([
                            html.Td(format_timestamp_with_nanoseconds(anom['start']) + " — " + format_timestamp_with_nanoseconds(anom['end']) if anom['start'] != anom['end'] else format_timestamp_with_nanoseconds(anom['start'])),
                            html.Td(anom['type'], style={'color': '#c0392b' if anom['type'] == 'SPOOFING' else '#e67e22'}),
                            html.Td(anom['desc'])
                        ]))
                    anomaly_log = html.Table([html.Thead(html.Tr([html.Th("Период (UTC)"), html.Th("Тип"), html.Th("Описание")])), html.Tbody(rows)], style={'width': '100%', 'borderCollapse': 'collapse'})
            
            if not icao:
                return go.Figure(), full_table, anomaly_log, tables_style, mapbox_style
            
            display_id = self.get_display_id(icao)
            
            # ---------- НИК-ТРЕК (цвет по NIC) ----------
            if mode == 'nic_track':
                pos_data = self.pos_dict.get(icao)
                if not pos_data or len(pos_data) < 2:
                    fig = go.Figure().add_annotation(text="Недостаточно данных координат", showarrow=False)
                    return fig, full_table, anomaly_log, tables_style, mapbox_style
                nic_data = self.nic_dict.get(icao, [])
                pos_sorted = sorted(pos_data, key=lambda x: x[0])
                use_mapbox = 'mapbox' in mapbox_toggle
                points = [(lat, lon, t, self._get_closest_nic(t, nic_data)) for t, lat, lon in pos_sorted]
                fig = go.Figure()
                if use_mapbox:
                    i = 0
                    while i < len(points) - 1:
                        j = i + 1
                        current_color = self._get_color_from_nic(points[i][3])
                        while j < len(points) and self._get_color_from_nic(points[j][3]) == current_color:
                            j += 1
                        lats, lons = [p[0] for p in points[i:j]], [p[1] for p in points[i:j]]
                        fig.add_trace(go.Scattermapbox(lat=lats, lon=lons, mode='lines', line=dict(width=3, color=current_color), showlegend=False, hoverinfo='none'))
                        i = j
                    for lat, lon, t, nic in points:
                        color = self._get_color_from_nic(nic)
                        hover = f"Время: {timestamp_to_utc(t).strftime('%H:%M:%S')}<br>NIC: {nic if nic is not None else 'нет данных'}"
                        fig.add_trace(go.Scattermapbox(lat=[lat], lon=[lon], mode='markers', marker=dict(size=6, color=color), text=hover, hoverinfo='text', showlegend=False))
                    center = (sum(p[0] for p in points)/len(points), sum(p[1] for p in points)/len(points))
                    fig.update_layout(title=f"Трек борта {display_id} с цветовой индикацией NIC", mapbox=dict(style="open-street-map", center=dict(lat=center[0], lon=center[1]), zoom=9), margin=dict(l=0, r=150, t=40, b=0), legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02))
                else:
                    i = 0
                    while i < len(points) - 1:
                        j = i + 1
                        current_color = self._get_color_from_nic(points[i][3])
                        while j < len(points) and self._get_color_from_nic(points[j][3]) == current_color:
                            j += 1
                        lons, lats = [p[1] for p in points[i:j]], [p[0] for p in points[i:j]]
                        fig.add_trace(go.Scatter(x=lons, y=lats, mode='lines', line=dict(width=3, color=current_color), showlegend=False))
                        i = j
                    for lat, lon, t, nic in points:
                        color = self._get_color_from_nic(nic)
                        hover = f"Время: {timestamp_to_utc(t).strftime('%H:%M:%S')}<br>NIC: {nic if nic is not None else 'нет данных'}"
                        fig.add_trace(go.Scatter(x=[lon], y=[lat], mode='markers', marker=dict(size=6, color=color), text=hover, hoverinfo='text', showlegend=False))
                    fig.update_layout(title=f"Трек борта {display_id} с цветовой индикацией NIC", xaxis_title="Долгота", yaxis_title="Широта", yaxis=dict(scaleanchor="x", scaleratio=1), template="plotly_white", hovermode='closest', margin=dict(r=150), legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02))
                for item in [go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='green'), name='NIC ≥ 10 (отлично)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='orange'), name='NIC 7–9 (средне)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='red'), name='NIC ≤ 6 (низкое)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='lightgray'), name='NIC нет данных')]:
                    fig.add_trace(item)
                return fig, full_table, anomaly_log, tables_style, mapbox_style
            
            # ---------- ОБЩАЯ КАРТА (без изменений) ----------
            if mode == 'track':
                if not self.pos_dict:
                    return go.Figure().add_annotation(text="Нет данных координат", showarrow=False), full_table, anomaly_log, tables_style, mapbox_style
                use_mapbox = 'mapbox' in mapbox_toggle
                if use_mapbox:
                    fig = go.Figure()
                    for track_icao, track_data in self.pos_dict.items():
                        if track_icao not in self.icao_list or track_icao == icao: continue
                        lats, lons = [lat for t, lat, lon in track_data], [lon for t, lat, lon in track_data]
                        fig.add_trace(go.Scattermapbox(lat=lats, lon=lons, mode='lines', line=dict(width=2, color='#a0a0a0'), opacity=0.8, hoverinfo='text', text=[f"Борт: {track_icao}"]*len(lons), showlegend=False))
                    curr_data = self.pos_dict.get(icao)
                    if curr_data:
                        lats, lons = [lat for t, lat, lon in curr_data], [lon for t, lat, lon in curr_data]
                        times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in curr_data]
                        fig.add_trace(go.Scattermapbox(lat=lats, lon=lons, mode='lines+markers', marker=dict(size=6, color='#d62728'), line=dict(width=3, color='#d62728'), text=times, name=display_id))
                    all_lats = [lat for tdata in self.pos_dict.values() for t, lat, lon in tdata]
                    all_lons = [lon for tdata in self.pos_dict.values() for t, lat, lon in tdata]
                    center_lat, center_lon = sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)
                    fig.update_layout(title="ОБЩАЯ КАРТА (Все обнаруженные треки) — реальная карта", mapbox=dict(style="open-street-map", center=dict(lat=center_lat, lon=center_lon), zoom=8), margin=dict(l=0, r=0, t=40, b=0), legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99), modebar=dict(orientation='v'))
                else:
                    fig = go.Figure()
                    for track_icao, track_data in self.pos_dict.items():
                        if track_icao not in self.icao_list or track_icao == icao: continue
                        lats, lons = [lat for t, lat, lon in track_data], [lon for t, lat, lon in track_data]
                        fig.add_trace(go.Scatter(x=lons, y=lats, mode='lines', line=dict(width=2, color='#a0a0a0'), opacity=0.8, hoverinfo='text', text=[f"Борт: {track_icao}"]*len(lons), showlegend=False))
                    curr_data = self.pos_dict.get(icao)
                    if curr_data:
                        lats, lons = [lat for t, lat, lon in curr_data], [lon for t, lat, lon in curr_data]
                        times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in curr_data]
                        fig.add_trace(go.Scatter(x=lons, y=lats, mode='lines+markers', marker=dict(size=5, color='#d62728'), line=dict(width=3, color='#d62728'), text=times, name=display_id))
                    fig.update_layout(title="ОБЩАЯ КАРТА (Все обнаруженные треки)", xaxis_title="Долгота", yaxis_title="Широта", yaxis=dict(scaleanchor="x", scaleratio=1), template="plotly_white", hovermode='closest')
                return fig, full_table, anomaly_log, tables_style, mapbox_style
            
            # ---------- ОСТАЛЬНЫЕ РЕЖИМЫ ----------
            fig = self._build_normal_figure(icao, mode, display_id)
            return fig, full_table, anomaly_log, tables_style, mapbox_style
    
    def _build_normal_figure(self, icao, mode, display_id):
        # (оставлен без изменений, как в предыдущей версии)
        if mode == 'kinematics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=("Высота (фт)", "Скорость (узлы)", "Курс (°)"))
            times, vals = self.get_times_values(self.alt_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Baro Alt', marker=dict(size=4, color='blue')), row=1, col=1)
            times, vals = self.get_times_values(self.gnss_alt_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='GNSS Alt', marker=dict(size=4, color='magenta')), row=1, col=1)
            times, vals = self.get_times_values(self.sel_alt_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='Selected Alt', line=dict(color='red', dash='dash', shape='vh')), row=1, col=1)
            times, vals = self.get_times_values(self.spd_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='GS', marker=dict(size=4, color='green')), row=2, col=1)
            times, vals = self.get_times_values(self.course_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Курс', marker=dict(size=4, color='purple')), row=3, col=1)
            fig.update_yaxes(range=[-10, 370], tickvals=[0,90,180,270,360], row=3, col=1)
            fig.update_layout(title=f"Кинематика полета: {display_id}", template="plotly_white", hovermode='x unified')
            return fig
        elif mode == 'integrity_and_accuracy':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=("NIC / SIL", "NACp / GVA", "NACv"))
            times, vals = self.get_times_values(self.nic_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='NIC (0-11)', line=dict(color='darkcyan', width=2, shape='vh'), fill='tozeroy', fillcolor='rgba(0,255,255,0.1)'), row=1, col=1)
            times, vals = self.get_times_values(self.sil_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='SIL (0-3)', line=dict(color='darkorange', dash='dash', shape='vh')), row=1, col=1)
            times, vals = self.get_times_values(self.nacp_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='NACp (0-11)', line=dict(color='green', width=2, shape='vh')), row=2, col=1)
            times, vals = self.get_times_values(self.gva_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='GVA (0-3)', line=dict(color='purple', dash='dash', shape='vh')), row=2, col=1)
            times, vals = self.get_times_values(self.nacv_dict.get(icao))
            if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='NACv (0-4)', line=dict(color='brown', width=2, shape='vh')), row=3, col=1)
            fig.update_yaxes(range=[0,12], tickvals=list(range(0,13,2)), row=1, col=1)
            fig.update_yaxes(range=[0,12], tickvals=list(range(0,13,2)), row=2, col=1)
            fig.update_yaxes(range=[0,4], tickvals=list(range(0,5)), row=3, col=1)
            fig.update_layout(title=f"Категории качества сигналов: {display_id}", template="plotly_white", hovermode='x unified')
            return fig
        elif mode == 'quality_metrics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, subplot_titles=("HIL (NIC)", "HFOM (NACp)", "VFOM (GVA)"))
            def add_metric(data_dict, mapping, zero_label, row, color):
                data = data_dict.get(icao)
                if not data: return
                times, vals, texts = [], [], []
                for t, val in sorted(data):
                    times.append(timestamp_to_utc(t))
                    if val == 0:
                        vals.append(None); texts.append(zero_label)
                    else:
                        v_m = mapping.get(val, 0)
                        vals.append(v_m); texts.append(f"{v_m} м")
                fig.add_trace(go.Scatter(x=times, y=vals, hovertext=texts, mode='lines+markers', name=color, line=dict(color=color)), row=row, col=1)
            add_metric(self.nic_dict, NIC_TO_HIL, "≥ 20 NM (37.04 км) или неизвестно", 1, 'red')
            add_metric(self.nacp_dict, NACP_TO_HFOM, "HFOM ≥ 18.52 км", 2, 'blue')
            add_metric(self.gva_dict, GVA_TO_VFOM, "Неизвестно или ≥10 м/с", 3, 'green')
            fig.update_layout(height=800, title_text=f"Параметры точности: {display_id}", template="plotly_white")
            return fig
        elif mode == 'baro_analysis':
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("Разница высот GNSS vs Baro (фт)", "Барокоррекция (гПа)"))
            times, vals = self.get_times_values(self.alt_diff_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Разница (фт)', marker=dict(size=4, color='red')), row=1, col=1)
                fig.add_hline(y=0, line_dash="dash", line_color="gray", row=1, col=1)
            times, vals = self.get_times_values(self.baro_correction_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Давление', marker=dict(size=4, color='brown')), row=2, col=1)
            fig.update_layout(title=f"Барометрический анализ: {display_id}", template="plotly_white", hovermode='x unified')
            return fig
        elif mode == 'quality_percentages':
            fig = go.Figure()
            if icao in self.nic_dict:
                times, vals = self.get_times_values(self.nic_dict[icao])
                percent_vals = [NIC_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers', name='HIL (%)', line=dict(color='red', width=2, shape='hv')))
            if icao in self.nacp_dict:
                times, vals = self.get_times_values(self.nacp_dict[icao])
                percent_vals = [NACP_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers', name='HFOM (%)', line=dict(color='blue', width=2, shape='hv')))
            if icao in self.gva_dict:
                times, vals = self.get_times_values(self.gva_dict[icao])
                percent_vals = [GVA_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers', name='VFOM (%)', line=dict(color='purple', width=2, dash='dash')))
            fig.update_layout(title=f"Качество данных в процентах: {display_id}", yaxis_title="Качество (%)", yaxis_range=[-5, 105], template="plotly_white", hovermode='x unified')
            fig.add_annotation(text="HIL: <7.5м → 37км<br>HFOM: <3м → >18.5км<br>VFOM: ≤45м → ≥150м", xref="paper", yref="paper", x=0.02, y=0.05, showarrow=False, font=dict(size=10), bgcolor="white", bordercolor="gray", borderwidth=1)
            return fig
        fig = go.Figure()
        fig.add_annotation(text=f"Режим {mode} не реализован", showarrow=False)
        return fig
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, State, dash_table
import numpy as np
import pandas as pd
from datetime import datetime, timezone

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

    def get_table_dataframe(self):
        rows = []
        for icao in self.icao_list:
            callsign = self.icao_callsigns.get(icao, "N/A")
            alt_data = self.alt_dict.get(icao, [[0, 0]])
            spd_data = self.spd_dict.get(icao, [[0, 0]])
            alt = alt_data[-1][1] if alt_data else 0
            spd = spd_data[-1][1] if spd_data else 0
            status_text = "аномалия" if icao in self.anomalies_dict else "норма"
            rows.append({
                "ICAO": icao,
                "Позывной": callsign,
                "Высота (фт)": int(alt),
                "Скорость (уз)": int(spd),
                "Статус": status_text
            })
        return pd.DataFrame(rows)

    def _get_anomaly_time_ranges(self, icao):
        """возвращает список кортежей (start_ts, end_ts) для аномалий данного борта"""
        if icao not in self.anomalies_dict:
            return []
        return [(anom['start'], anom['end']) for anom in self.anomalies_dict[icao]]

    def _group_anomalies(self, anomalies):
        """объединяет пересекающиеся/близкие аномалии (для совместимости)"""
        if not anomalies:
            return []
        sorted_anom = sorted(anomalies, key=lambda x: x['start'])
        grouped = []
        cur = sorted_anom[0].copy()
        for anom in sorted_anom[1:]:
            if anom['start'] - cur['end'] <= 10.0:
                cur['end'] = max(cur['end'], anom['end'])
                cur['desc_list'] = cur.get('desc_list', [cur['desc']]) + [anom['desc']]
            else:
                grouped.append(cur)
                cur = anom.copy()
        grouped.append(cur)
        result = []
        for g in grouped:
            desc = g['desc']
            if g['type'] == 'SPOOFING':
                avg_diff = sum(g.get('values', [])) / len(g.get('values', [1])) if g.get('values') else 0
                desc = f"аномальная разница высот: с {self._format_sec(g['start'])} по {self._format_sec(g['end'])} (средняя разница {avg_diff:.0f} фт)"
            result.append({
                'type': g['type'],
                'desc': desc,
                'start': g['start'],
                'end': g['end']
            })
        return result

    @staticmethod
    def _format_sec(ts):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime('%Y-%m-%d %H:%M:%S')

    def _get_anomaly_description(self, icao):
        """возвращает человекочитаемое описание статуса аномалии для бейджа"""
        if icao not in self.anomalies_dict:
            return "ГНСС стабильна", "normal"
        grouped = self._group_anomalies(self.anomalies_dict[icao])
        if not grouped:
            return "ГНСС стабильна", "normal"
        types = set()
        for g in grouped:
            types.add(g['type'])
        if 'SPOOFING' in types and len(types) > 1:
            return "ВНИМАНИЕ: Обнаружена подмена координат и другие аномалии", "critical"
        if 'SPOOFING' in types:
            return "ВНИМАНИЕ: Обнаружена подмена координат", "critical"
        if 'JAMMING' in types:
            return "ВНИМАНИЕ: Обнаружено подавление сигнала", "critical"
        if 'MULTIFACTOR' in types:
            return "ВНИМАНИЕ: Комплексная аномалия навигации", "critical"
        return "Обнаружена аномалия", "critical"

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
                html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px', 'flexWrap': 'wrap', 'justifyContent': 'center', 'alignItems': 'flex-end'}, children=[
                    html.Div([
                        html.Label("Борт (ICAO):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(id='icao-dropdown', options=[{'label': self.get_display_id(i), 'value': i} for i in self.icao_list], value=self.icao_list[0] if self.icao_list else None, style={'width': '300px'})
                    ]),
                    html.Div([
                        html.Label("Статус:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        html.Div(id='status-badge', style={'padding': '8px 16px', 'borderRadius': '20px', 'fontWeight': 'bold', 'fontSize': '16px', 'backgroundColor': '#28a745', 'color': 'white', 'display': 'inline-block'})
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
                    html.Div(id='mapbox-toggle-container', style={'marginBottom': '0'}, children=[
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
                        html.Button("Скачать таблицу (XLSX)", id="export-btn", n_clicks=0, style={'marginBottom': '10px'}),
                        dcc.Download(id="download-xlsx"),
                        html.Div(id='table-container')
                    ]),
                    html.Div(style={'flex': '1', 'backgroundColor': '#ffffff', 'borderRadius': '10px', 'padding': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
                        html.H3("Журнал безопасности (обнаруженные аномалии)", style={'textAlign': 'center', 'color': '#c0392b'}),
                        dash_table.DataTable(
                            id='anomaly-table',
                            columns=[
                                {'name': 'Период (UTC)', 'id': 'period'},
                                {'name': 'Тип', 'id': 'type'},
                                {'name': 'Описание', 'id': 'description'}
                            ],
                            data=[],
                            # toggle_columns=False,  # удалено — этот параметр не поддерживается в вашей версии
                            style_cell={'textAlign': 'left', 'padding': '8px'},
                            style_header={'backgroundColor': '#f1f1f1', 'fontWeight': 'bold'},
                            row_selectable=False,
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
        # Callback для обновления статус-бейджа
        @self.app.callback(
            Output('status-badge', 'children'),
            Output('status-badge', 'style'),
            Input('icao-dropdown', 'value')
        )
        def update_status_badge(icao):
            if not icao:
                return "ГНСС стабильна", {'padding': '8px 16px', 'borderRadius': '20px', 'fontWeight': 'bold', 'fontSize': '16px', 'backgroundColor': '#28a745', 'color': 'white', 'display': 'inline-block'}
            text, status = self._get_anomaly_description(icao)
            if status == 'critical':
                style = {'padding': '8px 16px', 'borderRadius': '20px', 'fontWeight': 'bold', 'fontSize': '16px', 'backgroundColor': '#dc3545', 'color': 'white', 'display': 'inline-block'}
            else:
                style = {'padding': '8px 16px', 'borderRadius': '20px', 'fontWeight': 'bold', 'fontSize': '16px', 'backgroundColor': '#28a745', 'color': 'white', 'display': 'inline-block'}
            return text, style

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
                type_map = {
                    'MULTIFACTOR': 'Мультифакторная',
                    'SPOOFING': 'Спуфинг',
                    'JAMMING': 'Подавление сигнала'
                }
                for anom in self.anomalies_dict[icao]:
                    start_ts = anom['start']
                    end_ts = anom['end']
                    start_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    end_str = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                    period = f"{start_str} – {end_str}" if end_ts > start_ts else start_str
                    anom_type = type_map.get(anom['type'], anom['type'])
                    anomaly_rows.append({
                        'period': period,
                        'type': anom_type,
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
                        title=dict(text="ТРЕК БОРТА С ЦВЕТОВОЙ ИНДИКАЦИЕЙ NIC", x=0.5, xanchor='center'),
                        mapbox=dict(style="open-street-map", center=dict(lat=center[0], lon=center[1]), zoom=9),
                        margin=dict(l=0, r=150, t=40, b=0),
                        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
                    )
                else:
                    fig.update_layout(
                        title=dict(text="ТРЕК БОРТА С ЦВЕТОВОЙ ИНДИКАЦИЕЙ NIC", x=0.5, xanchor='center'),
                        xaxis_title="долгота", yaxis_title="широта",
                        yaxis=dict(scaleanchor="x", scaleratio=1),
                        template="plotly_white", hovermode='closest', margin=dict(r=150),
                        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02)
                    )
                # легенда
                for item in [go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='green'), name='NIC ≥ 10 (отлично)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='orange'), name='NIC 7–9 (средне)'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='red'), name='NIC ≤ 6 ИЛИ АНОМАЛИЯ'),
                             go.Scatter(x=[None], y=[None], mode='markers', marker=dict(size=10, color='lightgray'), name='NIC нет данных')]:
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
                            line_color = 'red' if is_anomaly else '#1f77b4'
                            name = display_id if not is_anomaly else f"{display_id} (АНОМАЛИЯ)"
                            fig.add_trace(go.Scattermapbox(
                                lat=lats, lon=lons, mode='lines+markers',
                                marker=dict(size=6, color=line_color),
                                line=dict(width=3, color=line_color),
                                text=times, name=name
                            ))
                            i = j
                    # добавляем поясняющий элемент в легенду
                    fig.add_trace(go.Scattermapbox(
                        lat=[None], lon=[None], mode='lines',
                        line=dict(width=3, color='red'), name='Аномальный сегмент'
                    ))
                    all_lats = [lat for tdata in self.pos_dict.values() for t, lat, lon in tdata]
                    all_lons = [lon for tdata in self.pos_dict.values() for t, lat, lon in tdata]
                    center_lat, center_lon = sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)
                    fig.update_layout(
                        title=dict(text="ОБЩАЯ КАРТА (ВСЕ ОБНАРУЖЕННЫЕ ТРЕКИ)", x=0.5, xanchor='center'),
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
                            line_color = 'red' if is_anomaly else '#1f77b4'
                            name = display_id if not is_anomaly else f"{display_id} (АНОМАЛИЯ)"
                            fig.add_trace(go.Scatter(
                                x=lons, y=lats, mode='lines+markers', marker=dict(size=5, color=line_color),
                                line=dict(width=3, color=line_color), text=times, name=name
                            ))
                            i = j
                    fig.add_trace(go.Scatter(
                        x=[None], y=[None], mode='lines',
                        line=dict(width=3, color='red'), name='Аномальный сегмент'
                    ))
                    fig.update_layout(
                        title=dict(text="ОБЩАЯ КАРТА (ВСЕ ОБНАРУЖЕННЫЕ ТРЕКИ)", x=0.5, xanchor='center'),
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

        # callback для экспорта в Excel
        @self.app.callback(
            Output("download-xlsx", "data"),
            Input("export-btn", "n_clicks"),
            prevent_initial_call=True
        )
        def export_to_excel(n_clicks):
            try:
                df = self.get_table_dataframe()
                if df.empty:
                    # Если данных нет, создаём файл с пояснением
                    df = pd.DataFrame({"Сообщение": ["Нет данных для экспорта"]})
                return dcc.send_data_frame(
                    df.to_excel,
                    "aircraft_data.xlsx",
                    sheet_name="Сводка",
                    index=False,
                    engine='openpyxl'   # явно указываем движок
                )
            except Exception as e:
                print(f"Ошибка экспорта Excel: {e}")
                # Чтобы не оставлять пользователя без реакции, можно вернуть пустой дамп
                # Но в данном случае лучше выбросить исключение, чтобы увидеть в консоли
                raise

    def _build_normal_figure(self, icao, mode, display_id):
        # режим кинематики
        if mode == 'kinematics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=("ВЫСОТА (ФТ)", "СКОРОСТЬ (УЗЛЫ)", "КУРС (°)"))
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
            fig.update_layout(title=dict(text=f"КИНЕМАТИКА ПОЛЁТА: {display_id}", x=0.5, xanchor='center'), template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # категории целостности и точности
        if mode == 'integrity_and_accuracy':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=("NIC / SIL", "NACP / GVA", "NACV"))
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
            fig.update_layout(title=dict(text=f"КАТЕГОРИИ КАЧЕСТВА СИГНАЛОВ: {display_id}", x=0.5, xanchor='center'), template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # метрики в метрах (hil, hfom, vfom)
        if mode == 'quality_metrics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, subplot_titles=("HIL (NIC)", "HFOM (NACP)", "VFOM (GVA)"))
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
            add_metric(self.nacp_dict, NACP_TO_HFOM, "HFOM ≥ 18.52 км", 2, 'blue')
            add_metric(self.gva_dict, GVA_TO_VFOM, "неизвестно или ≥10 м/с", 3, 'green')
            fig.update_layout(height=800, title=dict(text=f"ПАРАМЕТРЫ ТОЧНОСТИ: {display_id}", x=0.5, xanchor='center'), template="plotly_white")
            self._add_anomaly_vrects(fig, icao)
            return fig

        # барометрический анализ
        if mode == 'baro_analysis':
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, subplot_titles=("РАЗНИЦА ВЫСОТ GNSS VS BARO (ФТ)", "БАРОКОРРЕКЦИЯ (ГПА)"))
            times, vals = self.get_times_values(self.alt_diff_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='разница (фт)', marker=dict(size=4, color='red')), row=1, col=1)
                # Добавляем пороговые линии для выявления спуфинга высоты
                fig.add_hline(y=500, line_dash="dash", line_color="orange", opacity=0.8, row=1, col=1,
                              annotation_text="Порог +500 фт", annotation_position="bottom right")
                fig.add_hline(y=-500, line_dash="dash", line_color="orange", opacity=0.8, row=1, col=1,
                              annotation_text="Порог -500 фт", annotation_position="top right")
                fig.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5, row=1, col=1)
                # Добавляем поясняющую аннотацию о спуфинге высоты
                fig.add_annotation(
                    text="Выход за пределы ±500 фт при стабильной барокоррекции – признак спуфинга высоты",
                    xref="paper", yref="paper", x=0.02, y=0.95, showarrow=False,
                    font=dict(size=10, color="darkred"), bgcolor="rgba(255,200,200,0.8)", bordercolor="red", borderwidth=1
                )
            times, vals = self.get_times_values(self.baro_correction_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='давление', marker=dict(size=4, color='brown')), row=2, col=1)
            fig.update_layout(title=dict(text=f"БАРОМЕТРИЧЕСКИЙ АНАЛИЗ (ВЫЯВЛЕНИЕ СПУФИНГА ВЫСОТЫ): {display_id}", x=0.5, xanchor='center'), template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # проценты качества
        if mode == 'quality_percentages':
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
            fig.update_layout(title=dict(text=f"КАЧЕСТВО ДАННЫХ В ПРОЦЕНТАХ: {display_id}", x=0.5, xanchor='center'), yaxis_title="качество (%)", yaxis_range=[-5, 105], template="plotly_white", hovermode='x unified')
            fig.add_annotation(text="HIL: <7.5м → 37км\nHFOM: <3м → >18.5км\nVFOM: ≤45м → ≥150м", xref="paper", yref="paper", x=0.02, y=0.05, showarrow=False, font=dict(size=10), bgcolor="white", bordercolor="gray", borderwidth=1)
            self._add_anomaly_vrects(fig, icao)
            return fig

        # спуфинг-анализ, сравнение скоростей
        if mode == 'spoofing_kinematics':
            fig = go.Figure()
            times, gs_vals = self.get_times_values(self.spd_dict.get(icao))
            if times:
                fig.add_trace(go.Scatter(x=times, y=gs_vals, mode='lines+markers', name='заявленная GS (узлы)', line=dict(color='green', width=2), marker=dict(size=4)))
            pos_data = self.pos_dict.get(icao)
            if pos_data and len(pos_data) >= 2:
                calc_speeds = self._compute_ground_speed_from_positions(pos_data)
                if calc_speeds:
                    calc_times, calc_vals = zip(*calc_speeds)
                    calc_times_utc = [timestamp_to_utc(t) for t in calc_times]
                    fig.add_trace(go.Scatter(x=calc_times_utc, y=calc_vals, mode='lines+markers', name='скорость по координатам (узлы)', line=dict(color='red', width=2, dash='dash'), marker=dict(size=4)))
            fig.update_layout(title=dict(text=f"СРАВНЕНИЕ СКОРОСТЕЙ (СПУФИНГ-АНАЛИЗ): {display_id}", x=0.5, xanchor='center'), xaxis_title="время (UTC)", yaxis_title="скорость (узлы)", template="plotly_white", hovermode='x unified')
            self._add_anomaly_vrects(fig, icao)
            return fig

        # джамминг-анализ: активность пакетов df
        if mode == 'jamming_activity':
            messages = self.messages_dict.get(icao, [])
            if not messages:
                fig = go.Figure().add_annotation(text="нет данных о сообщениях DF", showarrow=False)
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
                    name=f'DF{df}',
                    marker=dict(size=8, opacity=0.7),
                    text=[f'DF{df}<br>{timestamp_to_utc(ts).strftime("%H:%M:%S.%f")[:-3]}' for ts in timestamps],
                    hoverinfo='text'
                ))
            fig.update_layout(
                title=dict(text=f"АКТИВНОСТЬ СООБЩЕНИЙ ПО ТИПАМ DF: {display_id}", x=0.5, xanchor='center'),
                xaxis_title="время (UTC)",
                yaxis_title="тип сообщения (DF)",
                yaxis=dict(tickmode='array', tickvals=df_order, ticktext=[f'DF{df}' for df in df_order]),
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
                title=dict(text=f"ИНТЕНСИВНОСТЬ СООБЩЕНИЙ (MESSAGE RATE): {display_id}", x=0.5, xanchor='center'),
                xaxis_title="время (UTC)",
                yaxis_title="сообщений в секунду",
                template="plotly_white",
                hovermode='x unified'
            )
            fig.add_annotation(
                text="Резкое падение красной линии (DF17/18) при сохранении синей – признак подавления GNSS (JAMMING)",
                xref="paper", yref="paper", x=0.02, y=0.95, showarrow=False,
                font=dict(size=11, color="gray"), bgcolor="white", bordercolor="lightgray", borderwidth=1
            )
            self._add_anomaly_vrects(fig, icao)
            return fig

        # если режим не распознан
        fig = go.Figure()
        fig.add_annotation(text=f"режим {mode} не реализован", showarrow=False)
        return fig
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

        # Dash приложение
        self.app = dash.Dash(__name__, title='Авиационный Дашборд')
        self.setup_layout()
        self.setup_callbacks()
        
        print("\nЗапуск веб-интерфейса. Откройте в браузере: http://127.0.0.1:8050")
        self.app.run(debug=False, use_reloader=False)

    # -----------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------
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

    # -----------------------------------------------------------------
    # Layout Dash
    # -----------------------------------------------------------------
    def setup_layout(self):
        self.app.layout = html.Div(
            style={'font-family': 'sans-serif', 'padding': '20px', 'backgroundColor': '#f4f6f8', 'minHeight': '100vh'},
            children=[
                html.H2("Авиационный Навигационный Дашборд", style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '30px'}),
                
                # Панель выбора
                html.Div(style={'display': 'flex', 'gap': '20px', 'marginBottom': '20px', 'justifyContent': 'center'}, children=[
                    html.Div([
                        html.Label("Борт (ICAO):", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(
                            id='icao-dropdown',
                            options=[{'label': self.get_display_id(i), 'value': i} for i in self.icao_list],
                            value=self.icao_list[0] if self.icao_list else None,
                            style={'width': '400px'}
                        )
                    ]),
                    html.Div([
                        html.Label("Режим экрана:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
                        dcc.Dropdown(
                            id='mode-dropdown',
                            options=[
                                {'label': 'Схема трека (2D Карта)', 'value': 'track'},
                                {'label': 'Анимация полета (Плеер)', 'value': 'animation'},
                                {'label': 'Кинематика (Высота, Скорость, Курс)', 'value': 'kinematics'},
                                {'label': 'Категории целостности (NIC/SIL, NAC)', 'value': 'integrity_and_accuracy'},
                                {'label': 'Физические метрики (HIL, FOM)', 'value': 'quality_metrics'},
                                {'label': 'Барометрический анализ', 'value': 'baro_analysis'},
                                {'label': 'Качество данных в % (HIL/HFOM/VFOM)', 'value': 'quality_percentages'}
                            ],
                            value='track',
                            style={'width': '400px'}
                        )
                    ]),
                ]),
                
                # График
                html.Div(style={
                    'backgroundColor': '#ffffff',               
                    'padding': '15px',                          
                    'borderRadius': '10px',                     
                    'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.1)' 
                }, children=[
                    dcc.Graph(id='main-graph', style={'height': '60vh'})
                ]),
                
                # Две таблицы под графиком
                html.Div(style={'display': 'flex', 'gap': '20px', 'marginTop': '20px'}, children=[
                    html.Div(style={'flex': '1', 'backgroundColor': '#ffffff', 'borderRadius': '10px', 'padding': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
                        html.H3("Сводная информация по всем бортам", style={'textAlign': 'center'}),
                        html.Div(id='table-container')
                    ]),
                    html.Div(style={'flex': '1', 'backgroundColor': '#ffffff', 'borderRadius': '10px', 'padding': '15px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
                        html.H3("Журнал безопасности (Обнаруженные аномалии)", style={'textAlign': 'center', 'color': '#c0392b'}),
                        html.Div(id='anomaly-table-content')
                    ])
                ])
            ]
        )

    # -----------------------------------------------------------------
    # Callback Dash
    # -----------------------------------------------------------------
    def setup_callbacks(self):
        @self.app.callback(
            [Output('main-graph', 'figure'),
             Output('table-container', 'children'),
             Output('anomaly-table-content', 'children')],
            [Input('icao-dropdown', 'value'),
             Input('mode-dropdown', 'value')]
        )
        def update_graph(icao, mode):
            # Таблицы
            full_table = self.generate_styled_table()
            anomaly_log = "Аномалий не обнаружено"
            if icao and icao in self.anomalies_dict:
                anomalies = self.anomalies_dict[icao]
                rows = [html.Tr([
                    html.Td(format_timestamp_with_nanoseconds(a['time'])),
                    html.Td(a['type'], style={'color': '#c0392b' if a['type'] == 'SPOOFING' else '#e67e22'}),
                    html.Td(a['desc'])
                ]) for a in anomalies]
                anomaly_log = html.Table([
                    html.Thead(html.Tr([html.Th("Время (UTC)"), html.Th("Тип"), html.Th("Описание")])),
                    html.Tbody(rows)
                ], style={'width': '100%', 'borderCollapse': 'collapse'})
            
            if not icao:
                return go.Figure(), full_table, anomaly_log
            
            display_id = self.get_display_id(icao)
            
            # ---- Режим анимации (с использованием встроенных средств Plotly) ----
            if mode == 'animation':
                pos_data = self.pos_dict.get(icao)
                nic_data = self.nic_dict.get(icao)
                if not pos_data or len(pos_data) < 2:
                    fig = go.Figure().add_annotation(text="Недостаточно данных для анимации", showarrow=False)
                    return fig, full_table, anomaly_log
                
                pos_sorted = sorted(pos_data, key=lambda x: x[0])
                # Ограничиваем количество кадров для производительности (не более 300)
                step = max(1, len(pos_sorted) // 200)
                pos_sorted = pos_sorted[::step]
                lats = [lat for t, lat, lon in pos_sorted]
                lons = [lon for t, lat, lon in pos_sorted]
                times = [timestamp_to_utc(t) for t, lat, lon in pos_sorted]
                time_strs = [t.strftime('%H:%M:%S') for t in times]
                
                # Синхронизация NIC
                if nic_data:
                    nic_sorted = sorted(nic_data, key=lambda x: x[0])
                    synced_nics = []
                    for t_pos, _, _ in pos_sorted:
                        closest = min(nic_sorted, key=lambda x: abs(x[0] - t_pos))[1]
                        synced_nics.append(closest)
                else:
                    synced_nics = [0] * len(lats)
                
                # Построение фигуры с кадрами
                fig = make_subplots(rows=2, cols=1, row_heights=[0.7, 0.3],
                                    specs=[[{"type": "mapbox"}], [{"type": "xy"}]],
                                    vertical_spacing=0.1)
                
                # Базовые трейсы (пустые, будут заполняться кадрами)
                # Весь путь (серый фон)
                fig.add_trace(go.Scattermapbox(lat=lats, lon=lons, mode='lines',
                                               line=dict(width=2, color='gray'), opacity=0.3,
                                               name='Весь путь'), row=1, col=1)
                # Пройденный путь (будет меняться в кадрах)
                fig.add_trace(go.Scattermapbox(lat=[lats[0]], lon=[lons[0]], mode='lines',
                                               line=dict(width=4, color='blue'), name='Пройдено'), row=1, col=1)
                # Текущая позиция
                fig.add_trace(go.Scattermapbox(lat=[lats[0]], lon=[lons[0]], mode='markers',
                                               marker=dict(size=12, color='red'), name='Текущая позиция'), row=1, col=1)
                # График NIC (весь)
                fig.add_trace(go.Scatter(x=times, y=synced_nics, mode='lines',
                                         line=dict(color='orange', shape='vh'), name='Уровень NIC'), row=2, col=1)
                # Маркер текущего NIC
                fig.add_trace(go.Scatter(x=[times[0]], y=[synced_nics[0]], mode='markers',
                                         marker=dict(size=10, color='red'), name='Текущий NIC', showlegend=False), row=2, col=1)
                
                # Создание кадров
                frames = []
                for i in range(len(lats)):
                    frame = go.Frame(
                        data=[
                            # Обновляем пройденный путь (индекс 1)
                            go.Scattermapbox(lat=lats[:i+1], lon=lons[:i+1]),
                            # Обновляем позицию (индекс 2)
                            go.Scattermapbox(lat=[lats[i]], lon=[lons[i]]),
                            # Обновляем маркер NIC (индекс 4)
                            go.Scatter(x=[times[i]], y=[synced_nics[i]])
                        ],
                        name=str(i),
                        traces=[1, 2, 4]  # какие трейсы заменять
                    )
                    frames.append(frame)
                fig.frames = frames
                
                # Настройки анимации
                fig.update_layout(
                    title=f"Анимация полета: {display_id}",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    mapbox=dict(style="open-street-map",
                                center=dict(lat=sum(lats)/len(lats), lon=sum(lons)/len(lons)),
                                zoom=9),
                    updatemenus=[dict(
                        type="buttons",
                        showactive=False,
                        buttons=[
                            dict(label="Play",
                                 method="animate",
                                 args=[None, dict(frame=dict(duration=50, redraw=True), fromcurrent=True)]),
                            dict(label="Pause",
                                 method="animate",
                                 args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")])
                        ],
                        pad={"r": 10, "t": 10},
                        x=0.01,
                        y=1.1,
                        xanchor="left",
                        yanchor="top"
                    )],
                    sliders=[{
                        "currentvalue": {"prefix": "Кадр: "},
                        "steps": [
                            {"args": [[str(i)], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}],
                             "label": str(i), "method": "animate"}
                            for i in range(len(lats))
                        ]
                    }]
                )
                fig.update_xaxes(range=[times[0], times[-1]], row=2, col=1)
                fig.update_yaxes(range=[-0.5, 12.5], title="NIC", row=2, col=1)
                
                return fig, full_table, anomaly_log
            
            # ---- Все остальные режимы (без анимации) ----
            return self._build_normal_figure(icao, mode, display_id), full_table, anomaly_log
    
    # -----------------------------------------------------------------
    # Построение графиков для всех режимов, кроме анимации
    # -----------------------------------------------------------------
    def _build_normal_figure(self, icao, mode, display_id):
        if mode == 'track':
            # Общая карта со всеми треками
            if not self.pos_dict:
                fig = go.Figure()
                fig.add_annotation(text="Нет данных координат", showarrow=False)
                return fig
            fig = go.Figure()
            # Фоновые треки (серые)
            for track_icao, track_data in self.pos_dict.items():
                if track_icao not in self.icao_list or track_icao == icao:
                    continue
                lats = [lat for t, lat, lon in track_data]
                lons = [lon for t, lat, lon in track_data]
                fig.add_trace(go.Scatter(x=lons, y=lats, mode='lines',
                                         line=dict(width=1, color='grey'), opacity=0.6,
                                         hoverinfo='text', text=[f"Борт: {track_icao}"]*len(lons),
                                         showlegend=False))
            # Текущий трек
            curr_data = self.pos_dict.get(icao)
            if curr_data:
                lats = [lat for t, lat, lon in curr_data]
                lons = [lon for t, lat, lon in curr_data]
                times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in curr_data]
                fig.add_trace(go.Scatter(x=lons, y=lats, mode='lines+markers',
                                         marker=dict(size=4, color='red'), line=dict(width=2, color='red'),
                                         text=times, name=display_id))
            fig.update_layout(title="ОБЩАЯ КАРТА (Все обнаруженные треки)",
                              xaxis_title="Долгота", yaxis_title="Широта",
                              yaxis=dict(scaleanchor="x", scaleratio=1),
                              template="plotly_white", hovermode='closest',
                              legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99,
                                          bgcolor="rgba(255,255,255,0.8)", bordercolor="lightgray"))
            return fig
        
        elif mode == 'kinematics':
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                subplot_titles=("Высота (фт)", "Скорость (узлы)", "Курс (°)"))
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
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                subplot_titles=("NIC / SIL", "NACp / GVA", "NACv"))
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
            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                                subplot_titles=("HIL (NIC)", "HFOM (NACp)", "VFOM (GVA)"))
            def add_metric(data_dict, mapping, zero_label, row, color):
                data = data_dict.get(icao)
                if not data: return
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
            add_metric(self.nic_dict, NIC_TO_HIL, "≥ 20 NM (37.04 км) или неизвестно", 1, 'red')
            add_metric(self.nacp_dict, NACP_TO_HFOM, "HFOM ≥ 18.52 км", 2, 'blue')
            add_metric(self.gva_dict, GVA_TO_VFOM, "Неизвестно или ≥10 м/с", 3, 'green')
            fig.update_layout(height=800, title_text=f"Параметры точности: {display_id}", template="plotly_white")
            return fig
        
        elif mode == 'baro_analysis':
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                                subplot_titles=("Разница высот GNSS vs Baro (фт)", "Барокоррекция (гПа)"))
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
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers',
                                         name='HIL (%)', line=dict(color='red', width=2, shape='hv')))
            if icao in self.nacp_dict:
                times, vals = self.get_times_values(self.nacp_dict[icao])
                percent_vals = [NACP_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers',
                                         name='HFOM (%)', line=dict(color='blue', width=2, shape='hv')))
            if icao in self.gva_dict:
                times, vals = self.get_times_values(self.gva_dict[icao])
                percent_vals = [GVA_TO_PERCENT.get(v, 0) for v in vals]
                fig.add_trace(go.Scatter(x=times, y=percent_vals, mode='lines+markers',
                                         name='VFOM (%)', line=dict(color='purple', width=2, dash='dash')))
            fig.update_layout(title=f"Качество данных в процентах: {display_id}",
                              yaxis_title="Качество (%)", yaxis_range=[-5, 105],
                              template="plotly_white", hovermode='x unified')
            fig.add_annotation(
                text="HIL: <7.5м → 37км<br>HFOM: <3м → >18.5км<br>VFOM: ≤45м → ≥150м",
                xref="paper", yref="paper", x=0.02, y=0.05, showarrow=False,
                font=dict(size=10), bgcolor="white", bordercolor="gray", borderwidth=1
            )
            return fig
        
        # Fallback
        fig = go.Figure()
        fig.add_annotation(text=f"Режим {mode} не реализован", showarrow=False)
        return fig
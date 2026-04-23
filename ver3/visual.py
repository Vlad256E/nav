import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output
import numpy as np
from utils import timestamp_to_utc

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
                 icao_nic, icao_nacp, icao_gva, icao_sil, icao_nacv):
        
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
        
        # Настройка Dash приложения
        self.app = dash.Dash(__name__, title='Авиационный Дашборд')
        self.setup_layout()
        self.setup_callbacks()
        
        print("\nЗапуск веб-интерфейса. Откройте в браузере: http://127.0.0.1:8050")
        # Выключаем debug, чтобы не было конфликтов с основным потоком скрипта
        self.app.run(debug=False, use_reloader=False)

    def get_display_id(self, icao):
        callsign = self.icao_callsigns.get(icao, "N/A")
        squawk = self.icao_callsigns.get(f"{icao}_sq", "")
        if squawk: callsign += f" (SQ:{squawk})"
        modes_key = f"{icao}_modes"
        active_modes = self.icao_callsigns.get(modes_key, set())
        mode_str = f" ({', '.join(sorted(active_modes))})" if active_modes else ""
        return f"{callsign} ({icao}){mode_str}" if callsign != "N/A" else f"{icao}{mode_str}"

    def get_times_values(self, data):
        if not data: return [], []
        sorted_data = sorted(data)
        return [timestamp_to_utc(t) for t, v in sorted_data], [v for t, v in sorted_data]

    def setup_layout(self):
        self.app.layout = html.Div(
            style={'font-family': 'sans-serif', 'padding': '20px', 'backgroundColor': '#f4f6f8', 'minHeight': '100vh'}, 
            children=[
                html.H2("Авиационный Навигационный Дашборд", style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '30px'}),
                
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
                                {'label': 'Анимация полета (Плеер)', 'value': 'animation'}, # <--- НОВЫЙ РЕЖИМ
                                {'label': 'Кинематика (Высота, Скорость, Курс)', 'value': 'kinematics'},
                                {'label': 'Категории целостности (NIC/SIL, NAC)', 'value': 'integrity_and_accuracy'},
                                {'label': 'Физические метрики (HIL, FOM)', 'value': 'quality_metrics'},
                                {'label': 'Барометрический анализ', 'value': 'baro_analysis'}
                            ],
                            value='track',
                            style={'width': '400px'}
                        )
                    ])
                ]),
                
                html.Div(style={
                    'backgroundColor': '#ffffff',               
                    'padding': '15px',                          
                    'borderRadius': '10px',                     
                    'boxShadow': '0 4px 8px rgba(0, 0, 0, 0.1)' 
                }, children=[
                    dcc.Graph(id='main-graph', style={'height': '72vh'})
                ])
        ])

    def setup_callbacks(self):
        @self.app.callback(
            Output('main-graph', 'figure'),
            [Input('icao-dropdown', 'value'),
             Input('mode-dropdown', 'value')]
        )
        def update_graph(icao, mode):
            if not icao:
                return go.Figure().add_annotation(text="Нет данных", showarrow=False, font=dict(size=20))
            
            display_id = self.get_display_id(icao)

            # ---------------------------------------------------------
            # РЕЖИМ 1: ТРЕК И ОБЩАЯ КАРТА (2D)
            # ---------------------------------------------------------
            if mode == 'track':
                fig = go.Figure()
                
                # Фоновые треки (серые)
                for track_icao, track_data in self.pos_dict.items():
                    if track_icao not in self.icao_list or track_icao == icao: continue
                    lons = [lon for t, lat, lon in track_data]
                    lats = [lat for t, lat, lon in track_data]
                    fig.add_trace(go.Scatter(
                        x=lons, y=lats, mode='lines', 
                        line=dict(color='grey', width=1), opacity=0.4, 
                        hoverinfo='skip', showlegend=False
                    ))

                # Активный трек с раскраской
                data = self.pos_dict.get(icao)
                if data:
                    lons = [lon for t, lat, lon in data]
                    lats = [lat for t, lat, lon in data]
                    nic_data = self.nic_dict.get(icao, [])
                    nic_lookup = {t: v for t, v in nic_data}
                    colors = [nic_lookup.get(t, 0) for t, lat, lon in data]
                    
                    fig.add_trace(go.Scatter(
                        x=lons, y=lats, mode='lines+markers',
                        marker=dict(
                            color=colors, colorscale='RdYlGn', cmin=0, cmax=11,
                            size=6, showscale=True, 
                            colorbar=dict(title="NIC", thickness=15)
                        ),
                        line=dict(color='black', width=1),
                        name=display_id
                    ))
                
                fig.update_layout(
                    title=f"Схема трека: {display_id}",
                    xaxis_title="Долгота (°)",
                    yaxis_title="Широта (°)",
                    yaxis=dict(scaleanchor="x", scaleratio=1), # Сохранение пропорций карты
                    template="plotly_white"
                )
                return fig

            # ---------------------------------------------------------
            # РЕЖИМ 1.5: АНИМАЦИЯ ПОЛЕТА (ПЛЕЕР)
            # ---------------------------------------------------------
            elif mode == 'animation':
                fig = go.Figure()
                data = self.pos_dict.get(icao)
                
                if not data or len(data) < 2:
                    return go.Figure().add_annotation(text="Недостаточно данных координат для анимации", showarrow=False, font=dict(size=20))

                # Сортируем данные по времени
                data = sorted(data, key=lambda x: x[0])
                
                # Оптимизация: если точек слишком много (браузер начнет тормозить от тысяч кадров),
                # прореживаем их, чтобы максимум было около ~800 кадров
                step = max(1, len(data) // 800)
                data = data[::step]

                times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in data]
                lats = [lat for t, lat, lon in data]
                lons = [lon for t, lat, lon in data]

                # Trace 0: Полный серый маршрут (фон)
                fig.add_trace(go.Scatter(
                    x=lons, y=lats, mode='lines', 
                    line=dict(color='lightgrey', width=2), 
                    name='Весь маршрут', hoverinfo='skip'
                ))

                # Trace 1: Маркер текущей позиции самолета
                fig.add_trace(go.Scatter(
                    x=[lons[0]], y=[lats[0]], mode='markers',
                    marker=dict(color='red', size=12, symbol='circle', line=dict(color='darkred', width=2)),
                    name='Текущая позиция'
                ))

                # Trace 2: Пройденный путь (будет расти)
                fig.add_trace(go.Scatter(
                    x=[lons[0]], y=[lats[0]], mode='lines',
                    line=dict(color='blue', width=3),
                    name='Пройденный путь'
                ))

                # Генерируем кадры анимации и шаги для ползунка перемотки
                frames = []
                slider_steps = []
                
                for i in range(len(data)):
                    # Кадр содержит обновленные данные для маркера и пройденного пути
                    frames.append(go.Frame(
                        data=[
                            go.Scatter(x=[lons[i]], y=[lats[i]]),     # Обновляем Trace 1 (самолет)
                            go.Scatter(x=lons[:i+1], y=lats[:i+1])    # Обновляем Trace 2 (хвост)
                        ],
                        traces=[1, 2], # Указываем, какие слои обновлять
                        name=str(i)
                    ))
                    
                    slider_steps.append(dict(
                        args=[
                            [str(i)], 
                            dict(mode="immediate", frame=dict(duration=0, redraw=False), transition=dict(duration=0))
                        ],
                        label=times[i],
                        method="animate"
                    ))

                fig.frames = frames

                # Кнопки управления (Play, Fast, Pause)
                updatemenus = [dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(
                            label="▶ Норм",
                            method="animate",
                            args=[None, dict(frame=dict(duration=200, redraw=False), transition=dict(duration=0), fromcurrent=True, mode="immediate")]
                        ),
                        dict(
                            label="▶▶ Быстро",
                            method="animate",
                            args=[None, dict(frame=dict(duration=40, redraw=False), transition=dict(duration=0), fromcurrent=True, mode="immediate")]
                        ),
                        dict(
                            label="⏸ Пауза",
                            method="animate",
                            args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate", transition=dict(duration=0))]
                        )
                    ],
                    showactive=False,
                    x=0.05, y=1.1, xanchor="left", yanchor="top",
                    pad={"r": 10, "t": 10}
                )]

                # Ползунок (Таймлайн)
                sliders = [dict(
                    active=0,
                    yanchor="top",
                    xanchor="left",
                    currentvalue=dict(font=dict(size=14), prefix="UTC: ", visible=True, xanchor="right"),
                    transition=dict(duration=0, easing="linear"),
                    pad=dict(b=10, t=50),
                    len=0.9,
                    x=0.1, y=0,
                    steps=slider_steps
                )]

                fig.update_layout(
                    title=f"Анимация полета: {display_id}",
                    xaxis_title="Долгота (°)",
                    yaxis_title="Широта (°)",
                    yaxis=dict(scaleanchor="x", scaleratio=1), # Сохранение пропорций географической карты
                    template="plotly_white",
                    updatemenus=updatemenus,
                    sliders=sliders
                )
                return fig

            # ---------------------------------------------------------
            # РЕЖИМ 2: КИНЕМАТИКА
            # ---------------------------------------------------------
            elif mode == 'kinematics':
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                    subplot_titles=("Высота (фт)", "Скорость (узлы)", "Курс (°)"))
                
                # Высота
                times, vals = self.get_times_values(self.alt_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Baro Alt', marker=dict(size=4, color='blue')), row=1, col=1)
                
                times, vals = self.get_times_values(self.gnss_alt_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='GNSS Alt', marker=dict(size=4, color='magenta')), row=1, col=1)
                
                times, vals = self.get_times_values(self.sel_alt_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='Selected Alt', line=dict(color='red', dash='dash', shape='vh')), row=1, col=1)

                # Скорость
                times, vals = self.get_times_values(self.spd_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='GS', marker=dict(size=4, color='green')), row=2, col=1)

                # Курс
                times, vals = self.get_times_values(self.course_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines+markers', name='Курс', marker=dict(size=4, color='purple')), row=3, col=1)
                
                fig.update_yaxes(range=[-10, 370], tickvals=[0, 90, 180, 270, 360], row=3, col=1)
                fig.update_layout(title=f"Кинематика полета: {display_id}", template="plotly_white", hovermode='x unified')
                return fig

            # ---------------------------------------------------------
            # РЕЖИМ 3: ЦЕЛОСТНОСТЬ И ТОЧНОСТЬ
            # ---------------------------------------------------------
            elif mode == 'integrity_and_accuracy':
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                    subplot_titles=("NIC / SIL", "NACp / GVA", "NACv"))
                
                # NIC/SIL
                times, vals = self.get_times_values(self.nic_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='NIC (0-11)', line=dict(color='darkcyan', width=2, shape='vh'), fill='tozeroy', fillcolor='rgba(0, 255, 255, 0.1)'), row=1, col=1)
                times, vals = self.get_times_values(self.sil_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='SIL (0-3)', line=dict(color='darkorange', dash='dash', shape='vh')), row=1, col=1)
                
                # NACp/GVA
                times, vals = self.get_times_values(self.nacp_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='NACp (0-11)', line=dict(color='green', width=2, shape='vh')), row=2, col=1)
                times, vals = self.get_times_values(self.gva_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='GVA (0-3)', line=dict(color='purple', dash='dash', shape='vh')), row=2, col=1)

                # NACv
                times, vals = self.get_times_values(self.nacv_dict.get(icao))
                if times: fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='NACv (0-4)', line=dict(color='brown', width=2, shape='vh')), row=3, col=1)

                fig.update_yaxes(range=[0, 12], tickvals=list(range(0, 13, 2)), row=1, col=1)
                fig.update_yaxes(range=[0, 12], tickvals=list(range(0, 13, 2)), row=2, col=1)
                fig.update_yaxes(range=[0, 4], tickvals=list(range(0, 5)), row=3, col=1)
                
                fig.update_layout(title=f"Категории качества сигналов: {display_id}", template="plotly_white", hovermode='x unified')
                return fig

            # ---------------------------------------------------------
            # РЕЖИМ 4: ФИЗИЧЕСКИЕ МЕТРИКИ (Метры и проценты)
            # ---------------------------------------------------------
            elif mode == 'quality_metrics':
                fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                                    subplot_titles=("HIL (Метры)", "FOM (Метры)", "Качество (%)"))
                
                # HIL
                if self.nic_dict.get(icao):
                    times = [timestamp_to_utc(t) for t, _ in sorted(self.nic_dict[icao])]
                    vals = [NIC_TO_HIL.get(nic, 40000.0) for _, nic in sorted(self.nic_dict[icao])]
                    fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='HIL (м)', line=dict(color='red', width=2, shape='vh')), row=1, col=1)
                
                # FOM
                if self.nacp_dict.get(icao):
                    times = [timestamp_to_utc(t) for t, _ in sorted(self.nacp_dict[icao])]
                    vals = [NACP_TO_HFOM.get(n, 20000.0) for _, n in sorted(self.nacp_dict[icao])]
                    fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='HFOM (м)', line=dict(color='blue', width=2, shape='vh')), row=2, col=1)
                if self.gva_dict.get(icao):
                    times = [timestamp_to_utc(t) for t, _ in sorted(self.gva_dict[icao])]
                    vals = [GVA_TO_VFOM.get(g, 500.0) for _, g in sorted(self.gva_dict[icao])]
                    fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='VFOM (м)', line=dict(color='purple', dash='dash', width=2, shape='vh')), row=2, col=1)
                
                # Percentages
                if self.nic_dict.get(icao):
                    times = [timestamp_to_utc(t) for t, _ in sorted(self.nic_dict[icao])]
                    vals = [NIC_TO_PERCENT.get(v, 0) for _, v in sorted(self.nic_dict[icao])]
                    fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='HIL %', line=dict(color='red', width=2, shape='vh')), row=3, col=1)
                if self.nacp_dict.get(icao):
                    times = [timestamp_to_utc(t) for t, _ in sorted(self.nacp_dict[icao])]
                    vals = [NACP_TO_PERCENT.get(v, 0) for _, v in sorted(self.nacp_dict[icao])]
                    fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='HFOM %', line=dict(color='blue', width=2, shape='vh')), row=3, col=1)
                if self.gva_dict.get(icao):
                    times = [timestamp_to_utc(t) for t, _ in sorted(self.gva_dict[icao])]
                    vals = [GVA_TO_PERCENT.get(v, 0) for _, v in sorted(self.gva_dict[icao])]
                    fig.add_trace(go.Scatter(x=times, y=vals, mode='lines', name='VFOM %', line=dict(color='purple', dash='dash', shape='vh')), row=3, col=1)

                fig.update_yaxes(type="log", row=1, col=1)
                fig.update_yaxes(type="log", row=2, col=1)
                fig.update_yaxes(range=[-5, 110], row=3, col=1)
                
                fig.update_layout(title=f"Физические пределы качества: {display_id}", template="plotly_white", hovermode='x unified')
                return fig

            # ---------------------------------------------------------
            # РЕЖИМ 5: БАРОМЕТРИЧЕСКИЙ АНАЛИЗ
            # ---------------------------------------------------------
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

            return go.Figure()
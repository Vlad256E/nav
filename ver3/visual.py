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
        @self.app.callback(
            Output('main-graph', 'figure'),
            [Input('icao-dropdown', 'value'),
             Input('mode-dropdown', 'value')]
        )
        def update_graph(icao, mode):
            if not icao:
                return go.Figure()

            display_id = self.get_display_id(icao)

            # ---------------------------------------------------------
            # РЕЖИМ 1: ОБЩАЯ КАРТА (ВСЕ ТРЕКИ) с выделением текущего
            # ---------------------------------------------------------
            if mode == 'track':
                if not self.pos_dict:
                    return go.Figure().add_annotation(text="Нет данных координат", showarrow=False)

                fig = go.Figure()

                # 1. Сначала рисуем фоновые треки (все остальные борты) серым цветом
                for track_icao, track_data in self.pos_dict.items():
                    # Пропускаем, если борта нет в рабочем списке или это текущий выбранный борт
                    if track_icao not in self.icao_list or track_icao == icao: 
                        continue
                        
                    lats = [lat for t, lat, lon in track_data]
                    lons = [lon for t, lat, lon in track_data]
                    
                    fig.add_trace(go.Scatter(
                        x=lons, y=lats, mode='lines',
                        line=dict(width=1, color='grey'),
                        opacity=0.6, # Полупрозрачность для фона, как в visual2.py
                        hoverinfo='text',
                        text=[f"Борт: {track_icao}"] * len(lons), # Подсказка при наведении
                        showlegend=False
                    ))

                # 2. Затем рисуем трек выбранного борта (красным цветом и толще поверх остальных)
                current_data = self.pos_dict.get(icao)
                if current_data:
                    lats = [lat for t, lat, lon in current_data]
                    lons = [lon for t, lat, lon in current_data]
                    times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in current_data]
                    
                    fig.add_trace(go.Scatter(
                        x=lons, y=lats, mode='lines+markers',
                        marker=dict(size=4, color='red'),
                        line=dict(width=2, color='red'),
                        text=times,
                        name=display_id,
                        showlegend=True
                    ))

                # 3. Настройка внешнего вида графика (пропорции, легенда, заголовок)
                fig.update_layout(
                    title="ОБЩАЯ КАРТА (Все обнаруженные треки)",
                    xaxis_title="Долгота", 
                    yaxis_title="Широта",
                    yaxis=dict(scaleanchor="x", scaleratio=1), # Сохранение пропорций как на реальной карте
                    template="plotly_white",
                    hovermode='closest',
                    # Переносим легенду внутрь графика в правый верхний угол (как на скриншоте)
                    legend=dict(
                        yanchor="top", y=0.99, 
                        xanchor="right", x=0.99,
                        bgcolor="rgba(255, 255, 255, 0.8)", # Белый полупрозрачный фон легенды
                        bordercolor="lightgray",
                        borderwidth=1
                    )
                )
                
                return fig

            # ---------------------------------------------------------
            # РЕЖИМ 1.5: АНИМАЦИЯ ПОЛЕТА (С РЕАЛЬНОЙ КАРТОЙ)
            # ---------------------------------------------------------
            elif mode == 'animation':
                data = self.pos_dict.get(icao)
                if not data or len(data) < 2:
                    return go.Figure().add_annotation(text="Недостаточно данных", showarrow=False)

                # Сортировка и оптимизация количества точек
                data = sorted(data, key=lambda x: x[0])
                step = max(1, len(data) // 600)
                data = data[::step]

                lats = [lat for t, lat, lon in data]
                lons = [lon for t, lat, lon in data]
                times = [timestamp_to_utc(t).strftime('%H:%M:%S') for t, lat, lon in data]

                fig = go.Figure()

                # 1. Фоновый маршрут (серый)
                fig.add_trace(go.Scattermapbox(
                    lat=lats, lon=lons, 
                    mode='lines', 
                    line=dict(width=2, color='gray'), 
                    opacity=0.3, 
                    name='Весь путь'
                ))
                
                # 2. Пройденный путь (синий)
                fig.add_trace(go.Scattermapbox(
                    lat=[lats[0]], lon=[lons[0]], 
                    mode='lines', 
                    line=dict(width=4, color='blue'), 
                    name='Пройдено'
                ))

                # 3. Текущая позиция (красный кружок)
                # ВАЖНО: Убрал 'symbol', чтобы карта не требовала токен
                fig.add_trace(go.Scattermapbox(
                    lat=[lats[0]], lon=[lons[0]], 
                    mode='markers', 
                    marker=dict(size=14, color='red'), 
                    name='Самолет'
                ))

                # Создание кадров
                frames = []
                for i in range(len(data)):
                    frames.append(go.Frame(
                        data=[
                            go.Scattermapbox(lat=lats, lon=lons), 
                            go.Scattermapbox(lat=lats[:i+1], lon=lons[:i+1]), 
                            go.Scattermapbox(lat=[lats[i]], lon=[lons[i]])
                        ],
                        name=str(i)
                    ))
                fig.frames = frames

                # Настройка слайдера
                slider_steps = []
                for i in range(len(data)):
                    slider_steps.append(dict(
                        args=[[str(i)], dict(mode="immediate", frame=dict(duration=0, redraw=False), transition=dict(duration=0))],
                        label=times[i], 
                        method="animate"
                    ))

                # Итоговый Layout с Mapbox (для блока mode == 'animation')
                fig.update_layout(
                    title=f"Интерактивная карта: {display_id}",
                    autosize=True,
                    hovermode='closest',
                    # Делаем большой отступ снизу (b=100) для панели управления
                    margin=dict(l=20, r=20, t=50, b=100), 
                    mapbox=dict(
                        style="open-street-map",
                        center=dict(lat=np.mean(lats), lon=np.mean(lons)),
                        zoom=8
                    ),
                    # Настройка кнопок управления
                    updatemenus=[dict(
                        type="buttons",
                        direction="left",
                        showactive=False,
                        x=0.0, y=-0.1,
                        xanchor="left", yanchor="top",
                        pad=dict(r=10, t=0),
                        buttons=[
                            # Отмотка назад (Реверс)
                            dict(label="⏪", method="animate", args=[None, dict(frame=dict(duration=150, redraw=True), transition=dict(duration=0), fromcurrent=True, mode="immediate", direction="reverse")]),
                            # Пауза
                            dict(label="⏸", method="animate", args=[[None], dict(frame=dict(duration=0, redraw=False), mode="immediate")]),
                            # Плей (нормальная скорость)
                            dict(label="▶", method="animate", args=[None, dict(frame=dict(duration=150, redraw=True), transition=dict(duration=0), fromcurrent=True, mode="immediate", direction="forward")]),
                            # Ускорение (Кадр каждые 30мс)
                            dict(label="⏩", method="animate", args=[None, dict(frame=dict(duration=30, redraw=True), transition=dict(duration=0), fromcurrent=True, mode="immediate", direction="forward")])
                        ]
                    )],
                    # Настройка ползунка времени
                    sliders=[dict(
                        active=0,
                        steps=slider_steps,
                        x=0.25,              # Сдвигаем вправо, чтобы освободить место кнопкам
                        y=-0.1,              # На тот же уровень, что и кнопки
                        len=0.75,            # Занимает 75% ширины
                        xanchor="left",
                        yanchor="top",
                        pad=dict(t=0, b=0),
                        currentvalue=dict(visible=True, prefix="Время: ", font=dict(size=14))
                    )],
                    template="plotly_white"
                )
                
                # Принудительно отключаем авто-изменение отступов для осей
                fig.update_yaxes(automargin=False)
                fig.update_xaxes(automargin=False)
                
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
                
                fig.update_layout(
                    title=f"Физические пределы качества: {display_id}", 
                    template="plotly_white", 
                    hovermode='x unified',
                    # --- ДОБАВИТЬ ЭТОТ БЛОК ---
                    legend=dict(
                        orientation="h",   # Горизонтальная ориентация
                        yanchor="top",     # Привязка к верхнему краю легенды
                        y=-0.1,            # Опускаем ниже графика (отрицательное значение)
                        xanchor="center",  # Центрируем по X
                        x=0.5              # Ставим ровно посередине
                    ),
                    margin=dict(b=80)      # Увеличиваем нижний отступ, чтобы легенда влезла
                    # --------------------------
                )
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
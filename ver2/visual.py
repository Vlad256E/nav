import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
from matplotlib.ticker import ScalarFormatter, AutoLocator
import numpy as np
from utils import timestamp_to_utc

NIC_TO_HIL = {
    11: 7.5,
    10: 25.0,
    9: 75.0,
    8: 185.2,   # 0.1 NM
    7: 370.4,   # 0.2 NM
    6: 1111.2,  # 0.6 NM
    5: 1852.0,  # 1.0 NM
    4: 3704.0,  # 2.0 NM
    3: 7408.0,  # 4.0 NM
    2: 14816.0, # 8.0 NM
    1: 37040.0, # 20.0 NM
    0: 40000.0  # > 20 NM или Неизвестно
}

NACP_TO_HFOM = {
    11: 3.0,
    10: 10.0,
    9: 30.0,
    8: 92.6,    # 0.05 NM
    7: 185.2,   # 0.1 NM
    6: 555.6,   # 0.3 NM
    5: 926.0,   # 0.5 NM
    4: 1852.0,  # 1.0 NM
    3: 3704.0,  # 2.0 NM
    2: 7408.0,  # 4.0 NM
    1: 18520.0, # 10.0 NM
    0: 20000.0  # >= 10 NM или Неизвестно
}

GVA_TO_VFOM = {
    2: 45.0,
    1: 150.0,
    0: 500.0,   # > 150 м или Неизвестно
    3: 0.0      # Резерв
}

# словари для соотношения значений и процентов
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

# класс для создания и управления окном с графиками
class IcaoGraphs:
    # конструктор класса, вызывается при создании объекта
    def __init__(self, alt_dict, spd_dict, pos_dict, course_dict, adsb_icao_list, icao_callsigns, 
                 icao_sel_alt, icao_alt_diff, icao_baro_correction, icao_gnss_alt,
                 icao_nic, icao_nacp, icao_gva, icao_sil, icao_nacv):
        
        # собираем все icao, по которым есть какие-либо данные
        icao_with_data = set(alt_dict.keys()) | set(spd_dict.keys()) | set(pos_dict.keys()) | set(course_dict.keys()) | set(icao_gnss_alt.keys())
        
        # пересечение: берем только те борта, которые есть в очищенном adsb_icao_list
        self.icao_list = sorted(list(icao_with_data.intersection(adsb_icao_list)))
        
        # если нет данных, выводим сообщение и выходим
        if not self.icao_list:
            print("Нет данных для построения графиков")
            return

        # сохраняем словари с данными в атрибутах класса
        self.alt_dict = alt_dict
        self.spd_dict = spd_dict
        self.pos_dict = pos_dict
        self.course_dict = course_dict
        self.icao_callsigns = icao_callsigns
        self.sel_alt_dict = icao_sel_alt if icao_sel_alt else {}
        self.alt_diff_dict = icao_alt_diff if icao_alt_diff else {}
        self.baro_correction_dict = icao_baro_correction if icao_baro_correction else {} 
        self.gnss_alt_dict = icao_gnss_alt if icao_gnss_alt else {}

        # словари с параметрами качества
        self.nic_dict = icao_nic if icao_nic else {}
        self.nacp_dict = icao_nacp if icao_nacp else {}
        self.gva_dict = icao_gva if icao_gva else {}
        self.sil_dict = icao_sil if icao_sil else {}
        self.nacv_dict = icao_nacv if icao_nacv else {}
        
        self.icao_index = 0
    

        # список доступных режимов (типов графиков)
        self.plot_modes = [
            'all_tracks', 
            'altitude', 
            'gnss_altitude', 
            'speed', 
            'altitude_speed_combined', 
            'latitude', 
            'course', 
            'track', 
            'integrity', 
            'hil',
            'accuracy_pos', 
            'hfom',
            'vfom',
            'quality_percentages',
            'accuracy_vel', 
            'altitude_diff', 
            'baro_correction'
        ]
        
        self.plot_mode_idx = 0
        self.ylims = {mode: {} for mode in self.plot_modes}

        # пределы по умолчанию для осей y
        self.default_ylims = {
            'altitude': (-1200, 40000), 
            'gnss_altitude': (-1200, 40000),
            'speed': (0, 500), 
            'course': (0, 360), 
            'latitude': 'auto',
            'altitude_speed_combined': 'auto',
            'altitude_diff': (-2000, 2000),
            'baro_correction': (950, 1050),
            'integrity': (-0.5, 12.5),
            'accuracy_pos': (-0.5, 16.5),
            'accuracy_vel': (-0.5, 8.5),
            'hil': (-100, 45000 ),
            'hfom': (-100, 21000),
            'vfom': (-10, 600),
            'quality_percentages': (-5, 110)
        }

        # создание окна и основной области для рисования
        self.fig, self.ax = plt.subplots(figsize=(12, 7))
        self.fig.canvas.manager.set_window_title('Графики бортов')
        plt.subplots_adjust(bottom=0.25) # оставляем место снизу для кнопок
        
        self.ax2 = None
        self.cbar = None

        # создание областей для кнопок
        ax_prev_icao = plt.axes([0.05, 0.05, 0.2, 0.075])
        ax_next_icao = plt.axes([0.28, 0.05, 0.2, 0.075])
        ax_prev_mode = plt.axes([0.52, 0.05, 0.2, 0.075])
        ax_next_mode = plt.axes([0.75, 0.05, 0.2, 0.075])
        
        # создание и настройка кнопок
        self.btn_prev_icao = Button(ax_prev_icao, '<- Пред. борт', color='lightblue', hovercolor='skyblue')
        self.btn_next_icao = Button(ax_next_icao, 'След. борт ->', color='lightblue', hovercolor='skyblue')
        self.btn_prev_mode = Button(ax_prev_mode, '<- Пред. график', color='lightgreen', hovercolor='limegreen')
        self.btn_next_mode = Button(ax_next_mode, 'След. график ->', color='lightgreen', hovercolor='limegreen')
        
        # привязка функций-обработчиков к кнопкам
        self.btn_prev_icao.on_clicked(self.prev_icao)
        self.btn_next_icao.on_clicked(self.next_icao)
        self.btn_prev_mode.on_clicked(self.prev_mode)
        self.btn_next_mode.on_clicked(self.next_mode)
        
        # подключение обработчиков событий клавиатуры и колеса мыши
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)
        
        # первоначальная отрисовка графика
        self.plot_current()
        plt.show()

    # главная функция отрисовки текущего графика
    def plot_current(self):
        # удаляем вторую ось y, если она есть
        if self.ax2:
            self.ax2.remove()
            self.ax2 = None
        
        # удаляем цветовую шкалу, если есть
        if self.cbar:
            self.cbar.remove()
            self.cbar = None

        self.ax.clear()
        self.ax.set_aspect('auto')

        # проверка наличия данных
        if not self.icao_list:
            self.ax.text(0.5, 0.5, "Нет бортов с данными для отображения", 
                         ha='center', va='center', transform=self.ax.transAxes)
            self.fig.canvas.draw_idle()
            return

        icao = self.icao_list[self.icao_index]
        mode = self.plot_modes[self.plot_mode_idx]
        
        # формирование заголовка
        callsign = self.icao_callsigns.get(icao, "N/A")
        squawk = self.icao_callsigns.get(f"{icao}_sq", "")
        if squawk: callsign += f" (SQ:{squawk})"
        
        modes_key = f"{icao}_modes"
        active_modes = self.icao_callsigns.get(modes_key, set())
        mode_str = f" ({', '.join(sorted(active_modes))})" if active_modes else ""
        display_id = f"{callsign} ({icao}){mode_str}" if callsign != "N/A" else f"{icao}{mode_str}"
        
        data = None
        label = ""
        title = ""

        # режим общей карты: отображение треков всех бортов одновременно
        if mode == 'all_tracks':
            title = "ОБЩАЯ КАРТА (Все обнаруженные треки)"
            if not self.pos_dict:
                 self.ax.text(0.5, 0.5, "Нет координат", ha='center', transform=self.ax.transAxes)
            else:
                # отрисовка треков всех бортов серым, а текущий выделяем красным
                for track_icao, track_data in self.pos_dict.items():
                    if track_icao not in self.icao_list: continue
                    lons = [lon for t, lat, lon in track_data]
                    lats = [lat for t, lat, lon in track_data]
                    if track_icao == icao:
                        self.ax.plot(lons, lats, 'o-', color='red', linewidth=2, markersize=4, label=f"{display_id}", zorder=10)
                    else:
                        self.ax.plot(lons, lats, '-', color='grey', linewidth=1, alpha=0.6, zorder=1)
            self.ax.set_aspect('equal', adjustable='datalim')

        # блок отрисовки графика высоты (барометрической)
        elif mode == 'altitude':
            data = self.alt_dict.get(icao)
            sel_data = self.sel_alt_dict.get(icao)
            title, label = f"Высота (Baro): {display_id}", "Высота (футы)"
            if data:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='Барометрическая высота', color='blue')
            if sel_data:
                times = [timestamp_to_utc(t) for t, v in sorted(sel_data)]
                values = [v for t, v in sorted(sel_data)]
                self.ax.step(times, values, where='post', label='Выбранная высота', color='red', linestyle='--')
        
        # блок отрисовки gnss высоты (вычисляемой)
        elif mode == 'gnss_altitude':
            data = self.gnss_alt_dict.get(icao)
            title, label = f"GNSS Высота: {display_id}", "Высота (футы)"
            if data:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='GNSS Высота', color='magenta')

        # блок отрисовки графика скорости
        elif mode == 'speed':
            data = self.spd_dict.get(icao)
            title, label = f"Скорость: {display_id}", "Скорость (узлы)"
            if data:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='Скорость', color='green')
        
        # блок отрисовки комбинированного графика
        elif mode == 'altitude_speed_combined':
            title = f"Высота и скорость: {display_id}"
            alt_data = self.alt_dict.get(icao)
            spd_data = self.spd_dict.get(icao)
            self.ax.set_ylabel("Высота (футы)", color='blue')
            self.ax2 = self.ax.twinx() 
            self.ax2.set_ylabel("Скорость (узлы)", color='green')
            if alt_data:
                t = [timestamp_to_utc(t) for t, v in sorted(alt_data)]
                v = [v for t, v in sorted(alt_data)]
                self.ax.plot(t, v, 'o-', markersize=3, color='blue')
            if spd_data:
                t = [timestamp_to_utc(t) for t, v in sorted(spd_data)]
                v = [v for t, v in sorted(spd_data)]
                self.ax2.plot(t, v, 'o-', markersize=3, color='green')

        # блок отрисовки графика широты
        elif mode == 'latitude':
            data = self.pos_dict.get(icao)
            title, label = f"Широта: {display_id}", "Широта (°)"
            if data:
                times = [timestamp_to_utc(t) for t, lat, lon in data]
                lats = [lat for t, lat, lon in data]
                self.ax.plot(times, lats, 'o-', markersize=3, color='orange')

        # блок отрисовки графика курса
        elif mode == 'course':
            data = self.course_dict.get(icao)
            title, label = f"Курс: {display_id}", "Курс (°)"
            if data:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, color='purple')

        # блок отрисовки трека полёта (карты) с раскраской по nic
        elif mode == 'track':
            data = self.pos_dict.get(icao)
            nic_data = self.nic_dict.get(icao, [])
            
            title = f"Схема трека: {display_id}"
            
            if data:
                lons = [lon for t, lat, lon in data]
                lats = [lat for t, lat, lon in data]
                nic_lookup = {t: v for t, v in nic_data}
                colors = [nic_lookup.get(t, 0) for t, lat, lon in data]
                
                sc = self.ax.scatter(lons, lats, c=colors, cmap='RdYlGn', vmin=0, vmax=11, s=10, edgecolors='none', zorder=2)
                
                # добавили fraction и pad, чтобы шкала не сжимала график
                self.cbar = plt.colorbar(sc, ax=self.ax, shrink=0.5, fraction=0.046, pad=0.04, aspect=20)
                self.cbar.set_label('Значение NIC')

        # блок отрисовки графика целостности
        elif mode == 'integrity':
            nic_data = self.nic_dict.get(icao, [])
            sil_data = self.sil_dict.get(icao, [])
            title = f"Целостность: {display_id}"
            self.ax.set_ylabel("Уровень (NIC: 0-11, SIL: 0-3)")
            
            if not nic_data and not sil_data:
                 self.ax.text(0.5, 0.5, "Нет данных целостности (Reg 05/65)", ha='center', transform=self.ax.transAxes)
            
            if nic_data:
                times = [timestamp_to_utc(t) for t, v in sorted(nic_data)]
                values = [v for t, v in sorted(nic_data)]
                self.ax.step(times, values, where='post', color='darkcyan', linewidth=2, label='NIC (HIL) - Рег05')
                self.ax.fill_between(times, values, step='post', alpha=0.1, color='cyan')
            
            if sil_data:
                times = [timestamp_to_utc(t) for t, v in sorted(sil_data)]
                values = [v for t, v in sorted(sil_data)]
                self.ax.step(times, values, where='post', color='darkorange', linestyle='--', label='SIL - Рег65')
            
            self.ax.set_yticks(range(0, 13))
            self.ax.grid(True, axis='y')

        # блок отрисовки графика hil
        elif mode == 'hil':
            nic_data = self.nic_dict.get(icao, [])
            title, label = f"Предел Целостности (HIL): {display_id}", "HIL (метры)"
            
            # список значений из справочника
            hil_levels = sorted(list(set(NIC_TO_HIL.values())))

            if not nic_data:
                self.ax.text(0.5, 0.5, "Нет данных NIC для расчета HIL", ha='center', transform=self.ax.transAxes)
            else:
                times = []
                values = []
                for t, nic in sorted(nic_data):
                    hil_val = NIC_TO_HIL.get(nic, 40000.0) 
                    times.append(timestamp_to_utc(t))
                    values.append(hil_val)
                
                self.ax.step(times, values, where='post', color='red', linewidth=2, label='HIL')
                
                # Логарифмическая шкала, чтобы видеть и 7м и 40км
                self.ax.set_yscale('log')
                # Чуть расширяем границы, чтобы крайние точки не прилипали
                self.ax.set_ylim(min(hil_levels)*0.9, max(hil_levels)*1.1)
                
                self.ax.set_yticks(hil_levels)
                
                # Форматируем как обычные числа
                formatter = ScalarFormatter()
                formatter.set_scientific(False)
                self.ax.get_yaxis().set_major_formatter(formatter)
                
                # Сетка будет только на этих уровнях
                self.ax.grid(True, axis='y', linestyle='--', alpha=0.5)

        # блок отрисовки графика точности позиции
        elif mode == 'accuracy_pos':
            nacp_data = self.nacp_dict.get(icao, [])
            gva_data = self.gva_dict.get(icao, [])
            title = f"Точность Позиции: {display_id}"
            self.ax.set_ylabel("Категория")
            
            if not nacp_data and not gva_data:
                 self.ax.text(0.5, 0.5, "Нет данных точности (Reg 65 TC 31)", ha='center', transform=self.ax.transAxes)

            if nacp_data:
                times = [timestamp_to_utc(t) for t, v in sorted(nacp_data)]
                values = [v for t, v in sorted(nacp_data)]
                self.ax.step(times, values, where='post', color='green', linewidth=2, label='NACp (HFOM) [0-15]')
            
            if gva_data:
                times = [timestamp_to_utc(t) for t, v in sorted(gva_data)]
                values = [v for t, v in sorted(gva_data)]
                self.ax.step(times, values, where='post', color='purple', linestyle='--', label='GVA (VFOM) масштабир. [0-3]')

            self.ax.set_yticks(range(0, 17))
            self.ax.grid(True, axis='y')

        # блок отрисовки графика hfom
        elif mode == 'hfom':
            nacp_data = self.nacp_dict.get(icao, [])
            title, label = f"Точность (HFOM): {display_id}", "HFOM (метры, 95%)"
            
            # список уникальных значений из справочника
            hfom_levels = sorted(list(set(NACP_TO_HFOM.values())))

            if not nacp_data:
                self.ax.text(0.5, 0.5, "Нет данных NACp", ha='center', transform=self.ax.transAxes)
            else:
                times = []
                values = []
                for t, nacp in sorted(nacp_data):
                    hfom_val = NACP_TO_HFOM.get(nacp, 20000.0)
                    times.append(timestamp_to_utc(t))
                    values.append(hfom_val)
                
                self.ax.step(times, values, where='post', color='blue', linewidth=2, label='HFOM (гориз. точность)')
                
                # Логарифмическая шкала
                self.ax.set_yscale('log')
                self.ax.set_ylim(min(hfom_levels)*0.9, max(hfom_levels)*1.1)
                
                self.ax.set_yticks(hfom_levels)
                
                # Форматируем как обычные числа
                formatter = ScalarFormatter()
                formatter.set_scientific(False)
                self.ax.get_yaxis().set_major_formatter(formatter)
                
                self.ax.grid(True, axis='y', linestyle='--', alpha=0.5)
        
        # блок отрисовки графика vfom
        elif mode == 'vfom':
            gva_data = self.gva_dict.get(icao, [])
            title, label = f"Точность (VFOM): {display_id}", "VFOM (метры, 95%)"
            
            vfom_levels = sorted(list(set(GVA_TO_VFOM.values())))

            if not gva_data:
                self.ax.text(0.5, 0.5, "Нет данных GVA", ha='center', transform=self.ax.transAxes)
            else:
                times = []
                values = []
                for t, gva in sorted(gva_data):
                    vfom_val = GVA_TO_VFOM.get(gva, 500.0) 
                    times.append(timestamp_to_utc(t))
                    values.append(vfom_val)
                
                self.ax.step(times, values, where='post', color='purple', linewidth=2, label='VFOM (верт. точность)')
                
                self.ax.set_yticks(vfom_levels)
                self.ax.grid(True, axis='y', linestyle='-', alpha=0.5)

        # блок отрисовки графиков качества в процентах
        elif mode == 'quality_percentages':
            nic_data = self.nic_dict.get(icao, [])
            nacp_data = self.nacp_dict.get(icao, [])
            gva_data = self.gva_dict.get(icao, [])
            
            title = f"Качество данных в % (Сводный график): {display_id}"
            self.ax.set_ylabel("Качество (%, логарифмическая шкала)")
            
            if not nic_data and not nacp_data and not gva_data:
                 self.ax.text(0.5, 0.5, "Нет данных качества (Reg 05/65)", ha='center', transform=self.ax.transAxes)

            # Рисуем графики процентов
            if nic_data:
                times = [timestamp_to_utc(t) for t, v in sorted(nic_data)]
                values = [NIC_TO_PERCENT.get(v, 0) for t, v in sorted(nic_data)]
                self.ax.step(times, values, where='post', color='red', linewidth=2.5, label='HIL (%)')
            
            if nacp_data:
                times = [timestamp_to_utc(t) for t, v in sorted(nacp_data)]
                values = [NACP_TO_PERCENT.get(v, 0) for t, v in sorted(nacp_data)]
                self.ax.step(times, values, where='post', color='blue', linewidth=2.5, label='HFOM (%)')

            if gva_data:
                times = [timestamp_to_utc(t) for t, v in sorted(gva_data)]
                values = [GVA_TO_PERCENT.get(v, 0) for t, v in sorted(gva_data)]
                self.ax.step(times, values, where='post', color='purple', linestyle='--', linewidth=2.5, label='VFOM (%)')

            self.ax.set_yticks(range(0, 101, 10))
            self.ax.grid(True, axis='y')

            # Добавляем плашку с уточнением соотношения значений внутри графика
            info_text = (
                "Значения в метрах (от 100% к 0%):\n"
                "HIL:  < 7.5м  > 37км\n"
                "HFOM:  < 3м  →  > 18.5км\n"
                "VFOM:   <= 45м  →  >= 150м"
            )
            self.ax.text(0.02, 0.05, info_text, transform=self.ax.transAxes, 
                         fontsize=10, verticalalignment='bottom', horizontalalignment='left',
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor='gray', alpha=0.9), zorder=10)

        # блок отрисовки графика точности скорости
        elif mode == 'accuracy_vel':
            data = self.nacv_dict.get(icao)
            title, label = f"Точность Скорости (NACv): {display_id}", "NACv [0-4]"
            if not data:
                self.ax.text(0.5, 0.5, "Нет данных NACv (Reg 09 TC 19)", ha='center', transform=self.ax.transAxes)
            else:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.step(times, values, where='post', color='brown', linewidth=2, label='NACv')
                self.ax.set_yticks(range(0, 6))

        # блок отрисовки разницы высот
        elif mode == 'altitude_diff':
            data = self.alt_diff_dict.get(icao)
            title, label = f"Разница высот: {display_id}", "Разница (футы)"
            if data:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', color='red', markersize=3)
                self.ax.axhline(0, color='gray', linestyle='--')

        # блок отрисовки барокоррекции
        elif mode == 'baro_correction':
            data = self.baro_correction_dict.get(icao)
            title, label = f"Барокоррекция: {display_id}", "Давление (гПа)"
            if data:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', color='brown', markersize=3)

        # установка заголовка и сетки
        self.ax.set_title(title)
        self.ax.grid(True, linestyle='--', alpha=0.7)

        # настройка осей в зависимости от типа графика
        if mode == 'track' or mode == 'all_tracks':
            self.ax.set_aspect('equal', adjustable='datalim')
            if mode == 'track':
                 self.ax.set_xlabel("Долгота (°)")
                 self.ax.set_ylabel("Широта (°)")
        else:
            self.ax.set_xlabel("Время (UTC)")
            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.fig.autofmt_xdate(rotation=30)
            if mode not in ['integrity', 'accuracy_pos']:
                self.ax.set_ylabel(label)
        
        # отображение легенды
        if self.ax.get_legend_handles_labels()[0] and mode != 'altitude_speed_combined':
            self.ax.legend()

        # применение масштабирования
        if mode != 'altitude_speed_combined' and mode != 'all_tracks':
            ylim = self.ylims[mode].get(icao, self.default_ylims.get(mode))
            if ylim and ylim != 'auto':
                self.ax.set_ylim(ylim)

        self.fig.canvas.draw_idle()

    # функция-обработчик для масштабирования колесом мыши
    def on_scroll(self, event):
        if event.inaxes != self.ax: return
        base_scale = 1.2
        mode = self.plot_modes[self.plot_mode_idx]
        
        if event.button == 'down': scale_factor = 1 / base_scale
        elif event.button == 'up': scale_factor = base_scale
        else: return

        # специальная логика для 2d-масштабирования (карты)
        if mode == 'track' or mode == 'all_tracks':
            cur_xlim = self.ax.get_xlim()
            cur_ylim = self.ax.get_ylim()
            xdata = event.xdata
            ydata = event.ydata
            if xdata is None or ydata is None: return
            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
            rel_x = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rel_y = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
            self.ax.set_xlim([xdata - new_width * (1 - rel_x), xdata + new_width * rel_x])
            self.ax.set_ylim([ydata - new_height * (1 - rel_y), ydata + new_height * rel_y])
        else:
            # стандартное масштабирование по оси y
            cur_ylim = self.ax.get_ylim()
            ydata = event.ydata if event.ydata is not None else (cur_ylim[0] + cur_ylim[1]) / 2
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
            rel_y = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
            self.ax.set_ylim([ydata - new_height * (1-rel_y), ydata + new_height * rel_y])
        self.fig.canvas.draw_idle()

    # функции навигации по интерфейсу
    def next_icao(self, event=None):
        if not self.icao_list: return
        self.icao_index = (self.icao_index + 1) % len(self.icao_list)
        self.plot_current()

    def prev_icao(self, event=None):
        if not self.icao_list: return
        self.icao_index = (self.icao_index - 1 + len(self.icao_list)) % len(self.icao_list)
        self.plot_current()

    def next_mode(self, event=None):
        if not self.icao_list: return
        self.plot_mode_idx = (self.plot_mode_idx + 1) % len(self.plot_modes)
        self.plot_current()

    def prev_mode(self, event=None):
        if not self.icao_list: return
        self.plot_mode_idx = (self.plot_mode_idx - 1 + len(self.plot_modes)) % len(self.plot_modes)
        self.plot_current()

    def on_key(self, event):
        if event.key == 'right': self.next_icao()
        elif event.key == 'left': self.prev_icao()
        elif event.key == 'up': self.next_mode()
        elif event.key == 'down': self.prev_mode()
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
from matplotlib.ticker import ScalarFormatter, AutoLocator
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
        
        self.icao_index = 0

        # Обновленные сгруппированные режимы
        self.plot_modes = [
            'track',                   # Общая карта (2D)
            'kinematics',              # Высота, Скорость, Курс
            'integrity_and_accuracy',  # Категории NIC/SIL, NACp/GVA, NACv
            'quality_metrics',         # Физические метрики: HIL, HFOM/VFOM, Проценты
            'baro_analysis'            # Разница высот, Барокоррекция
        ]
        
        self.plot_mode_idx = 0
        self.data_axes = [] # Хранилище осей для текущих графиков
        self.cbar = None

        self.fig = plt.figure(figsize=(14, 8))
        self.fig.canvas.manager.set_window_title('Авиационный Навигационный Дашборд')
        
        # Кнопки
        ax_prev_icao = plt.axes([0.05, 0.05, 0.2, 0.075])
        ax_next_icao = plt.axes([0.28, 0.05, 0.2, 0.075])
        ax_prev_mode = plt.axes([0.52, 0.05, 0.2, 0.075])
        ax_next_mode = plt.axes([0.75, 0.05, 0.2, 0.075])
        
        self.btn_prev_icao = Button(ax_prev_icao, '<- Пред. борт', color='lightblue', hovercolor='skyblue')
        self.btn_next_icao = Button(ax_next_icao, 'След. борт ->', color='lightblue', hovercolor='skyblue')
        self.btn_prev_mode = Button(ax_prev_mode, '<- Пред. экран', color='lightgreen', hovercolor='limegreen')
        self.btn_next_mode = Button(ax_next_mode, 'След. экран ->', color='lightgreen', hovercolor='limegreen')
        
        self.btn_prev_icao.on_clicked(self.prev_icao)
        self.btn_next_icao.on_clicked(self.next_icao)
        self.btn_prev_mode.on_clicked(self.prev_mode)
        self.btn_next_mode.on_clicked(self.next_mode)
        
        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.fig.canvas.mpl_connect('scroll_event', self.on_scroll)
        
        self.plot_current()
        plt.show()

    def get_display_id(self, icao):
        callsign = self.icao_callsigns.get(icao, "N/A")
        squawk = self.icao_callsigns.get(f"{icao}_sq", "")
        if squawk: callsign += f" (SQ:{squawk})"
        modes_key = f"{icao}_modes"
        active_modes = self.icao_callsigns.get(modes_key, set())
        mode_str = f" ({', '.join(sorted(active_modes))})" if active_modes else ""
        return f"{callsign} ({icao}){mode_str}" if callsign != "N/A" else f"{icao}{mode_str}"

    def plot_current(self):
        # Удаляем старые графики и colorbar перед отрисовкой новых
        for ax in self.data_axes:
            ax.remove()
        self.data_axes = []
        if self.cbar:
            self.cbar.remove()
            self.cbar = None

        if not self.icao_list:
            ax = self.fig.add_axes([0.1, 0.25, 0.8, 0.65])
            ax.text(0.5, 0.5, "Нет бортов с данными для отображения", ha='center', va='center')
            self.data_axes.append(ax)
            self.fig.canvas.draw_idle()
            return

        icao = self.icao_list[self.icao_index]
        mode = self.plot_modes[self.plot_mode_idx]
        display_id = self.get_display_id(icao)

        # ---------------------------------------------------------
        # РЕЖИМ 1: ТРЕК И ОБЩАЯ КАРТА (2D)
        # ---------------------------------------------------------
        if mode == 'track':
            ax = self.fig.add_axes([0.1, 0.25, 0.8, 0.65])
            self.data_axes.append(ax)
            
            ax.set_title(f"Схема трека: {display_id}")
            ax.set_aspect('equal', adjustable='datalim')
            ax.set_xlabel("Долгота (°)")
            ax.set_ylabel("Широта (°)")

            # Отрисовка всех треков серым цветом для контекста
            for track_icao, track_data in self.pos_dict.items():
                if track_icao not in self.icao_list: continue
                lons = [lon for t, lat, lon in track_data]
                lats = [lat for t, lat, lon in track_data]
                if track_icao != icao:
                    ax.plot(lons, lats, '-', color='grey', linewidth=1, alpha=0.4, zorder=1)

            # Отрисовка активного трека с раскраской по NIC
            data = self.pos_dict.get(icao)
            if data:
                lons = [lon for t, lat, lon in data]
                lats = [lat for t, lat, lon in data]
                nic_data = self.nic_dict.get(icao, [])
                nic_lookup = {t: v for t, v in nic_data}
                colors = [nic_lookup.get(t, 0) for t, lat, lon in data]
                
                ax.plot(lons, lats, '-', color='black', linewidth=0.5, zorder=2) # Линия трека
                sc = ax.scatter(lons, lats, c=colors, cmap='RdYlGn', vmin=0, vmax=11, s=20, edgecolors='black', linewidth=0.3, zorder=3)
                
                self.cbar = plt.colorbar(sc, ax=ax, shrink=0.8, pad=0.02)
                self.cbar.set_label('Значение NIC (Целостность)')
            else:
                ax.text(0.5, 0.5, "Нет координат для данного борта", ha='center', transform=ax.transAxes)

        # ---------------------------------------------------------
        # РЕЖИМ 2: КИНЕМАТИКА (Высота, Скорость, Курс)
        # ---------------------------------------------------------
        elif mode == 'kinematics':
            gs = self.fig.add_gridspec(3, 1, hspace=0.15, bottom=0.20, top=0.92, left=0.08, right=0.95)
            ax1 = self.fig.add_subplot(gs[0, 0])
            ax2 = self.fig.add_subplot(gs[1, 0], sharex=ax1)
            ax3 = self.fig.add_subplot(gs[2, 0], sharex=ax1)
            self.data_axes.extend([ax1, ax2, ax3])
            
            ax1.set_title(f"Кинематика полета: {display_id}")
            
            # Высота
            alt_data = self.alt_dict.get(icao)
            gnss_data = self.gnss_alt_dict.get(icao)
            sel_data = self.sel_alt_dict.get(icao)
            
            if alt_data:
                ax1.plot([timestamp_to_utc(t) for t, v in sorted(alt_data)], [v for t, v in sorted(alt_data)], 'o-', markersize=2, label='Baro Alt', color='blue')
            if gnss_data:
                ax1.plot([timestamp_to_utc(t) for t, v in sorted(gnss_data)], [v for t, v in sorted(gnss_data)], 'o-', markersize=2, label='GNSS Alt', color='magenta')
            if sel_data:
                ax1.step([timestamp_to_utc(t) for t, v in sorted(sel_data)], [v for t, v in sorted(sel_data)], where='post', label='Selected Alt', color='red', linestyle='--')
            
            ax1.set_ylabel("Высота (фт)")
            if alt_data or gnss_data or sel_data: ax1.legend(loc='upper right')

            # Скорость
            spd_data = self.spd_dict.get(icao)
            if spd_data:
                ax2.plot([timestamp_to_utc(t) for t, v in sorted(spd_data)], [v for t, v in sorted(spd_data)], 'o-', markersize=2, color='green', label='GS (узлы)')
            ax2.set_ylabel("Скорость")
            if spd_data: ax2.legend(loc='upper right')

            # Курс
            crs_data = self.course_dict.get(icao)
            if crs_data:
                ax3.plot([timestamp_to_utc(t) for t, v in sorted(crs_data)], [v for t, v in sorted(crs_data)], 'o-', markersize=2, color='purple', label='Курс (°)')
            ax3.set_ylabel("Курс")
            ax3.set_ylim(-10, 370)
            ax3.set_yticks([0, 90, 180, 270, 360])
            if crs_data: ax3.legend(loc='upper right')

        # ---------------------------------------------------------
        # РЕЖИМ 3: КАТЕГОРИИ ЦЕЛОСТНОСТИ И ТОЧНОСТИ (Reg 05/65/09)
        # ---------------------------------------------------------
        elif mode == 'integrity_and_accuracy':
            gs = self.fig.add_gridspec(3, 1, hspace=0.15, bottom=0.20, top=0.92, left=0.08, right=0.95)
            ax1 = self.fig.add_subplot(gs[0, 0])
            ax2 = self.fig.add_subplot(gs[1, 0], sharex=ax1)
            ax3 = self.fig.add_subplot(gs[2, 0], sharex=ax1)
            self.data_axes.extend([ax1, ax2, ax3])
            
            ax1.set_title(f"Категории качества сигналов (Reg 05/65/09): {display_id}")

            # NIC / SIL
            nic_data = self.nic_dict.get(icao, [])
            sil_data = self.sil_dict.get(icao, [])
            if nic_data:
                ax1.step([timestamp_to_utc(t) for t, v in sorted(nic_data)], [v for t, v in sorted(nic_data)], where='post', color='darkcyan', linewidth=2, label='NIC (0-11)')
                ax1.fill_between([timestamp_to_utc(t) for t, v in sorted(nic_data)], [v for t, v in sorted(nic_data)], step='post', alpha=0.1, color='cyan')
            if sil_data:
                ax1.step([timestamp_to_utc(t) for t, v in sorted(sil_data)], [v for t, v in sorted(sil_data)], where='post', color='darkorange', linestyle='--', label='SIL (0-3)')
            ax1.set_ylabel("Уровень Целостности")
            ax1.set_yticks(range(0, 12, 2))
            if nic_data or sil_data: ax1.legend(loc='upper right')

            # NACp / GVA
            nacp_data = self.nacp_dict.get(icao, [])
            gva_data = self.gva_dict.get(icao, [])
            if nacp_data:
                ax2.step([timestamp_to_utc(t) for t, v in sorted(nacp_data)], [v for t, v in sorted(nacp_data)], where='post', color='green', linewidth=2, label='NACp (0-11)')
            if gva_data:
                ax2.step([timestamp_to_utc(t) for t, v in sorted(gva_data)], [v for t, v in sorted(gva_data)], where='post', color='purple', linestyle='--', label='GVA (0-3)')
            ax2.set_ylabel("Точность Позиции")
            ax2.set_yticks(range(0, 12, 2))
            if nacp_data or gva_data: ax2.legend(loc='upper right')

            # NACv
            nacv_data = self.nacv_dict.get(icao)
            if nacv_data:
                ax3.step([timestamp_to_utc(t) for t, v in sorted(nacv_data)], [v for t, v in sorted(nacv_data)], where='post', color='brown', linewidth=2, label='NACv (0-4)')
            ax3.set_ylabel("Точность Скор.")
            ax3.set_yticks(range(0, 5))
            if nacv_data: ax3.legend(loc='upper right')

        # ---------------------------------------------------------
        # РЕЖИМ 4: ФИЗИЧЕСКИЕ МЕТРИКИ (Метры и проценты)
        # ---------------------------------------------------------
        elif mode == 'quality_metrics':
            gs = self.fig.add_gridspec(3, 1, hspace=0.15, bottom=0.20, top=0.92, left=0.08, right=0.95)
            ax1 = self.fig.add_subplot(gs[0, 0])
            ax2 = self.fig.add_subplot(gs[1, 0], sharex=ax1)
            ax3 = self.fig.add_subplot(gs[2, 0], sharex=ax1)
            self.data_axes.extend([ax1, ax2, ax3])
            
            ax1.set_title(f"Физические пределы качества (Метры): {display_id}")

            # HIL (NIC -> HIL)
            nic_data = self.nic_dict.get(icao, [])
            if nic_data:
                times, values = zip(*[(timestamp_to_utc(t), NIC_TO_HIL.get(nic, 40000.0)) for t, nic in sorted(nic_data)])
                ax1.step(times, values, where='post', color='red', linewidth=2, label='HIL (м)')
                ax1.set_yscale('log')
                ax1.get_yaxis().set_major_formatter(ScalarFormatter())
            ax1.set_ylabel("HIL (log)")
            if nic_data: ax1.legend(loc='upper right')

            # HFOM / VFOM
            nacp_data = self.nacp_dict.get(icao, [])
            gva_data = self.gva_dict.get(icao, [])
            if nacp_data:
                times, values = zip(*[(timestamp_to_utc(t), NACP_TO_HFOM.get(n, 20000.0)) for t, n in sorted(nacp_data)])
                ax2.step(times, values, where='post', color='blue', linewidth=2, label='HFOM (м)')
                ax2.set_yscale('log')
                ax2.get_yaxis().set_major_formatter(ScalarFormatter())
            if gva_data:
                times, values = zip(*[(timestamp_to_utc(t), GVA_TO_VFOM.get(g, 500.0)) for t, g in sorted(gva_data)])
                ax2.step(times, values, where='post', color='purple', linestyle='--', linewidth=2, label='VFOM (м)')
            ax2.set_ylabel("FOM (log)")
            if nacp_data or gva_data: ax2.legend(loc='upper right')

            # Проценты
            if nic_data:
                ax3.step([timestamp_to_utc(t) for t, v in sorted(nic_data)], [NIC_TO_PERCENT.get(v, 0) for t, v in sorted(nic_data)], where='post', color='red', linewidth=2, label='HIL %')
            if nacp_data:
                ax3.step([timestamp_to_utc(t) for t, v in sorted(nacp_data)], [NACP_TO_PERCENT.get(v, 0) for t, v in sorted(nacp_data)], where='post', color='blue', linewidth=2, label='HFOM %')
            if gva_data:
                ax3.step([timestamp_to_utc(t) for t, v in sorted(gva_data)], [GVA_TO_PERCENT.get(v, 0) for t, v in sorted(gva_data)], where='post', color='purple', linestyle='--', label='VFOM %')
            ax3.set_ylabel("Качество (%)")
            ax3.set_ylim(-5, 110)
            if nic_data or nacp_data or gva_data: ax3.legend(loc='upper right')

        # ---------------------------------------------------------
        # РЕЖИМ 5: БАРОМЕТРИЧЕСКИЙ АНАЛИЗ
        # ---------------------------------------------------------
        elif mode == 'baro_analysis':
            gs = self.fig.add_gridspec(2, 1, hspace=0.15, bottom=0.20, top=0.92, left=0.08, right=0.95)
            ax1 = self.fig.add_subplot(gs[0, 0])
            ax2 = self.fig.add_subplot(gs[1, 0], sharex=ax1)
            self.data_axes.extend([ax1, ax2])
            
            ax1.set_title(f"Барометрический анализ: {display_id}")

            # Разница высот (GNSS vs Baro)
            diff_data = self.alt_diff_dict.get(icao)
            if diff_data:
                ax1.plot([timestamp_to_utc(t) for t, v in sorted(diff_data)], [v for t, v in sorted(diff_data)], 'o-', color='red', markersize=3, label='Разница (фт)')
                ax1.axhline(0, color='gray', linestyle='--')
            ax1.set_ylabel("Alt Diff")
            if diff_data: ax1.legend(loc='upper right')

            # Барокоррекция
            baro_data = self.baro_correction_dict.get(icao)
            if baro_data:
                ax2.plot([timestamp_to_utc(t) for t, v in sorted(baro_data)], [v for t, v in sorted(baro_data)], 'o-', color='brown', markersize=3, label='Давление (гПа)')
            ax2.set_ylabel("Baro Setting")
            if baro_data: ax2.legend(loc='upper right')

        # ---------------------------------------------------------
        # ОБЩЕЕ ФОРМАТИРОВАНИЕ ДЛЯ ВСЕХ ОСЕЙ ЭКРАНА
        # ---------------------------------------------------------
        for i, ax in enumerate(self.data_axes):
            ax.grid(True, linestyle='--', alpha=0.7)
            # Если это не карта трека, настраиваем ось времени
            if mode != 'track':
                # Прячем метки времени на всех графиках кроме нижнего (чтобы не сливались)
                if i < len(self.data_axes) - 1:
                    plt.setp(ax.get_xticklabels(), visible=False)
                else:
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
                    ax.set_xlabel("Время (UTC)")
                    plt.setp(ax.get_xticklabels(), rotation=30, ha='right')

        self.fig.canvas.draw_idle()

    def on_scroll(self, event):
        target_ax = event.inaxes
        # Если мышка не над одной из областей графиков (например, над кнопкой) - игнорируем
        if target_ax not in self.data_axes: 
            return
            
        base_scale = 1.2
        mode = self.plot_modes[self.plot_mode_idx]
        
        if event.button == 'down': scale_factor = 1 / base_scale
        elif event.button == 'up': scale_factor = base_scale
        else: return

        if mode == 'track':
            cur_xlim = target_ax.get_xlim()
            cur_ylim = target_ax.get_ylim()
            xdata = event.xdata
            ydata = event.ydata
            if xdata is None or ydata is None: return
            new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
            rel_x = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
            rel_y = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
            target_ax.set_xlim([xdata - new_width * (1 - rel_x), xdata + new_width * rel_x])
            target_ax.set_ylim([ydata - new_height * (1 - rel_y), ydata + new_height * rel_y])
        else:
            # Зум по оси Y для конкретного графика (на который наведена мышь)
            cur_ylim = target_ax.get_ylim()
            ydata = event.ydata if event.ydata is not None else (cur_ylim[0] + cur_ylim[1]) / 2
            new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor
            rel_y = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])
            target_ax.set_ylim([ydata - new_height * (1-rel_y), ydata + new_height * rel_y])
            
        self.fig.canvas.draw_idle()

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
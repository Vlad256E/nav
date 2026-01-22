import numpy as np
import pyModeS as pms
from datetime import datetime, timezone
import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button
from pathlib import Path
import sys


MAX_MESSAGE_LENGTH = 32
DATA_DIR = Path("data") # Папка, где лежат логи
DEFAULT_LOG_EXTENSION = ".t4433" # Расширение файлов логов

# словарь для преобразования режимов автопилота в понятные сокращения
MODE_MAP = {
    'U': 'AP',      # autopilot on
    '/': 'ALT',     # altitude hold
    'M': 'VNAV',    # vertical navigation
    'F': 'LNAV',    # lateral navigation
    'P': 'APP',     # approach mode
    'T': 'TCAS',    # tcas ra active
    'C': 'HDG'      # selected heading
}

# класс-контейнер для одного ads-b сообщения
class ADSBMessage:
    def __init__(self):
        self.timestamp = np.float64(0.0)
        self.message = np.zeros(MAX_MESSAGE_LENGTH, dtype=np.uint8)
        self.message_length = 0

# функция парсит одну строку из файла с данными
def parse_ads_b_line(line):
    # делим строку на части по пробелам
    parts = line.strip().split()
    if len(parts) < 2:
        return None
    try:
        # первую часть превращаем в число (время)
        timestamp = np.float64(parts[0])
    except ValueError:
        return None
    
    # проверка формата: если есть колонка DF/UF, смещаем чтение hex
    if len(parts) >= 3 and parts[1].upper() in ['DF', 'UF']:
        hex_parts = parts[2:]
    else:
        hex_parts = parts[1:]
    
    # остальные части соединяем в сплошную hex-строку
    message_spaced = ' '.join(hex_parts).upper().strip()
    message_str = message_spaced.replace(" ", "")
    
    if len(message_str) == 0 or not all(c in "0123456789ABCDEF" for c in message_str):
        return None
    
    # создаём объект-контейнер и заполняем его байтами
    msg = ADSBMessage()
    msg.timestamp = timestamp
    try:
        bytes_list = [int(message_str[i:i + 2], 16) for i in range(0, len(message_str), 2)]
        msg.message_length = min(len(bytes_list), MAX_MESSAGE_LENGTH)
        for i in range(msg.message_length):
            msg.message[i] = np.uint8(bytes_list[i])
    except:
        return None
        
    return msg, message_spaced, message_str

# функция конвертирует unix timestamp в объект datetime
def timestamp_to_utc(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)

# функция форматирует время, сохраняя наносекунды для точности
def format_timestamp_with_nanoseconds(ts):
    # форматируем основную часть времени (до секунд)
    main_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    main_dt_str = main_dt.strftime('%Y-%m-%d %H:%M:%S')
    
    # получаем дробную часть времени (наносекунды) как строку
    ts_str = f"{ts:.9f}"
    nanoseconds_str = ts_str.split('.')[1]
    
    # соединяем обе части
    return f"{main_dt_str}.{nanoseconds_str}"



# универсальная функция извлечения высоты 
def get_altitude_any_df(msg_str, df):
    try:
        # если это ADS-B (DF17/18)
        if df in [17, 18]:
            tc = pms.adsb.typecode(msg_str)
            if 9 <= tc <= 18:
                return pms.adsb.altitude(msg_str)
        # если это Mode S ELS (DF0, 4, 16, 20)
        elif df in [0, 4, 16, 20]:
            return pms.common.altcode(msg_str)
    except:
        return None
    return None

# получение Squawk (кода ответчика)
def get_squawk(msg_str, df):
    try:
        # работает для DF5 и DF21
        if df in [5, 21]:
            return pms.common.idcode(msg_str)
    except:
        return None
    return None

# функция извлекает скорость из сообщения
def get_velocity(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о скорости (тип 19)
        tc = pms.adsb.typecode(msg_str)
        if tc == 19:
            result = pms.adsb.velocity(msg_str)
            if result and result[0] is not None:
                return result[0]
        return None
    except:
        return None

# функция извлекает курс из сообщения
def get_course(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # также проверяем, что это сообщение о скорости (тип 19)
        tc = pms.adsb.typecode(msg_str)
        if tc == 19:
            _, heading, _, _ = pms.adsb.velocity(msg_str)
            return heading
        return None
    except:
        return None

# функция извлекает выбранную на автопилоте высоту и режимы
def get_selected_altitude(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о статусе (тип 29)
        tc = pms.adsb.typecode(msg_str)
        if tc != 29: return None
        sel_alt_info = pms.adsb.selected_altitude(msg_str)
        if sel_alt_info is None: return None
        selected_alt, raw_modes = sel_alt_info
        if selected_alt is not None and -2000 <= selected_alt <= 50000:
            # переводим режимы в понятные сокращения
            processed_modes = {MODE_MAP.get(m, m) for m in raw_modes}
            return selected_alt, processed_modes
        return None
    except Exception as e:
        return None

# функция получения разности высот
def get_altitude_difference(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о скорости (тип 19)
        tc = pms.typecode(msg_str)
        if tc != 19:
            return None
        
        altitude_diff = pms.adsb.altitude_diff(msg_str)
        if altitude_diff is not None and -2500 <= altitude_diff <= 2500:
            return altitude_diff
        
        return None
    except Exception as e:
        return None

# функция получения барокоррекции
def get_baro_correction(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение о статусе (тип 29)
        tc = pms.adsb.typecode(msg_str)
        if tc != 29:
            return None
        
        baro_setting = pms.adsb.baro_pressure_setting(msg_str)
        
        if baro_setting is not None:
            # разумные пределы для атмосферного давления
            if 800 <= baro_setting <= 1100:
                return baro_setting
                
        return None
        
    except Exception as e:
        return None

# функция извлекает позывной (callsign)
def get_callsign(msg_str):
    try:
        # проверяем, что это ads-b сообщение
        df = pms.df(msg_str)
        if df not in [17, 18]: return None
        # проверяем, что это сообщение идентификации (тип 1-4)
        tc = pms.adsb.typecode(msg_str)
        if 1 <= tc <= 4:
            callsign = pms.adsb.callsign(msg_str)
            if not callsign: return None
            # очищаем позывной от лишних символов
            return ''.join(c for c in callsign if c.isalnum())
        return None
    except:
        return None

# вспомогательная функция для генерации метки формата сообщения
def get_format_label(msg_str, df):
    
    if df in [0, 4, 5, 11]:
        length_type = "S"
    elif df in [16, 17, 18, 19, 20, 21, 24]:
        length_type = "L"
    else:
        # если что-то не так, то пробуем сделать вывод по длине строки
        length_bits = len(msg_str) * 4
        if length_bits == 56:
            length_type = "S"
        elif length_bits == 112:
            length_type = "L"
        else:
            length_type = "?"
    
    label = f"DF{df}"
    return f"{label}({length_type})"

# класс для создания и управления окном с графиками
class IcaoGraphs:
    # конструктор класса, вызывается при создании объекта
    def __init__(self, alt_dict, spd_dict, pos_dict, course_dict, adsb_icao_list, icao_callsigns, 
                 icao_sel_alt, icao_alt_diff, icao_baro_correction, icao_gnss_alt,
                 icao_airborne_pos_ts, icao_surface_pos_ts, icao_ident_timestamps,
                 icao_speed_ts, icao_status_ts, icao_target_state_ts, icao_operation_status_ts,
                 icao_df11_ts):
        
        # собираем все icao, по которым есть какие-либо данные
        icao_with_data = set(alt_dict.keys()) | set(spd_dict.keys()) | set(pos_dict.keys()) | set(course_dict.keys()) | set(icao_gnss_alt.keys())
        icao_with_data = icao_with_data | set(icao_airborne_pos_ts.keys()) | set(icao_df11_ts.keys()) # учитывается DF11
        
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
        
        # Данные временных меток для построения гистограмм интервалов
        self.icao_airborne_pos_ts = icao_airborne_pos_ts
        self.icao_surface_pos_ts = icao_surface_pos_ts
        self.icao_ident_timestamps = icao_ident_timestamps
        self.icao_speed_ts = icao_speed_ts
        self.icao_status_ts = icao_status_ts
        self.icao_target_state_ts = icao_target_state_ts
        self.icao_operation_status_ts = icao_operation_status_ts
        self.icao_df11_ts = icao_df11_ts # Сохраняем DF11
        
        self.icao_index = 0
        
        # список доступных режимов (типов графиков), включая анализ интервалов
        self.plot_modes = ['all_tracks', 'altitude', 'gnss_altitude', 'speed', 'altitude_speed_combined', 'latitude', 'course', 'track', 'altitude_diff', 'baro_correction',
                           'df11_msg_intervals', # Новый режим графика
                           'reg05_msg_intervals', 'reg06_msg_intervals', 'reg08_msg_intervals', 
                           'reg09_msg_intervals', 'reg61_msg_intervals', 'reg62_msg_intervals', 'reg65_msg_intervals']
        
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
            'baro_correction': (950, 1050)
        }

        # создание окна и основной области для рисования
        self.fig, self.ax = plt.subplots(figsize=(12, 7))
        self.fig.canvas.manager.set_window_title('Графики бортов и анализ интервалов')
        plt.subplots_adjust(bottom=0.25) # оставляем место снизу для кнопок
        
        self.ax2 = None

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

        # Режим общей карты: отображение треков всех бортов одновременно
        if mode == 'all_tracks':
            title = "ОБЩАЯ КАРТА (Все обнаруженные треки)"
            
            if not self.pos_dict:
                 self.ax.text(0.5, 0.5, "В этом файле нет координат (GPS) ни для одного борта", 
                              ha='center', transform=self.ax.transAxes)
            else:
                # отрисовка треков всех бортов серым, а текущий выделяем красным
                for track_icao, track_data in self.pos_dict.items():
                    # фильтрация треков на карте так же, как и список бортов
                    if track_icao not in self.icao_list: continue

                    lons = [lon for t, lat, lon in track_data]
                    lats = [lat for t, lat, lon in track_data]
                    
                    if track_icao == icao:
                        self.ax.plot(lons, lats, 'o-', color='red', linewidth=2, markersize=4, 
                                     label=f"{display_id} (Выбран)", zorder=10)
                    else:
                        self.ax.plot(lons, lats, '-', color='grey', linewidth=1, alpha=0.6, zorder=1)

            self.ax.set_aspect('equal', adjustable='datalim')
            self.ax.set_xlabel("Долгота (°)")
            self.ax.set_ylabel("Широта (°)")

        # блок отрисовки графика высоты (барометрической)
        elif mode == 'altitude':
            data = self.alt_dict.get(icao)
            sel_data = self.sel_alt_dict.get(icao)
            title, label = f"Высота: {display_id}", "Высота (футы)"
            if not data and not sel_data:
                self.ax.text(0.5, 0.5, f"Нет данных о высоте для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                if data:
                    times = [timestamp_to_utc(t) for t, v in sorted(data)]
                    values = [v for t, v in sorted(data)]
                    self.ax.plot(times, values, 'o-', markersize=3, label='Барометрическая высота', color='blue')
                if sel_data:
                    times = [timestamp_to_utc(t) for t, v in sorted(sel_data)]
                    values = [v for t, v in sorted(sel_data)]
                    self.ax.step(times, values, where='post', label='Выбранная высота', color='red', linestyle='--')
        
        # блок отрисовки GNSS высоты (вычисляемой)
        elif mode == 'gnss_altitude':
            data = self.gnss_alt_dict.get(icao)
            baro_data = self.alt_dict.get(icao)
            title, label = f"GNSS (Geom) Высота: {display_id}", "Высота (футы)"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных GNSS высоты для {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                if baro_data:
                    times_b = [timestamp_to_utc(t) for t, v in sorted(baro_data)]
                    values_b = [v for t, v in sorted(baro_data)]
                    self.ax.plot(times_b, values_b, '-', color='blue', alpha=0.3, label='Баро (спр.)')
                
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='GNSS Высота', color='magenta')

        # блок отрисовки графика скорости
        elif mode == 'speed':
            data = self.spd_dict.get(icao)
            title, label = f"Скорость: {display_id}", "Скорость (узлы)"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных о скорости для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='Скорость', color='green')

        # блок отрисовки комбинированного графика
        elif mode == 'altitude_speed_combined':
            title = f"Высота и скорость: {display_id}"
            alt_data = self.alt_dict.get(icao)
            spd_data = self.spd_dict.get(icao)
            
            if not alt_data and not spd_data:
                self.ax.text(0.5, 0.5, f"Нет данных о высоте и скорости для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                self.ax.set_ylabel("Высота (футы)", color='blue')
                self.ax.tick_params(axis='y', labelcolor='blue')
                self.ax2 = self.ax.twinx() 
                self.ax2.set_ylabel("Скорость (узлы)", color='green')
                self.ax2.tick_params(axis='y', labelcolor='green')

                lines1, labels1, lines2, labels2 = [], [], [], []
                if alt_data:
                    alt_times = [timestamp_to_utc(t) for t, v in sorted(alt_data)]
                    alt_values = [v for t, v in sorted(alt_data)]
                    line, = self.ax.plot(alt_times, alt_values, 'o-', markersize=3, label='Высота', color='blue')
                    lines1.append(line)
                    labels1.append('Высота')
                if spd_data:
                    spd_times = [timestamp_to_utc(t) for t, v in sorted(spd_data)]
                    spd_values = [v for t, v in sorted(spd_data)]
                    line, = self.ax2.plot(spd_times, spd_values, 'o-', markersize=3, label='Скорость', color='green')
                    lines2.append(line)
                    labels2.append('Скорость')
                
                self.ax.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        # блок отрисовки графика широты
        elif mode == 'latitude':
            data = self.pos_dict.get(icao)
            title, label = f"Координаты: {display_id}", "Широта (°)"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных о координатах для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                times = [timestamp_to_utc(t) for t, lat, lon in data]
                lats = [lat for t, lat, lon in data]
                self.ax.plot(times, lats, 'o-', markersize=3, label='Широта', color='orange')

        # блок отрисовки графика курса
        elif mode == 'course':
            data = self.course_dict.get(icao)
            title, label = f"Курс: {display_id}", "Курс (°)"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных о курсе для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='Курс', color='purple')

        # блок отрисовки трека полёта (карты) для одного борта
        elif mode == 'track':
            data = self.pos_dict.get(icao)
            title = f"Схема трека полёта: {display_id}"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных о координатах для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                lons = [lon for t, lat, lon in data]
                lats = [lat for t, lat, lon in data]
                self.ax.plot(lons, lats, 'o', markersize=2, label='Трек')

        # блок отрисовки разницы высот
        elif mode == 'altitude_diff':
            data = self.alt_diff_dict.get(icao)
            title, label = f"Разница высот (Выбранная - Baro): {display_id}", "Разница (футы)"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных о разнице высот для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='Разница (GNSS - Baro)', color='red')
                self.ax.axhline(y=0, color='gray', linestyle='--', alpha=0.7)

        # блок отрисовки барокоррекции
        elif mode == 'baro_correction':
            data = self.baro_correction_dict.get(icao)
            title, label = f"Барокоррекция: {display_id}", "Давление (гПа)"
            if not data:
                self.ax.text(0.5, 0.5, f"Нет данных о барокоррекции для борта {icao}", 
                             ha='center', va='center', transform=self.ax.transAxes)
            else:
                times = [timestamp_to_utc(t) for t, v in sorted(data)]
                values = [v for t, v in sorted(data)]
                self.ax.plot(times, values, 'o-', markersize=3, label='Барокоррекция', color='brown')
                self.ax.axhline(y=1013.25, color='green', linestyle='--', alpha=0.7, label='Стандартное давление (1013.25 гПа)')

        # Обработка режимов гистограмм (вызов вспомогательной функции)
        elif mode.endswith('_msg_intervals'):
            self._plot_histogram(mode, icao, display_id)
            return

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
            if mode != 'altitude_speed_combined':
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

    # вспомогательная функция для построения гистограмм интервалов сообщений
    def _plot_histogram(self, mode, icao, display_id):
        data_source = None
        color_bar = 'blue'
        color_out = 'mediumblue'
        center, dev = 500, 100
        title_text = ""

        # Выбор источника данных и параметров в зависимости от режима
        if mode == 'df11_msg_intervals':
            data_source = self.icao_df11_ts.get(icao)
            title_text = f"DF11 (Сквиттер захвата): {display_id}"
            color_bar, color_out = 'gray', 'black'
            center = 1000 
            dev = 200 # +/- 200 мс (окно 400 мс)
        elif mode == 'reg05_msg_intervals':
            data_source = self.icao_airborne_pos_ts.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера местоположения в воздухе (REG05): {display_id}"
            color_bar, color_out = 'blue', 'mediumblue'
            center, dev = 500, 100
        elif mode == 'reg06_msg_intervals':
            data_source = self.icao_surface_pos_ts.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера местоположения на земле (REG06): {display_id}"
            color_bar, color_out = 'red', 'firebrick'
            center, dev = 500, 100
        elif mode == 'reg08_msg_intervals':
            data_source = self.icao_ident_timestamps.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера опознавательного кода (REG08): {display_id}"
            color_bar, color_out = 'cyan', 'skyblue'
            center = 5000 
            dev = 200 # +/- 200 мс (окно 400 мс)
        elif mode == 'reg09_msg_intervals':
            data_source = self.icao_speed_ts.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера скорости (REG09): {display_id}"
            color_bar, color_out = 'lime', 'mediumseagreen'
            center, dev = 500, 100
        elif mode == 'reg61_msg_intervals':
            data_source = self.icao_status_ts.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера статуса (REG61): {display_id}"
            color_bar, color_out = 'darkviolet', 'indigo'
            center = 5000
            dev = 200 # +/- 200 мс (окно 400 мс)
        elif mode == 'reg62_msg_intervals':
            data_source = self.icao_target_state_ts.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера состояния и статуса цели (REG62): {display_id}"
            color_bar, color_out = 'gold', 'darkorange'
            center = 1250 
        elif mode == 'reg65_msg_intervals':
            data_source = self.icao_operation_status_ts.get(icao)
            title_text = f"Распределение интервалов сообщений сквиттера эксплуатационного статуса (REG65): {display_id}"
            color_bar, color_out = 'mediumaquamarine', 'lightseagreen'
            center = 2500

        self.ax.set_ylabel('Количество')
        self.ax.grid(True, linestyle='--', alpha=0.7)

        # проверка наличия достаточного количества данных
        if not data_source or len(data_source) < 2:
            self.ax.set_title(title_text)
            self.ax.text(0.5, 0.5, "Недостаточно данных для гистограммы", 
                         ha='center', va='center', transform=self.ax.transAxes)
            self.fig.canvas.draw_idle()
            return

        # расчёт интервалов между сообщениями
        timestamps = np.array(sorted(data_source))
        intervals = np.diff(timestamps) * 1000
        intervals = intervals[intervals >= 0]

        if len(intervals) == 0:
            self.ax.set_title(title_text)
            self.ax.text(0.5, 0.5, "Нет валидных интервалов", ha='center', va='center', transform=self.ax.transAxes)
            self.fig.canvas.draw_idle()
            return
        
        # Статистика min/max для заголовка
        min_val = np.min(intervals)
        max_val = np.max(intervals)
        
        full_title = f"{title_text}\nМин: {min_val:.1f} мс, Макс: {max_val:.1f} мс, Цель: {center} мс"
        self.ax.set_title(full_title)
        self.ax.set_xlabel('Интервал между сообщениями (мс)')

        # настройка бинов и разделение данных на группы
        num_bins = 10
        low = center - dev
        high = center + dev

        middle = intervals[(intervals >= low) & (intervals <= high)]
        left = intervals[intervals < low]
        right = intervals[intervals > high]
        
        bar_width = (high - low) / num_bins

        # отрисовка основного диапазона и "хвостов"
        self.ax.hist(middle, bins=np.linspace(low, high, num_bins + 1),
                     alpha=0.6, color=color_bar, edgecolor='black', 
                     label=f"В диапазоне ({low}-{high}): {len(middle)}")

        # Левый хвост (слишком частые)
        if len(left) > 0:
            self.ax.bar(low - bar_width, len(left), width=bar_width, align='edge',
                        color=color_out, edgecolor='black', hatch='//', label=f"Слишком частые (<{low}): {len(left)}")
            
            # Анализ левого хвоста (топ значений)
            counts, bins = np.histogram(left, bins=5)
            
            # Упрощение: вместо сложной сортировки numpy, сделаем более понятный список
            bin_data = []
            for i in range(len(counts)):
                # сохраняем пару: (количество, индекс)
                bin_data.append((counts[i], i))
            
            # сортируем по количеству (по убыванию)
            bin_data.sort(key=lambda x: x[0], reverse=True)
            
            # берем топ 3
            left_stats = []
            for count, idx in bin_data[:3]:
                if count > 0:
                    bin_center = (bins[idx] + bins[idx+1]) / 2
                    left_stats.append(f"~{bin_center:.0f}ms: {count}")
            
            if left_stats:
                info_text = "Частые 'быстрые':\n" + "\n".join(left_stats)
                self.ax.text(0.02, 0.95, info_text, transform=self.ax.transAxes, 
                             verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        # Правый хвост (пропуски)
        if len(right) > 0:
            self.ax.bar(high, len(right), width=bar_width, align='edge',
                        color=color_out, edgecolor='black', label=f"Слишком редкие (>{high}): {len(right)}")

        self.ax.set_xlim(low - bar_width * 2, high + bar_width * 2)
        self.ax.axvline(low, linestyle='--', color='black', alpha=0.8)
        self.ax.axvline(high, linestyle='--', color='black', alpha=0.8)
        
        self.ax.legend(loc='upper right')
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
        elif mode.endswith('_msg_intervals'):
            pass 
        else:
            # стандартное масштабирование по оси Y
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

# Функция выбора файла
def choose_input_file(cli_file: str | None) -> list[Path]:
    # если файл передан через аргументы, проверяем его наличие
    if cli_file:
        path = Path(cli_file)
        if not path.exists():
            raise FileNotFoundError(f"Файл {path} не найден")
        return [path]

    # иначе ищем файлы в папке по умолчанию
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Папка {DATA_DIR} не существует")

    files = sorted(DATA_DIR.glob(f"*{DEFAULT_LOG_EXTENSION}"))
    if not files:
        raise FileNotFoundError(
            f"В папке {DATA_DIR} нет файлов {DEFAULT_LOG_EXTENSION}"
        )

    return files

# --- MAIN ---
if __name__ == '__main__':
    # парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description="Анализ ADS-B данных")
    parser.add_argument("-f", "--file", help="Имя входного файла (по умолчанию ищется в папке data)", default=None)
    parser.add_argument("-a", "--aircraft", help="ICAO адрес конкретного борта")
    args = parser.parse_args()

    target_icao = args.aircraft.upper() if args.aircraft else None

    # выбор файла для анализа
    try:
        files_to_process = choose_input_file(args.file)
    except FileNotFoundError as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

    for file_path in files_to_process:
        # инициализация словарей для хранения данных
        icao_times = {}
        icao_altitude = {} # Барометрическая высота
        icao_gnss_altitude = {} # ГНСС (барометрическая + разность)
        icao_speed = {}
        icao_callsigns = {}
        icao_selected_altitude = {}
        icao_altitude_difference = {}
        icao_baro_correction = {}
        icao_has_selected_alt = {}
        adsb_icao_list = set()
        icao_positions = {}
        icao_courses = {}
        cpr_messages = {}
        icao_dfs = {} 

        # словари для временных меток (для гистограмм)
        icao_airborne_pos_ts = {}
        icao_surface_pos_ts = {}
        icao_ident_timestamps = {}
        icao_speed_ts = {}
        icao_status_ts = {}
        icao_target_state_ts = {}
        icao_operation_status_ts = {}
        icao_df11_ts = {} # Добавлено для DF11

        current_baro_buffer = {} 

        try:
            print(f"Файл: {file_path}")
            # чтение файла построчно
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip(): continue # пропуск пустых строк
                    parsed = parse_ads_b_line(line)
                    if parsed is None: continue
                    msg, message_spaced, message_str = parsed

                    try:
                        aa = pms.icao(message_str)
                        df = pms.df(message_str)
                    except Exception:
                        continue 

                    if target_icao and aa != target_icao: continue

                    adsb_icao_list.add(aa)
                    
                    # сбор статистики по форматам сообщений (DF)
                    fmt_label = get_format_label(message_str, df)
                    icao_dfs.setdefault(aa, set()).add(fmt_label)

                    # обновление времени первого/последнего сообщения
                    if aa not in icao_times:
                        icao_times[aa] = {"first": msg.timestamp, "last": msg.timestamp}
                    else:
                        icao_times[aa]["last"] = msg.timestamp
                    
                    # Сбор DF11 
                    if df == 11:
                        icao_df11_ts.setdefault(aa, []).append(msg.timestamp)

                    try:
                        # попытка извлечения высоты из любого доступного DF
                        alt = get_altitude_any_df(message_str, df)
                        if alt is not None and -2000 <= alt <= 60000:
                             icao_altitude.setdefault(aa, []).append((msg.timestamp, alt))
                             current_baro_buffer[aa] = (msg.timestamp, alt)
                        
                        # извлечение Squawk кода
                        sq = get_squawk(message_str, df)
                        if sq:
                            icao_callsigns[f"{aa}_sq"] = sq

                        # обработка ADS-B сообщений (DF17/18)
                        if df in [17, 18]:
                            tc = pms.adsb.typecode(message_str)
                            
                            # сбор данных для гистограмм
                            if (9 <= tc <= 18) or (20 <= tc <= 22):
                                icao_airborne_pos_ts.setdefault(aa, []).append(msg.timestamp)
                            if 5 <= tc <= 8:
                                icao_surface_pos_ts.setdefault(aa, []).append(msg.timestamp)
                            if 1 <= tc <= 4:
                                icao_ident_timestamps.setdefault(aa, []).append(msg.timestamp)
                            if tc == 19:
                                icao_speed_ts.setdefault(aa, []).append(msg.timestamp)
                            if tc == 28:
                                icao_status_ts.setdefault(aa, []).append(msg.timestamp)
                            if tc == 29:
                                icao_target_state_ts.setdefault(aa, []).append(msg.timestamp)
                            if tc == 31:
                                icao_operation_status_ts.setdefault(aa, []).append(msg.timestamp)

                            # декодирование координат (CPR)
                            if 9 <= tc <= 18:
                                cpr_messages.setdefault(aa, [None, None])
                                oe_flag = pms.adsb.oe_flag(message_str)
                                cpr_messages[aa][oe_flag] = (message_str, msg.timestamp)
                                # если есть оба сообщения (чет/нечет) в пределах 10 сек
                                if all(cpr_messages[aa]):
                                    msg0, t0 = cpr_messages[aa][0]
                                    msg1, t1 = cpr_messages[aa][1]
                                    if abs(t0 - t1) < 10: # если прошло не больше 10 секунд
                                        pos = pms.adsb.position(msg0, msg1, t0, t1)
                                        if pos:
                                            icao_positions.setdefault(aa, []).append((msg.timestamp, pos[0], pos[1]))
                                        cpr_messages[aa] = [None, None]
                            
                            # декодирование скорости и курса
                            elif tc == 19:
                                gs = get_velocity(message_str)
                                if gs is not None:
                                    icao_speed.setdefault(aa, []).append((msg.timestamp, gs))
                                course = get_course(message_str)
                                if course is not None:
                                    icao_courses.setdefault(aa, []).append((msg.timestamp, course))
                                
                                # расчет GNSS высоты на основе баро и разницы высот
                                alt_diff = get_altitude_difference(message_str)
                                if alt_diff is not None:
                                    icao_altitude_difference.setdefault(aa, []).append((msg.timestamp, alt_diff))
                                    
                                    if aa in current_baro_buffer:
                                        last_ts, last_baro = current_baro_buffer[aa]
                                        if abs(msg.timestamp - last_ts) < 5.0:
                                            gnss_alt = last_baro + alt_diff
                                            icao_gnss_altitude.setdefault(aa, []).append((msg.timestamp, gnss_alt))

                            # декодирование позывного (ICAO)
                            elif 1 <= tc <= 4:
                                cs = get_callsign(message_str)
                                if cs: icao_callsigns[aa] = cs

                            # декодирование параметров автопилота
                            elif tc == 29:
                                sel_alt = get_selected_altitude(message_str)
                                if sel_alt:
                                    sel_alt_value, modes = sel_alt
                                    icao_selected_altitude.setdefault(aa, []).append((msg.timestamp, sel_alt_value))
                                    icao_has_selected_alt[aa] = True
                                    modes_key = f"{aa}_modes"
                                    existing_modes = icao_callsigns.get(modes_key, set())
                                    icao_callsigns[modes_key] = existing_modes.union(modes)
                                
                                baro_corr = get_baro_correction(message_str)
                                if baro_corr is not None:
                                    icao_baro_correction.setdefault(aa, []).append((msg.timestamp, baro_corr))
                                    
                    except Exception:
                        continue

            total_icao_count = len(adsb_icao_list)
            
            # Оставляем только те борта, у которых был хоть один ADS-B пакет
            # борта, передающие только DF16 или другие Mode S без координат, исключаются
            filtered_icao_list = set()
            for icao in adsb_icao_list:
                 # получаем набор форматов для этого борта
                 dfs = icao_dfs.get(icao, set())
                 # проверяем, есть ли DF17 или DF18 (это ADS-B)
                 has_adsb = False
                 for label in dfs:
                     if "DF17" in label or "DF18" in label:
                         has_adsb = True
                         break
                
                 if has_adsb:
                     filtered_icao_list.add(icao)
            
            adsb_icao_list = filtered_icao_list
            filtered_count = total_icao_count - len(adsb_icao_list)

            # вывод сводной таблицы результатов
            print("=" * 155)
            print(" "*65 + "СВОДНАЯ ТАБЛИЦА")
            print("=" * 155)
            print(f"{'ICAO':<8} {'Рейс':<12} {'Формат':<24} {'Первое (UTC)':<35} {'Последнее (UTC)':<30} {'POS':<5} {'HDG':<5} {'SEL':<5} {'DIF':<5} {'BAR':<5} {'GNS':<5}")
            print("-" * 155)

            for icao in sorted(list(adsb_icao_list)):
                if icao not in icao_times: continue
                times = icao_times[icao]
                
                ts_first = times["first"]
                ts_last = times["last"]
                
                dt_first = datetime.fromtimestamp(int(ts_first), tz=timezone.utc)
                dt_last = datetime.fromtimestamp(int(ts_last), tz=timezone.utc)
                
                first_utc_str = format_timestamp_with_nanoseconds(ts_first)
                
                # если дата совпадает, выводим только время последнего сообщения
                if dt_first.date() == dt_last.date():
                    main_dt_str = dt_last.strftime('%H:%M:%S')
                    ts_str = f"{ts_last:.9f}"
                    nanoseconds_str = ts_str.split('.')[1]
                    last_utc_str = f"{main_dt_str}.{nanoseconds_str}"
                else:
                    last_utc_str = format_timestamp_with_nanoseconds(ts_last)
                
                callsign = icao_callsigns.get(icao, "N/A")
                squawk = icao_callsigns.get(f"{icao}_sq", "")
                if callsign == "N/A" and squawk:
                    callsign = f"SQ:{squawk}"
                
                my_dfs = sorted(list(icao_dfs.get(icao, set())))
                dfs_str = ",".join(my_dfs)
                if len(dfs_str) > 22: dfs_str = dfs_str[:19] + "..."

                # флаги наличия данных
                pos_flag = "+" if icao in icao_positions and icao_positions[icao] else "-"
                hdg_flag = "+" if icao in icao_courses and icao_courses[icao] else "-"
                sel_flag = "+" if icao_has_selected_alt.get(icao) else "-"
                dif_flag = "+" if icao in icao_altitude_difference and icao_altitude_difference[icao] else "-"
                bar_flag = "+" if icao in icao_baro_correction and icao_baro_correction[icao] else "-"
                gnss_flag = "+" if icao in icao_gnss_altitude and icao_gnss_altitude[icao] else "-"

                print(f"{icao:<8} {callsign:<12} {dfs_str:<24} {first_utc_str:<35} {last_utc_str:<30} {pos_flag:<5} {hdg_flag:<5} {sel_flag:<5} {dif_flag:<5} {bar_flag:<5} {gnss_flag:<5}")
                
            print(f"\nВсего бортов обнаружено: {total_icao_count}")
            print(f"Отфильтровано (без ADS-B): {filtered_count}")
            print(f"Осталось бортов (ADS-B): {len(adsb_icao_list)}\n")

            # запуск визуализации
            IcaoGraphs(icao_altitude, icao_speed, icao_positions, icao_courses, adsb_icao_list, icao_callsigns, 
                       icao_selected_altitude, icao_altitude_difference, icao_baro_correction, icao_gnss_altitude,
                       icao_airborne_pos_ts, icao_surface_pos_ts, icao_ident_timestamps,
                       icao_speed_ts, icao_status_ts, icao_target_state_ts, icao_operation_status_ts,
                       icao_df11_ts)

        except FileNotFoundError:
            print(f"Файл {file_path} не найден")
        except Exception as e:
            print(f"Произошла критическая ошибка: {e}")
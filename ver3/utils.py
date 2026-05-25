import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import sys
from config import DATA_DIR, DEFAULT_LOG_EXTENSION

# функция конвертирует unix timestamp в объект datetime
def timestamp_to_utc(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)

# функция форматирует время, сохраняя наносекунды для точности
def format_timestamp_with_nanoseconds(ts):
    main_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    main_dt_str = main_dt.strftime('%Y-%m-%d %H:%M:%S')
    ts_str = f"{ts:.9f}"
    nanoseconds_str = ts_str.split('.')[1]
    return f"{main_dt_str}.{nanoseconds_str}"

# Функция выбора файла
def choose_input_file(cli_file: str | None) -> list[Path]:
    if cli_file:
        path = Path(cli_file)
        if not path.exists():
            raise FileNotFoundError(f"Файл {path} не найден")
        return [path]

    if not DATA_DIR.exists():
        raise FileNotFoundError(f"Папка {DATA_DIR} не существует")

    files = sorted(DATA_DIR.glob(f"*{DEFAULT_LOG_EXTENSION}"))
    if not files:
        raise FileNotFoundError(
            f"В папке {DATA_DIR} нет файлов {DEFAULT_LOG_EXTENSION}"
        )
    return [files[0]]

class AnomalyDetector:
    def __init__(self, 
                 alt_diff_threshold=500,     # порог разницы высот (фт)
                 nic_threshold=6,            # порог NIC
                 min_duration=5.0,           # минимальная длительность аномалии (сек)
                 max_speed_kt=1200,          # максимальная реалистичная скорость (узлы) ~ 2200 км/ч
                 max_accel_kt_per_sec=200,   # максимальное ускорение (узлы/сек)
                 max_heading_change=180,     # максимальное изменение курса за 1 сек (градусы)
                 max_alt_change_per_sec=2000, # максимальное изменение высоты за 1 сек (фт)
                 max_pos_jump_m=5000,         # максимальный скачок координат (метры)
                 correlation_window=3.0      # окно для корреляции аномалий (сек)
                 ):
        
        self.alt_diff_threshold = alt_diff_threshold
        self.nic_threshold = nic_threshold
        self.min_duration = min_duration
        self.max_speed_kt = max_speed_kt
        self.max_accel_kt_per_sec = max_accel_kt_per_sec
        self.max_heading_change = max_heading_change
        self.max_alt_change_per_sec = max_alt_change_per_sec
        self.max_pos_jump_m = max_pos_jump_m
        self.correlation_window = correlation_window

    def _to_dataframe(self, data_list):
        """Преобразует список (timestamp, value) в pandas DataFrame с индексом по времени (float секунды)"""
        if not data_list:
            return pd.DataFrame()
        df = pd.DataFrame(data_list, columns=['timestamp', 'value'])
        df = df.drop_duplicates(subset='timestamp')
        df = df.set_index('timestamp').sort_index()
        return df

    def _detect_sustained_anomaly(self, df, column, threshold, condition='below'):
        """Обнаружение аномалии, длящейся не менее min_duration секунд.
           df.index - float (timestamp в секундах)"""
        if df.empty:
            return []
        
        if condition == 'below':
            mask = df[column] < threshold
        elif condition == 'above':
            mask = df[column] > threshold
        else:
            return []
        
        # Находим интервалы, где условие выполняется непрерывно
        changes = mask.astype(int).diff()
        starts = changes[changes == 1].index
        ends = changes[changes == -1].index
        
        if mask.iloc[0]:
            starts = starts.union([df.index[0]])
        if mask.iloc[-1]:
            ends = ends.union([df.index[-1]])
        
        intervals = []
        for start, end in zip(starts, ends):
            duration = end - start   # разница в секундах (float)
            if duration >= self.min_duration:
                intervals.append((start, end, duration))
        
        return intervals

    def _detect_kinematic_anomalies(self, icao, pos_data, speed_data, course_data, alt_data):
        """Обнаружение физически невозможных перемещений"""
        anomalies = []
        
        # 1. Аномалии скорости и ускорения
        if speed_data:
            df_speed = self._to_dataframe(speed_data)
            if len(df_speed) > 1:
                # Скорость выше порога
                speed_mask = df_speed['value'] > self.max_speed_kt
                for ts in speed_mask[speed_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'Невероятная скорость: {df_speed.loc[ts, "value"]:.0f} узлов (> {self.max_speed_kt})'
                    })
                
                # Аномальное ускорение (разность скоростей / время)
                df_speed['delta_v'] = df_speed['value'].diff()
                time_diff = df_speed.index.to_series().diff()   # числовая разница в секундах
                df_speed['accel'] = df_speed['delta_v'] / time_diff
                accel_mask = df_speed['accel'].abs() > self.max_accel_kt_per_sec
                for ts in accel_mask[accel_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'Аномальное ускорение: {df_speed.loc[ts, "accel"]:.0f} уз/сек'
                    })
        
        # 2. Аномалии курса (резкий разворот)
        if course_data:
            df_course = self._to_dataframe(course_data)
            if len(df_course) > 1:
                df_course['delta_heading'] = df_course['value'].diff().abs()
                # Нормализуем разницу курса (360 -> 0)
                df_course['delta_heading'] = df_course['delta_heading'].apply(lambda x: min(x, 360 - x))
                time_diff = df_course.index.to_series().diff()
                df_course['heading_rate'] = df_course['delta_heading'] / time_diff
                heading_mask = df_course['heading_rate'] > self.max_heading_change
                for ts in heading_mask[heading_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'Резкое изменение курса: {df_course.loc[ts, "heading_rate"]:.1f} град/сек'
                    })
        
        # 3. Аномалии высоты (скачок)
        if alt_data:
            df_alt = self._to_dataframe(alt_data)
            if len(df_alt) > 1:
                df_alt['delta_alt'] = df_alt['value'].diff()
                time_diff = df_alt.index.to_series().diff()
                df_alt['alt_rate'] = df_alt['delta_alt'].abs() / time_diff
                alt_mask = df_alt['alt_rate'] > self.max_alt_change_per_sec
                for ts in alt_mask[alt_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'Скачок высоты: {df_alt.loc[ts, "alt_rate"]:.0f} фт/сек'
                    })
        
        # 4. Скачки координат (если есть позиции)
        if pos_data:
            df_pos = pd.DataFrame(pos_data, columns=['timestamp', 'lat', 'lon'])
            df_pos = df_pos.drop_duplicates(subset='timestamp')
            df_pos = df_pos.set_index('timestamp').sort_index()
            if len(df_pos) > 1:
                from math import radians, sin, cos, sqrt, atan2
                def haversine(lon1, lat1, lon2, lat2):
                    R = 6371000  # метров
                    phi1, phi2 = radians(lat1), radians(lat2)
                    dphi = radians(lat2 - lat1)
                    dlambda = radians(lon2 - lon1)
                    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
                    c = 2 * atan2(sqrt(a), sqrt(1-a))
                    return R * c
                
                distances = []
                prev = None
                for ts, row in df_pos.iterrows():
                    if prev is not None:
                        dist = haversine(prev['lon'], prev['lat'], row['lon'], row['lat'])
                        distances.append((ts, dist))
                    prev = row
                
                if distances:
                    df_dist = pd.DataFrame(distances, columns=['timestamp', 'distance'])
                    df_dist = df_dist.set_index('timestamp')
                    time_diff = df_dist.index.to_series().diff()
                    df_dist['dist_rate'] = df_dist['distance'] / time_diff
                    jump_mask = df_dist['distance'] > self.max_pos_jump_m
                    for ts in jump_mask[jump_mask].index:
                        anomalies.append({
                            'time': ts,
                            'type': 'KINEMATIC',
                            'desc': f'Скачок координат: {df_dist.loc[ts, "distance"]:.0f} м'
                        })
        
        return anomalies

    def _detect_complex_anomalies(self, icao, alt_diff_data, nic_data, nacp_data, course_data):
        """Обнаружение комбинаций аномалий, усиливающих подозрение"""
        anomalies = []
        
        # Собираем все события во временной список
        events = []
        if alt_diff_data:
            for ts, val in alt_diff_data:
                if abs(val) > self.alt_diff_threshold:
                    events.append((ts, 'ALT_DIFF', val))
        if nic_data:
            for ts, val in nic_data:
                if val < self.nic_threshold:
                    events.append((ts, 'NIC_LOW', val))
        if nacp_data:
            for ts, val in nacp_data:
                if val < 6:   # NACp ниже 6 – плохая точность
                    events.append((ts, 'NACP_LOW', val))
        if course_data:
            df_course = self._to_dataframe(course_data)
            if len(df_course) > 1:
                df_course['delta'] = df_course['value'].diff().abs()
                df_course['delta'] = df_course['delta'].apply(lambda x: min(x, 360 - x))
                time_diff = df_course.index.to_series().diff()
                df_course['rate'] = df_course['delta'] / time_diff
                sudden = df_course[df_course['rate'] > self.max_heading_change/2]  # более мягкий порог
                for ts in sudden.index:
                    events.append((ts, 'SUDDEN_HEADING', sudden.loc[ts, 'rate']))
        
        if len(events) < 2:
            return []
        
        events.sort(key=lambda x: x[0])
        
        # Ищем окна, где в течение correlation_window секунд происходит несколько типов аномалий
        i = 0
        while i < len(events):
            window_start = events[i][0]
            window_end = window_start + self.correlation_window   # число секунд
            types_in_window = set()
            values = []
            j = i
            while j < len(events) and events[j][0] <= window_end:
                types_in_window.add(events[j][1])
                values.append(events[j][2] if len(events[j])>2 else None)
                j += 1
            if len(types_in_window) >= 2:
                type_str = ' + '.join(types_in_window)
                anomalies.append({
                    'time': window_start,
                    'type': 'COMPLEX',
                    'desc': f'Комплексная аномалия: {type_str} в течение {self.correlation_window} с'
                })
            i = j if j > i else i+1
        
        return anomalies

    def detect(self, icao, alt_diff_data, nic_data, pos_data=None, speed_data=None, course_data=None, alt_data=None, nacp_data=None):
        """
        Расширенный детектор аномалий.
        alt_diff_data, nic_data, pos_data, speed_data, course_data, alt_data, nacp_data - списки (timestamp, value)
        """
        all_anomalies = []
        
        # 1. Устойчивая аномалия разницы высот (спуфинг)
        df_alt_diff = self._to_dataframe(alt_diff_data)
        intervals = self._detect_sustained_anomaly(df_alt_diff, 'value', self.alt_diff_threshold, condition='above')
        for start, end, duration in intervals:
            mask = (df_alt_diff.index >= start) & (df_alt_diff.index <= end)
            mean_val = df_alt_diff.loc[mask, 'value'].mean()
            all_anomalies.append({
                'time': start,
                'type': 'SPOOFING',
                'desc': f'Устойчивая аномальная разница высот: средняя {mean_val:.0f} фт, длительность {duration:.1f} с'
            })
        
        # 2. Устойчивое падение NIC (джамминг/потеря целостности)
        df_nic = self._to_dataframe(nic_data)
        intervals = self._detect_sustained_anomaly(df_nic, 'value', self.nic_threshold, condition='below')
        for start, end, duration in intervals:
            mean_nic = df_nic.loc[(df_nic.index >= start) & (df_nic.index <= end), 'value'].mean()
            all_anomalies.append({
                'time': start,
                'type': 'JAMMING',
                'desc': f'Устойчивое падение NIC: средний {mean_nic:.1f}, длительность {duration:.1f} с'
            })
        
        # 3. Кинематические аномалии (физически невозможные движения)
        kin_anomalies = self._detect_kinematic_anomalies(icao, pos_data, speed_data, course_data, alt_data)
        all_anomalies.extend(kin_anomalies)
        
        # 4. Комплексные триггеры (корреляция нескольких параметров)
        complex_anomalies = self._detect_complex_anomalies(icao, alt_diff_data, nic_data, nacp_data, course_data)
        all_anomalies.extend(complex_anomalies)
        
        # Сортируем по времени
        all_anomalies.sort(key=lambda x: x['time'])
        return all_anomalies
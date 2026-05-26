import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import sys
from config import DATA_DIR, DEFAULT_LOG_EXTENSION


def timestamp_to_utc(timestamp):
    """конвертирует unix timestamp в объект datetime (utc)"""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def format_timestamp_with_nanoseconds(ts):
    """форматирует время, сохраняя наносекунды для точности"""
    main_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    main_dt_str = main_dt.strftime('%Y-%m-%d %H:%M:%S')
    ts_str = f"{ts:.9f}"
    nanoseconds_str = ts_str.split('.')[1]
    return f"{main_dt_str}.{nanoseconds_str}"


def choose_input_file(cli_file: str | None) -> list[Path]:
    """выбирает файл для обработки: либо из аргументов командной строки, либо первый в data"""
    if cli_file:
        path = Path(cli_file)
        if not path.exists():
            raise FileNotFoundError(f"файл {path} не найден")
        return [path]

    if not DATA_DIR.exists():
        raise FileNotFoundError(f"папка {DATA_DIR} не существует")

    files = sorted(DATA_DIR.glob(f"*{DEFAULT_LOG_EXTENSION}"))
    if not files:
        raise FileNotFoundError(
            f"в папке {DATA_DIR} нет файлов {DEFAULT_LOG_EXTENSION}"
        )
    return [files[0]]


class AnomalyDetector:
    def __init__(self,
                 alt_diff_threshold=500,
                 nic_threshold=6,
                 min_duration=5.0,
                 max_speed_kt=1200,
                 max_accel_kt_per_sec=200,
                 max_heading_change=180,
                 max_alt_change_per_sec=2000,
                 max_pos_jump_m=5000,
                 correlation_window=3.0,
                 dropout_gap_threshold=5.0,
                 speed_mismatch_percent=0.20,
                 min_speed_kts=30):
        """
        параметры детектора аномалий:
        alt_diff_threshold - порог разницы высот (фт)
        nic_threshold - порог nic
        min_duration - минимальная длительность аномалии (сек)
        max_speed_kt - максимальная реалистичная скорость (узлы)
        max_accel_kt_per_sec - максимальное ускорение (узлы/сек)
        max_heading_change - максимальное изменение курса за 1 сек (градусы)
        max_alt_change_per_sec - максимальное изменение высоты за 1 сек (фт)
        max_pos_jump_m - максимальный скачок координат (метры)
        correlation_window - окно для корреляции аномалий (сек)
        dropout_gap_threshold - максимальный допустимый перерыв в df17 (сек)
        speed_mismatch_percent - допустимое относительное отклонение скорости
        min_speed_kts - минимальная скорость для сравнения (узлы)
        """
        self.alt_diff_threshold = alt_diff_threshold
        self.nic_threshold = nic_threshold
        self.min_duration = min_duration
        self.max_speed_kt = max_speed_kt
        self.max_accel_kt_per_sec = max_accel_kt_per_sec
        self.max_heading_change = max_heading_change
        self.max_alt_change_per_sec = max_alt_change_per_sec
        self.max_pos_jump_m = max_pos_jump_m
        self.correlation_window = correlation_window
        self.dropout_gap_threshold = dropout_gap_threshold
        self.speed_mismatch_percent = speed_mismatch_percent
        self.min_speed_kts = min_speed_kts

    def _to_dataframe(self, data_list):
        """преобразует список (timestamp, value) в pandas dataframe с индексом по времени"""
        if not data_list:
            return pd.DataFrame()
        df = pd.DataFrame(data_list, columns=['timestamp', 'value'])
        df = df.drop_duplicates(subset='timestamp')
        df = df.set_index('timestamp').sort_index()
        return df

    def _detect_sustained_anomaly(self, df, column, threshold, condition='below'):
        """обнаружение аномалии, длящейся не менее min_duration секунд"""
        if df.empty:
            return []

        if condition == 'below':
            mask = df[column] < threshold
        elif condition == 'above':
            mask = df[column] > threshold
        else:
            return []

        changes = mask.astype(int).diff()
        starts = changes[changes == 1].index
        ends = changes[changes == -1].index

        if mask.iloc[0]:
            starts = starts.union([df.index[0]])
        if mask.iloc[-1]:
            ends = ends.union([df.index[-1]])

        intervals = []
        for start, end in zip(starts, ends):
            duration = end - start
            if duration >= self.min_duration:
                intervals.append((start, end, duration))

        return intervals

    def _detect_kinematic_anomalies(self, icao, pos_data, speed_data, course_data, alt_data):
        """обнаружение физически невозможных перемещений (векторизованные расчёты)"""
        anomalies = []

        # аномалии скорости и ускорения
        if speed_data:
            df_speed = self._to_dataframe(speed_data)
            if len(df_speed) > 1:
                speed_mask = df_speed['value'] > self.max_speed_kt
                for ts in speed_mask[speed_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'невероятная скорость: {df_speed.loc[ts, "value"]:.0f} узлов (> {self.max_speed_kt})'
                    })

                df_speed['delta_v'] = df_speed['value'].diff()
                time_diff = df_speed.index.to_series().diff()
                df_speed['accel'] = df_speed['delta_v'] / time_diff
                accel_mask = df_speed['accel'].abs() > self.max_accel_kt_per_sec
                for ts in accel_mask[accel_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'аномальное ускорение: {df_speed.loc[ts, "accel"]:.0f} уз/сек'
                    })

        # аномалии курса
        if course_data:
            df_course = self._to_dataframe(course_data)
            if len(df_course) > 1:
                df_course['delta_heading'] = df_course['value'].diff().abs()
                df_course['delta_heading'] = df_course['delta_heading'].apply(lambda x: min(x, 360 - x))
                time_diff = df_course.index.to_series().diff()
                df_course['heading_rate'] = df_course['delta_heading'] / time_diff
                heading_mask = df_course['heading_rate'] > self.max_heading_change
                for ts in heading_mask[heading_mask].index:
                    anomalies.append({
                        'time': ts,
                        'type': 'KINEMATIC',
                        'desc': f'резкое изменение курса: {df_course.loc[ts, "heading_rate"]:.1f} град/сек'
                    })

        # аномалии высоты
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
                        'desc': f'скачок высоты: {df_alt.loc[ts, "alt_rate"]:.0f} фт/сек'
                    })

        # скачки координат (векторизованный расчёт)
        if pos_data:
            df_pos = pd.DataFrame(pos_data, columns=['timestamp', 'lat', 'lon'])
            df_pos = df_pos.drop_duplicates(subset='timestamp')
            df_pos = df_pos.set_index('timestamp').sort_index()
            if len(df_pos) > 1:
                R = 6371000
                lat1 = np.radians(df_pos['lat'].values[:-1])
                lat2 = np.radians(df_pos['lat'].values[1:])
                dlat = lat2 - lat1
                dlon = np.radians(df_pos['lon'].values[1:] - df_pos['lon'].values[:-1])

                a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
                c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
                distances = R * c

                timestamps = df_pos.index[1:]
                for ts, dist in zip(timestamps, distances):
                    if dist > self.max_pos_jump_m:
                        anomalies.append({
                            'time': ts,
                            'type': 'KINEMATIC',
                            'desc': f'скачок координат: {dist:.0f} м'
                        })

        return anomalies

    def _detect_complex_anomalies(self, icao, alt_diff_data, nic_data, nacp_data, course_data):
        """обнаружение комбинаций аномалий (одновременно несколько типов)"""
        anomalies = []

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
                if val < 6:
                    events.append((ts, 'NACP_LOW', val))
        if course_data:
            df_course = self._to_dataframe(course_data)
            if len(df_course) > 1:
                df_course['delta'] = df_course['value'].diff().abs()
                df_course['delta'] = df_course['delta'].apply(lambda x: min(x, 360 - x))
                time_diff = df_course.index.to_series().diff()
                df_course['rate'] = df_course['delta'] / time_diff
                sudden = df_course[df_course['rate'] > self.max_heading_change/2]
                for ts in sudden.index:
                    events.append((ts, 'SUDDEN_HEADING', sudden.loc[ts, 'rate']))

        if len(events) < 2:
            return []

        events.sort(key=lambda x: x[0])

        i = 0
        while i < len(events):
            window_start = events[i][0]
            window_end = window_start + self.correlation_window
            types_in_window = set()
            j = i
            while j < len(events) and events[j][0] <= window_end:
                types_in_window.add(events[j][1])
                j += 1
            if len(types_in_window) >= 2:
                type_str = ' + '.join(types_in_window)
                anomalies.append({
                    'time': window_start,
                    'type': 'COMPLEX',
                    'desc': f'комплексная аномалия: {type_str} в течение {self.correlation_window} с'
                })
            i = j if j > i else i+1

        return anomalies

    def _detect_dropouts(self, messages):
        """
        ищет пропуски сообщений с координатами (df17/18), пока идут другие пакеты
        messages: список (timestamp, df)
        """
        if not messages:
            return []
        anomalies = []
        pos_msgs = [(ts, df) for ts, df in messages if df in (17, 18)]
        other_msgs = [(ts, df) for ts, df in messages if df not in (17, 18)]

        if len(pos_msgs) < 2:
            return []

        pos_times = [ts for ts, _ in pos_msgs]
        for i in range(1, len(pos_times)):
            gap = pos_times[i] - pos_times[i-1]
            if gap > self.dropout_gap_threshold:
                start_gap = pos_times[i-1]
                end_gap = pos_times[i]
                other_in_gap = any(start_gap <= ts <= end_gap for ts, _ in other_msgs)
                if other_in_gap:
                    anomalies.append({
                        'time': start_gap,
                        'type': 'DROPOUT',
                        'severity': 'high',
                        'desc': f'пропуск координатных сообщений (df17/18) на {gap:.1f} сек, хотя другие df продолжали поступать'
                    })
        return anomalies

    def _detect_speed_mismatch(self, speed_data, pos_data):
        """
        сравнивает заявленную путевую скорость (gs) со скоростью, вычисленной по координатам
        """
        if not speed_data or not pos_data or len(pos_data) < 2:
            return []

        pos_list = sorted(pos_data, key=lambda x: x[0])
        speed_list = sorted(speed_data, key=lambda x: x[0])
        anomalies = []

        def haversine_distance(lat1, lon1, lat2, lon2):
            R = 6371000
            phi1 = np.radians(lat1)
            phi2 = np.radians(lat2)
            dphi = np.radians(lat2 - lat1)
            dlambda = np.radians(lon2 - lon1)
            a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            return R * c

        for ts_spd, gs_spd in speed_list:
            idx = np.searchsorted([p[0] for p in pos_list], ts_spd)
            if idx == 0 or idx == len(pos_list):
                continue
            ts_prev, lat_prev, lon_prev = pos_list[idx-1]
            ts_next, lat_next, lon_next = pos_list[idx]
            if ts_next - ts_prev < 1e-6:
                continue
            dist_m = haversine_distance(lat_prev, lon_prev, lat_next, lon_next)
            time_s = ts_next - ts_prev
            speed_mps = dist_m / time_s
            speed_kts = speed_mps * 1.94384

            if gs_spd < self.min_speed_kts or speed_kts < self.min_speed_kts:
                continue
            rel_diff = abs(gs_spd - speed_kts) / max(gs_spd, speed_kts)
            if rel_diff > self.speed_mismatch_percent:
                anomalies.append({
                    'time': ts_spd,
                    'type': 'SPEED_MISMATCH',
                    'severity': 'critical',
                    'desc': f'несоответствие скоростей: заявлено {gs_spd:.0f} уз, по координатам {speed_kts:.0f} уз (отн. {rel_diff:.1%})'
                })
        return anomalies

    def detect(self, icao, alt_diff_data, nic_data, pos_data=None, speed_data=None,
               course_data=None, alt_data=None, nacp_data=None, messages=None):
        """
        основной метод детектора: собирает все аномалии из разных подпроверок
        """
        all_anomalies = []

        # устойчивая аномалия разницы высот
        df_alt_diff = self._to_dataframe(alt_diff_data)
        intervals = self._detect_sustained_anomaly(df_alt_diff, 'value', self.alt_diff_threshold, condition='above')
        for start, end, duration in intervals:
            mask = (df_alt_diff.index >= start) & (df_alt_diff.index <= end)
            mean_val = df_alt_diff.loc[mask, 'value'].mean()
            all_anomalies.append({
                'time': start,
                'type': 'SPOOFING',
                'severity': 'critical',
                'desc': f'устойчивая аномальная разница высот: средняя {mean_val:.0f} фт, длительность {duration:.1f} с'
            })

        # устойчивое падение nic
        df_nic = self._to_dataframe(nic_data)
        intervals = self._detect_sustained_anomaly(df_nic, 'value', self.nic_threshold, condition='below')
        for start, end, duration in intervals:
            mean_nic = df_nic.loc[(df_nic.index >= start) & (df_nic.index <= end), 'value'].mean()
            severity = 'warning' if mean_nic >= 4 else 'critical'
            all_anomalies.append({
                'time': start,
                'type': 'JAMMING',
                'severity': severity,
                'desc': f'устойчивое падение nic: средний {mean_nic:.1f}, длительность {duration:.1f} с'
            })

        # кинематические аномалии
        kin_anomalies = self._detect_kinematic_anomalies(icao, pos_data, speed_data, course_data, alt_data)
        for anom in kin_anomalies:
            anom['severity'] = 'critical'
        all_anomalies.extend(kin_anomalies)

        # комплексные триггеры
        complex_anomalies = self._detect_complex_anomalies(icao, alt_diff_data, nic_data, nacp_data, course_data)
        for anom in complex_anomalies:
            anom['severity'] = 'warning'
        all_anomalies.extend(complex_anomalies)

        # пропуски df17/18
        if messages:
            dropout_anomalies = self._detect_dropouts(messages)
            all_anomalies.extend(dropout_anomalies)

        # несоответствие скоростей
        if speed_data and pos_data:
            mismatch_anomalies = self._detect_speed_mismatch(speed_data, pos_data)
            all_anomalies.extend(mismatch_anomalies)

        all_anomalies.sort(key=lambda x: x['time'])
        return all_anomalies
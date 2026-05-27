import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import sys
from config import DATA_DIR, DEFAULT_LOG_EXTENSION

# -------------------------- вспомогательные функции --------------------------
def timestamp_to_utc(timestamp):
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)

def format_timestamp_with_nanoseconds(ts):
    main_dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    main_dt_str = main_dt.strftime('%Y-%m-%d %H:%M:%S')
    ts_str = f"{ts:.9f}"
    nanoseconds_str = ts_str.split('.')[1]
    return f"{main_dt_str}.{nanoseconds_str}"

def choose_input_file(cli_file: str | None) -> list[Path]:
    if cli_file:
        path = Path(cli_file)
        if not path.exists():
            raise FileNotFoundError(f"файл {path} не найден")
        return [path]
    if not DATA_DIR.exists():
        raise FileNotFoundError(f"папка {DATA_DIR} не существует")
    files = sorted(DATA_DIR.glob(f"*{DEFAULT_LOG_EXTENSION}"))
    if not files:
        raise FileNotFoundError(f"в папке {DATA_DIR} нет файлов {DEFAULT_LOG_EXTENSION}")
    return [files[0]]

# -------------------------- детектор аномалий (расширенная версия) --------------------------
class AnomalyDetector:
    def __init__(self,
                 score_threshold=50.0,          # порог суммы весов для фиксации аномалии
                 min_duration=5.0,              # минимальная длительность аномалии (сек)
                 # веса для различных факторов
                 weight_nic_low=20,              # NIC ниже порога
                 weight_speed_mismatch=40,       # расхождение скоростей > 20%
                 weight_high_accel=15,           # ускорение > max_accel_kt_per_sec
                 weight_high_heading_change=10,  # резкое изменение курса
                 weight_high_alt_rate=15,        # скачок высоты
                 weight_large_pos_jump=25,       # скачок координат
                 weight_dropout=20,              # пропуск координатных сообщений
                 weight_temporal_drift=30,       # временной дрейф (TOA anomaly)
                 weight_alt_diff_spoof=35,       # подозрительная разница высот с учётом QNH
                 # пороги для отдельных метрик
                 nic_threshold=6,
                 speed_mismatch_percent=0.20,
                 max_speed_kt=1200,
                 max_accel_kt_per_sec=200,
                 max_heading_change=180,
                 max_alt_change_per_sec=2000,
                 max_pos_jump_m=5000,
                 dropout_gap_threshold=5.0,
                 toa_jump_threshold=2.0,
                 toa_window_size=50,
                 min_speed_kts=30,
                 # пороги для высотной аномалии с учётом QNH
                 alt_diff_threshold_ft=500,      # базовая разница (фт) без учёта QNH
                 qnh_std_hpa=1013.25,            # стандартное давление
                 qnh_correction_factor=30.0):    # примерно 30 фт на 1 гПа отклонения
        """
        Параметры скорингового детектора аномалий.
        Добавлен учёт барокоррекции (QNH) для оценки разницы высот.
        """
        self.score_threshold = score_threshold
        self.min_duration = min_duration
        self.weight_nic_low = weight_nic_low
        self.weight_speed_mismatch = weight_speed_mismatch
        self.weight_high_accel = weight_high_accel
        self.weight_high_heading_change = weight_high_heading_change
        self.weight_high_alt_rate = weight_high_alt_rate
        self.weight_large_pos_jump = weight_large_pos_jump
        self.weight_dropout = weight_dropout
        self.weight_temporal_drift = weight_temporal_drift
        self.weight_alt_diff_spoof = weight_alt_diff_spoof

        self.nic_threshold = nic_threshold
        self.speed_mismatch_percent = speed_mismatch_percent
        self.max_speed_kt = max_speed_kt
        self.max_accel_kt_per_sec = max_accel_kt_per_sec
        self.max_heading_change = max_heading_change
        self.max_alt_change_per_sec = max_alt_change_per_sec
        self.max_pos_jump_m = max_pos_jump_m
        self.dropout_gap_threshold = dropout_gap_threshold
        self.toa_jump_threshold = toa_jump_threshold
        self.toa_window_size = toa_window_size
        self.min_speed_kts = min_speed_kts

        # высотные пороги
        self.alt_diff_threshold_ft = alt_diff_threshold_ft
        self.qnh_std_hpa = qnh_std_hpa
        self.qnh_correction_factor = qnh_correction_factor  # фт / гПа

        # кэш для подготовленных DataFrame по icao
        self._prepared_dfs = {}

    # ------------------------------------------------------------
    #  Подготовка единого DataFrame для одного борта
    # ------------------------------------------------------------
    def _prepare_dataframe(self, icao, alt_data, speed_data, course_data, pos_data,
                           nic_data, nacp_data, gva_data, sil_data, nacv_data,
                           alt_diff_data, baro_corr_data, gnss_alt_data, sel_alt_data,
                           messages):
        """
        Собирает все данные в один DataFrame с индексом timestamp (float).
        Колонки:
          alt, speed, course, lat, lon, nic, nacp, gva, sil, nacv,
          alt_diff, baro_corr, gnss_alt, sel_alt, df_code (тип сообщения)
        """
        # Начальный DataFrame из временных меток всех сообщений (для сохранения разрешения)
        all_ts = sorted(set([t for t, _ in messages]))
        df = pd.DataFrame(index=all_ts)

        # Функция для добавления временного ряда
        def add_series(df, data_list, col_name):
            if not data_list:
                return
            s = pd.Series({t: v for t, v in data_list})
            df[col_name] = s

        add_series(df, alt_data, 'alt')
        add_series(df, speed_data, 'speed')
        add_series(df, course_data, 'course')
        add_series(df, nic_data, 'nic')
        add_series(df, nacp_data, 'nacp')
        add_series(df, gva_data, 'gva')
        add_series(df, sil_data, 'sil')
        add_series(df, nacv_data, 'nacv')
        add_series(df, alt_diff_data, 'alt_diff')
        add_series(df, baro_corr_data, 'baro_corr')
        add_series(df, gnss_alt_data, 'gnss_alt')
        add_series(df, sel_alt_data, 'sel_alt')

        # Координаты – отдельно
        if pos_data:
            pos_df = pd.DataFrame(pos_data, columns=['timestamp', 'lat', 'lon']).set_index('timestamp')
            df['lat'] = pos_df['lat']
            df['lon'] = pos_df['lon']

        # Тип сообщения (df) – для анализа дропаутов
        if messages:
            df_msg = pd.DataFrame(messages, columns=['timestamp', 'df_code']).set_index('timestamp')
            df['df_code'] = df_msg['df_code']

        # Сортируем и сбрасываем дубликаты индекса (если есть)
        df = df.sort_index()
        df = df[~df.index.duplicated(keep='first')]
        return df

    # ------------------------------------------------------------
    #  Вспомогательные расчёты (векторизованные)
    # ------------------------------------------------------------
    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1 = np.radians(lat1)
        phi2 = np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlambda = np.radians(lon2 - lon1)
        a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
        return R * c

    def _compute_kinematic_scores(self, df):
        """Вычисляет веса для кинематических аномалий (ускорение, курс, высота, скачки координат)"""
        scores = pd.Series(0.0, index=df.index)

        # ----- ускорение (по скорости) -----
        if 'speed' in df.columns and len(df['speed'].dropna()) > 1:
            speed_series = df['speed'].dropna()
            dt = speed_series.index.to_series().diff()
            accel = speed_series.diff() / dt
            accel_mask = (accel.abs() > self.max_accel_kt_per_sec) & (dt > 0)
            for ts in accel_mask[accel_mask].index:
                scores.loc[ts] += self.weight_high_accel

        # ----- изменение курса -----
        if 'course' in df.columns and len(df['course'].dropna()) > 1:
            course_series = df['course'].dropna()
            dt_c = course_series.index.to_series().diff()
            delta_heading = course_series.diff().abs()
            delta_heading = delta_heading.apply(lambda x: min(x, 360 - x))
            heading_rate = delta_heading / dt_c
            heading_mask = (heading_rate > self.max_heading_change) & (dt_c > 0)
            for ts in heading_mask[heading_mask].index:
                scores.loc[ts] += self.weight_high_heading_change

        # ----- скорость изменения высоты (барометрической или GNSS) -----
        alt_col = None
        if 'gnss_alt' in df.columns and df['gnss_alt'].notna().any():
            alt_col = 'gnss_alt'
        elif 'alt' in df.columns and df['alt'].notna().any():
            alt_col = 'alt'
        if alt_col:
            alt_series = df[alt_col].dropna()
            dt_a = alt_series.index.to_series().diff()
            alt_rate = alt_series.diff().abs() / dt_a
            alt_mask = (alt_rate > self.max_alt_change_per_sec) & (dt_a > 0)
            for ts in alt_mask[alt_mask].index:
                scores.loc[ts] += self.weight_high_alt_rate

        # ----- скачки координат -----
        if 'lat' in df.columns and 'lon' in df.columns:
            pos_df = df[['lat', 'lon']].dropna()
            if len(pos_df) > 1:
                lats = pos_df['lat'].values
                lons = pos_df['lon'].values
                timestamps = pos_df.index.values
                dist = np.zeros(len(timestamps))
                for i in range(1, len(timestamps)):
                    dist[i] = self._haversine_distance(lats[i-1], lons[i-1], lats[i], lons[i])
                jump_mask = dist > self.max_pos_jump_m
                for i, ts in enumerate(timestamps):
                    if jump_mask[i]:
                        scores.loc[ts] += self.weight_large_pos_jump

        return scores

    def _compute_integrity_scores(self, df):
        """Веса на основе NIC, NACp, GVA, SIL"""
        scores = pd.Series(0.0, index=df.index)
        if 'nic' in df.columns:
            nic_low = df['nic'] < self.nic_threshold
            scores.loc[nic_low[nic_low].index] += self.weight_nic_low
        return scores

    def _compute_speed_mismatch_scores(self, df):
        """Сравнение заявленной скорости и скорости по координатам"""
        scores = pd.Series(0.0, index=df.index)
        if not ('speed' in df.columns and 'lat' in df.columns and 'lon' in df.columns):
            return scores

        pos_df = df[['lat', 'lon']].dropna()
        if len(pos_df) < 2:
            return scores
        times = pos_df.index.values
        lats = pos_df['lat'].values
        lons = pos_df['lon'].values
        speeds_comp = np.full(len(times), np.nan)
        for i in range(1, len(times)):
            dt = times[i] - times[i-1]
            if dt <= 0:
                continue
            dist = self._haversine_distance(lats[i-1], lons[i-1], lats[i], lons[i])
            speed_mps = dist / dt
            speeds_comp[i] = speed_mps * 1.94384

        for i, ts in enumerate(times):
            if np.isnan(speeds_comp[i]):
                continue
            mask = (df.index >= ts - 1.0) & (df.index <= ts + 1.0)
            speed_candidates = df.loc[mask, 'speed'].dropna()
            if speed_candidates.empty:
                continue
            gs_spd = speed_candidates.iloc[0]
            speed_kts = speeds_comp[i]
            if gs_spd < self.min_speed_kts or speed_kts < self.min_speed_kts:
                continue
            rel_diff = abs(gs_spd - speed_kts) / max(gs_spd, speed_kts)
            if rel_diff > self.speed_mismatch_percent:
                scores.loc[ts] += self.weight_speed_mismatch
        return scores

    def _compute_dropout_scores(self, df):
        """Пропуски координатных сообщений (DF17/18) при наличии других сообщений"""
        scores = pd.Series(0.0, index=df.index)
        if 'df_code' not in df.columns:
            return scores

        pos_mask = df['df_code'].isin([17, 18])
        pos_times = df.index[pos_mask].values
        other_times = df.index[~pos_mask].values

        if len(pos_times) < 2:
            return scores

        for i in range(1, len(pos_times)):
            gap = pos_times[i] - pos_times[i-1]
            if gap > self.dropout_gap_threshold:
                other_in_gap = np.any((other_times >= pos_times[i-1]) & (other_times <= pos_times[i]))
                if other_in_gap:
                    scores.loc[pos_times[i-1]] += self.weight_dropout
                    scores.loc[pos_times[i]] += self.weight_dropout
        return scores

    def _compute_temporal_drift_scores(self, df):
        """Анализ временных интервалов между последовательными сообщениями (TOA)"""
        scores = pd.Series(0.0, index=df.index)
        if len(df) < 3:
            return scores

        timestamps = df.index.values
        intervals = np.diff(timestamps)
        window = self.toa_window_size
        for i in range(1, len(timestamps)):
            left = max(0, i - window//2)
            right = min(len(intervals), i + window//2)
            med_interval = np.median(intervals[left:right])
            if med_interval <= 0:
                continue
            ratio = intervals[i-1] / med_interval
            if ratio > self.toa_jump_threshold or ratio < 1.0/self.toa_jump_threshold:
                scores.loc[timestamps[i]] += self.weight_temporal_drift
        return scores

    def _compute_altitude_spoofing_scores(self, df):
        """
        Корректировка оценки аномалий высоты с учетом барокоррекции (QNH) 
        и естественного температурного отклонения (D-Value) на больших высотах.
        """
        scores = pd.Series(0.0, index=df.index)
        
        if 'altitude_difference' not in df.columns:
            return scores

        for idx, row in df.iterrows():
            alt_diff = row.get('altitude_difference')
            baro_corr = row.get('baro_correction')
            alt = row.get('altitude', 0)
            
            # Пропускаем пустые строки, чтобы избежать ложных срабатываний из-за NaN
            if pd.isna(alt_diff) or pd.isna(alt):
                continue
                
            # 1. Динамический порог (D-Value)
            # На больших высотах разница из-за плотности воздуха растет (~8% от высоты).
            # Берем базовый порог 1000 футов ИЛИ 8% от текущей высоты (что больше).
            threshold = max(1000.0, alt * 0.08)

            # 2. Корректировка по давлению (QNH) для высот ниже эшелона перехода (обычно < 18000 ft)
            # Проверяем, что данные о давлении существуют и они адекватны (> 800 гПа)
            if alt < 18000 and not pd.isna(baro_corr) and baro_corr > 800 and baro_corr != 1013.25:
                # Ожидаемый сдвиг с учетом знака (GNSS - Baro = (QNH - 1013.25) * 30)
                expected_diff = (baro_corr - 1013.25) * 30
                
                # Насколько реальная разница отличается от ожидаемой физической
                residual = abs(alt_diff - expected_diff)
                
                if residual > threshold:
                    scores[idx] = 1.0
            else:
                # Для больших высот (стандартное давление) или если пилот не передал QNH
                if abs(alt_diff) > threshold:
                    scores[idx] = 1.0
                    
        return scores

    def _aggregate_anomalies(self, total_score, df, min_duration_sec):
        """Находит интервалы, где total_score >= score_threshold и длительностью >= min_duration_sec."""
        if total_score.empty:
            return []

        mask = total_score >= self.score_threshold
        if not mask.any():
            return []

        changes = mask.astype(int).diff()
        starts = mask.index[changes == 1]
        ends = mask.index[changes == -1]

        if mask.iloc[0]:
            starts = starts.union([mask.index[0]])
        if mask.iloc[-1]:
            ends = ends.union([mask.index[-1]])

        anomalies = []
        for start, end in zip(starts, ends):
            duration = end - start
            if duration >= min_duration_sec:
                scores_slice = total_score.loc[start:end]
                # Определяем доминирующий тип аномалии по максимальному весу
                # Для простоты оставляем MULTIFACTOR, но можно детализировать
                anomalies.append({
                    'time': start,
                    'type': 'MULTIFACTOR',
                    'severity': 'critical',
                    'desc': f'комплексная аномалия (суммарный вес {scores_slice.mean():.1f}) длительностью {duration:.1f} с'
                })
        return anomalies

    # ------------------------------------------------------------
    #  Основной метод detect (расширенная версия)
    # ------------------------------------------------------------
    def detect(self, icao, alt_diff_data, nic_data, pos_data=None, speed_data=None,
               course_data=None, alt_data=None, nacp_data=None, messages=None,
               gva_data=None, sil_data=None, nacv_data=None, baro_corr_data=None,
               gnss_alt_data=None, sel_alt_data=None):
        """
        Основной метод: строит единый DataFrame, вычисляет суммарный вес аномалий,
        возвращает список обнаруженных аномалий.
        Теперь учитывает барокоррекцию (QNH) для снижения ложных срабатываний по высоте.
        """
        cache_key = icao
        if cache_key not in self._prepared_dfs:
            df = self._prepare_dataframe(
                icao, alt_data, speed_data, course_data, pos_data,
                nic_data, nacp_data, gva_data, sil_data, nacv_data,
                alt_diff_data, baro_corr_data, gnss_alt_data, sel_alt_data,
                messages or []
            )
            self._prepared_dfs[cache_key] = df
        else:
            df = self._prepared_dfs[cache_key]

        if df.empty:
            return []

        # Вычисляем веса по каждой группе
        score_kin = self._compute_kinematic_scores(df)
        score_int = self._compute_integrity_scores(df)
        score_mm = self._compute_speed_mismatch_scores(df)
        score_drop = self._compute_dropout_scores(df)
        score_toa = self._compute_temporal_drift_scores(df)
        score_alt_spoof = self._compute_altitude_spoofing_scores(df)

        # Суммируем
        total_score = score_kin.add(score_int, fill_value=0) \
                             .add(score_mm, fill_value=0) \
                             .add(score_drop, fill_value=0) \
                             .add(score_toa, fill_value=0) \
                             .add(score_alt_spoof, fill_value=0)

        anomalies = self._aggregate_anomalies(total_score, df, self.min_duration)
        return anomalies
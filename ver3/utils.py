from datetime import datetime, timezone
from pathlib import Path
import sys
from config import DATA_DIR, DEFAULT_LOG_EXTENSION

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

    return [files[0]]

class AnomalyDetector:
    def __init__(self, alt_diff_threshold=500, nic_threshold=6):
        # Пороги срабатывания (можно настраивать)
        self.alt_diff_threshold = alt_diff_threshold 
        self.nic_threshold = nic_threshold

    def detect(self, icao, alt_diff_data, nic_data):
        anomalies = []
        
        # 1. Проверка расхождения высот (Baro vs GNSS)
        for ts, val in alt_diff_data:
            if abs(val) > self.alt_diff_threshold:
                anomalies.append({
                    'time': ts, 
                    'type': 'SPOOFING', 
                    'desc': f'Аномальная разница высот: {val} фт'
                })

        # 2. Проверка падения NIC
        for ts, val in nic_data:
            if val < self.nic_threshold:
                anomalies.append({
                    'time': ts, 
                    'type': 'JAMMING / LOW INTEGRITY', 
                    'desc': f'Падение NIC до уровня {val}'
                })
                
        # Сортируем все аномалии по времени
        return sorted(anomalies, key=lambda x: x['time'])
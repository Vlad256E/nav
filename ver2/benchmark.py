import time
import tracemalloc
import os
import psutil
from pathlib import Path
import decoder

# Укажи здесь пути к твоим тестовым файлам (от маленького к большому)
TEST_FILES = [
    "data/151D54.t4433",               # Маленький файл для проверки
    "data/2026-01-21_1.t4433",         # Средний файл (если есть)
    "data/stress_test.t4433"           # Твой склеенный гигантский лог
]

def run_memory_benchmark(file_path):
    print(f"\n{'-'*50}")
    print(f"Тестирование файла: {file_path}")
    
    if not os.path.exists(file_path):
        print("❌ Файл не найден! Проверь путь.")
        return

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"Размер файла: {file_size_mb:.2f} МБ")

    # Получаем текущий процесс для замера памяти на уровне ОС
    process = psutil.Process(os.getpid())
    
    # Запускаем отслеживание памяти объектов Python и таймер
    tracemalloc.start()
    start_time = time.time()
    
    parsed_lines = 0
    error_lines = 0
    
    # Симулируем логику парсинга из твоего main.py
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip(): 
                    continue
                
                # Вызываем твой декодер
                parsed = decoder.parse_ads_b_line(line)
                if parsed is not None:
                    parsed_lines += 1
                else:
                    error_lines += 1
                    
    except Exception as e:
        print(f"Ошибка при чтении файла: {e}")

    # Фиксируем результаты
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    end_time = time.time()
    tracemalloc.stop()

    exec_time = end_time - start_time
    peak_mb = peak_mem / (1024 * 1024)
    system_ram_mb = process.memory_info().rss / (1024 * 1024)

    # Вывод результатов
    print(f"✅ Обраработано валидных строк: {parsed_lines}")
    if error_lines > 0:
        print(f"⚠️ Пропущено невалидных строк: {error_lines}")
    print(f"⏱️ Время выполнения парсинга: {exec_time:.2f} секунд")
    print(f"🧠 Пиковое потребление памяти (чистый Python): {peak_mb:.2f} МБ")
    print(f"🖥️ Общее потребление ОЗУ процессом ОС: {system_ram_mb:.2f} МБ")

if __name__ == '__main__':
    print("🚀 Начало нагрузочного тестирования парсера ADS-B...")
    
    for f in TEST_FILES:
        run_memory_benchmark(f)
        
    print(f"\n{'-'*50}")
    print("🏁 Тестирование завершено! Можешь переносить цифры в таблицу для ТЗ.")
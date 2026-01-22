import sys
import argparse
from datetime import datetime, timezone
import pyModeS as pms

import config
import decoder
import utils
from visual import IcaoGraphs

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
        files_to_process = utils.choose_input_file(args.file)
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
                    parsed = decoder.parse_ads_b_line(line)
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
                    fmt_label = decoder.get_format_label(message_str, df)
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
                        alt = decoder.get_altitude_any_df(message_str, df)
                        if alt is not None and -2000 <= alt <= 60000:
                             icao_altitude.setdefault(aa, []).append((msg.timestamp, alt))
                             current_baro_buffer[aa] = (msg.timestamp, alt)
                        
                        # извлечение Squawk кода
                        sq = decoder.get_squawk(message_str, df)
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
                                gs = decoder.get_velocity(message_str)
                                if gs is not None:
                                    icao_speed.setdefault(aa, []).append((msg.timestamp, gs))
                                course = decoder.get_course(message_str)
                                if course is not None:
                                    icao_courses.setdefault(aa, []).append((msg.timestamp, course))
                                
                                # расчет GNSS высоты на основе баро и разницы высот
                                alt_diff = decoder.get_altitude_difference(message_str)
                                if alt_diff is not None:
                                    icao_altitude_difference.setdefault(aa, []).append((msg.timestamp, alt_diff))
                                    
                                    if aa in current_baro_buffer:
                                        last_ts, last_baro = current_baro_buffer[aa]
                                        if abs(msg.timestamp - last_ts) < 5.0:
                                            gnss_alt = last_baro + alt_diff
                                            icao_gnss_altitude.setdefault(aa, []).append((msg.timestamp, gnss_alt))

                            # декодирование позывного (ICAO)
                            elif 1 <= tc <= 4:
                                cs = decoder.get_callsign(message_str)
                                if cs: icao_callsigns[aa] = cs

                            # декодирование параметров автопилота
                            elif tc == 29:
                                sel_alt = decoder.get_selected_altitude(message_str)
                                if sel_alt:
                                    sel_alt_value, modes = sel_alt
                                    icao_selected_altitude.setdefault(aa, []).append((msg.timestamp, sel_alt_value))
                                    icao_has_selected_alt[aa] = True
                                    modes_key = f"{aa}_modes"
                                    existing_modes = icao_callsigns.get(modes_key, set())
                                    icao_callsigns[modes_key] = existing_modes.union(modes)
                                
                                baro_corr = decoder.get_baro_correction(message_str)
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
                
                first_utc_str = utils.format_timestamp_with_nanoseconds(ts_first)
                
                # если дата совпадает, выводим только время последнего сообщения
                if dt_first.date() == dt_last.date():
                    main_dt_str = dt_last.strftime('%H:%M:%S')
                    ts_str = f"{ts_last:.9f}"
                    nanoseconds_str = ts_str.split('.')[1]
                    last_utc_str = f"{main_dt_str}.{nanoseconds_str}"
                else:
                    last_utc_str = utils.format_timestamp_with_nanoseconds(ts_last)
                
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
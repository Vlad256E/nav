import sys
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import pyModeS as pms

import config
import decoder
import utils
from visual import IcaoGraphs
from utils import timestamp_to_utc, format_timestamp_with_nanoseconds, choose_input_file, AnomalyDetector
from models import FlightData

def parse_log_file(file_path, target_icao=None) -> FlightData:
    """
    Анализирует файл логов и возвращает FlightData с результатами.
    """
    data = FlightData()
    
    current_baro_buffer = {}
    cpr_messages = {}

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parsed = decoder.parse_ads_b_line(line)
            if parsed is None:
                continue
            msg, message_str = parsed

            try:
                aa = pms.icao(message_str)
                df = pms.df(message_str)
            except Exception:
                continue

            if target_icao and aa != target_icao:
                continue

            data.adsb_icao_list.add(aa)
            
            fmt_label = decoder.get_format_label(message_str, df)
            data.icao_dfs[aa].add(fmt_label)

            if aa not in data.icao_times:
                data.icao_times[aa] = {"first": msg.timestamp, "last": msg.timestamp}
            else:
                data.icao_times[aa]["last"] = msg.timestamp
            
            try:
                alt = decoder.get_altitude_any_df(message_str, df)
                if alt is not None and -2000 <= alt <= 60000:
                    data.icao_altitude[aa].append((msg.timestamp, alt))
                    current_baro_buffer[aa] = (msg.timestamp, alt)
                
                sq = decoder.get_squawk(message_str, df)
                if sq:
                    data.icao_callsigns[f"{aa}_sq"] = sq

                if df in [17, 18]:
                    tc = pms.adsb.typecode(message_str)
                    
                    nic_val = decoder.get_nic(message_str, tc)
                    if nic_val is not None:
                        data.icao_nic[aa].append((msg.timestamp, nic_val))

                    if 9 <= tc <= 18:
                        if aa not in cpr_messages:
                            cpr_messages[aa] = [None, None]
                        oe_flag = pms.adsb.oe_flag(message_str)
                        cpr_messages[aa][oe_flag] = (message_str, msg.timestamp)
                        
                        if all(cpr_messages[aa]):
                            msg0, t0 = cpr_messages[aa][0]
                            msg1, t1 = cpr_messages[aa][1]
                            if abs(t0 - t1) < 10:
                                pos = pms.adsb.position(msg0, msg1, t0, t1)
                                if pos:
                                    data.icao_positions[aa].append((msg.timestamp, pos[0], pos[1]))
                            cpr_messages[aa] = [None, None]
                    
                    elif tc == 19:
                        gs, course = decoder.get_velocity_and_course(message_str, tc)
                        if gs is not None:
                            data.icao_speed[aa].append((msg.timestamp, gs))
                        if course is not None:
                            data.icao_courses[aa].append((msg.timestamp, course))
                        
                        alt_diff = decoder.get_altitude_difference(message_str, tc)
                        if alt_diff is not None:
                            data.icao_altitude_difference[aa].append((msg.timestamp, alt_diff))
                            if aa in current_baro_buffer:
                                last_ts, last_baro = current_baro_buffer[aa]
                                if abs(msg.timestamp - last_ts) < 5.0:
                                    gnss_alt = last_baro + alt_diff
                                    data.icao_gnss_altitude[aa].append((msg.timestamp, gnss_alt))

                        nac_v = decoder.get_nac_v(message_str, tc)
                        if nac_v is not None:
                            data.icao_nacv[aa].append((msg.timestamp, nac_v))

                    elif 1 <= tc <= 4:
                        cs = decoder.get_callsign(message_str, tc)
                        if cs:
                            data.icao_callsigns[aa] = cs

                    elif tc == 29:
                        sel_alt = decoder.get_selected_altitude(message_str, tc)
                        if sel_alt:
                            sel_alt_value, modes = sel_alt
                            data.icao_selected_altitude[aa].append((msg.timestamp, sel_alt_value))
                            data.icao_has_selected_alt[aa] = True
                            data.icao_callsigns.setdefault(f"{aa}_modes", set()).update(modes)
                        
                        baro_corr = decoder.get_baro_correction(message_str, tc)
                        if baro_corr is not None:
                            data.icao_baro_correction[aa].append((msg.timestamp, baro_corr))

                    elif tc == 31:
                        nac_p, gva, sil = decoder.get_operational_status_params(message_str, tc)
                        if nac_p is not None:
                            data.icao_nacp[aa].append((msg.timestamp, nac_p))
                        if gva is not None:
                            data.icao_gva[aa].append((msg.timestamp, gva))
                        if sil is not None:
                            data.icao_sil[aa].append((msg.timestamp, sil))
                        
                        nb = decoder.get_nic_baro(message_str, tc)
                        if nb is not None:
                            data.icao_nic_baro[aa] = nb
                                
            except Exception:
                continue

    return data

def print_summary(data: FlightData, total_icao_count: int, filtered_count: int):
    """Вывод сводной таблицы в консоль."""
    print("=" * 155)
    print(" " * 65 + "СВОДНАЯ ТАБЛИЦА")
    print("=" * 155)
    print(f"{'ICAO':<8} {'Рейс':<12} {'Формат':<24} {'Первое (UTC)':<35} {'Последнее (UTC)':<30} {'POS':<5} {'HDG':<5} {'SEL':<5} {'DIF':<5} {'BAR':<5} {'GNS':<5} {'NB':<3}")
    print("-" * 155)

    for icao in sorted(data.adsb_icao_list):
        if icao not in data.icao_times:
            continue
        times = data.icao_times[icao]
        
        ts_first = times["first"]
        ts_last = times["last"]
        
        dt_first = datetime.fromtimestamp(int(ts_first), tz=timezone.utc)
        dt_last = datetime.fromtimestamp(int(ts_last), tz=timezone.utc)
        
        first_utc_str = format_timestamp_with_nanoseconds(ts_first)
        
        if dt_first.date() == dt_last.date():
            main_dt_str = dt_last.strftime('%H:%M:%S')
            ts_str = f"{ts_last:.9f}"
            nanoseconds_str = ts_str.split('.')[1]
            last_utc_str = f"{main_dt_str}.{nanoseconds_str}"
        else:
            last_utc_str = format_timestamp_with_nanoseconds(ts_last)
        
        callsign = data.icao_callsigns.get(icao, "N/A")
        squawk = data.icao_callsigns.get(f"{icao}_sq", "")
        if callsign == "N/A" and squawk:
            callsign = f"SQ:{squawk}"
        
        my_dfs = sorted(list(data.icao_dfs.get(icao, set())))
        dfs_str = ",".join(my_dfs)
        if len(dfs_str) > 22:
            dfs_str = dfs_str[:19] + "..."

        pos_flag = "+" if data.icao_positions.get(icao) else "-"
        hdg_flag = "+" if data.icao_courses.get(icao) else "-"
        sel_flag = "+" if data.icao_has_selected_alt.get(icao) else "-"
        dif_flag = "+" if data.icao_altitude_difference.get(icao) else "-"
        bar_flag = "+" if data.icao_baro_correction.get(icao) else "-"
        gnss_flag = "+" if data.icao_gnss_altitude.get(icao) else "-"
        nb_val = data.icao_nic_baro.get(icao, "-")

        print(f"{icao:<8} {callsign:<12} {dfs_str:<24} {first_utc_str:<35} {last_utc_str:<30} {pos_flag:<5} {hdg_flag:<5} {sel_flag:<5} {dif_flag:<5} {bar_flag:<5} {gnss_flag:<5} {nb_val:<3}")
        
    print(f"\nВсего бортов обнаружено: {total_icao_count}")
    print(f"Отфильтровано (без ADS-B): {filtered_count}")
    print(f"Осталось бортов (ADS-B): {len(data.adsb_icao_list)}\n")

# --- MAIN ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Анализ ADS-B данных")
    parser.add_argument("-f", "--file", help="Имя входного файла (по умолчанию ищется в папке data)", default=None)
    parser.add_argument("-a", "--aircraft", help="ICAO адрес конкретного борта")
    args = parser.parse_args()

    target_icao = args.aircraft.upper() if args.aircraft else None

    try:
        files_to_process = choose_input_file(args.file)
    except FileNotFoundError as e:
        print(f"Ошибка: {e}")
        sys.exit(1)

    for file_path in files_to_process:
        try:
            print(f"Файл: {file_path}")
            data = parse_log_file(file_path, target_icao)

            total_icao_count = len(data.adsb_icao_list)
            
            # Оставляем только борта с ADS-B
            filtered_icao_list = set()
            for icao in data.adsb_icao_list:
                if any("DF17" in label or "DF18" in label for label in data.icao_dfs.get(icao, set())):
                    filtered_icao_list.add(icao)
            filtered_count = total_icao_count - len(filtered_icao_list)
            data.adsb_icao_list = filtered_icao_list

            print_summary(data, total_icao_count, filtered_count)

            # Сортировка данных по времени
            for icao in data.adsb_icao_list:
                if icao in data.icao_altitude:
                    data.icao_altitude[icao].sort(key=lambda x: x[0])
                if icao in data.icao_speed:
                    data.icao_speed[icao].sort(key=lambda x: x[0])
                if icao in data.icao_positions:
                    data.icao_positions[icao].sort(key=lambda x: x[0])
                if icao in data.icao_courses:
                    data.icao_courses[icao].sort(key=lambda x: x[0])
                if icao in data.icao_gnss_altitude:
                    data.icao_gnss_altitude[icao].sort(key=lambda x: x[0])
                if icao in data.icao_selected_altitude:
                    data.icao_selected_altitude[icao].sort(key=lambda x: x[0])
                if icao in data.icao_nic:
                    data.icao_nic[icao].sort(key=lambda x: x[0])

            # Детектор аномалий
            detector = AnomalyDetector()
            icao_anomalies = {}
            for icao in data.adsb_icao_list:
                anomalies = detector.detect(
                    icao,
                    data.icao_altitude_difference.get(icao, []),
                    data.icao_nic.get(icao, []),
                    pos_data=data.icao_positions.get(icao, []),
                    speed_data=data.icao_speed.get(icao, []),
                    course_data=data.icao_courses.get(icao, []),
                    alt_data=data.icao_altitude.get(icao, []),
                    nacp_data=data.icao_nacp.get(icao, [])
                )
                if anomalies:
                    icao_anomalies[icao] = anomalies

            # Запуск визуализации
            IcaoGraphs(data.icao_altitude, data.icao_speed, data.icao_positions, data.icao_courses,
                       data.adsb_icao_list, data.icao_callsigns,
                       data.icao_selected_altitude, data.icao_altitude_difference,
                       data.icao_baro_correction, data.icao_gnss_altitude,
                       data.icao_nic, data.icao_nacp, data.icao_gva, data.icao_sil, data.icao_nacv,
                       icao_anomalies)

        except FileNotFoundError:
            print(f"Файл {file_path} не найден")
        except Exception as e:
            print(f"Произошла критическая ошибка: {e}")
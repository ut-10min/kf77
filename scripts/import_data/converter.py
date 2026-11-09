#!/usr/bin/env python3
"""参加登録 XLSX + 題目 XLSX + シフト PDF を既存サイト用 JSON に変換する。"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

from openpyxl import load_workbook
import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
WEEKDAYS = "月火水木金土日"


class ConversionError(ValueError):
    pass


def text(value):
    return str(value).strip() if value is not None else ""


def key(value):
    """全半角・空白・改行・ひらがな/カタカナを照合時だけ正規化。"""
    value = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text(value)))
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in value)


def common_id(value):
    if isinstance(value, (int, float)) and value == int(value):
        return str(int(value))
    return re.sub(r"\.0$", "", text(value))


def date_label(date):
    return f"{date.month}月{date.day}日（{WEEKDAYS[date.weekday()]}）"


def minute(value):
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ConversionError(f"時刻の形式が不正です: {value}")
    return int(match[1]) * 60 + int(match[2])


def clock(value):
    if not 0 <= value < 1440:
        raise ConversionError("日をまたぐ枠には対応していません。")
    return f"{value // 60:02d}:{value % 60:02d}"


def read_registrations(path, notes):
    wb = load_workbook(path, read_only=True, data_only=True)
    required = ["タイムスタンプ", "共通ID", "氏名", "氏名フリガナ", "氏名（英語表記）",
                "所属(〇〇研究科××専攻 等)", "専門（一単語で、例：海洋生物学、中国思想史など）"]
    try:
        candidates = []
        for sheet in wb:
            rows = list(sheet.iter_rows(values_only=True))
            if rows and all(key(h) in {key(c) for c in rows[0]} for h in required):
                candidates.append((sheet.title, rows))
        if len(candidates) != 1:
            raise ConversionError("参加登録の見出しを持つシートが一つ必要です。")
        sheet_name, rows = candidates[0]
        headers = {key(c): i for i, c in enumerate(rows[0]) if c is not None}
        latest = {}
        for row_no, row in enumerate(rows[1:], 2):
            if not any(v is not None for v in row):
                continue
            get = lambda h: row[headers[key(h)]]
            cid = common_id(get("共通ID"))
            name = re.sub(r"\s+", "", text(get("氏名")))
            stamp = get("タイムスタンプ")
            if not cid or not name or not isinstance(stamp, dt.datetime):
                raise ConversionError(f"参加登録 {sheet_name} {row_no}行: 共通ID・氏名・日時が必要です。")
            record = dict(name=name, kana=text(get("氏名フリガナ")),
                          english=text(get("氏名（英語表記）")), affiliation=text(get(required[5])),
                          field=text(get(required[6])), stamp=stamp, row=row_no, sheet=sheet_name)
            if cid in latest:
                previous = latest[cid]
                if key(previous['name']) != key(name):
                    raise ConversionError(f"共通IDに異なる氏名があります: {previous['name']} / {name}")
                if stamp == previous['stamp']:
                    fields = ['name', 'kana', 'english', 'affiliation', 'field']
                    if any(record[f] != previous[f] for f in fields):
                        raise ConversionError(f"同じ日時に異なる回答があります: {name}")
                selected = record if stamp >= previous['stamp'] else previous
                notes.append(f"{name}: 重複回答は新しい日時の行{selected['row']}を採用")
                latest[cid] = selected
            else:
                latest[cid] = record
        return list(latest.values())
    finally:
        wb.close()


def match_person(name, people):
    found = [p for p in people if key(name) in {key(p['name']), key(p['kana'])}]
    if len(found) != 1:
        raise ConversionError(f"氏名を一意に照合できません: {name}（一致{len(found)}件）")
    return found[0]


def split_affiliation(value):
    value = re.sub(r"\s+", "", text(value))
    match = re.match(r"^(.*?(?:研究科|学府))(.*)$", value)
    return (match[1], match[2]) if match else (value, "")


def read_talks(path, people, notes):
    wb = load_workbook(path, read_only=True, data_only=True)
    talks, sources = [], []
    try:
        nonempty = [s for s in wb if any(any(v is not None for v in row)
                                       for row in s.iter_rows(values_only=True))]
        if len(nonempty) != 1:
            raise ConversionError("題目一覧にはデータの入ったシートが一つ必要です。")
        sheet = nonempty[0]
        seen = set()
        for row_no, row in enumerate(sheet.iter_rows(values_only=True), 1):
            if not any(v is not None for v in row):
                continue
            # 元資料は見出しなし A=氏名 B=所属 C=題目 D=概要。
            if key(row[0]) in {"氏名", "講演者", "講演者名"}:
                continue
            if len(row) < 4 or any(not text(v) for v in row[:4]):
                raise ConversionError(f"題目一覧 {row_no}行: A〜D列の値が必要です。")
            name, affiliation, title, description = map(text, row[:4])
            person = match_person(name, people)
            talk_id = "speaker-" + person['name']
            if talk_id in seen:
                raise ConversionError(f"同じ講演者の題目が複数あります: {person['name']}")
            seen.add(talk_id)
            faculty, department = split_affiliation(affiliation)
            if key(affiliation) != key(person['affiliation']):
                notes.append(f"{person['name']}: 所属の差異あり。題目一覧の所属を採用")
            if key(name) != key(person['name']):
                notes.append(f"{name}: フリガナ照合により{person['name']}に統一")
            if not person['kana'] or not person['field']:
                raise ConversionError(f"フリガナまたは専門分野がありません: {person['name']}")
            talks.append(dict(id=talk_id, title=title, speaker=person['name'],
                              speakerKana=person['kana'], englishName=person['english'],
                              affiliation=faculty, department=department, field=person['field'],
                              description=description))
            sources.append(dict(talkId=talk_id, titleSheet=sheet.title, titleRow=row_no,
                                registrationSheet=person['sheet'], registrationRow=person['row']))
        if not talks:
            raise ConversionError("講演題目を抽出できませんでした。")
        return talks, sources
    finally:
        wb.close()


def read_schedule(path, year, talks, people, require_all_talks=True):
    schedule, days, provenance = [], {}, []
    talk_map = {t['speaker']: t for t in talks}
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            previous_bottom = 0
            for table in page.find_tables():
                rows = table.extract()
                if not rows or key(rows[0][0]) != '区分':
                    continue
                heading = page.crop((0, previous_bottom, page.width, table.bbox[1])).extract_text() or ''
                previous_bottom = table.bbox[3]
                headings = re.findall(r"(\d+)月(\d+)日\s+(\d{1,2}:\d{2})[～〜~–-](\d{1,2}:\d{2})", heading)
                if len(headings) != 1:
                    raise ConversionError(f"PDF {page_no}ページ: 日付・開催時間の見出しを読めません。")
                month, day, opening, closing = headings[0]
                date = dt.date(year, int(month), int(day))
                date_iso = date.isoformat()
                if date_iso in days:
                    raise ConversionError(f"日付が重複しています: {date_iso}")
                days[date_iso] = dict(date=date_iso, dateLabel=date_label(date), start=opening, end=closing)
                hours = []
                for value in rows[0][1:]:
                    m = re.fullmatch(r"(\d{1,2})時", key(value))
                    if not m:
                        raise ConversionError(f"PDFの時間列を認識できません: {value}")
                    hours.append(int(m[1]))
                if hours != list(range(minute(opening)//60, minute(closing)//60)):
                    raise ConversionError(f"{date_iso}: 見出しと時間列が一致しません。")
                time_rows = []
                for row_index, row in enumerate(rows[1:], 1):
                    label = unicodedata.normalize('NFKC', text(row[0]))
                    match = re.fullmatch(r"(\d+)[–−―ー-](\d+)", label)
                    if match:
                        lo, hi = map(int, match.groups())
                        if not 0 <= lo < hi <= 60:
                            raise ConversionError(f"区分が不正です: {label}")
                        time_rows.append((row_index, lo, hi))
                if not time_rows:
                    raise ConversionError("PDFの登壇時間行を認識できません。")
                for col, hour in enumerate(hours, 1):
                    covered = set()
                    for ri, lo, hi in time_rows:
                        base_start, base_end = hour*60+lo, hour*60+hi
                        raw = rows[ri][col]
                        if base_start in covered:
                            if text(raw):
                                raise ConversionError("結合枠と別の講演が重複しています。")
                            continue
                        if not text(raw):
                            raise ConversionError(f"{date_iso} {clock(base_start)}: 空欄です。自動補完しません。")
                        cell = table.rows[ri].cells[col]
                        merged = [(r, a, b) for r, a, b in time_rows
                                  if table.rows[r].cells[0][1] >= cell[1]-1
                                  and table.rows[r].cells[0][3] <= cell[3]+1]
                        if not merged:
                            raise ConversionError("PDFのセル範囲を認識できません。")
                        end = hour*60 + max(b for _, _, b in merged)
                        label = key(raw)
                        item = dict(date=date_iso, dateLabel=date_label(date),
                                    start=clock(base_start), end=clock(end))
                        if label.startswith(('座談会', '休憩')):
                            times = re.findall(r"\d{1,2}:\d{2}", label)
                            if times and (len(times) != 2 or [minute(t) for t in times] != [base_start, end]):
                                raise ConversionError(f"{date_iso}: 座談会・休憩の記載時間と結合セルが一致しません。")
                            # 既存表示は非講演を break として扱う。title はそのまま公開。
                            item.update(type='break', title='座談会' if label.startswith('座談会') else '休憩')
                        else:
                            person = match_person(raw, people)
                            talk = talk_map.get(person['name'])
                            if not talk:
                                raise ConversionError(f"シフトにある{person['name']}の講演題目がありません。")
                            item.update(type='talk', talkId=talk['id'], speaker=talk['speaker'])
                        covered.update(range(base_start, end))
                        schedule.append(item)
                        provenance.append(dict(date=date_iso, start=item['start'], page=page_no,
                                               row=ri+1, column=col+1, sourceLabel=text(raw)))
    if not days:
        raise ConversionError("シフト表を抽出できません。文字情報と罫線のあるPDFが必要です。")
    schedule.sort(key=lambda s: (s['date'], s['start']))
    validate(talks, schedule, days, require_all_talks=require_all_talks)
    return schedule, sorted(days.values(), key=lambda d: d['date']), provenance


def validate(talks, schedule, days, require_all_talks=True):
    by_id = {t['id']: t for t in talks}
    if len(by_id) != len(talks):
        raise ConversionError("講演IDが重複しています。")
    used = set()
    for date, day in days.items():
        end = minute(day['start'])
        for slot in sorted((s for s in schedule if s['date'] == date), key=lambda s: s['start']):
            if minute(slot['start']) != end or minute(slot['end']) <= end:
                raise ConversionError(f"{date} {slot['start']}: 時間の重複・欠落・逆転があります。")
            end = minute(slot['end'])
            if slot['type'] == 'talk':
                talk = by_id.get(slot['talkId'])
                if not talk or slot['speaker'] != talk['speaker']:
                    raise ConversionError("講演IDと氏名が一致しません。")
                used.add(slot['talkId'])
        if end != minute(day['end']):
            raise ConversionError(f"{date}: 終了時刻が開催時間と一致しません。")
    missing = set(by_id) - used
    if missing and require_all_talks:
        raise ConversionError("題目はあるが登壇枠がない講演: " + ', '.join(sorted(missing)))


def convert(shift, registration, titles, config, year=None):
    """書き込みなし。すべての照合・検証を完了して結果を返す。"""
    notes = []
    if year is None:
        match = re.search(r"(\d{4})年", config.get('dateTimeText', ''))
        if not match:
            raise ConversionError("開催年が不明です。--year で指定してください。")
        year = int(match[1])
    people = read_registrations(registration, notes)
    talks, talk_sources = read_talks(titles, people, notes)
    schedule, days, schedule_sources = read_schedule(shift, year, talks, people)
    updated_config = dict(config)
    updated_config['dateTimeText'] = str(year) + '年' + '／'.join(
        f"{d['dateLabel']}{d['start']}–{d['end']}" for d in days)
    names = {t['speaker'] for t in talks}
    excluded = sorted(p['name'] for p in people if p['name'] not in names)
    files = dict(shift=Path(shift), registration=Path(registration), titles=Path(titles))
    report = dict(
        counts=dict(talks=len(talks), talkSlots=sum(s['type']=='talk' for s in schedule),
                    otherSlots=sum(s['type']!='talk' for s in schedule), days=len(days)),
        days=days, notes=notes, registrationOnly=excluded,
        sources={kind: dict(filename=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                 for kind, p in files.items()},
        talks=talk_sources, schedule=schedule_sources)
    return {'config.json': updated_config, 'talks.json': talks, 'schedule.json': schedule}, report


def convert_schedule(shift, talks, config, year=None):
    """既存の講演IDと内容を保ち、PDFだけで日程を更新する。"""
    if year is None:
        match = re.search(r"(\d{4})年", config.get('dateTimeText', ''))
        if not match:
            raise ConversionError("開催年が不明です。--year で指定してください。")
        year = int(match[1])
    people = [dict(name=t['speaker'], kana=t.get('speakerKana', '')) for t in talks]
    schedule, days, sources = read_schedule(shift, year, talks, people, require_all_talks=False)
    used = {s.get('talkId') for s in schedule}
    unscheduled = [t['speaker'] for t in talks if t['id'] not in used]
    report = dict(counts=dict(talks=len(used - {None}), talkSlots=sum(s['type']=='talk' for s in schedule),
                             otherSlots=sum(s['type']!='talk' for s in schedule), days=len(days)),
                  days=days, notes=[f"{name}: 新シフトに登壇枠なし。講演情報は保持" for name in unscheduled],
                  sources=dict(shift=dict(filename=Path(shift).name,
                      sha256=hashlib.sha256(Path(shift).read_bytes()).hexdigest())), schedule=sources)
    return {'schedule.json': schedule}, report


def write_result(result, report, output, report_dir):
    """検証済みデータを一時保存し、既存JSONのバックアップ後に差し替える。"""
    output, report_dir = Path(output), Path(report_dir)
    if set(result) not in ({'config.json', 'talks.json', 'schedule.json'}, {'schedule.json'}):
        raise ConversionError("出力ファイルの組が不正です。")
    output.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=dt.datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=report_dir))
    stage = Path(tempfile.mkdtemp(prefix='.import-', dir=output))
    existed = {name: (output/name).exists() for name in result}
    try:
        for name, data in result.items():
            (stage/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            if existed[name]:
                shutil.copy2(output/name, backup/name)
        (backup/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        replaced = []
        try:
            for name in result:
                os.replace(stage/name, output/name)
                replaced.append(name)
        except BaseException:
            for name in replaced:
                if existed[name]:
                    shutil.copy2(backup/name, output/name)
                else:
                    (output/name).unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(stage)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shift', required=True, type=Path)
    parser.add_argument('--registration', type=Path)
    parser.add_argument('--titles', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT/'data/config.json')
    parser.add_argument('--output', type=Path, default=ROOT/'data')
    parser.add_argument('--report-dir', type=Path, default=ROOT/'.local/imports')
    parser.add_argument('--year', type=int)
    parser.add_argument('--schedule-only', action='store_true', help='既存の講演情報を使って日程だけ更新')
    parser.add_argument('--talks', type=Path, default=ROOT/'data/talks.json')
    parser.add_argument('--check', action='store_true', help='照合・検証のみ。書き込まない')
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        if args.schedule_only:
            result, report = convert_schedule(args.shift,
                json.loads(args.talks.read_text(encoding='utf-8')), config, args.year)
        else:
            if not args.registration or not args.titles:
                parser.error('--registration と --titles が必要です（日程のみは --schedule-only）。')
            result, report = convert(args.shift, args.registration, args.titles, config, args.year)
        if not args.check:
            destination = write_result(result, report, args.output, args.report_dir)
            print(f"保存先: {args.output}\nバックアップ・照合結果: {destination}")
        print(json.dumps(report['counts'], ensure_ascii=False))
        for note in report['notes']:
            print(note)
    except (ConversionError, OSError, ValueError) as exc:
        parser.exit(1, f"変換できませんでした: {exc}\n")


if __name__ == '__main__':
    main()

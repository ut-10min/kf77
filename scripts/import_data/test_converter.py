"""実行: python -m unittest discover -s scripts/import_data -v"""
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from converter import (ConversionError, ROOT, convert, convert_schedule, key, match_person,
                       read_registrations, validate, write_result)


class ConverterTests(unittest.TestCase):
    def test_kana_and_whitespace_match_without_fuzzy_guess(self):
        person = dict(name='安藤靖', kana='アンドウ ヤスシ')
        self.assertIs(match_person('あんどうや\nすし', [person]), person)
        with self.assertRaises(ConversionError):
            match_person('あんどうやすし', [person, dict(name='別人', kana='アンドウヤスシ')])
        with self.assertRaises(ConversionError):
            match_person('安東靖', [person])

    def test_duplicate_uses_timestamp_not_row_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'registrations.xlsx'
            book = Workbook()
            sheet = book.active
            sheet.append(['タイムスタンプ','共通ID','氏名','氏名フリガナ','氏名（英語表記）',
                          '所属(〇〇研究科××専攻 等)','専門（一単語で、例：海洋生物学、中国思想史など）'])
            sheet.append([dt.datetime(2026,10,2),123.0,'試験 太郎','シケン タロウ','Taro','理学系研究科物理学専攻','新分野'])
            sheet.append([dt.datetime(2026,10,1),123,'試験太郎','シケン タロウ','Taro','理学系研究科物理学専攻','旧分野'])
            book.save(path)
            people = read_registrations(path, [])
            self.assertEqual(len(people), 1)
            self.assertEqual(people[0]['field'], '新分野')

    def test_rejects_overlap_gap_and_bad_reference(self):
        talks = [dict(id='speaker-試験', speaker='試験')]
        days = {'2026-11-21': dict(start='10:00', end='10:40')}
        valid = [dict(date='2026-11-21',start='10:00',end='10:20',type='talk',talkId='speaker-試験',speaker='試験'),
                 dict(date='2026-11-21',start='10:20',end='10:40',type='break',title='座談会')]
        validate(talks, valid, days)
        for changes in [dict(start='10:10'), dict(start='10:30'), dict(end='10:10')]:
            with self.assertRaises(ConversionError):
                validate(talks, [valid[0], dict(valid[1], **changes)], days)
        with self.assertRaises(ConversionError):
            validate(talks, [dict(valid[0], talkId='unknown'), valid[1]], days)

    def test_output_rollback_on_write_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'data'
            output.mkdir()
            names = ['config.json','talks.json','schedule.json']
            for name in names:
                (output/name).write_text('original-'+name)
            replace = os.replace
            calls = []
            def fail_second(source, target):
                calls.append(target)
                if len(calls) == 2:
                    raise OSError('test failure')
                return replace(source, target)
            with patch('converter.os.replace', side_effect=fail_second):
                with self.assertRaises(OSError):
                    write_result({name: [] for name in names}, {}, output, Path(directory)/'reports')
            for name in names:
                self.assertEqual((output/name).read_text(), 'original-'+name)

    @unittest.skipUnless(os.environ.get('KF77_SHIFT_V4'), 'KF77_SHIFT_V4 指定時に新版PDFを確認')
    def test_updated_shift_keeps_talks_and_reads_unlabelled_merged_event(self):
        talks = json.loads((ROOT/'data/talks.json').read_text())
        config = json.loads((ROOT/'data/config.json').read_text())
        original = json.dumps(talks, ensure_ascii=False)
        result, report = convert_schedule(Path(os.environ['KF77_SHIFT_V4']), talks, config)
        self.assertEqual(set(result), {'schedule.json'})
        self.assertEqual(json.dumps(talks, ensure_ascii=False), original)
        slots = {(s['date'], s['start']): s for s in result['schedule.json']}
        for date, start, speaker in [('2026-11-21','11:40','岡田正直'),
                                     ('2026-11-22','11:20','山田江里子'),
                                     ('2026-11-22','14:00','安藤靖'),
                                     ('2026-11-23','10:20','梅村悠介'),
                                     ('2026-11-23','11:40','山田江里子')]:
            self.assertEqual(slots[date,start]['speaker'], speaker)
        event = slots['2026-11-23','12:00']
        self.assertEqual((event['type'],event['title'],event['end']),('break','座談会','12:40'))
        self.assertFalse(any(s.get('speaker')=='田口晴翔' for s in result['schedule.json']))
        self.assertEqual(report['counts'], dict(talks=12,talkSlots=51,otherSlots=3,days=3))

    @unittest.skipUnless(os.environ.get('KF77_SOURCE_DIR'), 'KF77_SOURCE_DIR 指定時に元資料との統合確認を実施')
    def test_supplied_files_end_to_end(self):
        folder = Path(os.environ['KF77_SOURCE_DIR'])
        result, report = convert(folder/'シフトkf77_ver01.pdf', folder/'kf77参加登録（回答）.xlsx',
                                 folder/'講演題目一覧内部用_kf77.xlsx',
                                 json.loads((ROOT/'data/config.json').read_text()))
        self.assertEqual(report['counts'], dict(talks=13,talkSlots=51,otherSlots=3,days=3))
        by_id = {t['id']:t for t in result['talks.json']}
        schedule = result['schedule.json']
        self.assertEqual([(x['date'],x['start'],x['end'],x['title']) for x in schedule if x['type']=='break'],
                         [(f'2026-11-{day}', '12:00','12:40','座談会') for day in [21,22,23]])
        self.assertEqual(next(s for s in schedule if s['date']=='2026-11-21')['talkId'], 'speaker-安藤靖')
        self.assertEqual(sum(s.get('talkId')=='speaker-佐藤諒' for s in schedule), 2)
        for slot in schedule:
            if slot['type']=='talk':
                self.assertEqual(slot['speaker'],by_id[slot['talkId']]['speaker'])
        public = json.dumps([result['talks.json'], result['schedule.json']],ensure_ascii=False)
        self.assertNotIn('メール',public)
        self.assertNotIn('@',public)
        self.assertNotIn('共通ID',public)
        self.assertNotIn('3253225576',public)


if __name__ == '__main__':
    unittest.main()

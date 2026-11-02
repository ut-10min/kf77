#!/usr/bin/env python3
"""3資料のファイル選択だけで変換する、localhost専用の画面。"""
import argparse
from email.parser import BytesParser
from email.policy import default
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import threading
import webbrowser
import zipfile

from converter import ROOT, ConversionError, convert, write_result

TOKEN = secrets.token_urlsafe(32)
MAX_UPLOAD = 25 * 1024 * 1024
PAGE = '''<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>kf77 講演データ変換</title>
<style>body{font:18px/1.7 system-ui,sans-serif;background:#f4f7fb;color:#142f50;margin:0}
main{max-width:680px;margin:40px auto;padding:28px;background:white;border-radius:16px}
label{display:block;margin:24px 0}input{display:block;max-width:100%;margin:8px 0;font:inherit}
button,a{font:inherit}button{background:#0055ad;color:white;border:0;padding:12px 24px;border-radius:8px;cursor:pointer}
.notice{background:#eef5ff;padding:18px;border-radius:8px;overflow-wrap:anywhere}h1{font-size:28px}small{color:#53667b}
@media(max-width:720px){main{margin:12px;padding:20px}}</style><main>
<h1>kf77 講演データ変換</h1>
<p>3つの資料を選んで変換すると、サイトの講演一覧・タイムテーブルを更新します。</p>
<p class="notice">資料はこのパソコン内で処理します。メールアドレス・内部の共通ID・運営シフトは公開JSONに含めません。現在のJSONは自動でバックアップします。</p>
<form method="post" enctype="multipart/form-data" action="/convert">
<input type="hidden" name="token" value="__TOKEN__">
<label>① シフト表（PDF）<input type="file" name="shift" accept=".pdf" required></label>
<label>② 参加登録の回答（Excel）<input type="file" name="registration" accept=".xlsx" required></label>
<label>③ 講演題目一覧（Excel）<input type="file" name="titles" accept=".xlsx" required></label>
<p><small>同じ形式の資料に対応します。照合できない氏名や不明な時刻があれば、更新せずエラーを表示します。</small></p>
<button type="submit">JSONに変換して更新</button></form>__RESULT__</main></html>'''


def build_site():
    node = shutil.which('node')
    bundled = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
    if not node and bundled.is_file():
        node = str(bundled)
    if not node:
        return 'JSONの更新が完了しました。ページへの反映には npm run build を実行してください。'
    try:
        subprocess.run([node, str(ROOT/'scripts/build-static.js')], cwd=ROOT,
                       check=True, capture_output=True, timeout=45)
        return 'JSONの更新と公開用HTMLの生成が完了しました。'
    except (subprocess.SubprocessError, OSError):
        return 'JSONは更新済みです。HTMLの生成に失敗しました。npm run build で詳細を確認してください。'


class Handler(BaseHTTPRequestHandler):
    def send_page(self, result='', status=200):
        content = PAGE.replace('__TOKEN__', TOKEN).replace('__RESULT__', result).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.valid_host() or self.path != '/':
            self.send_error(404)
            return
        self.send_page()

    def do_POST(self):
        if not self.valid_host() or self.path != '/convert':
            self.send_error(404)
            return
        try:
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers['Host']:
                raise ConversionError('別のサイトからの送信は受け付けません。')
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= MAX_UPLOAD:
                raise ConversionError('ファイルの合計は25MB以内にしてください。')
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data;'):
                raise ConversionError('ファイル選択フォームから送信してください。')
            message = BytesParser(policy=default).parsebytes(
                ('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+self.rfile.read(size))
            parts = {}
            for part in message.iter_parts():
                name = part.get_param('name', header='content-disposition')
                if name in parts or name not in {'token','shift','registration','titles'}:
                    raise ConversionError('送信内容が不正です。')
                parts[name] = part
            if set(parts) != {'token','shift','registration','titles'} or not secrets.compare_digest(
                    parts['token'].get_payload(decode=True).decode(), TOKEN):
                raise ConversionError('画面を再読み込みして3つのファイルを選んでください。')
            with tempfile.TemporaryDirectory(prefix='kf77-import-') as directory:
                paths = {}
                filenames = {}
                for name, extension in [('shift','.pdf'),('registration','.xlsx'),('titles','.xlsx')]:
                    filename = parts[name].get_filename() or ''
                    if Path(filename).suffix.lower() != extension:
                        raise ConversionError(f'{name}: {extension} ファイルを指定してください。')
                    payload = parts[name].get_payload(decode=True)
                    if not payload:
                        raise ConversionError('空のファイルは読み込めません。')
                    paths[name] = Path(directory)/(name+extension)
                    paths[name].write_bytes(payload)
                    filenames[name] = Path(filename).name
                    if extension == '.xlsx':
                        with zipfile.ZipFile(paths[name]) as archive:
                            if sum(x.file_size for x in archive.infolist()) > 100*1024*1024:
                                raise ConversionError('Excelの展開後サイズが上限を超えています。')
                config = json.loads((ROOT/'data/config.json').read_text(encoding='utf-8'))
                result, report = convert(paths['shift'], paths['registration'], paths['titles'], config)
                for name, filename in filenames.items():
                    report['sources'][name]['filename'] = filename
                backup = write_result(result, report, ROOT/'data', ROOT/'.local/imports')
            message = build_site()
            counts = report['counts']
            summary = f"講演{counts['talks']}件、登壇{counts['talkSlots']}枠、座談会・休憩{counts['otherSlots']}枠、{counts['days']}日分。"
            notes = ''.join('<li>'+html.escape(note)+'</li>' for note in report['notes'])
            self.send_page('<section class="notice"><h2>変換結果</h2><p>'+html.escape(message)+
                           '</p><p>'+summary+'</p><ul>'+notes+'</ul><p>バックアップ・照合レポート：<br><small>'+
                           html.escape(str(backup))+'</small></p></section>')
        except Exception as exc:
            self.send_page('<section class="notice"><h2>変換できませんでした</h2><p>'+
                           html.escape(str(exc))+'</p></section>', 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open-browser', action='store_true', help='起動後にブラウザーを開く')
    args = parser.parse_args()
    server = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f'変換画面: http://127.0.0.1:{args.port}/', flush=True)
    if args.open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f'http://127.0.0.1:{args.port}/')).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

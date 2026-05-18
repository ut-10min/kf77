# kf77 website

このリポジトリは、駒場祭77回生の講演企画の公式サイトのソースコードを管理しています。

基本的にdata/ 以下のJSONファイルを編集して、HTML内の仮表示を上書きする形で運用します。HTMLやCSS、JavaScriptは基本的に編集不要です。
- data/config.json: 外部リンク、日付、会場、SNS、動画、地図
- data/talks.json: 講演内容
- data/schedule.json: タイムテーブル

.gihub内のworkflowにあるstatic-pages.ymlで、push,pullの時点で自動的に`npm run build` を実行してこれらの情報を反映させ、`dist/` に静的HTMLを生成するようにしています。

Github Pagesの設定で、`dist/` を公開するようにするため、
1.リポジトリトップのツールバー左上にあるSettingsを押す
2.左のバーからPagesにアクセス
3.Build and deploymentのSourceをGithub Actionsに変更
という手順を踏んでください。

アンケートを画面内にアクティベートする等の処理はindex.htmlを編集してください。

## data/config.json について

`config.json` には、毎回変更する情報を置いています。

- 開催日時
- 会場名・住所
- 外部リンク
- SNSリンク
- 運営統括・運営メンバー


## HTML内の仮表示とconfigの関係

`data-config` / `data-link` / `data-sns` が付いた場所は、ページ読み込み後に `data/config.json` の値で上書きされます。ただこの処理を毎回クライアントで行うと、ページの表示が遅くなったり、JavaScriptが動かない環境で情報が表示されない可能性があります。そこでGithub Pagesのビルドプロセスで、これらのJSONの内容をHTMLに事前反映する形で静的ビルドできるようにしています。

HTML内には実データを重複して書かず、以下のような仮表示だけを置いています。

- 日時: `XXXX年X月XX日 XX:XX–XX:XX`
- 会場: `会場未定`
- URL: `href="#"`

JavaScriptが正常に動くと、configの値が優先されます。JavaScriptが動かない場合は、HTML内の仮表示がそのまま表示されます。

## talks.json と schedule.json について 

`talks.json`のテンプレは以下のようになっています。
```
  {
    "id": "speaker-小林涼太郎",
    "title": "ことばの使用から意味を見る",
    "speaker": "小林涼太郎",
    "speakerKana": "コバヤシ リョウタロウ",
    "englishName": "Ryotaro Kobayashi",
    "affiliation": "工学系研究科",
    "department": "システム創成学専攻",
    "field": "金融情報学",
    "description": "語の「意味」とは何かを明らかにすることは難しいですが、語の使用に注目すれば、データ中の統計的な分布から意味の一側面を捉えられます。この発想が最先端のAIや言語処理研究とどうつながっているかを話します。"
  },
```
`schedule.json`のテンプレは以下のようになっています。
```
  {
    "date": "2026-05-16",
    "dateLabel": "5月16日（土）",
    "start": "15:40",
    "end": "16:00",
    "talkId": "speaker-小林涼太郎",
    "speaker": "小林涼太郎",
    "type": "talk",
  },
```  
タイムテーブルのpdfやアンケート結果をこのjsonに反映させるときは、ChatGPT等をうまく活用してください。`talkId` と `speaker` は、`talks.json` の `id` と `speaker` を対応させる必要があります。
ワークショップもタイトルにワークショップとつけることで切り替わるように対応しているはずです、多分。

mf99ではレギュラーが発生してキャンセル処理もできるような拡張を施してあるので、万が一中止等の事態があれば参照してください。

## Node.js による静的ビルド

通常の開発では、これまで通りルート直下の `index.html`, `talks.html`, `timetable.html` をそのまま使えます。ローカルでもNode.js を使える環境では、以下で `dist/` に静的HTMLを生成できます。

```bash
npm run build
```

静的ビルドでは、`data/config.json`, `data/talks.json`, `data/schedule.json` の内容をHTMLへ事前反映します。これで基本的なパーツは静的に配信となり、YouTube と Google Map の iframe 生成だけは `dist/js/embed-runtime.js` でクライアント側で行う形になります。

## 自動Build周りの管理
Node.js のビルドスクリプトは、`scripts/static-build.js` と'.github/workflows/static-pages.yml'に書いています。Node.jsのバージョン指定等を行っているため、古くなっていたらバージョン等を更新してください。
# ✍️ AIライティングツール

Python + Streamlit + Gemini API で作った、個人用のAIライティングツールです。

## 機能

| ツール | 内容 |
| --- | --- |
| 📝 ブログ記事作成 | テーマ・キーワード・読者・トーンから記事本文 or 構成案を作成 |
| ✉️ メール返信 | 受信メールと伝えたい要点から返信文を複数パターン作成 |
| 📋 要約 | 文章 / テキストファイルを箇条書き・3行まとめなどで要約 |
| 🖊️ 校正・リライト | 誤字脱字チェック、丁寧に・簡潔に などの書き換え（修正理由付き） |
| 🌐 翻訳 | ニュアンスを保った多言語翻訳 |
| 📣 SNS投稿作成 | X / Instagram / Threads / LinkedIn / Facebook 向けの投稿文 |
| 💡 タイトル・キャッチコピー | タイトルやコピー案を大量に生成 |
| 💬 自由入力 | 自由なライティング依頼 |

共通機能: ストリーミング表示 / 追加指示での修正 / Markdownダウンロード / 履歴（セッション中のみ）/ モデル・創造性の切り替え

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --only-binary=:all: -r requirements.txt   # Python 3.15 ではビルド失敗を避けるため wheel のみを指定
cp .env.example .env   # GEMINI_API_KEY を設定
streamlit run app.py
```

APIキーは [Google AI Studio](https://aistudio.google.com/apikey) で発行できます。`.env` を使わずに、画面のサイドバーから入力することもできます。

## 構成

```
app.py                      # 画面（サイドバー・生成・結果表示）
writing_tools/
  gemini_client.py          # Gemini API 呼び出し
  tools.py                  # 各ツールの入力フォームとプロンプト
```

ツールを追加するには、`tools.py` にフォーム関数を書いて `TOOLS` に `Tool(...)` を追加するだけです。

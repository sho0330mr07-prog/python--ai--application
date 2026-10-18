# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

Python + Streamlit + Gemini API（`google-genai` SDK）で作った個人用のAIライティングツール（UIは日本語）。データベースと認証は意図的に持たない。状態はブラウザセッション中の `st.session_state` にのみ保持される。

## コマンド

```bash
source .venv/bin/activate
pip install --only-binary=:all: -r requirements.txt   # Python 3.15 では通常の pip install だと cryptography のビルドで失敗する
streamlit run app.py                                  # http://localhost:8501
```

設定は `.env`（`.env.example` 参照）から読み込む: `GEMINI_API_KEY`、任意で `GEMINI_MODEL`（組み込みの `MODELS` にないモデル名を指定すると選択肢の先頭に追加される）。APIキーはサイドバーからも入力できる。

テストスイートやリンターは未設定。UIの変更をヘッドレスで確認するには `streamlit.testing.v1.AppTest` を使う。`app.py` は絶対パスで渡すこと（相対パスは呼び出し元ファイル基準で解決される）。`writing_tools.gemini_client.GeminiClient.stream` を文字列のイテレーターを返す関数にモンキーパッチすれば、実際のAPIを呼ばずに生成フローを確認できる。

## アーキテクチャ

- `writing_tools/tools.py` — 各ツールは `Tool` データクラス（key, name, icon, システムプロンプト, temperature, `form`）。`form()` はStreamlitのウィジェットを描画し、ユーザープロンプト文字列を返す。必須（`*`）項目が未入力なら `None` を返し、生成ボタンが無効になる。ツールの追加は、フォーム関数を書いて `TOOLS` に追加するだけ。1回の実行で描画されるフォームは1つだが、ツール間でラベルが同じウィジェットには明示的な `key=` が必要。
- `writing_tools/gemini_client.py` — `stream()` が `generate_content_stream` のテキストチャンクを `st.write_stream` 用に yield する。429/500/503/504 は指数バックオフで再試行し、駄目なら（404 は即座に）`app.py` の `FALLBACK_MODELS` の順に別モデルへ切り替える。出力開始後のエラーは文章の重複を避けるため再試行しない。実際に応答したモデルは `used_model` に入る。
- `app.py` — サイドバー（ツール選択・設定・履歴）、メインフォーム、結果表示。

**生成フロー（重要）:** 生成リクエストは `st.session_state.pending = (tool_key, prompt)` としてキューに積む（生成ボタン、または修正フォームの `on_click` コールバックがセットする）。`show_result()` がそれを取り出し、その場でストリーミング表示して `st.session_state.results[tool_key]` と `history` に保存する。生成後に `st.rerun()` を再導入しないこと。このキュー方式は、再実行ループやエラーメッセージの消失を避けるためのもの。「修正」機能は、直前の結果とユーザーの指示から新しいプロンプトを組み立てる。

サイドバーの「創造性の調整」スライダーは、各ツールの基本temperatureに加算するオフセット（0〜2に制限）。

`Tool.key` はセッション状態やウィジェットのキー（`results[key]`、`refine_input_{key}`、フォーム `refine_{key}`）に使われているため、変更するとそのツールの保存済み結果が失われる。修正リクエストはそのツール自身のシステムプロンプトを使う。

UIテキストとプロンプトはすべて日本語。各ツールのシステムプロンプトは `BASE_SYSTEM`（前置きなしで成果物だけを出力させる指示）をベースにしている。

`load_dotenv()` はStreamlitの再実行ごとに呼ばれるが、設定済みの環境変数は上書きしない。そのため `.env` の既存の値を変更した場合は `streamlit run` の再起動が必要。

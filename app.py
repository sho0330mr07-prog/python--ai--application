"""AIライティングツール（Streamlit + Gemini API）

起動: streamlit run app.py
"""

import os
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from google.genai import errors

from writing_tools.gemini_client import GeminiClient
from writing_tools.tools import TOOLS, Tool

load_dotenv()

MODELS = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]
# 選択中のモデルが混雑（503）などで使えないときに順に試すモデル
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

st.set_page_config(page_title="AIライティングツール", page_icon="✍️", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []  # {time, tool, prompt, output}
if "results" not in st.session_state:
    st.session_state.results = {}  # ツールごとの最新の生成結果


# ---------------------------------------------------------------- サイドバー
def sidebar() -> tuple[Tool, GeminiClient | None]:
    with st.sidebar:
        st.title("✍️ AIライティング")
        tool = st.radio(
            "ツールを選択",
            TOOLS,
            format_func=lambda t: f"{t.icon} {t.name}",
            label_visibility="collapsed",
        )

        st.divider()
        env_key = os.getenv("GEMINI_API_KEY", "")
        with st.expander("⚙️ 設定", expanded=not env_key):
            # ウィジェットの初期値はブラウザに送られるため、.env のキーは入力欄に入れずサーバー側だけで使う
            if env_key:
                st.caption("🔑 .env の GEMINI_API_KEY を使用中")
                api_key = env_key
            else:
                api_key = st.text_input(
                    "Gemini APIキー",
                    type="password",
                    help=".env に GEMINI_API_KEY を書くと入力を省略できます",
                )
            default_model = os.getenv("GEMINI_MODEL", MODELS[0])
            options = MODELS if default_model in MODELS else [default_model, *MODELS]
            model = st.selectbox("モデル", options, index=options.index(default_model))
            st.session_state.temperature_offset = st.slider(
                "創造性の調整", -0.5, 0.5, 0.0, 0.1,
                help="プラスで自由な発想、マイナスで堅実な出力になります",
            )

        st.divider()
        st.subheader("🕘 履歴")
        if not st.session_state.history:
            st.caption("まだ履歴はありません")
        for item in reversed(st.session_state.history[-10:]):
            with st.expander(f"{item['time']} {item['tool']}"):
                st.markdown(item["output"])
        if st.session_state.history:
            st.button("履歴をクリア", on_click=clear_history, use_container_width=True)

    client = GeminiClient(api_key, model, FALLBACK_MODELS) if api_key else None
    return tool, client


# ---------------------------------------------------------------- 生成処理
# 生成リクエストは st.session_state.pending に (ツールのkey, プロンプト) として積み、
# 結果表示エリアで実行する。こうすると st.rerun() なしで正しい位置に結果を出せる。
def clear_history() -> None:
    st.session_state.history = []


def request_refine(tool_key: str) -> None:
    """「修正する」ボタンのコールバック。直前の結果と追加指示から修正依頼を作る。"""
    instruction = st.session_state.get(f"refine_input_{tool_key}", "").strip()
    output = st.session_state.results.get(tool_key)
    if instruction and output:
        st.session_state.pending = (
            tool_key,
            f"次の文章を、指示に従って修正してください。\n\n指示: {instruction}\n\n---文章---\n{output}",
        )


def generate(tool: Tool, client: GeminiClient, prompt: str) -> bool:
    """結果をストリーミング表示しながら生成し、保存する。成功したら True を返す。"""
    temperature = min(2.0, max(0.0, tool.temperature + st.session_state.temperature_offset))
    try:
        with st.container(border=True), st.spinner("生成中…（混雑時は自動で再試行します）"):
            output = st.write_stream(client.stream(prompt, tool.system, temperature))
    except errors.APIError as e:
        if e.code == 503:
            st.error("Geminiのサーバーが混雑しています（503）。少し時間をおいてから再度お試しください。")
        elif e.code == 429:
            st.error("APIの利用上限に達しました（429）。しばらく待つか、別のモデルを選んでください。")
        else:
            st.error(f"生成中にエラーが発生しました（{e.code}）: {e.message}")
        return False
    except Exception as e:  # 通信エラーなどを画面に表示する
        st.error(f"生成中にエラーが発生しました: {e}")
        return False

    if client.used_model != client.model:
        st.info(f"{client.model} が混雑中などで使えなかったため、{client.used_model} で生成しました。")

    st.session_state.results[tool.key] = output
    st.session_state.history.append(
        {
            "time": datetime.now().strftime("%H:%M"),
            "tool": tool.name,
            "prompt": prompt,
            "output": output,
        }
    )
    return True


def show_result(tool: Tool, client: GeminiClient | None) -> None:
    pending = st.session_state.pop("pending", None)
    streamed = False
    if pending and pending[0] == tool.key:
        if client is None:
            st.error("サイドバーの「設定」でGemini APIキーを入力してください。")
            return
        st.subheader("生成結果")
        if not generate(tool, client, pending[1]):
            return
        streamed = True

    output = st.session_state.results.get(tool.key)
    if not output:
        return

    if not streamed:
        st.subheader("生成結果")
        with st.container(border=True):
            st.markdown(output)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.download_button(
            "📥 Markdownでダウンロード",
            output,
            file_name=f"{tool.key}_{datetime.now():%Y%m%d_%H%M}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col2:
        with st.popover("📋 コピー用テキスト", use_container_width=True):
            st.code(output, language="markdown", wrap_lines=True)

    # 生成結果に追加の指示を出してブラッシュアップする
    with st.form(f"refine_{tool.key}", clear_on_submit=True):
        st.text_input(
            "🔁 追加の指示で修正する",
            placeholder="例: もう少し短く / 具体例を増やして / 敬語を強めに",
            key=f"refine_input_{tool.key}",
        )
        st.form_submit_button("修正する", on_click=request_refine, args=(tool.key,))


# ---------------------------------------------------------------- メイン
def main() -> None:
    tool, client = sidebar()

    st.title(f"{tool.icon} {tool.name}")
    st.caption(tool.description)

    prompt = tool.form()
    if st.button("✨ 生成する", type="primary", disabled=prompt is None):
        st.session_state.pending = (tool.key, prompt)
    if prompt is None:
        st.caption("* の付いた項目を入力すると生成できます")

    show_result(tool, client)


main()

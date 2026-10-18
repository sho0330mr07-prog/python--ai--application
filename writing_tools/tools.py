"""各ライティングツールの定義。

ツールごとに「入力フォームの描画」と「プロンプトの組み立て」を行う関数を持つ。
フォーム関数は入力が揃っていればプロンプト文字列を、不足していれば None を返す。
新しいツールを追加するときは関数を書いて TOOLS に登録するだけでよい。
"""

from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

BASE_SYSTEM = (
    "あなたは日本語のプロのライター兼編集者です。"
    "読み手にとって分かりやすく、自然で正確な文章を書きます。"
    "前置きや「承知しました」などの応答文は書かず、成果物だけを出力してください。"
)

TONES = ["ていねい", "フランク", "ビジネス", "やわらかい", "論理的", "熱意のある"]


@dataclass
class Tool:
    key: str
    name: str
    icon: str
    description: str
    system: str
    form: Callable[[], str | None]
    temperature: float = 0.7


def _uploaded_text(label: str, key: str) -> str:
    """テキストファイルがアップロードされていれば中身を返す。"""
    file = st.file_uploader(label, type=["txt", "md"], key=key)
    if file is None:
        return ""
    return file.read().decode("utf-8", errors="ignore")


# ---------------------------------------------------------------- ブログ記事
def blog_form() -> str | None:
    theme = st.text_input("記事のテーマ *", placeholder="例: 在宅ワークで集中力を保つコツ")
    col1, col2 = st.columns(2)
    with col1:
        keywords = st.text_input("SEOキーワード（カンマ区切り）", placeholder="在宅ワーク, 集中力")
        audience = st.text_input("想定読者", placeholder="例: 20〜30代の会社員")
    with col2:
        tone = st.selectbox("トーン", TONES, key="blog_tone")
        length = st.select_slider(
            "文字数の目安", options=[800, 1500, 2000, 3000, 5000], value=2000
        )
    mode = st.radio("出力内容", ["記事本文", "構成案（見出しのみ）"], horizontal=True)
    notes = st.text_area("盛り込みたい内容・補足", height=100)

    if not theme:
        return None
    if mode == "構成案（見出しのみ）":
        task = (
            "以下の条件でブログ記事の構成案を作成してください。"
            "タイトル案を3つ、リード文の方向性、H2/H3の見出し構成と各見出しで書く内容の要点を示してください。"
        )
    else:
        task = (
            f"以下の条件でブログ記事を約{length}文字で執筆してください。"
            "Markdown形式で、タイトル（#）、導入文、見出し（##, ###）、まとめを含めてください。"
        )
    return f"""{task}

- テーマ: {theme}
- SEOキーワード: {keywords or "指定なし"}
- 想定読者: {audience or "一般読者"}
- トーン: {tone}
- 補足: {notes or "なし"}
"""


# ---------------------------------------------------------------- メール返信
def email_form() -> str | None:
    received = st.text_area("受信したメール本文 *", height=200)
    points = st.text_area(
        "返信で伝えたいこと（箇条書きでOK）",
        height=100,
        placeholder="例: 日程は来週火曜で了承 / 資料は前日までに送る",
    )
    col1, col2 = st.columns(2)
    with col1:
        tone = st.selectbox("トーン", ["ビジネス（丁寧）", "社内向け（やや丁寧）", "カジュアル"])
        stance = st.selectbox("返答の方向性", ["指定なし", "承諾する", "お断りする", "質問・確認する", "お礼を伝える"])
    with col2:
        sender_name = st.text_input("自分の名前（署名用）")
        variations = st.number_input("パターン数", min_value=1, max_value=3, value=1)

    if not received:
        return None
    return f"""以下の受信メールに対する返信文を{variations}パターン作成してください。
各パターンには件名（Re: を付ける）と本文を含め、パターンごとに「## パターン1」のように見出しを付けてください。

- トーン: {tone}
- 返答の方向性: {stance}
- 伝えたいこと: {points or "受信内容に対する適切な返答"}
- 署名の名前: {sender_name or "（名前）"}

---受信メール---
{received}
"""


# ---------------------------------------------------------------- 要約
def summary_form() -> str | None:
    text = st.text_area("要約したい文章", height=250)
    uploaded = _uploaded_text("またはテキストファイルをアップロード", key="summary_file")
    col1, col2 = st.columns(2)
    with col1:
        style = st.selectbox("要約の形式", ["箇条書き", "段落（文章）", "3行まとめ", "見出し付きレポート"])
    with col2:
        length = st.selectbox("長さ", ["短め", "標準", "詳しめ"], index=1)
    extras = st.multiselect("追加で出力する項目", ["重要キーワード", "結論・アクション項目", "疑問点・不明点"])

    source = text or uploaded
    if not source:
        return None
    extra_line = f"\n要約の後に次の項目も出力してください: {', '.join(extras)}" if extras else ""
    return f"""以下の文章を「{style}」の形式で、{length}に要約してください。
原文にない情報は加えず、重要なポイントを漏らさないでください。{extra_line}

---原文---
{source}
"""


# ---------------------------------------------------------------- 校正・リライト
def rewrite_form() -> str | None:
    text = st.text_area("対象の文章 *", height=250)
    mode = st.selectbox(
        "処理内容",
        [
            "校正（誤字脱字・文法のチェック）",
            "読みやすく書き直す",
            "より丁寧にする",
            "カジュアルにする",
            "簡潔に短くする",
            "詳しく膨らませる",
            "小学生にも分かるように",
        ],
    )
    show_diff = st.checkbox("修正箇所と理由も表示する", value=True)

    if not text:
        return None
    diff_line = (
        "\n最後に「## 主な修正点」として、どこをなぜ直したかを箇条書きで示してください。" if show_diff else ""
    )
    return f"""次の文章に対して「{mode}」を行ってください。
元の意味や事実は変えないでください。「## 修正後」の見出しの下に修正後の文章を出力してください。{diff_line}

---対象の文章---
{text}
"""


# ---------------------------------------------------------------- 翻訳
LANGUAGES = ["英語", "日本語", "中国語（簡体字）", "韓国語", "スペイン語", "フランス語", "ドイツ語"]


def translate_form() -> str | None:
    text = st.text_area("翻訳したい文章 *", height=250)
    col1, col2 = st.columns(2)
    with col1:
        target = st.selectbox("翻訳先の言語", LANGUAGES)
    with col2:
        style = st.selectbox("スタイル", ["自然な意訳", "直訳寄り", "ビジネス文書向け", "カジュアルな会話調"])
    explain = st.checkbox("難しい表現の解説を付ける")

    if not text:
        return None
    explain_line = "\n翻訳の後に、訳し方に工夫した表現や注意点を簡単に解説してください。" if explain else ""
    return f"""次の文章を{target}に翻訳してください。スタイルは「{style}」です。{explain_line}

---原文---
{text}
"""


# ---------------------------------------------------------------- SNS投稿
PLATFORMS = {
    "X（旧Twitter）": "140字以内。ハッシュタグは2〜3個。",
    "Instagram": "絵文字を適度に使い、改行で読みやすく。末尾にハッシュタグを10個程度。",
    "Threads": "500字以内の親しみやすい文章。",
    "LinkedIn": "ビジネス向けの落ち着いた文体で、学びや気づきを中心に。",
    "Facebook": "近況報告のような自然な文章。",
}


def sns_form() -> str | None:
    topic = st.text_area("投稿したい内容 *", height=120, placeholder="例: ブログで在宅ワークの記事を公開した告知")
    col1, col2 = st.columns(2)
    with col1:
        platform = st.selectbox("プラットフォーム", list(PLATFORMS))
        tone = st.selectbox("トーン", TONES, index=1, key="sns_tone")
    with col2:
        count = st.number_input("案の数", min_value=1, max_value=5, value=3)
        url = st.text_input("URL（任意）")

    if not topic:
        return None
    return f"""{platform}向けの投稿文を{count}案作成してください。
- ルール: {PLATFORMS[platform]}
- トーン: {tone}
- URL: {url or "なし"}
- 内容: {topic}

各案には「## 案1」のように見出しを付けてください。
"""


# ---------------------------------------------------------------- タイトル・キャッチコピー
def headline_form() -> str | None:
    subject = st.text_area("対象の内容（記事・商品・サービスなど） *", height=120)
    col1, col2 = st.columns(2)
    with col1:
        kind = st.selectbox("種類", ["ブログタイトル", "キャッチコピー", "メール件名", "YouTubeタイトル", "商品名・ネーミング"])
    with col2:
        count = st.slider("案の数", 3, 20, 10)
    angle = st.multiselect(
        "切り口", ["数字を入れる", "疑問形", "ベネフィット重視", "意外性", "緊急性", "SEOを意識"]
    )

    if not subject:
        return None
    return f"""次の内容について「{kind}」を{count}案考えてください。
切り口: {', '.join(angle) if angle else "多様な切り口で"}
番号付きリストで出力し、各案の後に（ ）で狙いを一言添えてください。

---内容---
{subject}
"""


# ---------------------------------------------------------------- 自由入力
def free_form() -> str | None:
    prompt = st.text_area(
        "指示を自由に入力してください *",
        height=250,
        placeholder="例: 退職のあいさつ文を、お世話になった上司向けに300字程度で書いて",
    )
    return prompt or None


TOOLS: list[Tool] = [
    Tool("blog", "ブログ記事作成", "📝", "テーマからブログ記事や構成案を作成します。",
         BASE_SYSTEM + "SEOと読みやすさを意識し、具体例を交えて書いてください。", blog_form),
    Tool("email", "メール返信", "✉️", "受信メールに対する返信文を考えます。",
         BASE_SYSTEM + "日本のビジネスマナーに沿った自然なメールを書いてください。", email_form),
    Tool("summary", "要約", "📋", "長い文章をポイントを押さえて要約します。",
         BASE_SYSTEM, summary_form, temperature=0.3),
    Tool("rewrite", "校正・リライト", "🖊️", "誤字脱字のチェックや言い換えを行います。",
         BASE_SYSTEM, rewrite_form, temperature=0.4),
    Tool("translate", "翻訳", "🌐", "ニュアンスを保ったまま翻訳します。",
         "あなたはプロの翻訳者です。前置きは書かず、訳文（と指示された解説）だけを出力してください。",
         translate_form, temperature=0.3),
    Tool("sns", "SNS投稿作成", "📣", "各SNSに合わせた投稿文を作ります。",
         BASE_SYSTEM + "各SNSの文化に合った、反応を得やすい文章を書いてください。", sns_form, temperature=0.9),
    Tool("headline", "タイトル・キャッチコピー", "💡", "タイトルやコピーの案を大量に出します。",
         BASE_SYSTEM + "人の目を引く、印象に残る言葉を選んでください。", headline_form, temperature=1.0),
    Tool("free", "自由入力", "💬", "どんなライティング依頼でも自由に指示できます。",
         BASE_SYSTEM, free_form),
]

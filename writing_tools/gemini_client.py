"""Gemini API との通信をまとめたモジュール。"""

import time
from collections.abc import Iterator

from google import genai
from google.genai import errors, types

# 時間をおけば成功する可能性があるエラー（混雑・レート制限・一時的な障害）
RETRYABLE_CODES = {429, 500, 503, 504}
# 同じモデルで再試行しても無駄なので、すぐ次のモデルに切り替えるエラー
FALLBACK_ONLY_CODES = {404}


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_models: list[str] | None = None,
        max_retries: int = 3,
    ):
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.fallback_models = [m for m in (fallback_models or []) if m != model]
        self.max_retries = max_retries
        self.used_model = model  # 実際に応答したモデル（フォールバック時に変わる）

    def stream(
        self,
        prompt: str,
        system_instruction: str,
        temperature: float = 0.7,
    ) -> Iterator[str]:
        """生成結果をチャンクごとに返すジェネレーター（st.write_stream 用）。

        503 などの一時的なエラーは待ち時間を延ばしながら再試行し、
        それでも駄目なら fallback_models の順に別モデルで生成する。
        出力が始まった後のエラーは、文章が重複しないよう再試行せずそのまま送出する。
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        )
        last_error: errors.APIError | None = None
        for model in [self.model, *self.fallback_models]:
            for attempt in range(self.max_retries):
                started = False
                try:
                    for chunk in self._client.models.generate_content_stream(
                        model=model,
                        contents=prompt,
                        config=config,
                    ):
                        if chunk.text:
                            started = True
                            yield chunk.text
                    self.used_model = model
                    return
                except errors.APIError as e:
                    if started or e.code not in RETRYABLE_CODES | FALLBACK_ONLY_CODES:
                        raise
                    last_error = e
                    if e.code in FALLBACK_ONLY_CODES:
                        break
                    if attempt < self.max_retries - 1:
                        time.sleep(2**attempt)  # 1秒, 2秒, ...
        raise last_error

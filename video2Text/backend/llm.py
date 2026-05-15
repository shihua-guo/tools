import requests

class LLMProcessor:
    def __init__(self, api_key: str, model: str = "qwen-max"):
        self.api_key = api_key
        self.model = model
        self.url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }

        response = requests.post(self.url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def process(
        self,
        text: str,
        style: str,
        generate_content: bool = True,
        generate_titles: bool = False,
        generate_cover_prompt: bool = False,
    ) -> dict:
        prompts = {
            "小红书": "请将以下视频转录文字转换成一篇充满吸引力的小红书文案。要求：使用大量表情符号，语言亲和，分段清晰，包含相关的#标签。文字：",
            "抖音": "请根据以下视频转录文字，创作一段抖音视频脚本或简介。要求：前3秒必须吸睛，节奏感强，语言口语化，简洁有力。文字：",
            "严谨": "请对以下视频转录文字进行纠错和专业化润色。要求：逻辑严密，术语准确，风格客观。文字：",
            "B站": "请将以下视频转录文字转换成一篇适合B站专栏或简介的文章。要求：趣味性强，适当梗，内容详尽。文字：",
        }

        result = {
            "content": "",
            "titles": "",
            "cover_prompt": "",
        }

        if generate_content:
            content_prompt = prompts.get(style, prompts["严谨"])
            result["content"] = self._chat(
                "你是一个资深的自媒体运营专家和文案润色高手。",
                f"{content_prompt}\n\n{text}",
            )

        if generate_titles:
            result["titles"] = self._chat(
                "你是一个标题党专家。",
                f"请基于以下视频转录文字生成 5 个高点击率标题，兼顾信息准确与传播性。风格偏向：{style}。\n\n{text}",
            )

        if generate_cover_prompt:
            result["cover_prompt"] = self._chat(
                "你是一个 AI 绘画提示词专家。",
                f"请根据以下视频转录文字，生成一段用于 AI 绘画（如 Midjourney/Stable Diffusion）的封面图提示词（英文），并尽量贴合 {style} 风格。\n\n{text}",
            )

        return result

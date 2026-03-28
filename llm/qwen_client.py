"""
通义千问 LLM 客户端
适配 openai>=2.0 SDK
支持：普通对话、流式输出、JSON 结构化输出、Function Calling
"""
import json
from typing import Any, AsyncIterator, Dict, List, Optional

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from config.settings import settings


class QwenClient:
    """
    基于 OpenAI 兼容接口的通义千问客户端。

    openai v2 主要变化:
      - 同步客户端: openai.OpenAI()
      - 异步客户端: openai.AsyncOpenAI()
      - response_format 使用 {"type": "json_object"}
      - stream 返回 AsyncStream，需 async for
    """

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 支持的模型
    MODELS = {
        "max":   "qwen-max",
        "plus":  "qwen-plus",
        "turbo": "qwen-turbo",
        "long":  "qwen-long",
    }

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ):
        self.model = model or settings.QWEN_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens
        # openai v2: 直接传 base_url 和 api_key
        self._client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url=self.BASE_URL,
        )

    # ------------------------------------------------------------------
    # 核心对话接口
    # ------------------------------------------------------------------
    async def chat(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        response_format: Optional[str] = None,  # "json" | None
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        基础对话接口。返回模型回复字符串。

        Args:
            response_format: 传 "json" 则强制 JSON 输出（json_object 模式）
            tools:           Function calling 工具定义列表
        """
        messages = self._build_messages(user_message, system_message, history)

        kwargs: Dict[str, Any] = {
            "model":       model or self.model,
            "messages":    messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens":  self.max_tokens,
        }

        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # 多轮 Function Calling
    # ------------------------------------------------------------------
    async def chat_with_tools(
        self,
        user_message: str,
        tools: List[Dict],
        tool_executor: Optional[Any] = None,
        system_message: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        max_rounds: int = 5,
    ) -> str:
        """
        支持多轮 Function Calling 的对话。
        tool_executor: 异步可调用对象，接受 (name, arguments) 返回结果。
        """
        messages: List[ChatCompletionMessageParam] = self._build_messages(
            user_message, system_message, history
        )

        for _ in range(max_rounds):
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            choice = response.choices[0]
            msg = choice.message

            if choice.finish_reason == "tool_calls" and msg.tool_calls:
                # 追加 assistant 消息
                messages.append(msg.model_dump(exclude_none=True))
                # 执行每个工具调用
                for tc in msg.tool_calls:
                    if tool_executor:
                        tool_result = await tool_executor(
                            tc.function.name,
                            json.loads(tc.function.arguments or "{}"),
                        )
                    else:
                        tool_result = {"error": f"{tc.function.name} executor not provided"}
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      json.dumps(tool_result, ensure_ascii=False),
                    })
            else:
                return msg.content or ""

        return "[MaxRoundsExceeded]"

    # ------------------------------------------------------------------
    # 流式输出
    # ------------------------------------------------------------------
    async def stream_chat(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """流式输出，async for chunk in client.stream_chat(...)"""
        messages = self._build_messages(user_message, system_message)
        # openai v2: stream=True 返回 AsyncStream
        async with await self._client.chat.completions.create(
            model=model or self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

    # ------------------------------------------------------------------
    # 文本向量化
    # ------------------------------------------------------------------
    async def embed(self, text: str) -> List[float]:
        """文本向量化（用于记忆检索）"""
        response = await self._client.embeddings.create(
            model="text-embedding-v3",
            input=text,
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量向量化"""
        response = await self._client.embeddings.create(
            model="text-embedding-v3",
            input=texts,
        )
        return [item.embedding for item in response.data]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _build_messages(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[ChatCompletionMessageParam]:
        messages: List[ChatCompletionMessageParam] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        if history:
            messages.extend(history)  # type: ignore[arg-type]
        messages.append({"role": "user", "content": user_message})
        return messages

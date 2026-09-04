"""Chat model wrapper (Cursor or OpenAI). Swap without touching the graph."""
import json
import os
import re
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from operator import itemgetter
from typing import Any, Literal
from typing_extensions import override
from functools import lru_cache

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.language_models.model_profile import ModelProfile
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableLambda, RunnableMap, RunnablePassthrough
from langchain_core.utils.pydantic import is_basemodel_subclass
from pydantic import BaseModel, Field, SecretStr

from cursor_sdk import (
    Agent,
    AgentOptions,
    CursorClient,
    CustomTool,
    CursorAgentError,
    LocalAgentOptions,
    close_default_client,
)

_SDK_LOCK = threading.Lock()
_SDK_CLIENT = None


def get_sdk_client():
    """Keep one local SDK bridge alive for the whole kernel.

    Agent.create() with no client uses CURSOR_SDK_BRIDGE_URL when it is set.
    Cursor's Jupyter kernel often injects that URL after the process behind it
    has already exited, which shows up as ConnectError errno 61.
    """
    global _SDK_CLIENT
    with _SDK_LOCK:
        if _SDK_CLIENT is None:
            for key in (
                "CURSOR_SDK_BRIDGE_URL",
                "CURSOR_SDK_BRIDGE_TOKEN",
                "CURSOR_SDK_BRIDGE_AUTH_TOKEN",
            ):
                os.environ.pop(key, None)
            close_default_client()
            _SDK_CLIENT = CursorClient.launch_bridge(
                workspace=os.getcwd(),
                timeout=60,
                max_retries=2,
            )
        return _SDK_CLIENT


def reset_sdk_client() -> None:
    global _SDK_CLIENT
    with _SDK_LOCK:
        client = _SDK_CLIENT
        _SDK_CLIENT = None
        close_default_client()
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

_ROLE_LABELS = {
    "human": "User",
    "ai": "Assistant",
    "system": "System",
    "tool": "Tool",
    "function": "Function",
}


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def _messages_to_prompt(messages: list[BaseMessage]) -> str:
    lines = []
    for message in messages:
        role = _ROLE_LABELS.get(message.type, message.type.title())
        lines.append(f"{role}: {_message_text(message)}")
    return "\n\n".join(lines)


def _apply_stop(text: str, stop: list[str] | None) -> str:
    if not stop:
        return text
    cut = len(text)
    for token in stop:
        idx = text.find(token)
        if idx != -1:
            cut = min(cut, idx)
    return text[:cut]


def _coerce_json_text(text: str, schema_keys: Sequence[str] | None = None) -> str:
    """Pull a JSON object out of rambling model output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\s*```$", "", stripped)
        stripped = stripped.strip()
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", stripped)
    if match:
        try:
            json.loads(match.group())
            return match.group()
        except json.JSONDecodeError:
            pass

    found: dict[str, str] = {}
    for key in schema_keys or []:
        keyed = re.search(
            rf'{re.escape(key)}\s*["\']?\s*[:=]\s*["\']?(yes|no)["\']?',
            text,
            flags=re.I,
        )
        if keyed:
            found[key] = keyed.group(1).lower()
    if found:
        return json.dumps(found)
    return stripped


class CursorChatModel(BaseChatModel):
    """LangChain chat model backed by a local Cursor agent.

    Each call creates a fresh agent, sends the full message history, waits,
    then disposes. That matches LangChain's stateless chat-model contract.

    Built-in Cursor tools (shell, edit, ...) are off by default so this
    behaves like an LLM. Pass `custom_tools` for a KB retriever, or set
    `builtin_tools=None` to restore the SDK default toolset.
    """

    model_name: str = "composer-2.5"
    api_key: SecretStr | None = Field(default=None, exclude=True)
    cwd: str = "."
    name: str | None = None
    builtin_tools: Sequence[str] | None = Field(default_factory=list)
    custom_tools: Mapping[str, CustomTool] | None = Field(default=None, exclude=True)

    @property
    @override
    def _llm_type(self) -> str:
        """
        Required. Used to uniquely identify the type of the model. Used for logging
        """
        return "cursor-chat"

    @property
    @override
    def _identifying_params(self) -> Mapping[str, Any]:
        """
        Optional. Represent model parameterization for tracing purposes
        """
        return {
            "model_name": self.model_name,
            "cwd": self.cwd,
            "builtin_tools": list(self.builtin_tools) if self.builtin_tools is not None else None,
        }

    def _resolve_model_profile(self) -> ModelProfile | None:
        return {
            "name": self.model_name,
            "text_inputs": True,
            "text_outputs": True,
            "image_inputs": True,
            "tool_calling": bool(self.custom_tools),
            "structured_output": True,
            "temperature": False,
        }

    def _api_key_value(self) -> str:
        if self.api_key is not None:
            return self.api_key.get_secret_value()
        key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not key:
            raise ValueError("No Cursor API key. Set CURSOR_API_KEY or pass api_key=...")
        return key

    def _open_agent(self) -> Agent:
        return Agent.create(
            AgentOptions(
                model=self.model_name,
                api_key=self._api_key_value(),
                name=self.name,
                local=LocalAgentOptions(
                    cwd=self.cwd,
                    custom_tools=self.custom_tools,
                ),
                tools=self.builtin_tools,
            ),
            client=get_sdk_client(),
        )

    def _wait_run(self, prompt: str):
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with self._open_agent() as agent:
                    return agent.send(prompt).wait()
            except CursorAgentError as err:
                last_err = err
                if not err.is_retryable or attempt == 2:
                    raise RuntimeError(
                        f"Cursor agent failed to start: {err.message} "
                        f"(retryable={err.is_retryable}). "
                        "The local SDK bridge is not running. Restart the kernel, "
                        "re-run Setup + CursorChatModel, then the graph."
                    ) from err
                reset_sdk_client()
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError("Cursor agent failed to start") from last_err

    def _usage_metadata(self, result: Any) -> dict[str, Any]:
        usage = getattr(result, "usage", None)
        if usage is None:
            return {}
        return {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @override
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Required. Use to generate a chat result from a prompt
        """
        prompt = _messages_to_prompt(messages)
        result = self._wait_run(prompt)

        if result.status == "error":
            raise RuntimeError(f"Cursor run failed: {result.id}")

        text = _apply_stop(result.result or "", stop)
        message = AIMessage(
            content=text,
            response_metadata={
                "model_name": self.model_name,
                "run_id": result.id,
                "agent_id": result.agent_id,
                "status": str(result.status),
                "duration_ms": result.duration_ms,
                **self._usage_metadata(result),
            },
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)], # ChatResult expects ChatGeneration
            llm_output={"run_id": result.id, "agent_id": result.agent_id},
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """ 
        Optional. Use to implement streaming. Live token
        """
        prompt = _messages_to_prompt(messages)
        try:
            with self._open_agent() as agent:
                run = agent.send(prompt)
                for chunk_text in run.iter_text():
                    if not chunk_text:
                        continue
                    chunk = ChatGenerationChunk(message=AIMessageChunk(content=chunk_text))
                    if run_manager:
                        run_manager.on_llm_new_token(chunk_text, chunk=chunk)
                    yield chunk
                result = run.wait()
        except CursorAgentError as err:
            raise RuntimeError(
                f"Cursor agent failed to start: {err.message} (retryable={err.is_retryable})"
            ) from err

        if result.status == "error":
            raise RuntimeError(f"Cursor run failed: {result.id}")
    
    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        method: Literal["function_calling", "json_mode", "json_schema"] = "json_schema",
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        """Force JSON that matches `schema`, then parse it.

        Cursor is not used via native tool-calling here, so json_schema,
        json_mode, and function_calling all use prompt + parse.
        Pass a Pydantic class to get a validated instance back.
        """
        _ = kwargs.pop("strict", None)
        _ = kwargs.pop("tools", None)
        if kwargs:
            raise ValueError(f"Received unsupported arguments {kwargs}")
        if schema is None:
            raise ValueError("schema is required")

        is_pydantic = isinstance(schema, type) and is_basemodel_subclass(schema)
        if is_pydantic:
            output_parser: JsonOutputParser = PydanticOutputParser(pydantic_object=schema)
            schema_payload = schema.model_json_schema()
        elif isinstance(schema, dict):
            output_parser = JsonOutputParser()
            schema_payload = schema
        else:
            raise TypeError("schema must be a Pydantic model class or a JSON-schema dict")

        instruction = (
            "Reply with a single JSON object and nothing else. "
            "No markdown fences, no commentary."
        )
        if is_pydantic:
            instruction += "\n\n" + output_parser.get_format_instructions()
        else:
            instruction += "\n" + json.dumps(schema_payload, indent=2)

        schema_keys = (
            list(schema.model_fields)
            if is_pydantic
            else list((schema_payload.get("properties") or {}).keys())
        )

        def _inject(model_input: LanguageModelInput) -> list[BaseMessage]:
            if isinstance(model_input, PromptValue):
                messages = model_input.to_messages()
            elif isinstance(model_input, str):
                messages = [HumanMessage(content=model_input)]
            else:
                messages = list(model_input)
            return [*messages, HumanMessage(content=instruction)]

        def _parse(message: Any):
            text = _message_text(message) if isinstance(message, BaseMessage) else str(message)
            return output_parser.parse(_coerce_json_text(text, schema_keys))

        llm_with_schema = RunnableLambda(_inject) | self | RunnableLambda(_parse)

        if include_raw:
            parser_assign = RunnablePassthrough.assign(
                parsed=itemgetter("raw") | RunnableLambda(_parse),
                parsing_error=lambda _: None,
            )
            parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
            parser_with_fallback = parser_assign.with_fallbacks(
                [parser_none], exception_key="parsing_error"
            )
            return RunnableMap(raw=RunnableLambda(_inject) | self) | parser_with_fallback

        return llm_with_schema

@lru_cache(maxsize=1)
def get_llm():
    return CursorChatModel(model_name="composer-2.5")
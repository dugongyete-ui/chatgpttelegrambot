import asyncio
import base64
from io import BytesIO
import config
import logging
import re
import html as _html

import httpx
import tiktoken
from openai import AsyncOpenAI, BadRequestError, APIConnectionError, APITimeoutError

# httpx client with SSL verification disabled — required when the gateway
# is another Replit app (Replit's mTLS proxy causes cert errors from inside).
_http_client = httpx.AsyncClient(verify=False)

# setup openai client
openai_client = AsyncOpenAI(
    api_key=config.openai_api_key,
    base_url=config.openai_api_base,
    http_client=_http_client,
)

# optional OpenRouter client (OpenAI-compatible) for models declared with
# "provider: openrouter" in models.yml (e.g. Claude or other vendors)
openrouter_client = None
if config.openrouter_api_key:
    openrouter_client = AsyncOpenAI(
        api_key=config.openrouter_api_key,
        base_url=config.openrouter_api_base,
    )

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds between retries


def _md_to_html(text: str) -> str:
    """Convert markdown formatting to Telegram-safe HTML, strip bare symbols."""
    segments = []
    last = 0
    # Extract fenced code blocks and inline code first (preserve their content)
    CODE_RE = re.compile(r'(```(?:\w+)?\n?)([\s\S]*?)(```)|(`([^`\n]+)`)')
    for m in CODE_RE.finditer(text):
        segments.append(('text', text[last:m.start()]))
        if m.group(1):  # fenced block  ```...```
            inner = m.group(2).strip()
            segments.append(('pre', inner))
        else:           # inline `code`
            segments.append(('code', m.group(5)))
        last = m.end()
    segments.append(('text', text[last:]))

    out = []
    for kind, content in segments:
        if kind == 'pre':
            out.append(f'<pre>{_html.escape(content)}</pre>')
        elif kind == 'code':
            out.append(f'<code>{_html.escape(content)}</code>')
        else:
            p = content

            # Escape bare & that are NOT already part of an HTML entity
            p = re.sub(r'&(?!(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);)', '&amp;', p)

            # Strip markdown headers (# Title) — before anything else
            p = re.sub(r'^#{1,6}\s+', '', p, flags=re.MULTILINE)

            # Bold italic ***text*** or ___text___
            p = re.sub(r'\*{3}(.+?)\*{3}', r'<b><i>\1</i></b>', p, flags=re.DOTALL)
            p = re.sub(r'_{3}(.+?)_{3}', r'<b><i>\1</i></b>', p, flags=re.DOTALL)

            # Bold **text** or __text__
            p = re.sub(r'\*{2}(.+?)\*{2}', r'<b>\1</b>', p, flags=re.DOTALL)
            p = re.sub(r'_{2}(.+?)_{2}', r'<b>\1</b>', p, flags=re.DOTALL)

            # Italic *text* or _text_
            p = re.sub(r'\*([^\s*][^*]*?[^\s*])\*', r'<i>\1</i>', p, flags=re.DOTALL)
            p = re.sub(r'(?<![_\w])_([^_\n]+?)_(?![_\w])', r'<i>\1</i>', p)

            # Strikethrough ~~text~~
            p = re.sub(r'~~(.+?)~~', r'<s>\1</s>', p, flags=re.DOTALL)

            # Markdown bullet list  * item  or  - item  → bullet char
            p = re.sub(r'^\s*[-*]\s+', '• ', p, flags=re.MULTILINE)

            # Strip horizontal rules
            p = re.sub(r'^[-_*]{3,}\s*$', '', p, flags=re.MULTILINE)

            # Strip any remaining lone asterisks (formatting artifacts)
            p = re.sub(r'(?<!\w)\*+(?!\w)', '', p)

            # Curly / smart quotes → straight quotes for clean display
            p = p.replace('\u201c', '"').replace('\u201d', '"')
            p = p.replace('\u2018', "'").replace('\u2019', "'")

            out.append(p)

    return ''.join(out)


def _get_client_for_model(model):
    provider = config.models["info"].get(model, {}).get("provider", "openai")
    if provider == "openrouter":
        if openrouter_client is None:
            raise ValueError(
                "OpenRouter API key is not configured. "
                "Set OPENROUTER_API_KEY in your secrets."
            )
        return openrouter_client
    return openai_client


OPENAI_COMPLETION_OPTIONS = {
    "temperature": 0.7,
    "max_tokens": 1000,
    "timeout": 60.0,
}


class ChatGPT:
    def __init__(self, model="gpt-4o-mini"):
        assert model in config.models["info"], f"Unknown model: {model}"
        self.model = model
        self._client = _get_client_for_model(model)

    async def send_message(self, message, dialog_messages=[], chat_mode="assistant"):
        if chat_mode not in config.chat_modes.keys():
            raise ValueError(f"Chat mode {chat_mode} is not supported")

        n_dialog_messages_before = len(dialog_messages)
        answer = None
        attempt = 0
        while answer is None:
            try:
                if config.models["info"][self.model]["type"] == "chat_completion":
                    messages = self._generate_prompt_messages(message, dialog_messages, chat_mode)

                    r = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        **OPENAI_COMPLETION_OPTIONS
                    )
                    answer = r.choices[0].message.content
                else:
                    raise ValueError(f"Unknown model: {self.model}")

                answer = self._postprocess_answer(answer)
                n_input_tokens, n_output_tokens = r.usage.prompt_tokens, r.usage.completion_tokens

            except BadRequestError as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise ValueError("Dialog messages is reduced to zero, but still has too many tokens to make completion") from e
                dialog_messages = dialog_messages[1:]

            except (APIConnectionError, APITimeoutError) as e:
                attempt += 1
                if attempt >= MAX_RETRIES:
                    raise
                logger.warning(f"Connection error on attempt {attempt}/{MAX_RETRIES}, retrying in {RETRY_DELAY}s: {e}")
                await asyncio.sleep(RETRY_DELAY)

        n_first_dialog_messages_removed = n_dialog_messages_before - len(dialog_messages)

        return answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

    async def send_message_stream(self, message, dialog_messages=[], chat_mode="assistant"):
        if chat_mode not in config.chat_modes.keys():
            raise ValueError(f"Chat mode {chat_mode} is not supported")

        n_dialog_messages_before = len(dialog_messages)
        answer = None
        attempt = 0
        while answer is None:
            try:
                if config.models["info"][self.model]["type"] == "chat_completion":
                    messages = self._generate_prompt_messages(message, dialog_messages, chat_mode)

                    r_gen = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        **OPENAI_COMPLETION_OPTIONS
                    )

                    answer = ""
                    async for r_item in r_gen:
                        if len(r_item.choices) == 0:
                            continue
                        delta = r_item.choices[0].delta

                        if delta.content:
                            answer += delta.content
                            n_input_tokens, n_output_tokens = self._count_tokens_from_messages(messages, answer, model=self.model)
                            n_first_dialog_messages_removed = 0

                            yield "not_finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

                    answer = self._postprocess_answer(answer)

            except BadRequestError as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise e
                dialog_messages = dialog_messages[1:]

            except (APIConnectionError, APITimeoutError) as e:
                attempt += 1
                if attempt >= MAX_RETRIES:
                    raise
                logger.warning(f"Connection error on attempt {attempt}/{MAX_RETRIES}, retrying in {RETRY_DELAY}s: {e}")
                await asyncio.sleep(RETRY_DELAY)
                answer = None  # reset to retry

        yield "finished", answer, (n_input_tokens, n_output_tokens), n_first_dialog_messages_removed

    async def send_vision_message(
        self,
        message,
        dialog_messages=[],
        chat_mode="assistant",
        image_buffer: BytesIO = None,
    ):
        n_dialog_messages_before = len(dialog_messages)
        answer = None
        attempt = 0
        while answer is None:
            try:
                if config.models["info"][self.model].get("vision", False):
                    messages = self._generate_prompt_messages(
                        message, dialog_messages, chat_mode, image_buffer
                    )
                    r = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        **OPENAI_COMPLETION_OPTIONS
                    )
                    answer = r.choices[0].message.content
                else:
                    raise ValueError(f"Unsupported model: {self.model}")

                answer = self._postprocess_answer(answer)
                n_input_tokens, n_output_tokens = (
                    r.usage.prompt_tokens,
                    r.usage.completion_tokens,
                )
            except BadRequestError as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise ValueError(
                        "Dialog messages is reduced to zero, but still has too many tokens to make completion"
                    ) from e
                dialog_messages = dialog_messages[1:]

            except (APIConnectionError, APITimeoutError) as e:
                attempt += 1
                if attempt >= MAX_RETRIES:
                    raise
                logger.warning(f"Connection error on attempt {attempt}/{MAX_RETRIES}, retrying in {RETRY_DELAY}s: {e}")
                await asyncio.sleep(RETRY_DELAY)

        n_first_dialog_messages_removed = n_dialog_messages_before - len(dialog_messages)

        return (
            answer,
            (n_input_tokens, n_output_tokens),
            n_first_dialog_messages_removed,
        )

    async def send_vision_message_stream(
        self,
        message,
        dialog_messages=[],
        chat_mode="assistant",
        image_buffer: BytesIO = None,
    ):
        n_dialog_messages_before = len(dialog_messages)
        answer = None
        attempt = 0
        while answer is None:
            try:
                if config.models["info"][self.model].get("vision", False):
                    messages = self._generate_prompt_messages(
                        message, dialog_messages, chat_mode, image_buffer
                    )

                    r_gen = await self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        **OPENAI_COMPLETION_OPTIONS,
                    )

                    answer = ""
                    async for r_item in r_gen:
                        if len(r_item.choices) == 0:
                            continue
                        delta = r_item.choices[0].delta
                        if delta.content:
                            answer += delta.content
                            (
                                n_input_tokens,
                                n_output_tokens,
                            ) = self._count_tokens_from_messages(
                                messages, answer, model=self.model
                            )
                            n_first_dialog_messages_removed = (
                                n_dialog_messages_before - len(dialog_messages)
                            )
                            yield "not_finished", answer, (
                                n_input_tokens,
                                n_output_tokens,
                            ), n_first_dialog_messages_removed

                    answer = self._postprocess_answer(answer)

            except BadRequestError as e:  # too many tokens
                if len(dialog_messages) == 0:
                    raise e
                dialog_messages = dialog_messages[1:]

            except (APIConnectionError, APITimeoutError) as e:
                attempt += 1
                if attempt >= MAX_RETRIES:
                    raise
                logger.warning(f"Connection error on attempt {attempt}/{MAX_RETRIES}, retrying in {RETRY_DELAY}s: {e}")
                await asyncio.sleep(RETRY_DELAY)
                answer = None  # reset to retry

        yield "finished", answer, (
            n_input_tokens,
            n_output_tokens,
        ), n_first_dialog_messages_removed

    def _encode_image(self, image_buffer: BytesIO) -> bytes:
        return base64.b64encode(image_buffer.read()).decode("utf-8")

    def _generate_prompt_messages(self, message, dialog_messages, chat_mode, image_buffer: BytesIO = None):
        prompt = config.chat_modes[chat_mode]["prompt_start"]
        prompt += (
            "\n\nATURAN FORMAT: Jangan gunakan markdown (**, *, __, _, ##, ~~, dll). "
            "Untuk teks tebal gunakan tag HTML <b>teks</b>, miring <i>teks</i>, "
            "kode inline <code>kode</code>, blok kode <pre>kode</pre>. "
            "Selain itu tulis teks biasa tanpa simbol formatting apapun."
        )

        messages = [{"role": "system", "content": prompt}]

        for dialog_message in dialog_messages:
            messages.append({"role": "user", "content": dialog_message["user"]})
            messages.append({"role": "assistant", "content": dialog_message["bot"]})

        if image_buffer is not None:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": message,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{self._encode_image(image_buffer)}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            )
        else:
            messages.append({"role": "user", "content": message})

        return messages

    def _postprocess_answer(self, answer):
        answer = answer.strip()
        answer = _md_to_html(answer)
        return answer

    def _count_tokens_from_messages(self, messages, answer, model="gpt-3.5-turbo"):
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("o200k_base")

        tokens_per_message = 3
        tokens_per_name = 1

        # input
        n_input_tokens = 0
        for message in messages:
            n_input_tokens += tokens_per_message
            if isinstance(message["content"], list):
                for sub_message in message["content"]:
                    if "type" in sub_message:
                        if sub_message["type"] == "text":
                            n_input_tokens += len(encoding.encode(sub_message["text"]))
                        elif sub_message["type"] == "image_url":
                            pass
            else:
                if "type" in message:
                    if message["type"] == "text":
                        n_input_tokens += len(encoding.encode(message["text"]))
                    elif message["type"] == "image_url":
                        pass

        n_input_tokens += 2

        # output
        n_output_tokens = 1 + len(encoding.encode(answer))

        return n_input_tokens, n_output_tokens


async def transcribe_audio(audio_file) -> str:
    r = await openai_client.audio.transcriptions.create(model="whisper-1", file=audio_file)
    return r.text or ""



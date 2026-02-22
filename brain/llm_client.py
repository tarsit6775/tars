"""
╔══════════════════════════════════════════╗
║       TARS — LLM Client Abstraction      ║
╚══════════════════════════════════════════╝

Unified client for:
  - Anthropic (Claude) — native SDK
  - Gemini (Google) — google-genai SDK (new, pydantic-based)
  - OpenAI-compatible APIs (Groq, Together, etc)

Normalizes responses so planner.py and
browser_agent.py don't care which provider
is behind the scenes.
"""

import json
import logging
import random
import re
import time as _time
import uuid

logger = logging.getLogger("tars.llm_client")

# New Google GenAI SDK (google-genai)
try:
    from google import genai as _genai_module
    from google.genai import types as _genai_types
    _HAS_GEMINI = True
except ImportError:
    _genai_module = None
    _genai_types = None
    _HAS_GEMINI = False

# ─────────────────────────────────────────────
#  Protobuf → Python conversion
# ─────────────────────────────────────────────

def _proto_to_python(obj):
    """Recursively convert pydantic/protobuf objects to plain Python dicts/lists.
    
    Ensures fc.args values are json-serializable plain Python types.
    """
    if isinstance(obj, dict):
        return {k: _proto_to_python(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_proto_to_python(v) for v in obj]
    # Protobuf MapComposite behaves dict-like, RepeatedComposite list-like
    if hasattr(obj, 'items'):  # MapComposite
        return {k: _proto_to_python(v) for k, v in obj.items()}
    if hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
        return [_proto_to_python(v) for v in obj]
    return obj


# ─────────────────────────────────────────────
#  Normalized Response Objects
#  (Mimics Anthropic's format so existing code
#   works with zero changes)
# ─────────────────────────────────────────────

class ContentBlock:
    """A single content block (text or tool_use)."""
    def __init__(self, block_type, text=None, name=None, input_data=None, block_id=None):
        self.type = block_type
        self.text = text or ""
        self.name = name
        self.input = input_data or {}
        self.id = block_id


class Usage:
    """Token usage stats."""
    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class LLMResponse:
    """Normalized response — same shape as Anthropic's."""
    def __init__(self, content, stop_reason, usage):
        self.content = content          # List[ContentBlock]
        self.stop_reason = stop_reason  # "tool_use" | "end_turn"
        self.usage = usage              # Usage


# ─────────────────────────────────────────────
#  Tool Format Conversion
# ─────────────────────────────────────────────

def _anthropic_to_openai_tools(tools):
    """Convert Anthropic tool schemas to OpenAI function-calling format."""
    openai_tools = []
    for tool in tools:
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        # Ensure 'properties' key exists (OpenAI requires it)
        if "properties" not in schema:
            schema["properties"] = {}
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": schema,
            }
        })
    return openai_tools


def _openai_response_to_normalized(response):
    """Convert OpenAI chat completion response to our normalized format."""
    choice = response.choices[0]
    message = choice.message
    blocks = []

    # Text content
    if message.content:
        blocks.append(ContentBlock("text", text=message.content))

    # Tool calls
    has_tool_calls = False
    if message.tool_calls:
        has_tool_calls = True
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except json.JSONDecodeError:
                args = {}
            blocks.append(ContentBlock(
                "tool_use",
                name=tc.function.name,
                input_data=args,
                block_id=tc.id,
            ))

    stop_reason = "tool_use" if has_tool_calls else "end_turn"

    usage = Usage(
        input_tokens=getattr(response.usage, "prompt_tokens", 0),
        output_tokens=getattr(response.usage, "completion_tokens", 0),
    )

    return LLMResponse(content=blocks, stop_reason=stop_reason, usage=usage)


# ─────────────────────────────────────────────
#  Malformed Tool Call Recovery
#  (Groq/Llama sometimes generates XML-style
#   tool calls that fail validation. We parse
#   them here and recover.)
# ─────────────────────────────────────────────

def _parse_failed_tool_call(error):
    """
    Parse a Groq tool_use_failed error and extract the tool call.

    Groq's Llama models sometimes generate tool calls in XML format:
        <function=goto{"url": "https://example.com"}</function>
    or multi-param:
        <function=type{"selector": "#email", "text": "hello"}</function>

    We extract the function name and arguments, then build a proper
    LLMResponse as if the API had returned it correctly.

    Returns LLMResponse if parsed successfully, None otherwise.
    """
    error_str = str(error)

    # Try to get failed_generation directly from the error body (OpenAI SDK)
    failed_gen = None
    if hasattr(error, 'body') and isinstance(error.body, dict):
        failed_gen = error.body.get('failed_generation')
        if not failed_gen:
            # Sometimes nested under 'error'
            failed_gen = error.body.get('error', {}).get('failed_generation') if isinstance(error.body.get('error'), dict) else None

    # Fallback: regex extraction from error string
    if not failed_gen:
        fg_match = re.search(r"'failed_generation':\s*'(.+?)'\s*\}", error_str, re.DOTALL)
        if not fg_match:
            fg_match = re.search(r'"failed_generation":\s*"(.+?)"\s*\}', error_str, re.DOTALL)
        if fg_match:
            failed_gen = fg_match.group(1)
            failed_gen = failed_gen.replace('\\"', '"').replace("\\'", "'")

    # Pattern 2: Look for the XML pattern directly in the error string
    if not failed_gen:
        xml_match = re.search(r'<function=\w+.*?</function>', error_str)
        if xml_match:
            failed_gen = xml_match.group(0)

    # Pattern 3: "attempted to call tool 'tool_name={"args"}'" pattern  
    if not failed_gen:
        tool_match = re.search(r"attempted to call tool\s*'(\w+=\{.+)", error_str, re.DOTALL)
        if tool_match:
            raw = tool_match.group(1)
            # Clean up: remove trailing quote/bracket artifacts
            raw = raw.rstrip("'\"")
            failed_gen = raw

    if not failed_gen:
        return None

    # Now parse the XML-style function call(s)
    # Groq/Llama generates various formats:
    #   <function=goto{"url": "https://..."}</function>
    #   <function=goto>{"url": "https://..."}</function>  
    #   <function=look></function>
    #   <function=type{"selector": "#x", "text": "y"}</function>
    #   deploy_browser_agent={"task": "..."}  (no XML at all)

    # Unified pattern: function name, then optional JSON
    # Handle both <function=name>{"args"}</function> and <function=name{"args"}</function>
    calls = re.findall(
        r'<function=(\w+)>?\s*(.*?)\s*<?/function>',
        failed_gen,
        re.DOTALL,
    )

    # Fallback: no XML tags, just tool_name={"args"} or tool_name={...}
    if not calls:
        bare_match = re.match(r'(\w+)\s*=\s*(\{.+\})\s*$', failed_gen.strip(), re.DOTALL)
        if bare_match:
            calls = [(bare_match.group(1), bare_match.group(2))]

    # Fallback 2: look for tool_name({"args"}) pattern
    if not calls:
        paren_match = re.match(r'(\w+)\s*\(\s*(\{.+\})\s*\)\s*$', failed_gen.strip(), re.DOTALL)
        if paren_match:
            calls = [(paren_match.group(1), paren_match.group(2))]

    if not calls:
        return None

    blocks = []

    # Extract any text before the first <function tag
    text_before = re.split(r'<function=', failed_gen)[0].strip()
    if text_before:
        blocks.append(ContentBlock("text", text=text_before))

    for func_name, args_str in calls:
        # Parse the arguments JSON
        args = {}
        args_raw = args_str.strip()
        # Remove trailing > that sometimes gets captured
        if args_raw.endswith('>'):
            args_raw = args_raw[:-1].strip()
        if args_raw and args_raw.startswith('{'):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                # Try fixing common issues
                try:
                    # Remove trailing commas before }
                    cleaned = re.sub(r',\s*}', '}', args_raw)
                    # Fix escaped quotes
                    cleaned = cleaned.replace('\\"', '"')
                    # Fix Llama's escaped single quotes
                    cleaned = cleaned.replace("\\'", "'")
                    args = json.loads(cleaned)
                except json.JSONDecodeError:
                    logger.warning(f"[Parser] Could not parse args: {args_raw[:200]}")
                    pass

        call_id = f"call_{uuid.uuid4().hex[:24]}"
        blocks.append(ContentBlock(
            "tool_use",
            name=func_name,
            input_data=args,
            block_id=call_id,
        ))

    if not any(b.type == "tool_use" for b in blocks):
        return None

    logger.info(f"Recovered {len(calls)} malformed tool call(s): {[c[0] for c in calls]}")

    return LLMResponse(
        content=blocks,
        stop_reason="tool_use",
        usage=Usage(input_tokens=0, output_tokens=0),
    )


# ─────────────────────────────────────────────
#  Conversation Format Conversion
# ─────────────────────────────────────────────

def _convert_history_for_openai(messages, system_prompt):
    """
    Convert Anthropic-style conversation history to OpenAI format.

    Anthropic style:
      - system is a separate param
      - assistant content = list of ContentBlock objects
      - tool results = [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]

    OpenAI style:
      - system is a message with role "system"
      - assistant content = text + tool_calls
      - tool results = separate messages with role "tool"
    """
    openai_messages = [{"role": "system", "content": system_prompt}]

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            # Could be a string or a list of tool results
            if isinstance(content, str):
                openai_messages.append({"role": "user", "content": content})
            elif isinstance(content, list):
                # Tool results — convert to OpenAI tool messages
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": str(item.get("content", "")),
                        })
            else:
                openai_messages.append({"role": "user", "content": str(content)})

        elif role == "assistant":
            # Could be a string, list of ContentBlock objects, or list of dicts
            if isinstance(content, str):
                openai_messages.append({"role": "assistant", "content": content})
            elif isinstance(content, list):
                # Extract text and tool calls from content blocks
                text_parts = []
                tool_calls = []
                for block in content:
                    # Handle ContentBlock objects
                    if hasattr(block, "type"):
                        if block.type == "text" and block.text:
                            text_parts.append(block.text)
                        elif block.type == "tool_use":
                            tool_calls.append({
                                "id": block.id,
                                "type": "function",
                                "function": {
                                    "name": block.name,
                                    "arguments": json.dumps(block.input if isinstance(block.input, dict) else {}),
                                }
                            })
                    # Handle raw dicts (shouldn't happen but be safe)
                    elif isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": json.dumps(block.get("input", {})),
                                }
                            })

                assistant_msg = {"role": "assistant"}
                assistant_msg["content"] = "\n".join(text_parts) if text_parts else None
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                openai_messages.append(assistant_msg)

    return openai_messages


# ─────────────────────────────────────────────
#  Gemini-Native Format Conversion
# ─────────────────────────────────────────────

def _schema_dict_to_genai(schema_dict):
    """
    Recursively convert a JSON Schema dict into a google.genai types.Schema.

    Handles type, description, properties, required, items, and enum.
    """
    type_map = {
        "string": _genai_types.Type.STRING,
        "number": _genai_types.Type.NUMBER,
        "integer": _genai_types.Type.INTEGER,
        "boolean": _genai_types.Type.BOOLEAN,
        "array": _genai_types.Type.ARRAY,
        "object": _genai_types.Type.OBJECT,
    }

    kwargs = {}
    json_type = schema_dict.get("type", "string")
    kwargs["type"] = type_map.get(json_type, _genai_types.Type.STRING)

    if "description" in schema_dict:
        kwargs["description"] = schema_dict["description"]

    if "enum" in schema_dict:
        kwargs["enum"] = schema_dict["enum"]

    if "properties" in schema_dict:
        kwargs["properties"] = {
            k: _schema_dict_to_genai(v)
            for k, v in schema_dict["properties"].items()
        }

    if "required" in schema_dict:
        kwargs["required"] = schema_dict["required"]

    if "items" in schema_dict:
        kwargs["items"] = _schema_dict_to_genai(schema_dict["items"])

    return _genai_types.Schema(**kwargs)


def _anthropic_to_gemini_tools(tools):
    """
    Convert Anthropic tool schemas → list of google.genai types.Tool.

    Returns a single Tool containing all FunctionDeclarations.
    """
    if not tools:
        return None

    declarations = []
    for tool in tools:
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        if "properties" not in schema:
            schema["properties"] = {}

        params_schema = _schema_dict_to_genai(schema)

        declarations.append(_genai_types.FunctionDeclaration(
            name=tool["name"],
            description=tool.get("description", ""),
            parameters=params_schema,
        ))

    return [_genai_types.Tool(function_declarations=declarations)]


def _convert_history_for_gemini(messages, system_prompt):
    """
    Convert Anthropic-style conversation history → Gemini Content list.

    Anthropic uses:
      - role "user" with string content or list of tool_result dicts
      - role "assistant" with list of ContentBlock objects (text, tool_use)

    Gemini uses:
      - role "user" with Parts (text)
      - role "model" with Parts (text, function_call)
      - role "user" with Parts (function_response) for tool results

    Note: system_prompt is passed separately via GenerateContentConfig, not in history.
    """
    gemini_contents = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, str):
                gemini_contents.append(_genai_types.Content(
                    role="user",
                    parts=[_genai_types.Part(text=content)],
                ))
            elif isinstance(content, list):
                # Tool results → function_response parts (may include images)
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        result_content = item.get("content", "")
                        # Gemini expects function_response content as a dict
                        if isinstance(result_content, str):
                            response_dict = {"result": result_content}
                        elif isinstance(result_content, dict):
                            response_dict = result_content
                        else:
                            response_dict = {"result": str(result_content)}

                        parts.append(_genai_types.Part(
                            function_response=_genai_types.FunctionResponse(
                                name=item.get("tool_name", "unknown"),
                                response=response_dict,
                            )
                        ))
                        
                        # Vision support: if tool result has image data, add as inline image
                        # This lets Gemini actually SEE screenshots from the browser agent
                        img_b64 = item.get("_image_base64")
                        if img_b64:
                            try:
                                import base64 as _b64
                                img_bytes = _b64.b64decode(img_b64)
                                img_mime = item.get("_image_mime", "image/jpeg")
                                parts.append(_genai_types.Part.from_bytes(
                                    data=img_bytes,
                                    mime_type=img_mime,
                                ))
                                parts.append(_genai_types.Part(
                                    text="[Above is a screenshot of the current browser page. Use it to see the actual visual layout, buttons, fields, errors, CAPTCHAs, and anything the text description might miss.]"
                                ))
                            except Exception:
                                pass  # If image decoding fails, text-only fallback
                if parts:
                    gemini_contents.append(_genai_types.Content(
                        role="user",
                        parts=parts,
                    ))

        elif role == "assistant":
            parts = []
            if isinstance(content, str):
                parts.append(_genai_types.Part(text=content))
            elif isinstance(content, list):
                for block in content:
                    # ContentBlock objects
                    if hasattr(block, "type"):
                        if block.type == "text" and block.text:
                            parts.append(_genai_types.Part(text=block.text))
                        elif block.type == "tool_use":
                            args = block.input if isinstance(block.input, dict) else {}
                            parts.append(_genai_types.Part(
                                function_call=_genai_types.FunctionCall(
                                    name=block.name,
                                    args=args,
                                )
                            ))
                    # Raw dicts
                    elif isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(_genai_types.Part(text=block.get("text", "")))
                        elif block.get("type") == "tool_use":
                            parts.append(_genai_types.Part(
                                function_call=_genai_types.FunctionCall(
                                    name=block.get("name", ""),
                                    args=block.get("input", {}),
                                )
                            ))
            if parts:
                gemini_contents.append(_genai_types.Content(
                    role="model",
                    parts=parts,
                ))

    return gemini_contents


def _gemini_response_to_normalized(response):
    """Convert a google.genai response to our normalized LLMResponse."""
    blocks = []
    has_tool_calls = False

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call and part.function_call.name:
                    has_tool_calls = True
                    fc = part.function_call
                    args = _proto_to_python(dict(fc.args)) if fc.args else {}
                    call_id = fc.id or f"call_{uuid.uuid4().hex[:24]}"
                    blocks.append(ContentBlock(
                        "tool_use",
                        name=fc.name,
                        input_data=args,
                        block_id=call_id,
                    ))
                elif part.text:
                    blocks.append(ContentBlock("text", text=part.text))

    stop_reason = "tool_use" if has_tool_calls else "end_turn"

    usage = Usage()
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = Usage(
            input_tokens=getattr(response.usage_metadata, "prompt_token_count", 0) or 0,
            output_tokens=getattr(response.usage_metadata, "candidates_token_count", 0) or 0,
        )

    return LLMResponse(content=blocks, stop_reason=stop_reason, usage=usage)


# ─────────────────────────────────────────────
#  Streaming Wrapper
# ─────────────────────────────────────────────

class OpenAIStreamWrapper:
    """
    Wraps OpenAI streaming to match the interface planner.py expects.
    Collects the full response while yielding stream events.
    """
    def __init__(self, client, provider=None, **kwargs):
        self._client = client
        self._provider = provider
        self._kwargs = kwargs
        self._final_response = None

    def __enter__(self):
        create_kwargs = dict(stream=True, **self._kwargs)
        # Gemini's OpenAI compat endpoint doesn't support stream_options
        if self._provider != "gemini":
            create_kwargs["stream_options"] = {"include_usage": True}
        self._stream = self._client.chat.completions.create(**create_kwargs)
        self._collected_text = ""
        self._collected_tool_calls = {}  # index -> {id, name, arguments}
        self._usage = Usage()
        self._events = []
        return self

    def __exit__(self, *args):
        pass

    def __iter__(self):
        for chunk in self._stream:
            if not chunk.choices:
                # Usage chunk at the end
                if hasattr(chunk, "usage") and chunk.usage:
                    self._usage = Usage(
                        input_tokens=getattr(chunk.usage, "prompt_tokens", 0),
                        output_tokens=getattr(chunk.usage, "completion_tokens", 0),
                    )
                continue

            delta = chunk.choices[0].delta

            # Text delta
            if delta.content:
                self._collected_text += delta.content
                # Yield an event-like object for streaming
                event = _StreamEvent(delta.content)
                yield event

            # Tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in self._collected_tool_calls:
                        self._collected_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        self._collected_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            self._collected_tool_calls[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            self._collected_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            # Check for usage in the chunk
            if hasattr(chunk, "usage") and chunk.usage:
                self._usage = Usage(
                    input_tokens=getattr(chunk.usage, "prompt_tokens", 0),
                    output_tokens=getattr(chunk.usage, "completion_tokens", 0),
                )

    def get_final_message(self):
        """Build the normalized response from collected stream data."""
        blocks = []

        if self._collected_text:
            blocks.append(ContentBlock("text", text=self._collected_text))

        has_tools = False
        for idx in sorted(self._collected_tool_calls.keys(), key=lambda x: x if x is not None else -1):
            tc = self._collected_tool_calls[idx]
            has_tools = True
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            if not args and tc["arguments"]:
                logger.warning(f"Tool call '{tc['name']}' had arguments '{tc['arguments']}' but parsed to empty dict")
            elif not args:
                logger.warning(f"Tool call '{tc['name']}' received empty arguments from LLM")
            blocks.append(ContentBlock(
                "tool_use",
                name=tc["name"],
                input_data=args,
                block_id=tc["id"],
            ))

        stop_reason = "tool_use" if has_tools else "end_turn"
        return LLMResponse(content=blocks, stop_reason=stop_reason, usage=self._usage)


class _StreamEvent:
    """Mimics Anthropic's content_block_delta event."""
    def __init__(self, text):
        self.type = "content_block_delta"
        self.delta = _Delta(text)

class _Delta:
    def __init__(self, text):
        self.text = text


# ─────────────────────────────────────────────
#  Gemini Native Stream Wrapper
# ─────────────────────────────────────────────

class GeminiStreamWrapper:
    """
    Wraps Gemini's google.genai streaming to match the interface planner.py expects.
    
    Uses client.models.generate_content_stream() for proper streaming
    with separate function_call parts for each tool call.
    """
    def __init__(self, client, model, contents, config=None):
        self._client = client
        self._model = model
        self._contents = contents
        self._config = config
        self._collected_text = ""
        self._collected_tool_calls = []
        self._usage = Usage()

    def __enter__(self):
        self._stream = self._client.models.generate_content_stream(
            model=self._model,
            contents=self._contents,
            config=self._config,
        )
        return self

    def __exit__(self, *args):
        pass

    def __iter__(self):
        for chunk in self._stream:
            # Extract usage from streaming chunks
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                self._usage = Usage(
                    input_tokens=getattr(chunk.usage_metadata, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(chunk.usage_metadata, "candidates_token_count", 0) or 0,
                )

            if not chunk.candidates:
                continue

            candidate = chunk.candidates[0]
            if not candidate.content or not candidate.content.parts:
                continue

            for part in candidate.content.parts:
                if part.function_call and part.function_call.name:
                    fc = part.function_call
                    args = _proto_to_python(dict(fc.args)) if fc.args else {}
                    call_id = fc.id or f"call_{uuid.uuid4().hex[:24]}"
                    self._collected_tool_calls.append({
                        "name": fc.name,
                        "args": args,
                        "id": call_id,
                    })
                elif part.text:
                    self._collected_text += part.text
                    yield _StreamEvent(part.text)

    def get_final_message(self):
        """Build the normalized response from collected stream data."""
        blocks = []

        if self._collected_text:
            blocks.append(ContentBlock("text", text=self._collected_text))

        has_tools = bool(self._collected_tool_calls)
        for tc in self._collected_tool_calls:
            blocks.append(ContentBlock(
                "tool_use",
                name=tc["name"],
                input_data=tc["args"],
                block_id=tc["id"],
            ))

        stop_reason = "tool_use" if has_tools else "end_turn"
        return LLMResponse(content=blocks, stop_reason=stop_reason, usage=self._usage)


class GeminiRetryStreamWrapper:
    """
    Wraps GeminiStreamWrapper with automatic retry on transient errors.
    Same interface as RetryStreamWrapper but for google.genai SDK.
    """
    def __init__(self, client, model, contents, backoff_fn, max_retries=5, config=None):
        self._client = client
        self._model = model
        self._contents = contents
        self._backoff_fn = backoff_fn
        self._max_retries = max_retries
        self._config = config
        self._inner = None

    def __enter__(self):
        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._inner = GeminiStreamWrapper(
                    self._client, self._model, self._contents,
                    config=self._config,
                )
                self._inner.__enter__()
                self._inner._retry_attempt = attempt
                return self
            except Exception as e:
                last_error = e
                if self._is_retryable(e) and attempt < self._max_retries:
                    delay = self._get_delay(e, attempt)
                    logger.warning(f"Gemini stream error ({type(e).__name__}) — retry {attempt}/{self._max_retries} in {delay:.1f}s")
                    _time.sleep(delay)
                    continue
                raise
        raise last_error

    def __exit__(self, *args):
        if self._inner:
            self._inner.__exit__(*args)

    def __iter__(self):
        try:
            yield from self._inner
        except Exception as e:
            if self._is_retryable(e):
                attempt = getattr(self._inner, '_retry_attempt', 1)
                if attempt < self._max_retries:
                    delay = self._get_delay(e, attempt)
                    logger.warning(f"Gemini mid-stream error ({type(e).__name__}) — retry {attempt}/{self._max_retries} in {delay:.1f}s")
                    _time.sleep(delay)
                    self._inner = GeminiStreamWrapper(
                        self._client, self._model, self._contents,
                        config=self._config,
                    )
                    self._inner.__enter__()
                    self._inner._retry_attempt = attempt + 1
                    yield from self._inner
                    return
            raise

    def get_final_message(self):
        return self._inner.get_final_message()

    def _is_retryable(self, error):
        error_str = str(error).lower()
        return any(marker in error_str for marker in (
            "rate_limit", "rate limit", "429",
            "500", "502", "503", "529",
            "overloaded", "capacity", "resource_exhausted",
            "connection", "timeout", "timed out",
            "service unavailable", "internal server error",
        ))

    def _get_delay(self, error, attempt):
        error_str = str(error).lower()
        if any(m in error_str for m in ("rate_limit", "rate limit", "429", "resource_exhausted")):
            return self._backoff_fn(attempt, base=2.0, cap=90.0)
        return self._backoff_fn(attempt, base=1.0, cap=30.0)


# ─────────────────────────────────────────────
#  Retry-Aware Stream Wrapper (OpenAI-compat)
#  (Retries the ENTIRE streaming request on
#   rate limits, 5xx, connection errors)
# ─────────────────────────────────────────────

class RetryStreamWrapper:
    """
    Wraps OpenAIStreamWrapper with automatic retry on transient errors.
    
    On rate limit (429), server error (5xx), or connection error:
      - Waits with exponential backoff + jitter
      - Retries the full streaming request
      - Up to max_retries attempts
    
    From the caller's perspective, this is transparent — same
    context-manager + iterator interface as OpenAIStreamWrapper.
    """
    def __init__(self, client, backoff_fn, max_retries=5, provider=None, **kwargs):
        self._client = client
        self._kwargs = kwargs
        self._backoff_fn = backoff_fn
        self._max_retries = max_retries
        self._provider = provider
        self._inner = None

    def __enter__(self):
        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                self._inner = OpenAIStreamWrapper(self._client, provider=self._provider, **self._kwargs)
                self._inner.__enter__()
                # Wrap iteration to catch mid-stream errors
                self._inner._retry_attempt = attempt
                return self
            except Exception as e:
                last_error = e
                if self._is_retryable(e) and attempt < self._max_retries:
                    delay = self._get_delay(e, attempt)
                    logger.warning(f"Stream error ({type(e).__name__}) — retry {attempt}/{self._max_retries} in {delay:.1f}s")
                    _time.sleep(delay)
                    continue
                raise
        raise last_error

    def __exit__(self, *args):
        if self._inner:
            self._inner.__exit__(*args)

    def __iter__(self):
        """Iterate over stream events, retrying on mid-stream failures."""
        try:
            yield from self._inner
        except Exception as e:
            if self._is_retryable(e):
                attempt = getattr(self._inner, '_retry_attempt', 1)
                if attempt < self._max_retries:
                    delay = self._get_delay(e, attempt)
                    logger.warning(f"Mid-stream error ({type(e).__name__}) — retry {attempt}/{self._max_retries} in {delay:.1f}s")
                    _time.sleep(delay)
                    # Restart the stream from scratch
                    self._inner = OpenAIStreamWrapper(self._client, provider=self._provider, **self._kwargs)
                    self._inner.__enter__()
                    self._inner._retry_attempt = attempt + 1
                    yield from self._inner
                    return
            raise

    def get_final_message(self):
        return self._inner.get_final_message()

    def _is_retryable(self, error):
        """Check if an error is transient and worth retrying."""
        error_str = str(error).lower()
        return any(marker in error_str for marker in (
            "rate_limit", "rate limit", "429",
            "500", "502", "503", "529",
            "overloaded", "capacity", "resource_exhausted",
            "connection", "timeout", "timed out",
            "service unavailable", "internal server error",
        ))

    def _get_delay(self, error, attempt):
        """Get appropriate delay based on error type."""
        error_str = str(error).lower()
        # Rate limits need longer waits
        if any(m in error_str for m in ("rate_limit", "rate limit", "429", "resource_exhausted")):
            return self._backoff_fn(attempt, base=2.0, cap=90.0)
        # Server errors — shorter waits
        return self._backoff_fn(attempt, base=1.0, cap=30.0)


# ─────────────────────────────────────────────
#  Anthropic Stream Wrapper
#  (Normalizes Anthropic streaming responses
#   to use our ContentBlock/LLMResponse types)
# ─────────────────────────────────────────────

class AnthropicStreamWrapper:
    """Wraps Anthropic's MessageStream so get_final_message() returns our normalized LLMResponse."""

    def __init__(self, client, wrap_fn, **kwargs):
        self._client = client
        self._wrap_fn = wrap_fn
        self._kwargs = kwargs
        self._stream = None

    def __enter__(self):
        self._stream = self._client.messages.stream(**self._kwargs)
        self._inner = self._stream.__enter__()
        return self

    def __exit__(self, *args):
        if self._stream:
            self._stream.__exit__(*args)

    def __iter__(self):
        yield from self._inner

    def get_final_message(self):
        raw = self._inner.get_final_message()
        return self._wrap_fn(raw)


# ─────────────────────────────────────────────
#  Main LLM Client
# ─────────────────────────────────────────────

class LLMClient:
    """
    Unified LLM client. Supports:
      - provider: "anthropic" → uses anthropic SDK
      - provider: "gemini" → uses google-genai SDK (Client-based)
      - provider: "groq" / "together" / "openai" / "openrouter"
          → uses openai SDK with custom base_url

    Usage is identical to before — just swap the client.
    """

    PROVIDER_URLS = {
        "groq": "https://api.groq.com/openai/v1",
        "together": "https://api.together.xyz/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
    }

    def __init__(self, provider, api_key, **kwargs):
        self.provider = provider
        self.api_key = api_key

        if provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=api_key)
            self._mode = "anthropic"
        elif provider == "gemini":
            if not _HAS_GEMINI:
                raise ImportError(
                    "google-genai is required for Gemini provider. "
                    "Install it: pip install google-genai"
                )
            self._client = _genai_module.Client(api_key=api_key)
            self._mode = "gemini"
        else:
            from openai import OpenAI
            base_url = kwargs.get("base_url") or self.PROVIDER_URLS.get(provider)
            if not base_url:
                raise ValueError(f"Unknown provider '{provider}'. Use: anthropic, gemini, groq, together, openrouter, openai — or pass base_url=")
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            self._mode = "openai"

    # ── Non-streaming call (used by agents) ──

    @staticmethod
    def _backoff_delay(attempt, base=0.5, cap=30.0):
        """Exponential backoff with full jitter: delay = random(0, min(cap, base * 2^attempt))."""
        exp = min(cap, base * (2 ** attempt))
        return random.uniform(0, exp)

    def create(self, model, max_tokens, system, tools, messages, temperature=0, tool_choice=None):
        """Create a completion (non-streaming). Returns normalized LLMResponse.
        
        Includes recovery logic for Groq/Llama tool_use_failed errors —
        the model sometimes generates malformed XML tool calls which the
        API rejects. We parse the failed generation and recover the tool call.
        
        Retry strategy: exponential backoff with full jitter.
          attempt 1: random(0, 1.0s)
          attempt 2: random(0, 2.0s)
          attempt 3: random(0, 4.0s)  … capped at 30s
        
        temperature=0 by default for deterministic tool calls.
        tool_choice: "auto" (default), "required" (force tool use), or None.
        """
        if self._mode == "anthropic":
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
                temperature=temperature,
            )
            return self._wrap_anthropic_response(resp)
        elif self._mode == "gemini":
            # ── Google GenAI SDK path ──
            gemini_tools = _anthropic_to_gemini_tools(tools)
            gemini_contents = _convert_history_for_gemini(messages, system)

            config = _genai_types.GenerateContentConfig(
                system_instruction=system,
                tools=gemini_tools,
                temperature=temperature,
                automatic_function_calling=_genai_types.AutomaticFunctionCallingConfig(disable=True),
            )
            if max_tokens:
                config.max_output_tokens = max_tokens

            max_retries = 5
            for attempt in range(1, max_retries + 1):
                try:
                    resp = self._client.models.generate_content(
                        model=model,
                        contents=gemini_contents,
                        config=config,
                    )
                    return _gemini_response_to_normalized(resp)
                except Exception as e:
                    error_str = str(e).lower()

                    # Rate limit / resource exhausted
                    if any(m in error_str for m in ("rate_limit", "rate limit", "429", "resource_exhausted")) and attempt < max_retries:
                        delay = self._backoff_delay(attempt, base=2.0, cap=60.0)
                        logger.warning(f"Gemini rate limited — retry {attempt}/{max_retries} in {delay:.1f}s")
                        _time.sleep(delay)
                        continue

                    # Server errors
                    if any(code in error_str for code in ("500", "502", "503", "529")) and attempt < max_retries:
                        delay = self._backoff_delay(attempt, base=1.0, cap=30.0)
                        logger.warning(f"Gemini server error — retry {attempt}/{max_retries} in {delay:.1f}s")
                        _time.sleep(delay)
                        continue

                    raise
        else:
            openai_tools = _anthropic_to_openai_tools(tools)
            openai_messages = _convert_history_for_openai(messages, system)

            max_retries = 5
            for attempt in range(1, max_retries + 1):
                try:
                    kwargs = {
                        "model": model,
                        "max_tokens": max_tokens,
                        "messages": openai_messages,
                        "temperature": temperature,
                    }
                    if openai_tools:
                        kwargs["tools"] = openai_tools
                        kwargs["tool_choice"] = tool_choice or "auto"
                    resp = self._client.chat.completions.create(**kwargs)
                    return _openai_response_to_normalized(resp)
                except Exception as e:
                    error_str = str(e)

                    # Groq/Llama tool_use_failed — try to recover the tool call
                    if "tool_use_failed" in error_str:
                        recovered = _parse_failed_tool_call(e)
                        if recovered:
                            return recovered
                        # If recovery failed, retry with backoff
                        if attempt < max_retries:
                            delay = self._backoff_delay(attempt)
                            logger.warning(f"tool_use_failed — retry {attempt}/{max_retries} in {delay:.1f}s")
                            _time.sleep(delay)
                            continue

                    # Rate limit — retry with longer backoff
                    if "rate_limit" in error_str.lower() and attempt < max_retries:
                        delay = self._backoff_delay(attempt, base=1.0, cap=60.0)
                        logger.warning(f"Rate limited — retry {attempt}/{max_retries} in {delay:.1f}s")
                        _time.sleep(delay)
                        continue

                    # Server errors (5xx) — transient, retry
                    if any(code in error_str for code in ("500", "502", "503", "529")) and attempt < max_retries:
                        delay = self._backoff_delay(attempt, base=1.0, cap=30.0)
                        logger.warning(f"Server error — retry {attempt}/{max_retries} in {delay:.1f}s")
                        _time.sleep(delay)
                        continue

                    raise

    # ── Streaming call (used by planner) ──

    def stream(self, model, max_tokens, system, tools, messages, temperature=None):
        """Stream a completion. Returns context manager with Anthropic-like interface.
        
        temperature=None lets the provider use its default for brain streaming
        (slightly creative for conversation, but structured for tool calls).
        
        Wraps in RetryStreamWrapper so rate limits, 5xx, and transient errors
        are automatically retried with exponential backoff (up to 5 attempts).
        """
        if self._mode == "anthropic":
            kwargs = dict(
                model=model,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )
            if temperature is not None:
                kwargs["temperature"] = temperature
            return AnthropicStreamWrapper(self._client, self._wrap_anthropic_response, **kwargs)
        elif self._mode == "gemini":
            # ── Google GenAI SDK streaming ──
            gemini_tools = _anthropic_to_gemini_tools(tools)
            gemini_contents = _convert_history_for_gemini(messages, system)

            config = _genai_types.GenerateContentConfig(
                system_instruction=system,
                tools=gemini_tools,
                automatic_function_calling=_genai_types.AutomaticFunctionCallingConfig(disable=True),
            )
            if max_tokens:
                config.max_output_tokens = max_tokens
            if temperature is not None:
                config.temperature = temperature

            return GeminiRetryStreamWrapper(
                self._client,
                model,
                gemini_contents,
                self._backoff_delay,
                config=config,
            )
        else:
            openai_tools = _anthropic_to_openai_tools(tools)
            openai_messages = _convert_history_for_openai(messages, system)
            kwargs = dict(
                model=model,
                max_tokens=max_tokens,
                tools=openai_tools if openai_tools else None,
                messages=openai_messages,
            )
            if temperature is not None:
                kwargs["temperature"] = temperature
            return RetryStreamWrapper(self._client, self._backoff_delay, provider=self.provider, **kwargs)

    # ── Helper ──

    def _wrap_anthropic_response(self, resp):
        """Normalize native Anthropic response into our LLMResponse format.
        
        Anthropic SDK returns objects with .content (list of ContentBlock),
        .stop_reason, and .usage. We wrap them into our normalized classes
        so all providers return the exact same type, preventing isinstance()
        mismatches downstream.
        """
        blocks = []
        for block in resp.content:
            if block.type == "text":
                blocks.append(ContentBlock("text", text=block.text))
            elif block.type == "tool_use":
                blocks.append(ContentBlock(
                    "tool_use",
                    name=block.name,
                    input_data=block.input,
                    block_id=block.id,
                ))

        stop_reason = "tool_use" if resp.stop_reason == "tool_use" else "end_turn"
        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
        )
        return LLMResponse(content=blocks, stop_reason=stop_reason, usage=usage)

from __future__ import annotations

import asyncio
import inspect
import json
import re
import sys
import traceback
from contextlib import asynccontextmanager
from typing import Any


class Context:
    def __init__(self, lifespan_context: dict[str, Any]):
        self.lifespan_context = lifespan_context


class NativeMCP:
    def __init__(self, name: str, lifespan=None):
        self.name = name
        self._lifespan = lifespan
        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: list[dict[str, Any]] = []
        self._prompts: dict[str, dict[str, Any]] = {}
        self._stdout_lock = asyncio.Lock()
        self._shutdown_requested = False
        self._use_content_length = False

    def tool(self, func=None, **kwargs):
        def decorator(f):
            self._tools[f.__name__] = {
                "name": f.__name__,
                "description": inspect.getdoc(f) or "",
                "inputSchema": self._build_input_schema(f, skip_params={"ctx", "self"}),
                "func": f,
                "sig": inspect.signature(f),
            }
            return f

        return decorator(func) if func else decorator

    def resource(self, uri_template: str, *, name: str | None = None):
        def decorator(f):
            entry = {
                "uri_template": uri_template,
                "name": name or f.__name__,
                "description": inspect.getdoc(f) or "",
                "func": f,
                "sig": inspect.signature(f),
            }
            if "{" in uri_template and "}" in uri_template:
                entry["kind"] = "template"
                entry["uri_regex"] = self._compile_uri_template(uri_template)
                entry["arguments"] = self._build_argument_specs(f, skip_params={"ctx", "self"})
            else:
                entry["kind"] = "resource"
                entry["uri"] = uri_template
            self._resources.append(entry)
            return f

        return decorator

    def prompt(self, func=None, **kwargs):
        def decorator(f):
            self._prompts[f.__name__] = {
                "name": f.__name__,
                "description": inspect.getdoc(f) or "",
                "arguments": self._build_argument_specs(f, skip_params={"ctx", "self"}),
                "func": f,
                "sig": inspect.signature(f),
            }
            return f

        return decorator(func) if func else decorator

    async def run_stdio_async(self):
        if self._lifespan:
            async with self._lifespan(self) as ctx:
                await self._run_loop(ctx)
        else:
            @asynccontextmanager
            async def empty_lifespan():
                yield {}

            async with empty_lifespan() as ctx:
                await self._run_loop(ctx)

    async def send_message(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        async with self._stdout_lock:
            if getattr(self, "_use_content_length", False):
                header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                sys.stdout.buffer.write(header + body)
            else:
                sys.stdout.buffer.write(body + b"\n")
            sys.stdout.buffer.flush()

    async def send_result(self, msg_id: Any, result: dict[str, Any]) -> None:
        await self.send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

    async def send_error(self, msg_id: Any, code: int, message: str) -> None:
        await self.send_message(
            {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
        )

    def _read_headers_and_body(self) -> dict[str, Any] | None:
        stream = sys.stdin.buffer

        while True:
            first = stream.read(1)
            if not first:
                return None
            if first in b" \t\r\n":
                continue
            break

        if first == b"{":
            line = first + stream.readline()
            if not line:
                return None
            try:
                self._use_content_length = False
                return json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                self._log_stderr("Ignoring malformed line-delimited JSON request")
                return {}

        headers: dict[str, str] = {}
        first_line = first + stream.readline()
        if not first_line:
            return None

        while True:
            line = first_line if first_line is not None else stream.readline()
            first_line = None
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break

            decoded = line.decode("ascii", errors="replace").strip()
            if ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length = headers.get("content-length")
        if not content_length:
            self._log_stderr("Ignoring request without Content-Length header")
            return {}

        try:
            size = int(content_length)
        except ValueError:
            self._log_stderr(f"Ignoring request with invalid Content-Length: {content_length}")
            return {}

        body = stream.read(size)
        if len(body) != size:
            return None

        try:
            self._use_content_length = True
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._log_stderr("Ignoring malformed framed JSON request")
            return {}

    async def read_message(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._read_headers_and_body)

    async def _run_loop(self, lifespan_ctx: dict[str, Any]):
        while not self._shutdown_requested:
            req = await self.read_message()
            if req is None:
                break
            await self._handle_request(req, lifespan_ctx)

    async def _handle_request(self, req: dict[str, Any], lifespan_ctx: dict[str, Any]) -> None:
        if not req:
            return

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params") or {}

        try:
            if req_id is None:
                if method in {"notifications/initialized", "initialized"}:
                    return
                if method == "exit":
                    self._shutdown_requested = True
                    return
                return

            if method == "initialize":
                await self.send_result(
                    req_id,
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"listChanged": False},
                            "prompts": {"listChanged": False},
                        },
                        "serverInfo": {"name": self.name, "version": "native-2.0"},
                    },
                )
                return

            if method == "ping":
                await self.send_result(req_id, {})
                return

            if method == "shutdown":
                self._shutdown_requested = True
                await self.send_result(req_id, {})
                return

            if method == "tools/list":
                await self.send_result(
                    req_id,
                    {
                        "tools": [
                            {
                                "name": item["name"],
                                "description": item["description"],
                                "inputSchema": item["inputSchema"],
                            }
                            for item in self._tools.values()
                        ]
                    },
                )
                return

            if method == "tools/call":
                await self._handle_tool_call(req_id, params, lifespan_ctx)
                return

            if method == "resources/list":
                await self.send_result(
                    req_id,
                    {
                        "resources": [
                            {
                                "uri": item["uri"],
                                "name": item["name"],
                                "description": item["description"],
                                "mimeType": "application/json",
                            }
                            for item in self._resources
                            if item["kind"] == "resource"
                        ]
                    },
                )
                return

            if method == "resources/templates/list":
                await self.send_result(
                    req_id,
                    {
                        "resourceTemplates": [
                            {
                                "uriTemplate": item["uri_template"],
                                "name": item["name"],
                                "description": item["description"],
                                "mimeType": "application/json",
                            }
                            for item in self._resources
                            if item["kind"] == "template"
                        ]
                    },
                )
                return

            if method == "resources/read":
                await self._handle_resource_read(req_id, params, lifespan_ctx)
                return

            if method == "prompts/list":
                await self.send_result(
                    req_id,
                    {
                        "prompts": [
                            {
                                "name": item["name"],
                                "description": item["description"],
                                "arguments": item["arguments"],
                            }
                            for item in self._prompts.values()
                        ]
                    },
                )
                return

            if method == "prompts/get":
                await self._handle_prompt_get(req_id, params, lifespan_ctx)
                return

            await self.send_error(req_id, -32601, f"Method {method} not found")
        except Exception as exc:
            self._log_stderr(f"Request handler crash: {exc}\n{traceback.format_exc()}")
            await self.send_error(req_id, -32000, str(exc))

    async def _handle_tool_call(
        self, req_id: Any, params: dict[str, Any], lifespan_ctx: dict[str, Any]
    ) -> None:
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = self._tools.get(name)
        if tool is None:
            await self.send_result(
                req_id,
                {"content": [{"type": "text", "text": f"Tool {name} not found"}], "isError": True},
            )
            return

        try:
            out = await self._invoke_callable(tool["func"], tool["sig"], args, lifespan_ctx)
            text = self._stringify(out)
            await self.send_result(req_id, {"content": [{"type": "text", "text": text}]})
        except Exception as exc:
            self._log_stderr(f"Tool {name} failed: {exc}\n{traceback.format_exc()}")
            await self.send_result(
                req_id,
                {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "isError": True},
            )

    async def _handle_resource_read(
        self, req_id: Any, params: dict[str, Any], lifespan_ctx: dict[str, Any]
    ) -> None:
        uri = params.get("uri")
        if not uri:
            await self.send_error(req_id, -32602, "Missing resource uri")
            return

        entry, args = self._match_resource(uri)
        if entry is None:
            await self.send_error(req_id, -32602, f"Resource not found: {uri}")
            return

        out = await self._invoke_callable(entry["func"], entry["sig"], args, lifespan_ctx)
        await self.send_result(
            req_id,
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json" if not isinstance(out, str) else "text/plain",
                        "text": self._stringify(out),
                    }
                ]
            },
        )

    async def _handle_prompt_get(
        self, req_id: Any, params: dict[str, Any], lifespan_ctx: dict[str, Any]
    ) -> None:
        name = params.get("name")
        args = params.get("arguments") or {}
        prompt = self._prompts.get(name)
        if prompt is None:
            await self.send_error(req_id, -32602, f"Prompt not found: {name}")
            return

        out = await self._invoke_callable(prompt["func"], prompt["sig"], args, lifespan_ctx)
        text = self._stringify(out) if not isinstance(out, str) else out
        await self.send_result(
            req_id,
            {
                "description": prompt["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            },
        )

    async def _invoke_callable(
        self,
        func,
        sig: inspect.Signature,
        args: dict[str, Any],
        lifespan_ctx: dict[str, Any],
    ) -> Any:
        call_kwargs = {}
        for param_name, param in sig.parameters.items():
            if param_name in {"ctx", "context"}:
                call_kwargs[param_name] = Context(lifespan_ctx)
                continue
            if param_name == "self":
                continue
            if param_name not in args:
                continue
            call_kwargs[param_name] = self._coerce_value(args[param_name], param.annotation)

        if inspect.iscoroutinefunction(func):
            return await func(**call_kwargs)
        return func(**call_kwargs)

    def _match_resource(self, uri: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        for entry in self._resources:
            if entry["kind"] == "resource" and entry["uri"] == uri:
                return entry, {}
            if entry["kind"] == "template":
                match = entry["uri_regex"].match(uri)
                if match:
                    return entry, match.groupdict()
        return None, {}

    def _build_input_schema(
        self, func, *, skip_params: set[str]
    ) -> dict[str, Any]:
        sig = inspect.signature(func)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for param_name, param in sig.parameters.items():
            if param_name in skip_params:
                continue
            properties[param_name] = {"type": self._annotation_to_json_type(param.annotation)}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": False,
        }
        if required:
            schema["required"] = required
        return schema

    def _build_argument_specs(self, func, *, skip_params: set[str]) -> list[dict[str, Any]]:
        sig = inspect.signature(func)
        arguments: list[dict[str, Any]] = []
        for param_name, param in sig.parameters.items():
            if param_name in skip_params:
                continue
            entry: dict[str, Any] = {
                "name": param_name,
                "required": param.default is inspect.Parameter.empty,
            }
            if param.annotation is not inspect.Parameter.empty:
                entry["type"] = self._annotation_to_json_type(param.annotation)
            arguments.append(entry)
        return arguments

    def _annotation_to_json_type(self, annotation: Any) -> str:
        if annotation == int:
            return "integer"
        if annotation == bool:
            return "boolean"
        if annotation == float:
            return "number"
        if getattr(annotation, "__origin__", None) in {list, tuple}:
            return "array"
        return "string"

    def _coerce_value(self, value: Any, annotation: Any) -> Any:
        if annotation == int and not isinstance(value, int):
            return int(value)
        if annotation == float and not isinstance(value, float):
            return float(value)
        if annotation == bool and not isinstance(value, bool):
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "yes", "on"}:
                    return True
                if lowered in {"0", "false", "no", "off"}:
                    return False
            return bool(value)
        return value

    def _compile_uri_template(self, template: str) -> re.Pattern[str]:
        pattern = re.escape(template)
        pattern = re.sub(r"\\\{([a-zA-Z_][a-zA-Z0-9_]*)\\\}", r"(?P<\1>[^/]+)", pattern)
        return re.compile(f"^{pattern}$")

    def _stringify(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, indent=2)

    def _log_stderr(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

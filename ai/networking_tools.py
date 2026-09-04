r"""
Networking tool wiring
=========================
networking/ (http_client, ssh_client, ftp_client, websocket) was a fully
built, zero-dependency-on-anything-else package with nothing anywhere in
the codebase importing it - a dormant island, same bug class documented
in docs/TASK6_DORMANT_AUDIT.md for the other 11 packages found there.
Verified via `grep -rn "networking\." .` outside networking/ itself:
zero hits before this file.

SSH/FTP/WebSocket are connection-based, so unlike a stateless HTTP call
they need a handle the model can refer back to across several tool
calls ("connect", then "run a command", then "close"). Same
lazy-singleton *dict* pattern already used for apps/* in
ai/apps_tools.py (there it's keyed by app name; here it's keyed by a
session_id the model picks, e.g. "home_server", so more than one
connection can be open at once).

HTTP is stateless per call instead - a fresh networking.http_client.
HTTPClient() per request, base_url="" so the model always passes a full
URL. skills/internet/web_tools.py already covers search + readable-text
extraction; this is for calling arbitrary APIs / webhooks, matching
networking/http_client.py's own docstring.

Risk note (documented here, not hidden): ssh_run_command can execute
arbitrary commands on whatever host is connected, same trust model as
the already-wired local run_command tool (core/executor.py) - the
module's own docstring frames this as "a machine they [the user]
control". Not gated any tighter than local run_command already is, for
consistency - see ai/tools_schema.py's local run_command entry.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's _tool() - duplicated on
    purpose (see ai/new_skills_tools.py's docstring for why: avoids a
    circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


# ---------------------------------------------------------------------------
# Session registries - one dict per connection type, keyed by a model-chosen
# session_id. Mirrors ai/apps_tools.py's _get()/_instances lazy pattern.
# ---------------------------------------------------------------------------
_ssh_sessions: Dict[str, object] = {}
_ftp_sessions: Dict[str, object] = {}
_ws_sessions: Dict[str, object] = {}
_ws_messages: Dict[str, list] = {}


def _get_ssh(session_id: str, create: bool = False):
    if session_id not in _ssh_sessions:
        if not create:
            return None
        from networking.ssh_client import SSHClient

        _ssh_sessions[session_id] = SSHClient()
    return _ssh_sessions[session_id]


def _get_ftp(session_id: str, create: bool = False):
    if session_id not in _ftp_sessions:
        if not create:
            return None
        from networking.ftp_client import FTPClient

        _ftp_sessions[session_id] = FTPClient()
    return _ftp_sessions[session_id]


# ---------------------------------------------------------------------------
# Tool schema
# ---------------------------------------------------------------------------
NETWORKING_TOOLS = [
    # -- HTTP (stateless) --------------------------------------------------
    _tool(
        "http_get",
        "Send an HTTP GET request to any URL and return status/body.",
        {"url": {"type": "string"}, "headers": {"type": "object", "description": "Optional extra headers"}},
        ["url"],
    ),
    _tool(
        "http_post",
        "Send an HTTP POST request with a JSON body to any URL.",
        {"url": {"type": "string"}, "json_body": {"type": "object"}, "headers": {"type": "object"}},
        ["url"],
    ),
    _tool(
        "http_put",
        "Send an HTTP PUT request with a JSON body to any URL.",
        {"url": {"type": "string"}, "json_body": {"type": "object"}, "headers": {"type": "object"}},
        ["url"],
    ),
    _tool(
        "http_delete",
        "Send an HTTP DELETE request to any URL.",
        {"url": {"type": "string"}, "headers": {"type": "object"}},
        ["url"],
    ),
    # -- SSH (session-based) -------------------------------------------------
    _tool(
        "ssh_connect",
        "Open an SSH connection to a remote host the user controls, for remote "
        "administration (e.g. 'SSH into my home server'). Give session_id a "
        "short name (e.g. 'home_server') to refer back to this connection in "
        "later calls. Provide either password or key_filename.",
        {
            "session_id": {"type": "string"},
            "hostname": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "key_filename": {"type": "string"},
            "port": {"type": "integer", "description": "Default 22"},
            "trust_unknown_hosts": {
                "type": "boolean",
                "description": "Only for a first connection to a host you control",
            },
        },
        ["session_id", "hostname", "username"],
    ),
    _tool(
        "ssh_run_command",
        "Run a shell command on a host connected via ssh_connect and return stdout/stderr/exit code.",
        {"session_id": {"type": "string"}, "command": {"type": "string"}, "timeout": {"type": "integer"}},
        ["session_id", "command"],
    ),
    _tool(
        "ssh_upload_file",
        "Upload a local file to the connected SSH host via SFTP.",
        {"session_id": {"type": "string"}, "local_path": {"type": "string"}, "remote_path": {"type": "string"}},
        ["session_id", "local_path", "remote_path"],
    ),
    _tool(
        "ssh_download_file",
        "Download a file from the connected SSH host via SFTP.",
        {"session_id": {"type": "string"}, "remote_path": {"type": "string"}, "local_path": {"type": "string"}},
        ["session_id", "remote_path", "local_path"],
    ),
    _tool(
        "ssh_close",
        "Close an SSH session opened with ssh_connect.",
        {"session_id": {"type": "string"}},
        ["session_id"],
    ),
    # -- FTP (session-based) -------------------------------------------------
    _tool(
        "ftp_connect",
        "Open an FTP(S) connection to a remote host. Give session_id a short "
        "name to refer back to this connection in later calls. Uses FTPS "
        "(TLS) by default.",
        {
            "session_id": {"type": "string"},
            "hostname": {"type": "string"},
            "username": {"type": "string", "description": "Default 'anonymous'"},
            "password": {"type": "string"},
            "port": {"type": "integer", "description": "Default 21"},
            "use_tls": {"type": "boolean", "description": "Default true (FTPS)"},
        },
        ["session_id", "hostname"],
    ),
    _tool(
        "ftp_list_directory",
        "List a directory on the connected FTP host.",
        {"session_id": {"type": "string"}, "remote_path": {"type": "string"}},
        ["session_id"],
    ),
    _tool(
        "ftp_upload_file",
        "Upload a local file to the connected FTP host.",
        {"session_id": {"type": "string"}, "local_path": {"type": "string"}, "remote_path": {"type": "string"}},
        ["session_id", "local_path", "remote_path"],
    ),
    _tool(
        "ftp_download_file",
        "Download a file from the connected FTP host.",
        {"session_id": {"type": "string"}, "remote_path": {"type": "string"}, "local_path": {"type": "string"}},
        ["session_id", "remote_path", "local_path"],
    ),
    _tool(
        "ftp_delete_file",
        "Delete a file on the connected FTP host.",
        {"session_id": {"type": "string"}, "remote_path": {"type": "string"}},
        ["session_id", "remote_path"],
    ),
    _tool(
        "ftp_close",
        "Close an FTP session opened with ftp_connect.",
        {"session_id": {"type": "string"}},
        ["session_id"],
    ),
    # -- WebSocket (session-based) --------------------------------------------
    _tool(
        "websocket_connect",
        "Open a persistent WebSocket connection (e.g. a live price/status "
        "feed). Give session_id a short name to refer back to it. Incoming "
        "messages are buffered - read them with websocket_get_messages.",
        {"session_id": {"type": "string"}, "url": {"type": "string"}, "timeout": {"type": "integer"}},
        ["session_id", "url"],
    ),
    _tool(
        "websocket_send",
        "Send a text message over an open WebSocket session.",
        {"session_id": {"type": "string"}, "message": {"type": "string"}},
        ["session_id", "message"],
    ),
    _tool(
        "websocket_get_messages",
        "Return and clear the messages received on this WebSocket session since it was last read.",
        {"session_id": {"type": "string"}},
        ["session_id"],
    ),
    _tool(
        "websocket_is_connected",
        "Check whether a WebSocket session is still connected.",
        {"session_id": {"type": "string"}},
        ["session_id"],
    ),
    _tool(
        "websocket_close",
        "Close a WebSocket session opened with websocket_connect.",
        {"session_id": {"type": "string"}},
        ["session_id"],
    ),
]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
def _http_client():
    from networking.http_client import HTTPClient

    return HTTPClient()


def _ssh_connect(a: Dict) -> Dict:
    client = _get_ssh(a.get("session_id", ""), create=True)
    return client.connect(
        hostname=a.get("hostname", ""),
        username=a.get("username", ""),
        password=a.get("password"),
        key_filename=a.get("key_filename"),
        port=a.get("port", 22),
        trust_unknown_hosts=a.get("trust_unknown_hosts", False),
    )


def _ssh_op(a: Dict, fn_name: str, **kwargs) -> Dict:
    client = _get_ssh(a.get("session_id", ""))
    if client is None:
        return {"error": f"No SSH session '{a.get('session_id')}' - call ssh_connect first"}
    return getattr(client, fn_name)(**kwargs)


def _ftp_connect(a: Dict) -> Dict:
    client = _get_ftp(a.get("session_id", ""), create=True)
    return client.connect(
        hostname=a.get("hostname", ""),
        username=a.get("username", "anonymous"),
        password=a.get("password", ""),
        port=a.get("port", 21),
        use_tls=a.get("use_tls", True),
    )


def _ftp_op(a: Dict, fn_name: str, **kwargs) -> Dict:
    client = _get_ftp(a.get("session_id", ""))
    if client is None:
        return {"error": f"No FTP session '{a.get('session_id')}' - call ftp_connect first"}
    return getattr(client, fn_name)(**kwargs)


def _websocket_connect(a: Dict) -> Dict:
    from networking.websocket import WebSocketClient

    session_id = a.get("session_id", "")
    buf = _ws_messages.setdefault(session_id, [])

    def _on_message(message):
        buf.append(message)

    client = WebSocketClient(a.get("url", ""), on_message=_on_message)
    result = client.connect(timeout=a.get("timeout", 10))
    if result.get("success"):
        _ws_sessions[session_id] = client
    return result


def _ws_op(a: Dict, fn_name: str, **kwargs) -> Dict:
    client = _ws_sessions.get(a.get("session_id", ""))
    if client is None:
        return {"error": f"No WebSocket session '{a.get('session_id')}' - call websocket_connect first"}
    return getattr(client, fn_name)(**kwargs)


def _ws_get_messages(a: Dict) -> Dict:
    session_id = a.get("session_id", "")
    messages = _ws_messages.get(session_id, [])
    _ws_messages[session_id] = []
    return {"messages": messages}


def _ws_is_connected(a: Dict) -> Dict:
    client = _ws_sessions.get(a.get("session_id", ""))
    if client is None:
        return {"connected": False, "error": f"No WebSocket session '{a.get('session_id')}'"}
    return {"connected": client.is_connected()}


NETWORKING_DIRECT_HANDLERS: Dict = {
    "http_get": lambda a: _http_client().get(a.get("url", ""), headers=a.get("headers")),
    "http_post": lambda a: _http_client().post(
        a.get("url", ""), json_body=a.get("json_body"), headers=a.get("headers")
    ),
    "http_put": lambda a: _http_client().put(a.get("url", ""), json_body=a.get("json_body"), headers=a.get("headers")),
    "http_delete": lambda a: _http_client().delete(a.get("url", ""), headers=a.get("headers")),
    "ssh_connect": _ssh_connect,
    "ssh_run_command": lambda a: _ssh_op(a, "run_command", command=a.get("command", ""), timeout=a.get("timeout", 30)),
    "ssh_upload_file": lambda a: _ssh_op(
        a, "upload_file", local_path=a.get("local_path", ""), remote_path=a.get("remote_path", "")
    ),
    "ssh_download_file": lambda a: _ssh_op(
        a, "download_file", remote_path=a.get("remote_path", ""), local_path=a.get("local_path", "")
    ),
    "ssh_close": lambda a: _ssh_op(a, "close"),
    "ftp_connect": _ftp_connect,
    "ftp_list_directory": lambda a: _ftp_op(a, "list_directory", remote_path=a.get("remote_path", ".")),
    "ftp_upload_file": lambda a: _ftp_op(
        a, "upload_file", local_path=a.get("local_path", ""), remote_path=a.get("remote_path", "")
    ),
    "ftp_download_file": lambda a: _ftp_op(
        a, "download_file", remote_path=a.get("remote_path", ""), local_path=a.get("local_path", "")
    ),
    "ftp_delete_file": lambda a: _ftp_op(a, "delete_file", remote_path=a.get("remote_path", "")),
    "ftp_close": lambda a: _ftp_op(a, "close"),
    "websocket_connect": _websocket_connect,
    "websocket_send": lambda a: _ws_op(a, "send", message=a.get("message", "")),
    "websocket_get_messages": _ws_get_messages,
    "websocket_is_connected": _ws_is_connected,
    "websocket_close": lambda a: _ws_op(a, "close"),
}

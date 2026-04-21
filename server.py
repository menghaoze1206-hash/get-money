#!/usr/bin/env python3
import json
import os
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
STATIC_DIR = BASE_DIR / "static"
PORT = 8765

ESTIMATE_URL = "https://fundgz.1234567.com.cn/js/{code}.js"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)
JSONP_PATTERN = re.compile(r"jsonpgz\((.*)\);?$")


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not WATCHLIST_FILE.exists():
        WATCHLIST_FILE.write_text(
            json.dumps(
                [
                    {"code": "161725", "name": "招商中证白酒指数(LOF)A"},
                    {"code": "110022", "name": "易方达消费行业股票"},
                    {"code": "003096", "name": "中欧医疗健康混合A"},
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def load_watchlist():
    ensure_data_dir()
    raw = WATCHLIST_FILE.read_text(encoding="utf-8")
    items = json.loads(raw)
    return items if isinstance(items, list) else []


def save_watchlist(items):
    ensure_data_dir()
    WATCHLIST_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_estimate(code: str):
    code = code.strip()
    if not code.isdigit():
        raise ValueError("基金代码必须是数字")

    url = ESTIMATE_URL.format(code=parse.quote(code))
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": "https://fund.eastmoney.com/"})
    with request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8", errors="replace").strip()

    match = JSONP_PATTERN.match(body)
    if not match:
        raise ValueError("上游返回格式异常，可能该基金暂不支持估值")

    payload = json.loads(match.group(1))
    payload["estimateSource"] = "fundgz.1234567.com.cn"
    return payload


class FundHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        parsed = parse.urlparse(self.path)
        if parsed.path in ("", "/"):
            path = "/index.html"
        else:
            path = parsed.path
        full_path = (STATIC_DIR / path.lstrip("/")).resolve()
        try:
            full_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not full_path.exists() or not full_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", self.guess_type(full_path.suffix))
        self.send_header("Content-Length", str(full_path.stat().st_size))
        self.end_headers()

    def do_GET(self):
        parsed = parse.urlparse(self.path)
        if parsed.path == "/api/watchlist":
            self.respond_json({"items": load_watchlist()})
            return

        if parsed.path == "/api/estimate":
            qs = parse.parse_qs(parsed.query)
            code = (qs.get("code") or [""])[0]
            if not code:
                self.respond_json({"error": "缺少 code 参数"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                data = fetch_estimate(code)
            except ValueError as exc:
                self.respond_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except error.HTTPError as exc:
                self.respond_json(
                    {"error": f"上游接口返回 {exc.code}"},
                    status=HTTPStatus.BAD_GATEWAY,
                )
            except Exception as exc:
                self.respond_json(
                    {"error": f"请求上游接口失败: {exc}"},
                    status=HTTPStatus.BAD_GATEWAY,
                )
            else:
                self.respond_json(data)
            return

        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = parse.urlparse(self.path)
        if parsed.path != "/api/watchlist":
            self.respond_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)
            return

        payload = self.read_json_body()
        code = str(payload.get("code", "")).strip()
        if not code.isdigit():
            self.respond_json({"error": "基金代码必须是数字"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            estimate = fetch_estimate(code)
        except Exception as exc:
            self.respond_json(
                {"error": f"基金代码无效或当前不可查询: {exc}"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        items = load_watchlist()
        if any(item.get("code") == code for item in items):
            self.respond_json({"items": items})
            return

        items.append({"code": code, "name": estimate.get("name") or code})
        save_watchlist(items)
        self.respond_json({"items": items}, status=HTTPStatus.CREATED)

    def do_DELETE(self):
        parsed = parse.urlparse(self.path)
        prefix = "/api/watchlist/"
        if not parsed.path.startswith(prefix):
            self.respond_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)
            return

        code = parsed.path[len(prefix):].strip()
        items = load_watchlist()
        next_items = [item for item in items if item.get("code") != code]
        if len(next_items) == len(items):
            self.respond_json({"error": "基金不存在"}, status=HTTPStatus.NOT_FOUND)
            return

        save_watchlist(next_items)
        self.respond_json({"items": next_items})

    def read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        return json.loads(body or "{}")

    def serve_static(self, path: str):
        if path in ("", "/"):
            path = "/index.html"
        full_path = (STATIC_DIR / path.lstrip("/")).resolve()
        try:
            full_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.respond_json({"error": "非法路径"}, status=HTTPStatus.FORBIDDEN)
            return

        if not full_path.exists() or not full_path.is_file():
            self.respond_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)
            return

        content_type = self.guess_type(full_path.suffix)
        data = full_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def guess_type(ext: str) -> str:
        return {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(ext, "application/octet-stream")

    def log_message(self, fmt, *args):
        return


def main():
    ensure_data_dir()
    port = PORT
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    server = ThreadingHTTPServer(("127.0.0.1", port), FundHandler)
    print(f"Server running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

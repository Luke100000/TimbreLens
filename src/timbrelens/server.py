from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, site: Path, data: Path, **kwargs):
        self.site = site.resolve()
        self.data = data.resolve()
        super().__init__(*args, directory=str(self.site), **kwargs)

    def translate_path(self, path: str) -> str:
        relative = Path(super().translate_path(path)).relative_to(self.site)
        if relative.parts[:1] == ("data",):
            return str(self.data.joinpath(*relative.parts[1:]))
        return str(self.site / relative)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def serve(
    site: Path = Path("site"),
    data: Path = Path("data"),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    if not (site / "index.html").is_file():
        raise ValueError(f"No index.html in {site}")
    handler = partial(PreviewHandler, site=site, data=data)
    with ThreadingHTTPServer((host, port), handler) as server:
        print(f"Preview: http://{host}:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

"""Servidor web do simulador CFTV com painel em tempo real.

Uso rapido:
python servidor_web_cftv.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from simulador_cftv import ConfiguracaoSimulador
from simulador_cftv import EventoCFTV
from simulador_cftv import calcular_resumo
from simulador_cftv import gerar_evento
from simulador_cftv import inteiro_nao_negativo
from simulador_cftv import validar_configuracao

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"


class EstadoSimulacao:
    def __init__(self, cfg: ConfiguracaoSimulador) -> None:
        self.cfg = cfg
        self.lock = threading.Lock()
        self.rng = random.Random(cfg.seed)
        self.uso_disco_atual = cfg.uso_disco_inicial
        self.ciclo = 0
        self.eventos: list[EventoCFTV] = []

    def gerar_proximo_evento(self) -> EventoCFTV:
        with self.lock:
            self.ciclo += 1
            evento, self.uso_disco_atual = gerar_evento(
                ciclo=self.ciclo,
                uso_disco_atual=self.uso_disco_atual,
                cfg=self.cfg,
                rng=self.rng,
                time_provider=datetime.now,
            )
            self.eventos.append(evento)
            return evento

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            evento = self.eventos[-1] if self.eventos else EventoCFTV(
                ciclo=0,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                conectividade=0,
                sinal_video=0,
                banda_mbps=0.0,
                uso_disco_pct=self.uso_disco_atual,
            )
            resumo = calcular_resumo(self.eventos)
            return {
                "evento": asdict(evento),
                "resumo": resumo,
            }


class SimuladorLoop(threading.Thread):
    def __init__(self, estado: EstadoSimulacao) -> None:
        super().__init__(daemon=True)
        self.estado = estado
        self._stopped = threading.Event()

    def stop(self) -> None:
        self._stopped.set()

    def run(self) -> None:
        while not self._stopped.is_set():
            self.estado.gerar_proximo_evento()
            self._stopped.wait(self.estado.cfg.intervalo_segundos)


class CFTVRequestHandler(BaseHTTPRequestHandler):
    estado: EstadoSimulacao

    def _send_common_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")

    def _path_only(self) -> str:
        # Ignore query params so routes like /api/status?source=zabbix keep working.
        return urlparse(self.path).path

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_common_headers()
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_file(self, file_path: Path, content_type: str) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo nao encontrado")
            return

        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self._send_common_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = self._path_only()

        if path == "/api/status":
            payload = self.estado.snapshot()
            self._send_json(payload)
            return

        if path == "/healthz":
            self._send_json({"status": "ok", "timestamp": datetime.now().isoformat(timespec="seconds")})
            return

        if path == "/" or path == "/index.html":
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return

        if path == "/styles.css":
            self._send_file(WEB_DIR / "styles.css", "text/css; charset=utf-8")
            return

        if path == "/app.js":
            self._send_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Rota nao encontrada")

    def log_message(self, format: str, *args: Any) -> None:
        return


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Servidor web do painel CFTV")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host de bind do servidor")
    parser.add_argument("--port", type=inteiro_nao_negativo, default=8080, help="Porta de bind do servidor")
    parser.add_argument("--intervalo", type=float, default=2.0, help="Intervalo de atualizacao da simulacao")
    parser.add_argument("--chance-rede-online", type=float, default=0.90, help="Probabilidade da rede estar online")
    parser.add_argument("--chance-video-ok", type=float, default=0.95, help="Probabilidade de camera com sinal")
    parser.add_argument("--uso-disco-inicial", type=float, default=50.0, help="Uso inicial de disco")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reproducibilidade")
    return parser


def cfg_from_args(args: argparse.Namespace) -> ConfiguracaoSimulador:
    cfg = ConfiguracaoSimulador(
        intervalo_segundos=args.intervalo,
        chance_rede_online=args.chance_rede_online,
        chance_video_ok_quando_online=args.chance_video_ok,
        uso_disco_inicial=args.uso_disco_inicial,
        seed=args.seed,
        exibir_resumo=False,
        sem_sleep=False,
    )
    validar_configuracao(cfg)
    return cfg


def main() -> None:
    parser = criar_parser()
    args = parser.parse_args()

    if args.port > 65535:
        parser.error("--port deve estar entre 0 e 65535")

    cfg = cfg_from_args(args)
    estado = EstadoSimulacao(cfg)

    # Gera o primeiro evento para a UI abrir com dados validos.
    estado.gerar_proximo_evento()

    handler_class = type(
        "CFTVHandler",
        (CFTVRequestHandler,),
        {"estado": estado},
    )

    loop = SimuladorLoop(estado)
    server = ThreadingHTTPServer((args.host, args.port), handler_class)

    print(f"Painel CFTV disponivel em http://{args.host}:{args.port}")
    print("Pressione Ctrl+C para encerrar.")

    loop.start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nEncerrando servidor...")
    finally:
        loop.stop()
        server.server_close()
        time.sleep(0.05)


if __name__ == "__main__":
    main()

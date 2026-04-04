"""Servidor web do simulador CFTV com painel em tempo real.

Uso rapido:
python servidor_web_cftv.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import sys
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

# Logging estruturado em JSON
logger = logging.getLogger(__name__)

def setup_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S',
    )

setup_logging(os.getenv("LOG_LEVEL", "INFO"))


class EstadoSimulacao:
    def __init__(self, cfg: ConfiguracaoSimulador) -> None:
        self.cfg = cfg
        self.lock = threading.Lock()
        self.rng = random.Random(cfg.seed)
        self.uso_disco_atual = cfg.uso_disco_inicial
        self.ciclo = 0
        self.eventos: list[EventoCFTV] = []
        self.inicializacao = datetime.now()
        self.total_requisicoes = 0
        self.total_erros = 0

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

    def health(self) -> dict[str, Any]:
        with self.lock:
            uptime_s = (datetime.now() - self.inicializacao).total_seconds()
            return {
                "status": "ok",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "uptime_seconds": int(uptime_s),
                "ciclos_executados": self.ciclo,
                "total_requisicoes": self.total_requisicoes,
                "total_erros": self.total_erros,
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
        self.estado.total_requisicoes += 1

        if path == "/api/status":
            payload = self.estado.snapshot()
            self._send_json(payload)
            logger.info(f"GET {path} 200")
            return

        if path == "/healthz":
            payload = self.estado.health()
            self._send_json(payload)
            logger.info(f"GET {path} 200")
            return

        if path == "/metrics":
            metrics = self._prometheus_metrics()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self._send_common_headers()
            self.end_headers()
            self.wfile.write(metrics.encode("utf-8"))
            logger.info(f"GET {path} 200")
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

        self.estado.total_erros += 1
        self.send_error(HTTPStatus.NOT_FOUND, "Rota nao encontrada")
        logger.warning(f"GET {path} 404")

    def _prometheus_metrics(self) -> str:
        snapshot = self.estado.snapshot()
        health = self.estado.health()
        evento = snapshot["evento"]
        resumo = snapshot["resumo"]

        lines = [
            "# HELP cftv_evento_conectividade Conectividade atual (0 ou 1)",
            "# TYPE cftv_evento_conectividade gauge",
            f"cftv_evento_conectividade {evento['conectividade']}",
            "# HELP cftv_evento_sinal_video Sinal de video (0 ou 1)",
            "# TYPE cftv_evento_sinal_video gauge",
            f"cftv_evento_sinal_video {evento['sinal_video']}",
            "# HELP cftv_evento_banda_mbps Banda instantanea em Mbps",
            "# TYPE cftv_evento_banda_mbps gauge",
            f"cftv_evento_banda_mbps {evento['banda_mbps']}",
            "# HELP cftv_evento_uso_disco_pct Uso de disco em percentual",
            "# TYPE cftv_evento_uso_disco_pct gauge",
            f"cftv_evento_uso_disco_pct {evento['uso_disco_pct']}",
            "# HELP cftv_resumo_uptime_rede_pct Uptime de rede em percentual",
            "# TYPE cftv_resumo_uptime_rede_pct gauge",
            f"cftv_resumo_uptime_rede_pct {resumo['uptime_rede_pct']}",
            "# HELP cftv_resumo_camera_ok_pct Camera OK em percentual",
            "# TYPE cftv_resumo_camera_ok_pct gauge",
            f"cftv_resumo_camera_ok_pct {resumo['camera_ok_pct']}",
            "# HELP cftv_resumo_banda_media_mbps Banda media em Mbps",
            "# TYPE cftv_resumo_banda_media_mbps gauge",
            f"cftv_resumo_banda_media_mbps {resumo['banda_media_mbps']}",
            "# HELP cftv_uptime_seconds Tempo desde inicializacao",
            "# TYPE cftv_uptime_seconds gauge",
            f"cftv_uptime_seconds {health['uptime_seconds']}",
            "# HELP cftv_total_requisicoes Total de requisicoes HTTP",
            "# TYPE cftv_total_requisicoes counter",
            f"cftv_total_requisicoes {health['total_requisicoes']}",
            "# HELP cftv_total_erros Total de erros HTTP",
            "# TYPE cftv_total_erros counter",
            f"cftv_total_erros {health['total_erros']}",
        ]
        return "\n".join(lines) + "\n"

    def log_message(self, format: str, *args: Any) -> None:
        return


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Servidor web do painel CFTV")
    parser.add_argument("--host", type=str, default=os.getenv("HOST", "0.0.0.0"), help="Host de bind do servidor")
    parser.add_argument("--port", type=inteiro_nao_negativo, default=int(os.getenv("PORT", "8080")), help="Porta de bind do servidor")
    parser.add_argument("--intervalo", type=float, default=float(os.getenv("INTERVAL", "2.0")), help="Intervalo de atualizacao da simulacao")
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
    server.timeout = 5  # Request timeout

    logger.info(f"Painel CFTV iniciando em http://{args.host}:{args.port}")
    logger.info(f"Saude: http://{args.host}:{args.port}/healthz")
    logger.info(f"Metricas: http://{args.host}:{args.port}/metrics")

    def signal_handler(signum: int, frame: Any) -> None:
        logger.info("Sinal de encerramento recebido, encerrando graciosamente...")
        loop.stop()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    loop.start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logger.warning("Encerramento por teclado")
        loop.stop()
        server.server_close()
    finally:
        logger.info("Servidor encerrado")


if __name__ == "__main__":
    main()

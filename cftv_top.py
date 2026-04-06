"""Simulador CFTV em modo terminal puro, estilo top do Ubuntu.

Uso:
  python cftv_top.py --perfil-carga camera
  python cftv_top.py --perfil-carga camera --intervalo 1
  python cftv_top.py burst --duracao 60

O modo burst grava um arquivo de controle local para que a proxima execucao
leia o comando e aplique a carga temporaria sem precisar de interface grafica.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from simulador_cftv import ConfiguracaoSimulador
from simulador_cftv import EventoCFTV
from simulador_cftv import calcular_resumo
from simulador_cftv import gerar_evento
from simulador_cftv import inteiro_nao_negativo
from simulador_cftv import montar_saida_top
from simulador_cftv import validar_configuracao

BASE_DIR = Path(__file__).resolve().parent
CONTROL_FILE = BASE_DIR / ".cftv_control.json"
STATE_FILE = BASE_DIR / ".cftv_state.json"


def salvar_comando(acao: str, duracao: float) -> None:
    payload = {
        "acao": acao,
        "duracao": duracao,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    CONTROL_FILE.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def ler_comando_pendente() -> dict[str, object] | None:
    if not CONTROL_FILE.exists():
        return None
    try:
        payload = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
        CONTROL_FILE.unlink(missing_ok=True)
        return payload
    except Exception:
        return None


def salvar_estado(evento: EventoCFTV, resumo: dict[str, object], perfil_carga: str) -> None:
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "perfil_carga": perfil_carga,
        "evento": asdict(evento),
        "resumo": resumo,
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulador CFTV em terminal puro")
    subparsers = parser.add_subparsers(dest="subcomando")

    rodar = subparsers.add_parser("run", help="Executa a simulacao no terminal estilo top")
    rodar.add_argument("--intervalo", type=float, default=2.0, help="Intervalo entre atualizacoes")
    rodar.add_argument("--perfil-carga", type=str, default="camera", choices=["camera", "normal", "stress", "burst"])
    rodar.add_argument("--chance-rede-online", type=float, default=0.90)
    rodar.add_argument("--chance-video-ok", type=float, default=0.95)
    rodar.add_argument("--uso-disco-inicial", type=float, default=50.0)
    rodar.add_argument("--seed", type=int, default=None)
    rodar.add_argument("--sem-limpar", action="store_true", help="Nao limpa a tela a cada ciclo")
    rodar.add_argument("--sem-salvar", action="store_true", help="Nao salva arquivo de estado")

    burst = subparsers.add_parser("burst", help="Dispara burst temporario para a proxima simulacao")
    burst.add_argument("--duracao", type=float, default=60.0, help="Duracao do burst em segundos")

    stress = subparsers.add_parser("stress", help="Dispara stress temporario para a proxima simulacao")
    stress.add_argument("--duracao", type=float, default=60.0, help="Duracao do stress em segundos")

    normal = subparsers.add_parser("normal", help="Volta ao modo normal para a proxima simulacao")
    normal.add_argument("--duracao", type=float, default=10.0, help="Janela de restauracao (informativa)")

    return parser


def obter_cfg_base(args: argparse.Namespace) -> ConfiguracaoSimulador:
    cfg = ConfiguracaoSimulador(
        intervalo_segundos=args.intervalo,
        perfil_carga=args.perfil_carga,
        chance_rede_online=args.chance_rede_online,
        chance_video_ok_quando_online=args.chance_video_ok,
        uso_disco_inicial=args.uso_disco_inicial,
        seed=args.seed,
        formato_saida="top",
        exibir_resumo=True,
        sem_sleep=False,
    )
    validar_configuracao(cfg)
    return cfg


def aplicar_comando_pendente(perfil_base: str) -> str:
    comando = ler_comando_pendente()
    if not comando:
        return perfil_base

    acao = str(comando.get("acao", "")).strip().lower()
    if acao in {"burst", "stress", "normal"}:
        return acao
    return perfil_base


def limpar_tela() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


def executar(args: argparse.Namespace) -> None:
    cfg = obter_cfg_base(args)
    rng = random.Random(cfg.seed)
    uso_disco = cfg.uso_disco_inicial
    ciclo = 0
    eventos: list[EventoCFTV] = []
    perfil_base = cfg.perfil_carga
    perfil_ativo = aplicar_comando_pendente(perfil_base)
    inicio = datetime.now()

    print("CFTV terminal mode iniciado")
    print("Comandos disponiveis: run | burst --duracao 60 | stress --duracao 60 | normal")
    print("Ctrl+C para parar\n")

    try:
        while True:
            if not args.sem_limpar:
                limpar_tela()

            perfil_ativo = aplicar_comando_pendente(perfil_base)
            cfg.perfil_carga = perfil_ativo

            ciclo += 1
            evento, uso_disco = gerar_evento(
                ciclo=ciclo,
                uso_disco_atual=uso_disco,
                cfg=cfg,
                rng=rng,
                time_provider=datetime.now,
            )
            eventos.append(evento)
            resumo = calcular_resumo(eventos)

            uptime = (datetime.now() - inicio).total_seconds()
            print(montar_saida_top(evento, uptime_segundos=uptime))
            print(f"Perfil atual: {perfil_ativo} | Base: {perfil_base} | Ciclo: {ciclo}")
            print(f"Comando pendente: {'sim' if CONTROL_FILE.exists() else 'nao'}")
            print(f"Arquivo de estado: {STATE_FILE}")

            if not args.sem_salvar:
                salvar_estado(evento, resumo, perfil_ativo)

            time.sleep(cfg.intervalo_segundos)
    except KeyboardInterrupt:
        print("\nSimulacao encerrada pelo usuario.")
        if eventos:
            print("\nResumo final")
            final = calcular_resumo(eventos)
            print(json.dumps(final, ensure_ascii=True, indent=2))


def main() -> None:
    parser = criar_parser()
    args = parser.parse_args()

    if args.subcomando in {"burst", "stress", "normal"}:
        duracao = float(getattr(args, "duracao", 60.0))
        salvar_comando(args.subcomando, duracao)
        print(f"Comando '{args.subcomando}' gravado por {duracao} segundos em {CONTROL_FILE}")
        return

    if args.subcomando != "run":
        args = parser.parse_args(["run"])

    executar(args)


if __name__ == "__main__":
    main()

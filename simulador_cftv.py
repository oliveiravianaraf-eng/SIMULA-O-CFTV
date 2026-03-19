"""Simulador de servidor CFTV para testes de monitoramento.

Recursos principais:
- Simulacao configuravel por linha de comando
- Saida em texto ou JSON
- Resumo estatistico ao final
- Modo de execucao finita para testes
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections.abc import Callable
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass
class ConfiguracaoSimulador:
    intervalo_segundos: float = 5.0
    chance_rede_online: float = 0.90
    chance_video_ok_quando_online: float = 0.95
    uso_disco_inicial: float = 50.0
    limite_sobrescrita_disco: float = 95.0
    uso_disco_retorno: float = 50.0
    incremento_disco_min: float = 0.1
    incremento_disco_max: float = 0.5
    banda_sem_video_min: float = 0.1
    banda_sem_video_max: float = 0.3
    banda_com_video_min: float = 2.5
    banda_com_video_max: float = 4.5
    ciclos: int = 0  # 0 = infinito
    seed: int | None = None
    formato_saida: str = "texto"  # texto|json
    exibir_resumo: bool = True
    sem_sleep: bool = False


@dataclass(frozen=True)
class EventoCFTV:
    ciclo: int
    timestamp: str
    conectividade: int
    sinal_video: int
    banda_mbps: float
    uso_disco_pct: float


def validar_probabilidade(valor: float, nome: str) -> None:
    if not 0 <= valor <= 1:
        raise ValueError(f"{nome} deve estar entre 0 e 1. Valor recebido: {valor}")


def inteiro_nao_negativo(valor: str) -> int:
    convertido = int(valor)
    if convertido < 0:
        raise argparse.ArgumentTypeError("o valor deve ser maior ou igual a 0")
    return convertido


def validar_faixa(minimo: float, maximo: float, nome: str) -> None:
    if minimo > maximo:
        raise ValueError(f"Faixa invalida para {nome}: minimo ({minimo}) maior que maximo ({maximo})")


def validar_configuracao(cfg: ConfiguracaoSimulador) -> None:
    validar_probabilidade(cfg.chance_rede_online, "chance_rede_online")
    validar_probabilidade(cfg.chance_video_ok_quando_online, "chance_video_ok_quando_online")

    validar_faixa(cfg.incremento_disco_min, cfg.incremento_disco_max, "incremento_disco")
    validar_faixa(cfg.banda_sem_video_min, cfg.banda_sem_video_max, "banda_sem_video")
    validar_faixa(cfg.banda_com_video_min, cfg.banda_com_video_max, "banda_com_video")

    if cfg.intervalo_segundos <= 0:
        raise ValueError("intervalo_segundos deve ser maior que 0")

    if cfg.ciclos < 0:
        raise ValueError("ciclos nao pode ser negativo")

    if cfg.formato_saida not in {"texto", "json"}:
        raise ValueError("formato_saida deve ser 'texto' ou 'json'")

    if not 0 <= cfg.uso_disco_inicial <= 100:
        raise ValueError("uso_disco_inicial deve estar entre 0 e 100")

    if not 0 <= cfg.uso_disco_retorno <= 100:
        raise ValueError("uso_disco_retorno deve estar entre 0 e 100")

    if not 0 <= cfg.limite_sobrescrita_disco <= 100:
        raise ValueError("limite_sobrescrita_disco deve estar entre 0 e 100")

    if cfg.uso_disco_retorno >= cfg.limite_sobrescrita_disco:
        raise ValueError("uso_disco_retorno deve ser menor que limite_sobrescrita_disco")


def status_rede(chance_online: float, rng: random.Random) -> int:
    return 1 if rng.random() < chance_online else 0


def status_video(conectividade: int, chance_video_ok: float, rng: random.Random) -> int:
    if conectividade == 0:
        return 0
    return 1 if rng.random() < chance_video_ok else 0


def calcular_banda(conectividade: int, sinal_video: int, cfg: ConfiguracaoSimulador, rng: random.Random) -> float:
    if conectividade == 0:
        return 0.0
    if sinal_video == 0:
        return rng.uniform(cfg.banda_sem_video_min, cfg.banda_sem_video_max)
    return rng.uniform(cfg.banda_com_video_min, cfg.banda_com_video_max)


def atualizar_disco(uso_atual: float, cfg: ConfiguracaoSimulador, rng: random.Random) -> float:
    uso_atual += rng.uniform(cfg.incremento_disco_min, cfg.incremento_disco_max)
    if uso_atual >= cfg.limite_sobrescrita_disco:
        return cfg.uso_disco_retorno
    return uso_atual


def montar_linha_log(evento: EventoCFTV) -> str:
    status_rede_txt = "Online " if evento.conectividade else "Offline"
    status_video_txt = "OK       " if evento.sinal_video else "Sem Sinal"
    return (
        f"[{evento.timestamp}] [CFTV] Ciclo: {evento.ciclo:04d} | Rede: {status_rede_txt} | "
        f"Camera: {status_video_txt} | Banda: {evento.banda_mbps:.2f} Mbps | Disco: {evento.uso_disco_pct:.1f}%"
    )


def formatar_evento_json(evento: EventoCFTV) -> str:
    return json.dumps(asdict(evento), ensure_ascii=True)


def calcular_resumo(eventos: list[EventoCFTV]) -> dict[str, float | int]:
    total = len(eventos)
    if total == 0:
        return {
            "total_ciclos": 0,
            "uptime_rede_pct": 0.0,
            "camera_ok_pct": 0.0,
            "banda_media_mbps": 0.0,
            "disco_final_pct": 0.0,
        }

    rede_online = sum(1 for e in eventos if e.conectividade == 1)
    camera_ok = sum(1 for e in eventos if e.sinal_video == 1)
    banda_media = sum(e.banda_mbps for e in eventos) / total
    disco_final = eventos[-1].uso_disco_pct

    return {
        "total_ciclos": total,
        "uptime_rede_pct": (rede_online / total) * 100,
        "camera_ok_pct": (camera_ok / total) * 100,
        "banda_media_mbps": banda_media,
        "disco_final_pct": disco_final,
    }


def imprimir_resumo(eventos: list[EventoCFTV]) -> None:
    resumo = calcular_resumo(eventos)
    print("\nResumo da simulacao")
    print(f"- Total de ciclos: {int(resumo['total_ciclos'])}")
    print(f"- Uptime de rede: {resumo['uptime_rede_pct']:.1f}%")
    print(f"- Camera com video OK: {resumo['camera_ok_pct']:.1f}%")
    print(f"- Banda media: {resumo['banda_media_mbps']:.2f} Mbps")
    print(f"- Uso de disco final: {resumo['disco_final_pct']:.1f}%")


def gerar_evento(
    *,
    ciclo: int,
    uso_disco_atual: float,
    cfg: ConfiguracaoSimulador,
    rng: random.Random,
    time_provider: Callable[[], datetime],
) -> Tuple[EventoCFTV, float]:
    conectividade = status_rede(cfg.chance_rede_online, rng)
    sinal_video = status_video(conectividade, cfg.chance_video_ok_quando_online, rng)
    banda = calcular_banda(conectividade, sinal_video, cfg, rng)
    novo_uso_disco = atualizar_disco(uso_disco_atual, cfg, rng)

    evento = EventoCFTV(
        ciclo=ciclo,
        timestamp=time_provider().strftime("%Y-%m-%d %H:%M:%S"),
        conectividade=conectividade,
        sinal_video=sinal_video,
        banda_mbps=round(banda, 2),
        uso_disco_pct=round(novo_uso_disco, 1),
    )
    return evento, novo_uso_disco


def simular_cftv(
    cfg: ConfiguracaoSimulador,
    *,
    time_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> list[EventoCFTV]:
    validar_configuracao(cfg)

    rng = random.Random(cfg.seed)
    if time_provider is None:
        time_provider = datetime.now
    if sleeper is None:
        sleeper = time.sleep

    print("Iniciando simulador do servidor de CFTV...")
    print("Pressione Ctrl+C para parar o script.\n")

    uso_disco = cfg.uso_disco_inicial
    ciclo_atual = 0
    eventos: list[EventoCFTV] = []

    try:
        while True:
            ciclo_atual += 1
            evento, uso_disco = gerar_evento(
                ciclo=ciclo_atual,
                uso_disco_atual=uso_disco,
                cfg=cfg,
                rng=rng,
                time_provider=time_provider,
            )
            eventos.append(evento)

            if cfg.formato_saida == "json":
                print(formatar_evento_json(evento))
            else:
                print(montar_linha_log(evento))

            if cfg.ciclos > 0 and ciclo_atual >= cfg.ciclos:
                print("\nSimulacao finalizada: numero de ciclos atingido.")
                break

            if not cfg.sem_sleep:
                sleeper(cfg.intervalo_segundos)

    except KeyboardInterrupt:
        print("\nSimulacao encerrada pelo usuario.")

    if cfg.exibir_resumo:
        imprimir_resumo(eventos)

    return eventos


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulador de servidor CFTV")
    parser.add_argument("--intervalo", type=float, default=5.0, help="Intervalo entre ciclos em segundos")
    parser.add_argument("--ciclos", type=inteiro_nao_negativo, default=0, help="Quantidade de ciclos (0 = infinito)")
    parser.add_argument("--chance-rede-online", type=float, default=0.90, help="Probabilidade da rede estar online")
    parser.add_argument(
        "--chance-video-ok",
        type=float,
        default=0.95,
        help="Probabilidade de video ok quando a rede esta online",
    )
    parser.add_argument("--uso-disco-inicial", type=float, default=50.0, help="Uso inicial de disco em porcentagem")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reproducao dos resultados")
    parser.add_argument(
        "--formato",
        type=str,
        default="texto",
        choices=["texto", "json"],
        help="Formato de saida no console",
    )
    parser.add_argument(
        "--sem-resumo",
        action="store_true",
        help="Nao exibe resumo final",
    )
    parser.add_argument(
        "--sem-sleep",
        action="store_true",
        help="Nao aguarda entre ciclos (util para testes)",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> ConfiguracaoSimulador:
    return ConfiguracaoSimulador(
        intervalo_segundos=args.intervalo,
        ciclos=args.ciclos,
        chance_rede_online=args.chance_rede_online,
        chance_video_ok_quando_online=args.chance_video_ok,
        uso_disco_inicial=args.uso_disco_inicial,
        seed=args.seed,
        formato_saida=args.formato,
        exibir_resumo=not args.sem_resumo,
        sem_sleep=args.sem_sleep,
    )


def main() -> None:
    parser = criar_parser()
    args = parser.parse_args()
    cfg = config_from_args(args)
    try:
        simular_cftv(cfg)
    except ValueError as exc:
        print(f"Erro de configuracao: {exc}")
        raise SystemExit(2)


if __name__ == "__main__":
    main()

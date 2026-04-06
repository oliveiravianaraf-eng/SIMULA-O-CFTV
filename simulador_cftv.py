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


PERFIS_CARGA = {"camera", "normal", "stress", "burst"}
FORMATOS_SAIDA = {"texto", "json", "top"}


@dataclass
class ConfiguracaoSimulador:
    intervalo_segundos: float = 5.0
    perfil_carga: str = "camera"
    chance_rede_online: float = 0.90
    chance_video_ok_quando_online: float = 0.95
    uso_disco_inicial: float = 50.0
    limite_sobrescrita_disco: float = 95.0
    uso_disco_retorno: float = 50.0
    incremento_disco_min: float = 0.1
    incremento_disco_max: float = 4.5
    banda_sem_video_min: float = 0.1
    banda_sem_video_max: float = 8.0
    banda_com_video_min: float = 2.5
    banda_com_video_max: float = 95.0
    req_por_seg_min: float = 12.0
    req_por_seg_max: float = 55.0
    cpu_base_min: float = 18.0
    cpu_base_max: float = 42.0
    mem_base_min: float = 28.0
    mem_base_max: float = 52.0
    ciclos: int = 0  # 0 = infinito
    seed: int | None = None
    formato_saida: str = "texto"  # texto|json|top
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
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    load1: float = 0.0
    load5: float = 0.0
    load15: float = 0.0
    req_por_seg: float = 0.0
    iowait_pct: float = 0.0
    fps: float = 0.0
    perda_frames_pct: float = 0.0
    processos_ativos: int = 0
    temperatura_c: float = 0.0


def clamp(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def parametros_por_perfil(perfil_carga: str) -> dict[str, float]:
    if perfil_carga == "burst":
        return {
            "banda_video_min": 28.0,
            "banda_video_max": 95.0,
            "banda_sem_video_min": 2.0,
            "banda_sem_video_max": 8.0,
            "req_por_seg_min": 800.0,
            "req_por_seg_max": 5000.0,
            "cpu_base_min": 55.0,
            "cpu_base_max": 90.0,
            "mem_base_min": 55.0,
            "mem_base_max": 92.0,
            "disco_inc_min": 1.5,
            "disco_inc_max": 4.5,
            "fps_min": 8.0,
            "fps_max": 15.0,
            "processos_min": 180.0,
            "processos_max": 620.0,
        }

    if perfil_carga == "stress":
        return {
            "banda_video_min": 15.0,
            "banda_video_max": 60.0,
            "banda_sem_video_min": 1.0,
            "banda_sem_video_max": 4.0,
            "req_por_seg_min": 180.0,
            "req_por_seg_max": 1200.0,
            "cpu_base_min": 42.0,
            "cpu_base_max": 78.0,
            "mem_base_min": 45.0,
            "mem_base_max": 82.0,
            "disco_inc_min": 0.8,
            "disco_inc_max": 2.4,
            "fps_min": 10.0,
            "fps_max": 22.0,
            "processos_min": 130.0,
            "processos_max": 360.0,
        }

    if perfil_carga == "normal":
        return {
            "banda_video_min": 3.5,
            "banda_video_max": 9.0,
            "banda_sem_video_min": 0.2,
            "banda_sem_video_max": 0.9,
            "req_por_seg_min": 18.0,
            "req_por_seg_max": 110.0,
            "cpu_base_min": 16.0,
            "cpu_base_max": 34.0,
            "mem_base_min": 25.0,
            "mem_base_max": 48.0,
            "disco_inc_min": 0.12,
            "disco_inc_max": 0.55,
            "fps_min": 18.0,
            "fps_max": 30.0,
            "processos_min": 80.0,
            "processos_max": 140.0,
        }

    return {
        "banda_video_min": 2.5,
        "banda_video_max": 4.5,
        "banda_sem_video_min": 0.1,
        "banda_sem_video_max": 0.3,
        "req_por_seg_min": 12.0,
        "req_por_seg_max": 55.0,
        "cpu_base_min": 18.0,
        "cpu_base_max": 42.0,
        "mem_base_min": 28.0,
        "mem_base_max": 52.0,
        "disco_inc_min": 0.1,
        "disco_inc_max": 0.5,
        "fps_min": 15.0,
        "fps_max": 25.0,
        "processos_min": 70.0,
        "processos_max": 120.0,
    }


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
    if cfg.perfil_carga not in PERFIS_CARGA:
        raise ValueError(f"perfil_carga deve ser um de {sorted(PERFIS_CARGA)}")

    validar_probabilidade(cfg.chance_rede_online, "chance_rede_online")
    validar_probabilidade(cfg.chance_video_ok_quando_online, "chance_video_ok_quando_online")

    validar_faixa(cfg.incremento_disco_min, cfg.incremento_disco_max, "incremento_disco")
    validar_faixa(cfg.banda_sem_video_min, cfg.banda_sem_video_max, "banda_sem_video")
    validar_faixa(cfg.banda_com_video_min, cfg.banda_com_video_max, "banda_com_video")

    if cfg.intervalo_segundos <= 0:
        raise ValueError("intervalo_segundos deve ser maior que 0")

    if cfg.ciclos < 0:
        raise ValueError("ciclos nao pode ser negativo")

    if cfg.formato_saida not in FORMATOS_SAIDA:
        raise ValueError("formato_saida deve ser 'texto', 'json' ou 'top'")

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
    perfil = parametros_por_perfil(cfg.perfil_carga)
    if conectividade == 0:
        return 0.0
    if sinal_video == 0:
        minimo = max(cfg.banda_sem_video_min, perfil["banda_sem_video_min"])
        maximo = max(minimo, min(cfg.banda_sem_video_max, perfil["banda_sem_video_max"]))
        return rng.uniform(minimo, maximo)
    minimo = max(cfg.banda_com_video_min, perfil["banda_video_min"])
    maximo = max(minimo, min(cfg.banda_com_video_max, perfil["banda_video_max"]))
    return rng.uniform(minimo, maximo)


def atualizar_disco(uso_atual: float, cfg: ConfiguracaoSimulador, rng: random.Random) -> float:
    perfil = parametros_por_perfil(cfg.perfil_carga)
    minimo = max(cfg.incremento_disco_min, perfil["disco_inc_min"])
    maximo = max(minimo, min(cfg.incremento_disco_max, perfil["disco_inc_max"]))
    uso_atual += rng.uniform(minimo, maximo)
    if uso_atual >= cfg.limite_sobrescrita_disco:
        return cfg.uso_disco_retorno
    return uso_atual


def gerar_metricas_sistema(
    cfg: ConfiguracaoSimulador,
    rng: random.Random,
    banda_mbps: float,
    uso_disco_pct: float,
    conectividade: int,
    sinal_video: int,
    req_por_seg: float,
    incremento_disco: float,
) -> dict[str, float | int]:
    perfil = parametros_por_perfil(cfg.perfil_carga)
    cpu_base = rng.uniform(cfg.cpu_base_min, cfg.cpu_base_max)
    mem_base = rng.uniform(cfg.mem_base_min, cfg.mem_base_max)

    if cfg.perfil_carga == "burst":
        cpu_sobracarga = 18.0
        mem_sobracarga = 14.0
    elif cfg.perfil_carga == "stress":
        cpu_sobracarga = 10.0
        mem_sobracarga = 8.0
    elif cfg.perfil_carga == "normal":
        cpu_sobracarga = 4.0
        mem_sobracarga = 3.0
    else:
        cpu_sobracarga = 6.0
        mem_sobracarga = 4.0

    cpu_pct = clamp(cpu_base + banda_mbps * 1.05 + req_por_seg * 0.02 + incremento_disco * 2.8 + cpu_sobracarga, 0, 100)
    mem_pct = clamp(mem_base + req_por_seg * 0.01 + incremento_disco * 1.5 + mem_sobracarga, 0, 100)

    iowait_pct = clamp(incremento_disco * 3.2 + (banda_mbps / 18.0) + (req_por_seg / 1600.0), 0, 100)
    load1 = round(clamp((cpu_pct / 24.0) + (req_por_seg / 350.0) + (iowait_pct / 18.0), 0, 99.0), 2)
    load5 = round(clamp(load1 * 0.84 + rng.uniform(0.0, 0.35), 0, 99.0), 2)
    load15 = round(clamp(load1 * 0.63 + rng.uniform(0.0, 0.25), 0, 99.0), 2)

    fps_min = perfil["fps_min"]
    fps_max = perfil["fps_max"]
    fps = rng.uniform(fps_min, fps_max)
    perda_frames = 0.0
    if cpu_pct > 85 or iowait_pct > 12 or sinal_video == 0:
        perda_frames = clamp((cpu_pct - 80) * 0.8 + iowait_pct * 1.2 + (0 if sinal_video else 18.0), 0, 100)
        fps = max(0.0, fps - perda_frames / 12.0)

    processos = int(rng.uniform(perfil["processos_min"], perfil["processos_max"]) + (req_por_seg / 25.0))
    temperatura = clamp(34.0 + cpu_pct * 0.32 + iowait_pct * 0.35 + rng.uniform(-1.2, 1.8), 0, 100)

    return {
        "cpu_pct": round(cpu_pct, 1),
        "mem_pct": round(mem_pct, 1),
        "load1": load1,
        "load5": load5,
        "load15": load15,
        "req_por_seg": round(req_por_seg, 1),
        "iowait_pct": round(iowait_pct, 1),
        "fps": round(fps, 1),
        "perda_frames_pct": round(perda_frames, 1),
        "processos_ativos": processos,
        "temperatura_c": round(temperatura, 1),
    }


def montar_linha_log(evento: EventoCFTV) -> str:
    status_rede_txt = "Online " if evento.conectividade else "Offline"
    status_video_txt = "OK       " if evento.sinal_video else "Sem Sinal"
    return (
        f"[{evento.timestamp}] [CFTV] Ciclo: {evento.ciclo:04d} | Rede: {status_rede_txt} | "
        f"Camera: {status_video_txt} | Banda: {evento.banda_mbps:.2f} Mbps | Disco: {evento.uso_disco_pct:.1f}% | "
        f"CPU: {evento.cpu_pct:.1f}% | RAM: {evento.mem_pct:.1f}% | REQ: {evento.req_por_seg:.1f}/s"
    )


def montar_saida_top(evento: EventoCFTV, uptime_segundos: float = 0.0) -> str:
    uptime_min = int(max(0, uptime_segundos) // 60)
    total = max(evento.processos_ativos, 1)
    running = 1 if evento.conectividade else 0
    zombie = 1 if evento.perda_frames_pct > 25 else 0
    sleeping = max(0, total - running - zombie)
    idle = clamp(100.0 - evento.cpu_pct, 0, 99.9)

    return (
        f"top - {evento.timestamp} up {uptime_min} min, 1 user, load average: {evento.load1:.2f}, {evento.load5:.2f}, {evento.load15:.2f}\n"
        f"Tasks: {total} total, {running} running, {sleeping} sleeping, 0 stopped, {zombie} zombie\n"
        f"%Cpu(s): {evento.cpu_pct:.1f} us, {evento.iowait_pct:.1f} wa, {idle:.1f} id, 0.0 hi, 0.0 si, 0.0 st\n"
        f"MiB Mem : {evento.mem_pct:.1f}% used | Disco: {evento.uso_disco_pct:.1f}% | Banda: {evento.banda_mbps:.2f} Mbps\n"
        f"MiB Swap: 0.0 total, 0.0 free, 0.0 used. {max(0.0, 100.0 - evento.mem_pct):.1f} avail Mem\n"
        f"{('camera-stream' if evento.conectividade else 'camera-offline'):>10}  {evento.cpu_pct:>5.1f}  {evento.mem_pct:>5.1f}  {evento.req_por_seg:>7.1f}  {evento.fps:>5.1f} fps"
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
            "cpu_media_pct": 0.0,
            "mem_media_pct": 0.0,
            "req_media_por_seg": 0.0,
            "temperatura_max_c": 0.0,
        }

    rede_online = sum(1 for e in eventos if e.conectividade == 1)
    camera_ok = sum(1 for e in eventos if e.sinal_video == 1)
    banda_media = sum(e.banda_mbps for e in eventos) / total
    disco_final = eventos[-1].uso_disco_pct
    cpu_media = sum(e.cpu_pct for e in eventos) / total
    mem_media = sum(e.mem_pct for e in eventos) / total
    req_media = sum(e.req_por_seg for e in eventos) / total
    temp_max = max(e.temperatura_c for e in eventos)

    return {
        "total_ciclos": total,
        "uptime_rede_pct": (rede_online / total) * 100,
        "camera_ok_pct": (camera_ok / total) * 100,
        "banda_media_mbps": banda_media,
        "disco_final_pct": disco_final,
        "cpu_media_pct": cpu_media,
        "mem_media_pct": mem_media,
        "req_media_por_seg": req_media,
        "temperatura_max_c": temp_max,
    }


def imprimir_resumo(eventos: list[EventoCFTV]) -> None:
    resumo = calcular_resumo(eventos)
    print("\nResumo da simulacao")
    print(f"- Total de ciclos: {int(resumo['total_ciclos'])}")
    print(f"- Uptime de rede: {resumo['uptime_rede_pct']:.1f}%")
    print(f"- Camera com video OK: {resumo['camera_ok_pct']:.1f}%")
    print(f"- Banda media: {resumo['banda_media_mbps']:.2f} Mbps")
    print(f"- Uso de disco final: {resumo['disco_final_pct']:.1f}%")
    print(f"- CPU media: {resumo['cpu_media_pct']:.1f}%")
    print(f"- RAM media: {resumo['mem_media_pct']:.1f}%")
    print(f"- Requisicoes media: {resumo['req_media_por_seg']:.1f}/s")
    print(f"- Temperatura max: {resumo['temperatura_max_c']:.1f} C")


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
    perfil = parametros_por_perfil(cfg.perfil_carga)
    req_por_seg = rng.uniform(perfil["req_por_seg_min"], perfil["req_por_seg_max"])
    if conectividade == 0:
        req_por_seg *= 0.18
    if sinal_video == 0:
        req_por_seg *= 0.55

    metricas_sistema = gerar_metricas_sistema(
        cfg=cfg,
        rng=rng,
        banda_mbps=banda,
        uso_disco_pct=novo_uso_disco,
        conectividade=conectividade,
        sinal_video=sinal_video,
        req_por_seg=req_por_seg,
        incremento_disco=novo_uso_disco - uso_disco_atual,
    )

    evento = EventoCFTV(
        ciclo=ciclo,
        timestamp=time_provider().strftime("%Y-%m-%d %H:%M:%S"),
        conectividade=conectividade,
        sinal_video=sinal_video,
        banda_mbps=round(banda, 2),
        uso_disco_pct=round(novo_uso_disco, 1),
        cpu_pct=metricas_sistema["cpu_pct"],
        mem_pct=metricas_sistema["mem_pct"],
        load1=metricas_sistema["load1"],
        load5=metricas_sistema["load5"],
        load15=metricas_sistema["load15"],
        req_por_seg=metricas_sistema["req_por_seg"],
        iowait_pct=metricas_sistema["iowait_pct"],
        fps=metricas_sistema["fps"],
        perda_frames_pct=metricas_sistema["perda_frames_pct"],
        processos_ativos=metricas_sistema["processos_ativos"],
        temperatura_c=metricas_sistema["temperatura_c"],
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
            elif cfg.formato_saida == "top":
                print(montar_saida_top(evento, uptime_segundos=ciclo_atual * cfg.intervalo_segundos))
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
    parser.add_argument(
        "--perfil-carga",
        type=str,
        default="camera",
        choices=sorted(PERFIS_CARGA),
        help="Perfil de carga da simulacao",
    )
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
        choices=sorted(FORMATOS_SAIDA),
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
        perfil_carga=args.perfil_carga,
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

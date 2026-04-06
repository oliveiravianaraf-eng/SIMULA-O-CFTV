import json
import unittest

from simulador_cftv import (
    ConfiguracaoSimulador,
    EventoCFTV,
    atualizar_disco,
    calcular_banda,
    calcular_resumo,
    formatar_evento_json,
    gerar_evento,
    montar_saida_top,
    simular_cftv,
    validar_configuracao,
)


class TestSimuladorCFTV(unittest.TestCase):
    def test_validar_configuracao_probabilidade_invalida(self) -> None:
        cfg = ConfiguracaoSimulador(chance_rede_online=1.2)
        with self.assertRaises(ValueError):
            validar_configuracao(cfg)

    def test_calcular_banda_offline_deve_ser_zero(self) -> None:
        cfg = ConfiguracaoSimulador()
        rng_seed = 123
        import random

        rng = random.Random(rng_seed)
        banda = calcular_banda(conectividade=0, sinal_video=0, cfg=cfg, rng=rng)
        self.assertEqual(banda, 0.0)

    def test_atualizar_disco_deve_reiniciar_no_limite(self) -> None:
        cfg = ConfiguracaoSimulador(
            limite_sobrescrita_disco=95.0,
            uso_disco_retorno=50.0,
            incremento_disco_min=1.0,
            incremento_disco_max=1.0,
        )
        import random

        rng = random.Random(10)
        novo_uso = atualizar_disco(uso_atual=94.5, cfg=cfg, rng=rng)
        self.assertEqual(novo_uso, 50.0)

    def test_formato_evento_json_valido(self) -> None:
        evento = EventoCFTV(
            ciclo=1,
            timestamp="2026-03-19 10:00:00",
            conectividade=1,
            sinal_video=1,
            banda_mbps=3.2,
            uso_disco_pct=50.4,
        )
        payload = json.loads(formatar_evento_json(evento))
        self.assertEqual(payload["ciclo"], 1)
        self.assertEqual(payload["conectividade"], 1)
        self.assertEqual(payload["sinal_video"], 1)

    def test_simulacao_reprodutivel_com_seed(self) -> None:
        cfg1 = ConfiguracaoSimulador(ciclos=8, seed=42, sem_sleep=True, exibir_resumo=False)
        cfg2 = ConfiguracaoSimulador(ciclos=8, seed=42, sem_sleep=True, exibir_resumo=False)

        eventos_1 = simular_cftv(cfg1)
        eventos_2 = simular_cftv(cfg2)

        assinaturas_1 = [
            (e.ciclo, e.conectividade, e.sinal_video, e.banda_mbps, e.uso_disco_pct)
            for e in eventos_1
        ]
        assinaturas_2 = [
            (e.ciclo, e.conectividade, e.sinal_video, e.banda_mbps, e.uso_disco_pct)
            for e in eventos_2
        ]

        self.assertEqual(assinaturas_1, assinaturas_2)

    def test_calcular_resumo_sem_eventos(self) -> None:
        resumo = calcular_resumo([])
        self.assertEqual(resumo["total_ciclos"], 0)
        self.assertEqual(resumo["uptime_rede_pct"], 0.0)
        self.assertEqual(resumo["camera_ok_pct"], 0.0)

    def test_perfil_burst_gera_banda_alta(self) -> None:
        import random
        from datetime import datetime

        cfg = ConfiguracaoSimulador(
            perfil_carga="burst",
            chance_rede_online=1.0,
            chance_video_ok_quando_online=1.0,
            seed=7,
            sem_sleep=True,
            exibir_resumo=False,
        )
        rng = random.Random(cfg.seed)
        evento, _ = gerar_evento(
            ciclo=1,
            uso_disco_atual=50.0,
            cfg=cfg,
            rng=rng,
            time_provider=datetime.now,
        )

        self.assertGreaterEqual(evento.banda_mbps, 28.0)
        self.assertGreaterEqual(evento.cpu_pct, 55.0)
        self.assertGreaterEqual(evento.req_por_seg, 800.0)

    def test_saida_top_contem_metricas_principais(self) -> None:
        evento = EventoCFTV(
            ciclo=1,
            timestamp="2026-04-06 12:00:00",
            conectividade=1,
            sinal_video=1,
            banda_mbps=41.5,
            uso_disco_pct=84.0,
            cpu_pct=88.2,
            mem_pct=77.1,
            load1=4.3,
            load5=3.8,
            load15=3.1,
            req_por_seg=1422.0,
            iowait_pct=11.4,
            fps=11.2,
            perda_frames_pct=7.5,
            processos_ativos=318,
            temperatura_c=79.4,
        )

        saida = montar_saida_top(evento, uptime_segundos=3600)
        self.assertIn("load average", saida)
        self.assertIn("%Cpu(s)", saida)
        self.assertIn("camera-stream", saida)


if __name__ == "__main__":
    unittest.main()

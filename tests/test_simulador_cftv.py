import json
import unittest

from simulador_cftv import (
    ConfiguracaoSimulador,
    EventoCFTV,
    atualizar_disco,
    calcular_banda,
    calcular_resumo,
    formatar_evento_json,
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


if __name__ == "__main__":
    unittest.main()

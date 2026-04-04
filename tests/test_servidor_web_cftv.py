import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from servidor_web_cftv import CFTVRequestHandler
from servidor_web_cftv import EstadoSimulacao
from simulador_cftv import ConfiguracaoSimulador


class TestServidorWebCFTV(unittest.TestCase):
    def setUp(self) -> None:
        cfg = ConfiguracaoSimulador(intervalo_segundos=0.1, ciclos=1, sem_sleep=True, exibir_resumo=False)
        self.estado = EstadoSimulacao(cfg)
        self.estado.gerar_proximo_evento()

        handler_class = type("TestCFTVHandler", (CFTVRequestHandler,), {"estado": self.estado})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

        self.server_thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        self.server_thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)

    def test_rota_status_retorna_payload(self) -> None:
        with urlopen(f"{self.base_url}/api/status?source=test", timeout=2) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))

        self.assertIn("evento", payload)
        self.assertIn("resumo", payload)
        self.assertIn("conectividade", payload["evento"])

    def test_rota_healthz_retorna_ok(self) -> None:
        with urlopen(f"{self.base_url}/healthz", timeout=2) as response:
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload["status"], "ok")
        self.assertIn("timestamp", payload)

    def test_rota_index_retorna_html(self) -> None:
        with urlopen(f"{self.base_url}/", timeout=2) as response:
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")

        self.assertIn("<title>CFTV Painel Operacional</title>", body)

    def test_rota_inexistente_retorna_404(self) -> None:
        with self.assertRaises(HTTPError) as context:
            urlopen(f"{self.base_url}/nao-existe", timeout=2)

        self.assertEqual(context.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

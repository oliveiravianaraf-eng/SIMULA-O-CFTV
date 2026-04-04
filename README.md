# SIMULA-O-CFTV

Simulador de servidor de CFTV para testes de monitoramento (ex.: Zabbix, Grafana, Prometheus ou scripts proprios).

Agora o projeto tambem inclui um painel web profissional com tema azul e atualizacao em tempo real.

## O que foi melhorado

- Codigo modular (funcoes separadas por responsabilidade)
- Parametros configuraveis por linha de comando
- Validacao de configuracao para evitar valores invalidos
- Saida com timestamp para facilitar analise de eventos
- Saida estruturada em JSON (`--formato json`)
- Resumo estatistico no final da simulacao
- Modo de execucao finita (`--ciclos`) para testes automatizados
- Reproducao de cenarios com seed fixa (`--seed`)

## Como executar

### Local (dev)

```bash
python simulador_cftv.py
```

### Docker (prod/lab)

```bash
docker-compose up --build
```

Ou manualmente:

```bash
docker build -t cftv-dashboard .
docker run -p 8080:8080 -e LOG_LEVEL=INFO cftv-dashboard
```

## Painel web profissional (azul)

Iniciar servidor web do painel:

```bash
python servidor_web_cftv.py --host 0.0.0.0 --port 8080
```

Abrir no navegador:

```text
http://SEU_IP_DA_VM:8080
```

Saude da aplicacao (para monitoramento):

```text
http://SEU_IP_DA_VM:8080/healthz
```

Exemplo com ambiente instavel:

```bash
python servidor_web_cftv.py --host 0.0.0.0 --port 8080 --chance-rede-online 0.75 --chance-video-ok 0.85 --intervalo 1
```

## Exemplos

Rodar 10 ciclos com 1 segundo de intervalo:

```bash
python simulador_cftv.py --ciclos 10 --intervalo 1
```

Rodar com seed fixa (resultado reproduzivel):

```bash
python simulador_cftv.py --seed 42 --ciclos 20
```

Simular ambiente mais instavel de rede:

```bash
python simulador_cftv.py --chance-rede-online 0.75 --chance-video-ok 0.85
```

Saida em JSON (boa para ingestao por log pipeline):

```bash
python simulador_cftv.py --ciclos 5 --sem-sleep --formato json
```

## Parametros principais

### Simulador

- `--intervalo`: intervalo entre ciclos em segundos (padrao: 5)
- `--ciclos`: quantidade de ciclos (padrao: 0 = infinito)
- `--chance-rede-online`: probabilidade da rede estar online (0 a 1, padrao: 0.90)
- `--chance-video-ok`: probabilidade de video OK quando a rede esta online (0 a 1, padrao: 0.95)
- `--uso-disco-inicial`: uso inicial de disco em % (padrao: 50)
- `--seed`: seed para reproducao da simulacao
- `--formato`: formato de saida (`texto` ou `json`)
- `--sem-resumo`: desabilita o resumo estatistico ao fim
- `--sem-sleep`: nao espera entre ciclos (util para testes)

### Servidor web

- `--host` (env: `HOST`): bind address (padrao: 0.0.0.0)
- `--port` (env: `PORT`): porta HTTP (padrao: 8080)
- `--intervalo` (env: `INTERVAL`): ciclo de atualizacao em segundos (padrao: 2.0)

### Logging

- `LOG_LEVEL` (env var): DEBUG, INFO, WARNING, ERROR (padrao: INFO)

## Testes automatizados

Executar todos os testes:

```bash
python -m unittest discover -s tests -v
```

## Executar na VM Ubuntu

1. Atualize pacotes e instale Python:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

2. Clone e entre no projeto:

```bash
git clone <URL_DO_REPOSITORIO>
cd SIMULA-O-CFTV
```

3. (Opcional) Crie ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

4. Rode os testes:

```bash
python3 -m unittest discover -s tests -v
```

5. Suba o painel:

```bash
python3 servidor_web_cftv.py --host 0.0.0.0 --port 8080
```

6. Se houver firewall ativo na VM:

```bash
sudo ufw allow 8080/tcp
```

## Rodar como servico (systemd)

1. Copie o arquivo `deploy/systemd/cftv-dashboard.service` para `/etc/systemd/system/`.
2. Ajuste `WorkingDirectory` e `ExecStart` para o caminho real na VM.
3. Execute:

```bash
sudo systemctl daemon-reload
sudo systemctl enable cftv-dashboard
sudo systemctl start cftv-dashboard
sudo systemctl status cftv-dashboard
```

## Endpoints disponiveis

- `GET /` - Painel de dashboard
- `GET /api/status` - Status atual (JSON)
- `GET /healthz` - Health check com uptime (JSON)
- `GET /metrics` - Metricas Prometheus (text/plain)
- `GET /styles.css` - CSS do painel
- `GET /app.js` - JavaScript do painel

## Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto (baseado em `.env.example`):

```bash
cp .env.example .env
# Edite conforme necessario
```

## Logs estruturados

Os logs sao emitidos em formato texto estruturado com timestamp ISO.
Para debug detalhado, use:

```bash
LOG_LEVEL=DEBUG python servidor_web_cftv.py
```

Todos os eventos HTTP sao registrados automaticamente.

## Integracao pratica com Zabbix

Itens iniciais recomendados:

- HTTP Agent: `http://<IP_VM>:8080/healthz` (check saude + uptime)
- HTTP Agent: `http://<IP_VM>:8080/api/status` (dados principais)
- HTTP Agent: `http://<IP_VM>:8080/metrics` (Prometheus format para Grafana)
- Dependent items (JSONPath) do `/api/status`:
	- `$.evento.conectividade`
	- `$.evento.sinal_video`
	- `$.evento.banda_mbps`
	- `$.evento.uso_disco_pct`
	- `$.resumo.uptime_rede_pct`
	- `$.resumo.camera_ok_pct`
	- `$.resumo.banda_media_mbps`

Triggers uteis:

- Health endpoint indisponivel por 1 minuto
- Conectividade (`evento.conectividade`) igual a 0 por 3 coletas
- Camera sem sinal (`evento.sinal_video`) por 3 coletas
- Uso de disco acima de 90%

Veja tambem: `zabbix/cftv-zabbix-items.md`.
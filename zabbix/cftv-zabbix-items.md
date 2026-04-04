# CFTV + Zabbix (Pratico)

## Itens HTTP Agent

- Name: `CFTV healthz`
- Type: HTTP agent
- Key: `cftv.healthz.raw`
- URL: `http://{HOST.CONN}:8080/healthz`
- Update interval: `30s`

- Name: `CFTV status raw`
- Type: HTTP agent
- Key: `cftv.status.raw`
- URL: `http://{HOST.CONN}:8080/api/status`
- Update interval: `30s`

## Dependent items (JSONPath)

- Name: `CFTV conectividade`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.evento.conectividade`
- JSONPath: `$.evento.conectividade`

- Name: `CFTV sinal video`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.evento.sinal_video`
- JSONPath: `$.evento.sinal_video`

- Name: `CFTV banda atual`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.evento.banda_mbps`
- JSONPath: `$.evento.banda_mbps`

- Name: `CFTV disco atual`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.evento.uso_disco_pct`
- JSONPath: `$.evento.uso_disco_pct`

- Name: `CFTV uptime rede`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.resumo.uptime_rede_pct`
- JSONPath: `$.resumo.uptime_rede_pct`

- Name: `CFTV camera ok pct`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.resumo.camera_ok_pct`
- JSONPath: `$.resumo.camera_ok_pct`

- Name: `CFTV banda media`
- Type: Dependent item
- Master item: `cftv.status.raw`
- Key: `cftv.resumo.banda_media_mbps`
- JSONPath: `$.resumo.banda_media_mbps`

## Triggers sugeridos

- `CFTV health endpoint offline`
- Expression: `max(/HOST/cftv.healthz.raw,#2)=0`

- `CFTV rede offline`
- Expression: `max(/HOST/cftv.evento.conectividade,#3)=0`

- `CFTV camera sem sinal`
- Expression: `max(/HOST/cftv.evento.sinal_video,#3)=0`

- `CFTV disco alto`
- Expression: `last(/HOST/cftv.evento.uso_disco_pct)>90`

## Dica operacional

Use `zabbix-agent2` na VM para monitorar CPU, RAM, disco e processo, e combine com os itens HTTP acima para visao de aplicacao.

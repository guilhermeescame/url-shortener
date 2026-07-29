# URL Shortener

🇺🇸 [English version](README.md)

Encurtador de URLs em microserviços, empacotado para rodar em Kubernetes com
entrega contínua via GitOps.

## Arquitetura

```
navegador ──► frontend (nginx) ──► api (FastAPI) ──► redis
                proxy /api e /r      encurta e         armazena
                                     redireciona       os links
```

| Serviço  | Stack           | Responsabilidade                    |
|----------|-----------------|-------------------------------------|
| frontend | nginx, HTML/JS  | Interface web e proxy reverso       |
| api      | Python, FastAPI | Encurtamento e redirecionamento     |
| redis    | Redis 7         | Persistência dos pares código → URL |

## Executando localmente

Requer Docker.

```bash
docker compose up --build
```

A aplicação fica disponível em **http://localhost:8080**.

## Executando no Kubernetes (kind)

Requer [kind](https://kind.sigs.k8s.io/) e `kubectl`.

```bash
# Cluster com as portas 80/443 mapeadas para localhost, mais o ingress controller
kind create cluster --name url-shortener --config kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=120s

# Buildar as imagens e carregá-las no cluster
docker build -t url-shortener-api:0.1.0 ./api
docker build -t url-shortener-frontend:0.1.0 ./frontend
kind load docker-image url-shortener-api:0.1.0 --name url-shortener
kind load docker-image url-shortener-frontend:0.1.0 --name url-shortener

kubectl apply -f k8s/
```

A aplicação fica disponível em **http://localhost**. O Ingress roteia `/api` e
`/r` direto para o serviço da API; todo o resto vai para o frontend.

## API

| Método | Rota                | Descrição                          |
|--------|---------------------|------------------------------------|
| `POST` | `/api/shorten`      | Encurta uma URL                    |
| `GET`  | `/r/{code}`         | Redireciona para a URL original    |
| `GET`  | `/api/stats/{code}` | Número de acessos do código        |
| `GET`  | `/healthz`          | Health check com checagem do Redis |

`/healthz` é exposto apenas na porta interna da API (`8000`), consumido pelo
healthcheck do Compose e pelas probes do Kubernetes.

```bash
curl -X POST http://localhost:8080/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://kubernetes.io/docs/tutorials/"}'
```

```json
{ "code": "aB3xY9", "short_url": "/r/aB3xY9" }
```

Documentação interativa em `http://localhost:8080/api/docs`.

## Decisões técnicas

**Proxy reverso no frontend.** O nginx encaminha `/api` e `/r` para a API,
mantendo tudo na mesma origem. Elimina configuração de CORS e espelha o
comportamento do Ingress no Kubernetes.

**Configuração por variável de ambiente.** O endereço do Redis vem de
`REDIS_HOST`, sem endpoint fixo no código — a mesma imagem roda em Compose,
Kubernetes ou apontando para um Redis gerenciado.

**Health check dedicado.** `/healthz` valida a conectividade com o Redis e serve
tanto ao healthcheck do Compose quanto às probes de liveness e readiness do
Kubernetes.

**Códigos gerados com `secrets`.** IDs aleatórios de 6 caracteres em vez de
sequenciais, evitando enumeração dos links encurtados. A gravação usa `SET NX`
para garantir atomicidade contra colisões.

**Container sem privilégios.** A API roda como usuário não-root, requisito comum
de políticas de segurança em clusters.

**Probes de liveness e readiness com escopos diferentes.** A readiness bate no
`/healthz`, que checa o Redis: um pod da API sem seu armazenamento sai da
rotação do Service e não recebe tráfego. A liveness checa só a porta TCP — se
também dependesse do Redis, uma queda dele viraria um loop de restart em cascata
de todos os pods da API, sem consertar nada.

**Redis como StatefulSet.** Identidade estável de pod e um PersistentVolumeClaim
por réplica preservam os dados entre restarts; Deployments ficam reservados aos
serviços sem estado.

**Logs estruturados em JSON no stdout.** A API emite um objeto JSON por evento —
access logs com latência, eventos de domínio, erros — seguindo o princípio
twelve-factor de tratar logs como fluxo de eventos. `docker logs` (e depois
`kubectl logs` e Loki) consomem sem gambiarras de parsing. Requests de health
check ficam fora do fluxo para não virar ruído de probe, e apenas o host de
destino das URLs é logado, nunca query strings completas. O Compose limita o
driver json-file a 3 × 10 MB por container.

**Limites de recursos em todos os serviços.** Limites de CPU e memória espelham
os `resources.limits/requests` do Kubernetes. O Redis roda com `maxmemory`
abaixo do limite do container e política `noeviction` — degrada com erro claro
em vez de sofrer OOM kill ou despejar links encurtados silenciosamente.

## Roadmap

- [x] Containerização e orquestração local com Docker Compose
- [x] Deploy em Kubernetes: Deployments, Services, Ingress e probes
- [ ] Empacotamento com Helm e configuração por ambiente
- [ ] Pipeline de build e publicação de imagens com GitHub Actions
- [ ] Entrega contínua declarativa com ArgoCD
- [ ] Métricas e dashboards com Prometheus e Grafana

## Licença

[MIT](LICENSE)

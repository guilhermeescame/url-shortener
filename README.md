# URL Shortener

🇧🇷 [Versão em português](README.pt-BR.md)

A microservices URL shortener, packaged to run on Kubernetes with continuous
delivery via GitOps.

## Architecture

```
browser ──► frontend (nginx) ──► api (FastAPI) ──► redis
              proxies /api and /r    shortens and      stores
                                     redirects         the links
```

| Service  | Stack           | Responsibility                     |
|----------|-----------------|-------------------------------------|
| frontend | nginx, HTML/JS  | Web UI and reverse proxy            |
| api      | Python, FastAPI | Shortening and redirecting          |
| redis    | Redis 7         | Persistence of code → URL pairs     |

## Running locally

Requires Docker.

```bash
docker compose up --build
```

The application is available at **http://localhost:8080**.

## API

| Method | Route               | Description                        |
|--------|---------------------|------------------------------------|
| `POST` | `/api/shorten`      | Shorten a URL                      |
| `GET`  | `/r/{code}`         | Redirect to the original URL       |
| `GET`  | `/api/stats/{code}` | Hit count for a short code         |
| `GET`  | `/healthz`          | Health check with Redis connectivity |

`/healthz` is exposed only on the API's internal port (`8000`), consumed by the
Compose healthcheck and by Kubernetes probes.

```bash
curl -X POST http://localhost:8080/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://kubernetes.io/docs/tutorials/"}'
```

```json
{ "code": "aB3xY9", "short_url": "/r/aB3xY9" }
```

Interactive documentation at `http://localhost:8080/api/docs`.

## Design decisions

**Reverse proxy in the frontend.** Nginx forwards `/api` and `/r` to the API,
keeping everything same-origin. This eliminates CORS configuration and mirrors
the role of an Ingress on Kubernetes.

**Configuration via environment variables.** The Redis address comes from
`REDIS_HOST`, with no hardcoded endpoint — the same image runs on Compose,
Kubernetes, or against a managed Redis.

**Dedicated health check.** `/healthz` validates Redis connectivity and serves
both the Compose healthcheck and Kubernetes liveness/readiness probes.

**Codes generated with `secrets`.** Random 6-character IDs instead of sequential
ones, preventing enumeration of shortened links. Writes use `SET NX` for
atomicity against collisions.

**Unprivileged container.** The API runs as a non-root user, a common
requirement of cluster security policies.

**Structured JSON logs to stdout.** The API emits one JSON object per event —
access logs with latency, domain events, errors — following the twelve-factor
principle of treating logs as an event stream. `docker logs` (and later
`kubectl logs` and Loki) consume them without parsing hacks. Health check
requests are excluded to keep the stream free of probe noise, and only the
target host of shortened URLs is logged, never full query strings. Compose
caps the json-file driver at 3 × 10 MB per container.

**Resource constraints on every service.** CPU and memory limits mirror
Kubernetes `resources.limits/requests`. Redis runs with `maxmemory` below its
container limit and `noeviction` policy — it degrades with a clear error
instead of being OOM-killed or silently evicting shortened links.

## Roadmap

- [x] Containerization and local orchestration with Docker Compose
- [ ] Kubernetes deployment: Deployments, Services, Ingress, and probes
- [ ] Helm packaging with per-environment configuration
- [ ] Image build and publish pipeline with GitHub Actions
- [ ] Declarative continuous delivery with ArgoCD
- [ ] Metrics and dashboards with Prometheus and Grafana

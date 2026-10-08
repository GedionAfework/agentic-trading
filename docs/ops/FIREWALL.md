# Firewall and private bind

## Required posture
| Service | Public internet | Bind |
|---------|-----------------|------|
| Nginx :443 | Yes (API only) | 0.0.0.0 |
| API uvicorn | No (nginx upstream) | 127.0.0.1:8000 |
| Postgres | No | 127.0.0.1:5433 |
| Redis | No | 127.0.0.1:6380 |
| Object storage | No | 127.0.0.1:9000 |
| Ollama | No | 127.0.0.1:11434 |
| Prometheus/Grafana | No (admin VPN/SSH tunnel) | 127.0.0.1 |

## Compose
```bash
docker compose -f infra/docker/docker-compose.yml \
  -f infra/docker/docker-compose.prod.yml up -d
```

## Scan
```bash
./scripts/exposure_scan.sh
```

## Host firewall (example ufw)
```bash
ufw default deny incoming
ufw allow OpenSSH
ufw allow 443/tcp
ufw enable
```

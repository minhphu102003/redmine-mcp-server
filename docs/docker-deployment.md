# Docker & VPS Deployment

Run the server locally with Docker, or deploy it hardened on a VPS behind Caddy (HTTPS). For the 5-minute version, see the [README](../README.md#quick-start--5-minutes).

## 1. Run locally with Docker

**Prerequisites:** Docker Desktop (or Engine) running.

```bash
cp .env.example .env.docker
```

Edit `.env.docker` — minimum for local use:

```bash
REDMINE_URL=https://redmine.yourcompany.com
REDMINE_API_KEY=your_api_key
```

Start:

```bash
docker compose up --build -d
curl http://localhost:8000/health
```

Or run the image directly:

```bash
docker build -t redmine-mcp-server .
docker run -p 8000:8000 --env-file .env.docker redmine-mcp-server
# alternative helper script: ./deploy.sh
```

Useful day-to-day commands:

```bash
docker compose logs -f redmine-mcp-server   # follow logs
docker compose ps                            # container + health status
docker compose up --build -d                 # rebuild after git pull
docker compose down                          # stop (data in ./data and ./logs is kept)
```

Notes:
- `./data` (memory store) and `./logs` are bind-mounted, so they survive restarts.
- `./credentials` is mounted read-only for Google Sheets service-account keys.
- The local compose publishes port `8000` — fine on your machine, never expose it directly on a VPS (use §2 instead).

## 2. Deploy on a VPS (hardened, HTTPS via Caddy)

**Prerequisites:**
- A VPS with Docker + Docker Compose plugin.
- A domain (e.g. `mcp.example.com`) whose DNS `A` record points to the VPS (Caddy gets Let's Encrypt certificates automatically).
- Firewall allowing only `22` (SSH), `80`, `443`. Never expose app port `8000` or the Docker API publicly. SSH keys only, no password login.

### Step 1 — Configure environment

```bash
cp .env.docker.vps.example .env.docker
```

Edit `.env.docker` for public use:

```bash
REDMINE_AUTH_MODE=dynamic          # or oauth — never legacy on public hosts
REDMINE_MCP_READ_ONLY=true         # recommended for boss/manager machines
PUBLIC_BASE_URL=https://mcp.example.com
PUBLIC_HOST=mcp.example.com
```

### Step 2 — Point Caddy at your domain

Edit `deploy/caddy/Caddyfile`: replace `mcp.example.com` with your domain. It already proxies only `/mcp`, `/health`, `/files/*`, blocks probe paths (`/.env`, `/.git`, `/wp-*`, ...), and writes JSON access logs.

### Step 3 — Launch

```bash
docker compose -f docker-compose.vps.yml up --build -d
```

The VPS stack differs from local: the app is **not** port-published (only Caddy binds 80/443), runs read-only with dropped capabilities, memory/CPU/pid limits, and an internal-only backend network.

### Step 4 — Verify

```bash
curl -I https://mcp.example.com/health        # 200 over HTTPS
docker ps --format "table {{.Names}}\t{{.Ports}}"   # :8000 must NOT appear
docker compose -f docker-compose.vps.yml ps   # both containers healthy
```

Then point your agent at `https://mcp.example.com/mcp` (see [integrations](./integrations.md)).

### Updating

```bash
git pull
docker compose -f docker-compose.vps.yml up --build -d
```

### Troubleshooting

| Symptom | Check |
|---|---|
| `curl /health` fails locally | `docker compose logs redmine-mcp-server`; is `.env.docker` set? |
| HTTPS never issues on VPS | DNS `A` record → VPS? ports 80/443 reachable? `docker logs redmine-mcp-caddy` |
| 401 `missing_configuration` | `dynamic` mode requires `X-Redmine-URL` + `X-Redmine-API-Key` headers per request |
| 403 on Redmine calls | `REDMINE_ALLOWED_HOSTS` allowlist, or Redmine blocking the VPS IP |
| High CPU / strange containers | See incident response in the security skill (`.agents/private/skills/security.md`): isolate, inspect, rotate keys, rebuild clean |

Security baseline (SSH hardening, fail2ban, no public Docker API) lives in the security skill — apply it before opening the VPS to the internet.

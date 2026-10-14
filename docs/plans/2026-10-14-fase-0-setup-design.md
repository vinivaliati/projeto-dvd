# Fase 0: Setup (design)

- **Data:** 2026-10-14
- **Branch:** `feat/fase-0-setup`
- **Status:** revisado pelos agentes `tech-lead-midia`, `qa`, `revisor-codigo` e `organizador`;
  aguardando aprovação do Vini.

## Objetivo

Deixar o esqueleto do repositório pronto, com qualidade de portfólio, para as próximas fases
começarem direto no domínio. A fase está pronta quando:

1. `docker compose up` sobe o serviço `web` e `http://localhost:8000/` mostra a página "hello";
2. `http://localhost:8000/health` responde 200 com as versões de `ffmpeg`, `ffprobe`,
   `dvdauthor`, `spumux`, `tsMuxeR` e `xorriso` encontradas no container;
3. o CI no GitHub Actions fica verde no PR `feat/fase-0-setup` para `main` (lint, tipos, testes
   com cobertura mínima e smoke test via `docker compose`);
4. `make lint`, `make test`, `make format` e `make dev` funcionam e estão documentados no README.

## Fora de escopo (vai para a fase que precisa)

| Item | Fase | Motivo |
|---|---|---|
| `config.py` (pydantic-settings) e as variáveis do app (`MEDIA_ROOTS`, `WORK_DIR`...) | 1 | Na Fase 0 nenhum código lê configuração. O compose já monta os volumes. |
| SQLite, SQLModel, Alembic, volume `data` | 1 | Ainda não há dados para guardar. |
| Tailwind e a pasta `api/` | 1 | Só existem duas rotas e uma página. |
| Serviço `worker` no compose | 3 | Sem job para processar, o worker seria código morto. Ajusta a seção 6.2 do `CLAUDE.md`. |
| Fontes no container (`spumux` e PGS do tsMuxeR) | 4 e 6 | Só necessárias para legendas. |
| Soft pulldown (`mjpegtools` ou pós-processamento) | 3 | Decisão de mídia da Fase 3. |
| Pastas vazias dos módulos (`library/`, `encode/`...) | cada uma na sua fase | Pasta vazia não comunica nada. |
| Variáveis e atribuição do TMDB | 2 | O TMDB só entra na Fase 2. |

## Decisões

### Imagem Docker

- Base `python:3.12.x-slim-trixie` fixada por **digest** (`@sha256:...`). Debian 13, com ffmpeg 7.1
  (o bookworm está no 5.1). Confirmado pelo `tech-lead-midia` no container: libx264, mpeg2video,
  ac3, pcm_s16be/s24be, zscale e tonemap presentes.
- Pacotes apt com **versão fixada** (ex: `ffmpeg=7:7.1.5-0+deb13u1`), numa lista única ordenada,
  com `--no-install-recommends`: `ffmpeg`, `dvdauthor` (inclui o `spumux`) e `xorriso`. Quando o
  Debian publicar uma correção, o build quebra. Isso é intencional: a atualização passa a ser uma
  decisão consciente, registrada em commit.
- `tsMuxeR` **2.7.0** (release estável de 2025-04-21, mais nova que as nightlies):
  - URL: `https://github.com/justdan96/tsMuxer/releases/download/2.7.0/tsMuxer-2.7.0-linux.zip`
  - sha256 do zip: `ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987`
  - binário estático (sem dependência de glibc), extraído com `python -I -m zipfile -e` (sem
    instalar `unzip`) para `/usr/local/bin/tsMuxeR`.
  - Só existe para x86-64. Guardar uma cópia do zip fora do GitHub (o projeto tem pouca
    atividade): registrar como tarefa no README, seção de manutenção.
- uv copiado de `ghcr.io/astral-sh/uv:<versão fixa>`; dependências com `uv sync --frozen --no-dev`.
- Usuário não root `app` com **UID/GID 1000** (build args `UID`/`GID`), igual ao usuário padrão do
  WSL, para os arquivos gerados em `/work` e `/output` pertencerem ao Vini. Com `HOME` real
  (`/home/app`), que o `spumux` vai usar para fontes na Fase 4.
- `HEALTHCHECK` via `python -c "import urllib.request; ..."` (a imagem slim não tem `curl`).

### Variáveis e volumes

O compose precisa do caminho **no host**; o app (a partir da Fase 1) usa o caminho **no
container**. São variáveis diferentes. Isso estende a seção 6.1 do `CLAUDE.md`.

| Variável (`.env`) | Exemplo | Montada em | Modo |
|---|---|---|---|
| `HOST_MEDIA_DIR` | `/mnt/e/Filmes` | `/media` | `ro` |
| `HOST_WORK_DIR` | `/home/vinivaliati/projeto-dvd-work` (ext4, **nunca** `/mnt/c`) | `/work` | rw |
| `HOST_OUTPUT_DIR` | `/mnt/c/Users/vinivaliati/Videos/projeto-dvd` | `/output` | rw |

- Um HD por enquanto. Para mais de um, adicionar outra linha de volume (documentado no
  `.env.example`).
- Porta publicada só em `127.0.0.1:8000:8000`: o app não tem autenticação e enxerga o HD.

### Aplicação

```
src/projeto_dvd/
  __init__.py
  app.py              # FastAPI: GET / e GET /health
  tools.py            # comandos de versão, parser e detecção das ferramentas de mídia
  web/templates/
    index.html        # página hello (Jinja)
tests/
  fixtures/tool_versions/   # saída real de cada ferramenta, capturada da imagem
  unit/
    test_tools.py
    test_app.py
```

- Templates já em `web/templates/`, como na seção 7, para não mover arquivo na Fase 1.
- `app.py` fica na raiz do pacote; a pasta `api/` nasce na Fase 1, quando houver mais rotas.

**Detecção de versões (`tools.py`)**, com comandos medidos no container pelo `tech-lead-midia`:

| Ferramenta | Comando | Código de saída | Saída | Regex |
|---|---|---|---|---|
| ffmpeg | `ffmpeg -version` | 0 | stdout | `ffmpeg version (\S+)` |
| ffprobe | `ffprobe -version` | 0 | stdout | `ffprobe version (\S+)` |
| dvdauthor | `dvdauthor --help` | 1 | stderr | `dvdauthor, version ([\d.]+)` |
| spumux | `spumux --help` | 255 | stderr | `spumux, version ([\d.]+)` |
| xorriso | `xorriso -version` | 0 | stdout | `^xorriso ([\d.]+)` |
| tsMuxeR | `tsMuxeR --version` | 0 | stdout | `tsMuxeR version ([\d.]+)` |

- Um dicionário único com comando e regex por ferramenta (adicionar ferramenta = uma entrada).
- `parse_version(tool, output) -> str | None`: função pura.
- `detect_versions() -> dict[str, str | None]`: roda cada comando com `subprocess.run` (lista de
  argumentos, sem `shell=True`, `timeout=10`), **ignora o código de saída**, junta stdout e stderr
  e aplica a regex. Vira `None` quando dá `FileNotFoundError`, `TimeoutExpired` ou a regex não
  casa. Resultado em cache (`functools.cache`): as versões não mudam com o container rodando, e
  assim o healthcheck não dispara 6 processos a cada intervalo.
- `GET /health`: 200 com `{"status": "ok", "tools": {...}}` quando todas têm versão; 503 com
  `{"status": "missing", "tools": {...}}` (mesmo formato, `null` na que falta) caso contrário.
- `GET /`: página hello (nome do projeto, uma frase sobre o objetivo, link para `/health`).

### Qualidade

- `pyproject.toml` com uv, `requires-python = ">=3.12,<3.13"`, `.python-version` versionado,
  layout `src/`.
- Runtime: `fastapi`, `uvicorn` (sem `[standard]`: os extras não são usados), `jinja2`.
- Dev: `ruff`, `mypy`, `pytest`, `pytest-cov`, `httpx` (para o `TestClient`).
- `ruff`: regras `E`, `F`, `I`, `B`, `UP`, `SIM`, `RUF`, e format.
- `mypy --strict` em todo o projeto.
- `pytest`: `--cov=projeto_dvd --cov-fail-under=90`, marcador `slow` registrado.
- Mocks só na fronteira (`subprocess.run` via `monkeypatch`; no `/health`, a função
  `detect_versions`), com o cache limpo entre testes.

### Makefile

Todos os alvos usam `uv run`, para funcionar sem venv ativado (local e CI).

| Alvo | Faz |
|---|---|
| `make dev` | `docker compose up --build` |
| `make test` | `uv run pytest` |
| `make lint` | `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` |
| `make format` | `uv run ruff format` e `uv run ruff check --fix` |

### CI (GitHub Actions)

Workflow `ci.yml`, em push e pull request, com versão do uv fixada no `astral-sh/setup-uv`:

1. **quality:** `uv sync --frozen`, `make lint`, `make test`.
2. **docker:**
   - cria um `.env` de teste com pastas temporárias;
   - `docker compose up -d --build --wait` (usa o healthcheck; sem `sleep` nem loop manual, e o
     próprio compose falha se o healthcheck não passar dentro do limite);
   - `curl -fsS` em `/` e em `/health`, com `jq` conferindo que as 6 ferramentas existem e não
     são `null`;
   - confere que o container não roda como root (`docker compose exec web id -u` diferente de 0);
   - em caso de falha, `docker compose logs` (`if: failure()`).

### Repositório

- `.gitignore`:
  - Python e ferramentas: `.venv/`, `__pycache__/`, `.coverage`, `htmlcov/`, `.mypy_cache/`,
    `.ruff_cache/`, `.pytest_cache/`;
  - segredos e locais: `.env`, `.claude/settings.local.json`;
  - mídia e intermediários: `*.mkv`, `*.mp4`, `*.avi`, `*.m4v`, `*.ts`, `*.m2ts`, `*.vob`, `*.mpg`,
    `*.m2v`, `*.ac3`, `*.sup`, `*.iso`, `VIDEO_TS/`, `BDMV/`;
  - pastas de trabalho e artes por pasta (não por extensão, para não bloquear screenshots do
    README): `work/`, `output/`, `data/`;
  - banco: `*.db`, `*.db-journal`, `*.sqlite`, `*.sqlite3`.
  - `*.srt` **não** é ignorado (fixtures de teste vão usar).
- `.dockerignore`: `.git`, `.env`, `.venv`, caches, `tests/`, `docs/`.
- `git mv readme.md README.md`; README em inglês: o que o app faz, status (Fase 0), stack, como
  rodar com Docker, comandos de desenvolvimento, manutenção (cópia do tsMuxeR), licença.
- Licença MIT.
- Agentes em `.claude/agents/` (já criados e revisados).

## Testes

| Comportamento | Teste |
|---|---|
| `parse_version` extrai a versão certa da saída real das 6 ferramentas | unitário parametrizado com `tests/fixtures/tool_versions/` |
| `parse_version` devolve `None` para saída vazia ou formato inesperado | unitário |
| `detect_versions` aceita código de saída diferente de 0 (dvdauthor 1, spumux 255) | unitário (`subprocess.run` mockado) |
| `detect_versions` devolve `None` em `FileNotFoundError` e em `TimeoutExpired` | unitário |
| `GET /` responde 200 com HTML | unitário (`TestClient`) |
| `GET /health` responde 200 com tudo presente e 503 com `null` na que falta, mesmo formato | unitário (`detect_versions` mockado) |
| A imagem tem todas as ferramentas, roda como não root e o compose sobe saudável | smoke test no CI |

TDD: cada teste é escrito e visto falhando antes da implementação.

## Pré-requisitos do ambiente local

- Docker Desktop com a integração WSL ligada para a distro do Vini.
- `uv` instalado no usuário (script oficial).
- `gh` opcional, para abrir o PR pela linha de comando.

## Ordem de entrega (grupos)

1. Configs de qualidade (`pyproject.toml`, `.python-version`, `uv.lock`, `Makefile`).
2. App e testes (TDD), incluindo as fixtures capturadas da imagem.
3. Docker (`Dockerfile`, `docker-compose.yml`, `.env.example`, `.dockerignore`).
4. CI (`.github/workflows/ci.yml`).
5. Repositório (`README.md`, `LICENSE`, `.gitignore`).
6. `CLAUDE.md`: Estado atual, roadmap e Log de decisões, com:
   - worker adiado para a Fase 3 (ajusta 6.2);
   - `config.py`, TMDB e volume `data` adiados para as Fases 1 e 2;
   - variáveis `HOST_*` separadas dos caminhos no container (estende 6.1);
   - trixie com apt fixado por versão e base por digest; tsMuxeR 2.7.0 por sha256;
   - container com usuário não root UID 1000;
   - `/health` com versões das ferramentas como base do smoke test;
   - `app.py` na raiz do pacote até a Fase 1; pastas de módulo criadas só quando usadas;
   - licença MIT; `mypy --strict` no projeto todo.

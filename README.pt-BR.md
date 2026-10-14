# projeto-dvd

[![CI](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml/badge.svg)](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml)

[English](README.md) | **Português**

Um app web local que transforma uma coleção pessoal de filmes e séries em **discos de DVD e
Blu-ray com menus navegáveis**, além de **capas para imprimir** e colocar nas caixinhas.

O objetivo é uma coleção física feita para durar: discos que seguem as especificações oficiais
de DVD-Video e BDMV à risca, para tocar num player comum daqui a 20 anos, com menus simples o
bastante para uma criança ou um avô usarem só com o controle remoto.

> **Status:** Fase 0 (estrutura do projeto). Hoje o app mostra uma página inicial e um health
> check das ferramentas de mídia. O roadmap está no [`CLAUDE.md`](CLAUDE.md).

## Pipeline planejado

```
scan → probe → metadados (TMDB) → projeto de disco (DVD-5/9, BD-25/50) → encode → menu → authoring → ISO
```

O app gera um arquivo `.iso`. A gravação é feita no Windows (ImgBurn ou o gravador nativo),
porque o WSL não acessa o gravador de disco.

## Stack

- Python 3.12, FastAPI, Jinja2 (HTMX e Tailwind chegam com as primeiras telas de verdade)
- Ferramentas de mídia: ffmpeg, dvdauthor/spumux, tsMuxeR, xorriso
- Docker e docker compose; CI no GitHub Actions
- uv, ruff, mypy (strict), pytest

## Rodando com Docker

Requisitos: Docker (no Windows, Docker Desktop com a integração WSL ligada).

```bash
cp .env.example .env   # depois ajuste os três caminhos
# O Docker criaria as pastas que faltam com dono root; o subshell não deixa o .env no seu terminal.
(set -a; . ./.env; mkdir -p "$HOST_WORK_DIR" "$HOST_OUTPUT_DIR")
make dev               # docker compose up --build
```

Abra <http://localhost:8000>. O endereço <http://localhost:8000/health> lista as versões das
ferramentas de mídia encontradas no container e responde 503 se faltar alguma.

A pasta de mídia é montada como **somente leitura**: o app nunca altera os arquivos originais.

## Desenvolvimento

Requisitos: [uv](https://docs.astral.sh/uv/).

| Comando | O que faz |
|---|---|
| `make test` | Roda os testes com cobertura (mínimo de 90%) |
| `make lint` | Lint e checagem de formato com ruff, mypy strict |
| `make format` | Formata e corrige automaticamente com ruff |
| `make dev` | Faz o build e sobe o app com docker compose |

## Manutenção

- As ferramentas de mídia têm versão fixada (digest da imagem base, versões dos pacotes do
  Debian, checksum do tsMuxeR). Quando o Debian publica uma atualização de segurança, o build
  quebra de propósito: atualize as versões no `Dockerfile` e faça o commit.
- O tsMuxeR tem pouca atividade no projeto original. Guarde uma cópia do
  `tsMuxer-2.7.0-linux.zip` (sha256 `ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987`)
  fora do GitHub.

## Licença

[MIT](LICENSE)

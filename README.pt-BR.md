# projeto-dvd

[![CI](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml/badge.svg)](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml)

[English](README.md) | **Português**

Um app web local que transforma uma coleção pessoal de filmes e séries em **discos de DVD e
Blu-ray com menus navegáveis**, além de **capas para imprimir** e colocar nas caixinhas.

O objetivo é uma coleção física feita para durar: discos que seguem as especificações oficiais
de DVD-Video e BDMV à risca, para tocar num player comum daqui a 20 anos, com menus simples o
bastante para uma criança ou um avô usarem só com o controle remoto.

> **Status:** Fase 1 (biblioteca). O app lista cada pasta de disco da pasta de entrada e lê os
> dados técnicos dos vídeos com o ffprobe: duração, resolução, codecs, HDR, faixas de áudio e de
> legenda, capítulos e legendas externas. O roadmap está no [`CLAUDE.md`](CLAUDE.md).

## Pipeline planejado

```
scan → probe → metadados (TMDB) → projeto de disco (DVD-5/9, BD-25/50) → encode → menu → authoring → ISO
```

O app gera um arquivo `.iso`. A gravação é feita no Windows (ImgBurn ou o gravador nativo),
porque o WSL não acessa o gravador de disco.

## Como funciona a pasta de entrada

Cada subpasta da pasta de entrada é um disco. Coloque os vídeos de cada disco numa subpasta
própria; o app nunca varre o HD inteiro.

```
entrada\                          (HOST_MEDIA_DIR, montada em /media, somente leitura)
  Senhor dos Aneis\               → 1 pasta = 1 disco
    A Sociedade do Anel.mkv
    As Duas Torres.mkv
    O Retorno do Rei.mkv
    O Retorno do Rei.pt-BR.srt    → legenda externa do vídeo acima
  Friends T1\
    Temporada 1\S01E01.mkv        → subpastas dentro da pasta do disco são permitidas
```

- Vídeos: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`, `.ts`, `.m2ts`.
- Legendas externas: `.srt`, `.ass`, `.ssa`, `.sup`, e `.idx` ao lado do seu `.sub`. A legenda
  pertence ao vídeo cujo nome começa o dela (`Filme.pt-BR.srt` → `Filme.mkv`); quando vários
  combinam, ganha o nome mais longo (`Filme.2.pt.srt` → `Filme.2.mkv`).
- Vídeos soltos direto na pasta de entrada, fora de uma pasta de disco, não aparecem. Links
  simbólicos são ignorados.
- O scan é incremental: um arquivo só é lido de novo quando o tamanho ou a data de modificação
  mudam.
- A pasta de entrada pode ficar no `C:` ou no próprio HD externo. Copiar para o `C:` ocupa
  espaço (um filme em Blu-ray tem de 30 a 50 GB).

## Stack

- Python 3.12, FastAPI, Jinja2, HTMX e um CSS próprio pequeno (sem etapa de build)
- SQLite com SQLModel e Alembic
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

A pasta de entrada (`HOST_MEDIA_DIR`) não é criada para você: crie com uma subpasta por disco e,
se ela estiver no HD externo, conecte o HD antes do `make dev`. Sem isso, o Docker monta uma pasta
vazia e a biblioteca não mostra nenhum disco.

Abra <http://localhost:8000>. O endereço <http://localhost:8000/health> lista as versões das
ferramentas de mídia encontradas no container e responde 503 se faltar alguma.

A pasta de entrada é montada como **somente leitura**: o app nunca altera os arquivos originais.

O resultado dos scans fica num banco SQLite no volume Docker `data`, então sobrevive a um novo
build. `docker compose down -v` apaga esse volume (só o cache do scan, nunca os vídeos); o
próximo scan lê tudo de novo.

## Desenvolvimento

Requisitos: [uv](https://docs.astral.sh/uv/).

| Comando | O que faz |
|---|---|
| `make test` | Roda os testes unitários com cobertura (mínimo de 90%) |
| `make test-slow` | Roda os testes de integração dentro da imagem Docker, com o ffmpeg real e sem rede |
| `make lint` | Lint e checagem de formato com ruff, mypy strict |
| `make format` | Formata e corrige automaticamente com ruff |
| `make fixtures` | Gera de novo as fixtures JSON do ffprobe com o ffmpeg fixado na imagem |
| `make dev` | Faz o build e sobe o app com docker compose |

Para rodar o app sem Docker (o scan precisa do `ffprobe` no `PATH`):

```bash
MEDIA_DIR=/caminho/para/entrada DATABASE_URL=sqlite:///./projeto_dvd.db \
  uv run uvicorn projeto_dvd.app:create_app --factory
```

## Manutenção

- As ferramentas de mídia têm versão fixada (digest da imagem base, versões dos pacotes do
  Debian, checksum do tsMuxeR). Quando o Debian publica uma atualização de segurança, o build
  quebra de propósito: atualize as versões no `Dockerfile` e faça o commit. Depois de atualizar
  o ffmpeg, rode `make test-slow`: ele compara as fixtures commitadas com a saída do ffprobe novo.
  A fixture de Dolby Vision perfil 5 é escrita à mão: confira também se o ffprobe ainda chama o
  side data de "DOVI configuration record".
- O tsMuxeR tem pouca atividade no projeto original. Guarde uma cópia do
  `tsMuxer-2.7.0-linux.zip` (sha256 `ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987`)
  fora do GitHub.
- O HTMX 2.0.11 fica versionado em `src/projeto_dvd/web/static/htmx.min.js` (origem
  `https://unpkg.com/htmx.org@2.0.11/dist/htmx.min.js`, sha256
  `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`).

## Licença

[MIT](LICENSE)

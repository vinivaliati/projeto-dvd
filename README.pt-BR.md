# projeto-dvd

[![CI](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml/badge.svg)](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml)

[English](README.md) | **Português**

Um app web local que transforma uma coleção pessoal de filmes e séries em **discos de DVD e
Blu-ray com menus navegáveis**, além de **capas para imprimir** e colocar nas caixinhas.

O objetivo é uma coleção física feita para durar: discos que seguem as especificações oficiais
de DVD-Video e BDMV à risca, para tocar num player comum daqui a 20 anos, com menus simples o
bastante para uma criança ou um avô usarem só com o controle remoto.

> **Status:** Fase 2 (curadoria) em cima da Fase 3 (DVD mínimo). Cada vídeo de uma pasta de
> disco ganha o match no TMDB (filme ou episódio, dados em pt-BR e artes), e uma pasta com um
> vídeo vira um ISO de DVD-Video sem menu, conferido automaticamente antes de chegar à pasta de
> saída. O roadmap está no [`CLAUDE.md`](CLAUDE.md).

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
- Use um arquivo de vídeo por título (por exemplo, um `.mkv` feito com o MakeMKV). Pastas de disco
  copiadas (`VIDEO_TS`, `BDMV`) não são suportadas: os `.VOB` ficam de fora e um `BDMV` completo
  listaria todos os clipes.
- O scan é incremental: um arquivo só é lido de novo quando o tamanho ou a data de modificação
  mudam.
- A pasta de entrada pode ficar no `C:` ou no próprio HD externo. Copiar para o `C:` ocupa
  espaço (um filme em Blu-ray tem de 30 a 50 GB).

## Match no TMDB

Os menus e as capas das próximas fases precisam saber qual filme ou episódio é cada vídeo. O
app procura no [TMDB](https://www.themoviedb.org/) e o Vini confirma.

1. Crie uma conta grátis no TMDB, abra Configurações > API e copie o **Token de leitura da API**
   (o longo). Coloque no `.env` como `TMDB_TOKEN=...` e rode `docker compose up -d`. Sem o token,
   a tela da pasta explica isso e todo o resto funciona.
2. Numa pasta escaneada, clique em **Buscar no TMDB**. Cada vídeo ganha um cartão com uma
   sugestão tirada do nome do arquivo (nomes de release, `S01E03`, `1x03`, `T01E03`,
   `Temporada 2/03.mkv`, `title_t00.mkv` do MakeMKV...). Um nome que não diz nada usa o nome da
   pasta.
3. **Sugestão** é um título (e ano) que bate exatamente; **Confira** marca o que é ambíguo (dois
   filmes com o mesmo nome, um arquivo de 20 minutos sugerido como filme, um episódio que o TMDB
   não tem). **Confirmar todas as sugestões** confirma só as seguras; **Corrigir** busca à mão
   (filme ou série, temporada e episódio).
4. Confirmar salva os dados em pt-BR (em inglês quando não há tradução) e baixa as artes padrão:
   `HOST_OUTPUT_DIR\covers\<pasta>\<Título (ano)>\poster.jpg`, `backdrop.jpg`, `logo.png` e
   `metadata.json` (episódios: `S01E03.jpg` e `S01E03.json` na pasta da série). A escolha entre
   várias imagens chega com as capas.

O formulário "Gerar DVD" passa a sugerir o áudio no idioma original informado pelo TMDB.

<img src="src/projeto_dvd/web/static/tmdb.svg" alt="TMDB" height="14">
Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB ("This product
uses the TMDB API but is not endorsed or certified by TMDB."). Os dados e as imagens são usados
para fins pessoais e não comerciais (imprimir as capas da própria coleção).

## Gerando um DVD

1. Coloque um vídeo numa pasta de disco, abra a pasta no app e clique em **Escanear**.
2. Clique em **Gerar DVD**. O formulário já vem com tudo sugerido; mude o que quiser:
   - **Áudio:** as faixas em português e no idioma original vêm marcadas; escolha a que toca
     ao colocar o disco. AC-3 compatível é copiado sem perda; o resto (DTS, TrueHD, AAC...)
     vira AC-3, sem inventar canais.
   - **Legendas:** legendas de texto (um `.srt` ao lado do vídeo, ou uma faixa de texto dentro
     do MKV) viram legendas de DVD; escolha uma para começar ligada, ou nenhuma.
   - **Capítulos:** os do arquivo, ou a cada N minutos (no máximo 99).
   - **Disco:** DVD-5 (camada única, 4,7 GB) ou DVD-9 (dupla camada, 8,5 GB); cada cartão mostra
     o tamanho e a qualidade da imagem: "Ótima" (5 Mbps ou mais), "Aceitável" (3,5 a 5),
     "Baixa" (abaixo de 3,5, pede confirmação) ou "Não cabe".
3. A tela do job mostra cada etapa, o progresso e o tempo que falta; dá para fechar e voltar
   por **Jobs**. Um filme de 2 h em 1080p leva de 20 a 30 minutos num processador de 6 núcleos.
4. O ISO é conferido automaticamente (tamanho, estrutura VIDEO_TS, faixas e idiomas,
   capítulos, ordem dos campos, sincronia do áudio, decodificação completa). Só um ISO
   aprovado é copiado para `HOST_OUTPUT_DIR\iso\<pasta>.iso` (a tela do job mostra o caminho
   completo no Windows); um reprovado fica na pasta de trabalho, com o motivo.
5. Teste o ISO no VLC (Mídia, Abrir disco) com o checklist da tela do job e grave no Windows
   com o ImgBurn ("Write image file to disc", velocidade baixa, verificar).

Como funciona, em resumo: MPEG-2 em 2 passes (nunca `-target ntsc-dvd`, que duplica quadros);
filmes em 23,976 recebem **soft pulldown** por um pequeno patcher que edita o arquivo no lugar
(o player mostra 29,97 sem tranco); fontes 480i continuam entrelaçadas; rips de DVD são
classificados pelos quadros; o `dvdauthor` monta um título que começa sozinho e o
`genisoimage -dvd-video -udf` gera o ISO.

**Ainda não suportado** (a tela explica o motivo): HDR e 4K, PAL/25 fps, 24 fps exato, 29,97
progressivo, 59,94, taxa de quadros variável, 1080i, legendas em imagem (PGS, VobSub) e estilo
ASS, menus e vários títulos por disco. Para um filme cuja legenda em português é imagem,
coloque um `.srt` ao lado dele.

A pasta de trabalho precisa de **cerca de 2 vezes o tamanho do disco** livre (uns 18 GB para um
DVD-9): cada arquivo intermediário é apagado assim que a etapa seguinte dá certo, e **Apagar
arquivos temporários**, na tela do job, remove o que sobrar.

## Stack

- Python 3.12, FastAPI, Jinja2, HTMX e um CSS próprio pequeno (sem etapa de build)
- httpx2 para a API do TMDB (e o `MockTransport` dele nos testes: eles nunca chamam o TMDB)
- SQLite (WAL) com SQLModel e Alembic; um processo worker separado roda os jobs
- Ferramentas de mídia: ffmpeg, dvdauthor/spumux, genisoimage, tsMuxeR, xorriso
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

Rodam dois serviços: `web` (as telas) e `worker` (um job de DVD por vez). `docker compose logs
worker` mostra o que o worker está fazendo; `docker compose stop` para o encode em andamento em
poucos segundos e marca o job como falho (gere de novo). O app só responde em
`localhost`/`127.0.0.1` e recusa pedidos que alteram dados vindos de outros sites.

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

Para gerar um disco pelo terminal, com as escolhas sugeridas (desenvolvimento e depuração):

```bash
docker compose run --rm worker python -m projeto_dvd.jobs.pipeline "Nome da pasta"
```

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
- As legendas do DVD usam a fonte DejaVu Sans da imagem (`fonts-dejavu-core`, fixada). O patcher
  de soft pulldown deixa o `time_code` do GOP na escala de 24p; os players ignoram, mas confira
  no primeiro teste num player físico.
- O tsMuxeR tem pouca atividade no projeto original. Guarde uma cópia do
  `tsMuxer-2.7.0-linux.zip` (sha256 `ceaaa181ab70e201685b1e45260d337d1cbdb0aba1408d4fbc47e232a7e4c987`)
  fora do GitHub.
- O HTMX 2.0.11 fica versionado em `src/projeto_dvd/web/static/htmx.min.js` (origem
  `https://unpkg.com/htmx.org@2.0.11/dist/htmx.min.js`, sha256
  `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`).

- O logo do TMDB no rodapé é o `src/projeto_dvd/web/static/tmdb.svg`, o logo "blue short" de
  https://www.themoviedb.org/about/logos-attribution (sha256
  `8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c`).

## Licença

[MIT](LICENSE)

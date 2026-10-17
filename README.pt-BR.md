# projeto-dvd

[![CI](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml/badge.svg)](https://github.com/vinivaliati/projeto-dvd/actions/workflows/ci.yml)

[English](README.md) | **Português**

Um app web local que transforma uma coleção pessoal de filmes e séries em **discos de DVD e
Blu-ray com menus navegáveis**, além de **capas para imprimir** e colocar nas caixinhas.

O objetivo é uma coleção física feita para durar: discos que seguem as especificações oficiais
de DVD-Video e BDMV à risca, para tocar num player comum daqui a 20 anos, com menus simples o
bastante para uma criança ou um avô usarem só com o controle remoto.

> **Status:** Fase 4b (retomar, cache de encode, cópia de rip de DVD) sobre a 4a (montador e
> menus de DVD). Cada vídeo de uma pasta de disco ganha o
> match no TMDB (filme ou episódio, dados em pt-BR e artes), e a pasta inteira vira um ISO de
> DVD-Video com menus (filmes, ou uma temporada com "Tocar todos"), conferido automaticamente
> antes de chegar à pasta de saída. O roadmap está no [`CLAUDE.md`](CLAUDE.md).

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

A tela "Montar DVD" usa os nomes do TMDB no menu, o fundo como arte do menu e o idioma
original para sugerir o áudio.

<img src="src/projeto_dvd/web/static/tmdb.svg" alt="TMDB" height="14">
Este produto usa a API do TMDB, mas não é endossado nem certificado pelo TMDB ("This product
uses the TMDB API but is not endorsed or certified by TMDB."). Os dados e as imagens são usados
para fins pessoais e não comerciais (imprimir as capas da própria coleção).

## Montando um DVD

![Uma página do menu como a TV mostra](docs/images/menu-preview.png)

1. Coloque os vídeos de um disco numa pasta (três filmes, ou os episódios de uma temporada),
   abra a pasta no app e clique em **Escanear**.
2. Clique em **Montar DVD**. A tela já vem com tudo sugerido e salva cada mudança:
   - **Títulos:** filmes ou série, na ordem do disco (suba e desça cada um). Os nomes vêm do
     TMDB quando o match está confirmado, ou do nome do arquivo.
   - **Idiomas, para o disco todo:** os idiomas de áudio e de legenda, o áudio que toca
     primeiro e a legenda que começa ligada. Cada título usa a melhor faixa de cada idioma; o
     título que não tem um deles aparece na lista (toca a própria primeira faixa, ou fica sem
     legenda). AC-3 compatível é copiado sem perda; o resto vira AC-3, sem inventar canais.
     Legendas de texto (`.srt` ou faixa de texto do MKV) viram legendas de DVD.
   - **Menu:** o preview de cada página, com o fundo (do TMDB ou escuro), a cor de destaque
     (de uma paleta fechada, ou tirada do fundo) e o lado dos botões.
   - **Capítulos:** os do arquivo, ou a cada N minutos (no máximo 99 por título).
   - **Disco:** DVD-5 ou DVD-9; cada cartão mostra o tamanho e a qualidade da imagem do disco
     inteiro ("Ótima", "Aceitável", "Baixa" pede confirmação, "Não cabe"). Todos os títulos
     usam o mesmo bitrate de vídeo, então a qualidade é a mesma do primeiro ao último.
3. A tela do job mostra as etapas do título atual, o progresso e o tempo que falta; dá para
   fechar e voltar por **Jobs**.
4. O ISO é conferido automaticamente (tamanho, estrutura VIDEO_TS e, em cada título e página
   de menu, faixas, idiomas, capítulos, ordem dos campos, sincronia e decodificação completa).
   Só um ISO aprovado é copiado para `HOST_OUTPUT_DIR\iso\<pasta>.iso`.
5. Teste o ISO no VLC (Mídia, Abrir disco) com o checklist da tela do job e grave no Windows
   com o ImgBurn ("Write image file to disc", velocidade baixa, verificar).

**No disco:** ao colocar, abre o menu principal. Um disco de filmes lista os filmes (mais de
seis ganham páginas próprias); um disco de série tem "Tocar todos", as páginas de episódios
(um episódio escolhido segue até o fim do disco) e as páginas de idioma. "Áudio" e "Legendas"
são páginas próprias, com um ✓ no idioma ligado. O filme volta à própria página e ao próprio
botão; as teclas Menu e Title do controle sempre voltam ao menu principal.

**Retomar, o cache e os rips de DVD:**

- **Retomar:** um job que parou no meio (o WSL ou o PC reiniciou, faltou espaço, foi cancelado)
  tem o botão **Retomar**. Ele roda o mesmo plano de novo, e os títulos já codificados vêm do
  cache.
- **Cache:** o vídeo MPEG-2 de cada título codificado fica em `HOST_WORK_DIR/cache` (hard link,
  sem cópia), com a chave no próprio comando do encode. Montar de novo um disco com outro menu,
  outra ordem ou outros capítulos pula o encode. Acima de `CACHE_LIMIT_GB` (padrão 50; 0
  desliga), os mais antigos saem; a tela de Jobs mostra o tamanho e limpa.
- **Rips de DVD:** o vídeo MPEG-2 de um rip de DVD (720x480 com o sequence header de DVD) é
  copiado byte a byte em vez de recodificado, quando o áudio escolhido cabe no espaço que o disco
  original tinha. Os capítulos são os do rip, levados ao GOP fechado mais próximo; o job confere
  o fluxo logo depois de extrair, e a QA confere que o vídeo no disco é idêntico. "Recodificar os
  rips" desliga a cópia num disco.

Como funciona, em resumo:

- **Vídeo:** MPEG-2 em 2 passes (nunca `-target ntsc-dvd`, que duplica quadros); filmes em
  23,976 recebem **soft pulldown** por um pequeno patcher que edita o arquivo no lugar; fontes
  480i continuam entrelaçadas; rips de DVD são classificados pelos quadros.
- **Menus:** desenhados com o Pillow em pixels quadrados e reduzidos para 720x480; o destaque
  dos botões é um subpicture de 4 cores desenhado direto em 720x480 (sem antialias). Um menu
  16:9 tem uma segunda camada de botões para a TV 4:3 que mostra o menu com faixas pretas. Cada
  página é um segundo de MPEG-2 parado com AC-3 silencioso.
- **Navegação:** `dvdauthor` com um titleset por título (cada um declara exatamente as próprias
  faixas) e todo pulo passando pelo VMGM, onde três PGCs só de comandos abrem a página
  principal, despacham o próximo título e mostram a página em que a pessoa estava. Os GPRMs guardam os idiomas, o próximo episódio e o botão
  destacado. Um disco aceita até 60 títulos (o despachante cabe nos 128 comandos de uma PGC).
- **ISO:** `genisoimage -dvd-video -udf`.
- **Testes:** os testes lentos montam discos de verdade e navegam neles com a libdvdnav, a
  biblioteca de navegação do VLC (o player físico continua sendo o teste final).

**Ainda não suportado** (a tela explica o motivo): HDR e 4K, PAL/25 fps, 24 fps exato, 29,97
progressivo, 59,94, taxa de quadros variável, 1080i, legendas em imagem (PGS, VobSub) e estilo
ASS, menu de capítulos e menu com vídeo. Para um filme cuja legenda em português é imagem,
coloque um `.srt` ao lado dele.

A pasta de trabalho precisa de **cerca de 3 vezes o tamanho do disco** livre com o cache ligado
(uns 27 GB para um DVD-9; 2 vezes sem ele): cada arquivo intermediário é apagado assim que a
etapa seguinte dá certo, e **Apagar arquivos temporários**, na tela do job, remove o que sobrar.

## Stack

- Python 3.12, FastAPI, Jinja2, HTMX e um CSS próprio pequeno (sem etapa de build)
- httpx2 para a API do TMDB (e o `MockTransport` dele nos testes: eles nunca chamam o TMDB)
- Pillow para as páginas do menu e o preview delas
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

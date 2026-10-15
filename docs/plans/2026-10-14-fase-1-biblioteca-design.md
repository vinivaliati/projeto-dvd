# Fase 1: Biblioteca (design)

- **Data:** 2026-10-14
- **Branch:** `feat/fase-1-biblioteca`
- **Status:** design aprovado pelo Vini no chat; revisado por `tech-lead-midia`, `designer`, `qa`,
  `revisor-codigo` e `organizador`; aguardando revisão do Vini.

## Contexto e intenção

O Vini não vai catalogar um HD inteiro. O fluxo dele é **um disco de cada vez**, com calma:

1. faz uma limpa nos arquivos;
2. coloca numa pasta `entrada` (no Windows) uma **subpasta por disco** (ex: os 3 filmes de
   O Senhor dos Anéis numa subpasta);
3. o app mostra cada subpasta como um disco em potencial, com os dados técnicos de cada vídeo.

Não é para automatizar além do necessário: o Vini ainda vai ajeitar capas e comprar gravador e
mídia.

```
entrada\                          (HOST_MEDIA_DIR, montada em /media, somente leitura)
  Senhor dos Aneis\               → 1 pasta = 1 projeto de disco (ou box, Fase 7)
    A Sociedade do Anel.mkv
    As Duas Torres.mkv
    O Retorno do Rei.mkv
    O Retorno do Rei.pt-BR.srt    → legenda externa do vídeo acima
  Friends T1\
    Temporada 1\S01E01.mkv        → subpastas dentro da pasta do disco são permitidas
```

A pasta `entrada` pode estar no `C:` ou no próprio HD externo: o que importa é a estrutura de
subpastas. Copiar para o `C:` ocupa espaço (um filme em Blu-ray tem de 30 a 50 GB).

## Pronto quando

1. Com `HOST_MEDIA_DIR` apontando para uma pasta com subpastas, `GET /` lista cada subpasta com
   nome, quantidade de vídeos, tamanho total e status (vazia, não escaneada, ok, com avisos,
   mudou desde o último scan). Depois do scan, também a duração total.
2. Na página da pasta, "Escanear" roda o ffprobe e mostra a tabela da seção "Telas".
3. Um segundo scan sem mudanças **não roda o ffprobe** de novo. Arquivo novo ou alterado é
   reprocessado; arquivo removido sai do banco; arquivo que deu erro é tentado de novo.
4. Um arquivo que o ffprobe não lê aparece com aviso e não interrompe o scan.
5. O app nunca escreve em `/media`: provado por teste (árvore idêntica antes e depois; scan sobre
   pasta somente leitura) e no CI (`touch /media/...` falha no container).
6. CI verde, incluindo os testes de integração (`slow`) rodando **dentro da imagem**.
7. Definição de pronto da seção 2.5 do `CLAUDE.md`.

## Fora de escopo

| Item | Fase |
|---|---|
| Match no TMDB, nomes "bonitos", coleções, status de match e filtros na biblioteca | 2 |
| Perfil de disco, calculadora, escolha de faixas, limite de 8 áudios do DVD | 4 (a Fase 1 só guarda o ffprobe completo) |
| Avisos de entrelaçado e VFR (dados já ficam no JSON) | 3 |
| Fila de jobs, scan em segundo plano com progresso | 3, se precisar |
| Várias pastas de entrada, tela de configurações | quando precisar |
| Tabelas de pastas, faixas ou projetos (`SourceFolder`, `DiscProject`) | 3/4 |
| Detecção de HDR sem tag (heurística) | não planejado: sem tag, assume SDR |

## Decisões

### Pasta de entrada

- Uma pasta de entrada só, montada em `/media:ro`. Cada **subpasta imediata** é uma "pasta de
  disco"; vídeos são procurados recursivamente dentro dela.
- Variável do app: `MEDIA_DIR=/media` (um caminho), substituindo `MEDIA_ROOTS` (lista).
- Arquivos soltos na raiz de `/media` são ignorados. Subpastas ilegíveis (ex: `$RECYCLE.BIN`,
  `System Volume Information`) são puladas sem erro.
- **Links simbólicos são ignorados**: pasta de disco que seja link não aparece; dentro dela,
  `os.walk(followlinks=False)` e arquivos que sejam link são pulados. Assim nada fora de `/media`
  é lido.
- Nomes são normalizados para Unicode NFC antes de comparar e de gravar (acentos vindos do
  Windows podem chegar em NFD).

### Arquivos reconhecidos

- Vídeo: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`, `.ts`, `.m2ts` (sem diferenciar maiúsculas).
- Legenda externa: `.srt`, `.ass`, `.ssa`, `.sup`, e `.idx` **somente** se houver o `.sub` de
  mesmo nome. Regras:
  - na mesma pasta do vídeo, nome começando com o nome do vídeo (sem extensão) seguido de `.`,
    sem diferenciar maiúsculas;
  - cada legenda vai **só para o vídeo de nome mais longo** que casar (`Filme.2.pt-BR.srt` é do
    `Filme.2.mkv`, não do `Filme.mkv`);
  - dois vídeos com o mesmo nome e extensões diferentes (`Filme.mkv` e `Filme.mp4`) recebem a
    legenda os dois;
  - o trecho do meio vira o "idioma" exibido como está (`pt-BR`, `en.forced`); sem trecho, "não
    definido".
- Todo o resto é ignorado (`Thumbs.db`, `desktop.ini`, `.nfo`, imagens).

### Scan (síncrono e incremental)

- Disparado pelo botão "Escanear" (`POST`, HTMX). A resposta volta quando termina. Abordagem A,
  aprovada pelo Vini: sem fila, sem progresso.
- Para cada vídeo da pasta: **`stat` primeiro**, depois compara `(caminho, tamanho, mtime_ns)`
  com o banco por **igualdade** (o Explorer preserva o mtime ao copiar, então "mais antigo"
  também conta como mudança):
  - igual e sem erro anterior: não faz nada;
  - novo, diferente **ou com erro anterior**: roda o ffprobe e grava o resultado (ou o erro),
    junto com o `stat` tirado **antes** do ffprobe (um arquivo ainda sendo copiado será
    reprocessado no scan seguinte);
  - no banco mas não mais no disco: remove a linha.
- Arquivo que some entre a listagem, o `stat` e o ffprobe: ignorado, sem derrubar o scan.
- ffprobe ausente no sistema: o scan para com uma mensagem única, sem marcar todos os arquivos
  com erro.
- **Concorrência:** um `threading.Lock` global no servidor; se já houver scan rodando, a resposta
  é "Já existe um scan em andamento". No cliente, `hx-disabled-elt` e `hx-sync="this:drop"` no
  botão. Gravação por upsert pelo `path`.
- A rota é `def` (não `async def`): o ffprobe bloqueia e roda no threadpool. Não há timeout de
  requisição (uvicorn e HTMX não têm por padrão); no pior caso, 60 s por arquivo. Aceito.
- O status "mudou desde o último scan" usa a mesma comparação, só com `stat`, por isso a lista de
  pastas abre na hora.
- **Linhas órfãs:** ao abrir a biblioteca, linhas de pastas que não existem mais são apagadas.
- O scan registra no log quantos arquivos foram enviados ao ffprobe (para conferir o incremental
  no `/mnt/c` real, item de QA manual).

### ffprobe

- Comando: `ffprobe -v error -print_format json -show_format -show_streams -show_chapters
  <caminho absoluto>`, lista de argumentos, sem shell, timeout de 60 s. Caminho absoluto para que
  um arquivo chamado `-algo.mkv` nunca vire opção.
- Medido pelo `tech-lead-midia`: o ffprobe lê só cabeçalhos (1 a 6 MB em arquivos de 410 MB, em
  0,1 s). Não mexer em `probesize`/`analyzeduration`.
- Erro (código diferente de 0, timeout, JSON inválido): grava o stderr truncado em 500
  caracteres e segue.
- O JSON bruto é guardado inteiro: tem `field_order`, `sample_aspect_ratio`, `pix_fmt`,
  `side_data_list` e disposições, que as Fases 3, 4 e 6 vão usar.

### Resumo (função pura sobre o JSON)

| Grupo | Regra |
|---|---|
| Vídeo | primeiro stream de vídeo com `disposition.attached_pic != 1` (capas não contam); sem nenhum, "sem faixa de vídeo" |
| Duração | `format.duration`; se faltar, "?" (não usar a duração dos streams: no MKV ela só vem em `tags.DURATION`) |
| fps | `avg_frame_rate`; se `0/0`, `r_frame_rate`; se os dois forem `0/0`, "?" (sem divisão por zero) |
| Aspecto | `display_aspect_ratio`; se faltar ou for `0:1`, calcular de `sample_aspect_ratio` e resolução |
| HDR | `color_transfer` em `smpte2084` ou `arib-std-b67`, **ou** `side_data_list` com `DOVI configuration record` |
| Dolby Vision perfil 5 | `dv_profile == 5` no side data DOVI: aviso próprio (sem base HDR10, a conversão de cor é outra) |
| Canais | `channel_layout` (`5.1` e `5.1(side)` viram "5.1", `stereo` vira "estéreo", `mono`, `7.1`); se faltar, pelo `channels` (1, 2, 6, 8; outro número aparece como "N canais") |
| Idioma | `tags.language`; ausente ou `und` vira "não definido" (só exibição) |
| Legenda interna | **texto**: `subrip`, `ass`, `mov_text`, `webvtt`, `text`; **imagem**: `hdmv_pgs_subtitle`, `dvd_subtitle`, `dvb_subtitle`, `xsub`; outro codec, "desconhecido" |
| Capítulos | quantidade |

**Avisos** (texto neutro, sem prometer comportamento de fases futuras):
- "Não foi possível ler o arquivo" (erro do ffprobe);
- "Sem faixa de vídeo";
- "HDR (precisa de conversão para SDR)";
- "Dolby Vision perfil 5 (conversão de cor a confirmar)";
- "Acima de 1080p" (largura > 1920 **ou** altura > 1080; 1920x1080 não avisa, 2048x858 avisa).

### Banco

- SQLite com SQLModel; migrações com Alembic. Mantidos (e não `sqlite3` da stdlib) porque o
  domínio da seção 7.1 vai crescer com relações; trocar depois custa mais.
- Tabela única `media_file`:

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int | chave |
| `folder` | str | nome da pasta de disco (NFC), indexado |
| `path` | str | caminho relativo a `/media`, POSIX, NFC, único |
| `size` | int | bytes |
| `mtime_ns` | int | `st_mtime_ns` |
| `probe_json` | str ou nulo | saída bruta do ffprobe |
| `error` | str ou nulo | stderr truncado quando o ffprobe falha |
| `scanned_at` | datetime | UTC |

- Engine com `check_same_thread=False` e uma sessão por requisição (dependência do FastAPI).
- **Alembic:**
  - migrações em `src/projeto_dvd/db/migrations/` (vão junto na imagem), `Config` montado pelo
    código (sem depender de `alembic.ini` em runtime);
  - `env.py` sem `fileConfig()` (não derruba os loggers do uvicorn);
  - `render_as_batch=True` desde a primeira migração (SQLite);
  - aplicado no `lifespan` do app. Quando o `worker` existir (Fase 3), só o `web` migra.
- Banco em `/data/projeto_dvd.db`, num volume nomeado `data`. O Dockerfile cria `/data` com dono
  `app` antes do `USER app`.
- Fora do Docker, `DATABASE_URL` precisa ser definida (documentado no README); os testes sempre
  usam um banco em `tmp_path`.

### Configuração (`config.py`)

`Settings` (pydantic-settings, já previsto na seção 7): `MEDIA_DIR` (padrão `/media`) e
`DATABASE_URL` (padrão `sqlite:////data/projeto_dvd.db`).

### Telas

Texto da interface em português (quem usa é o Vini). Termos técnicos como estão (HDR, codec, fps,
5.1). Números no formato brasileiro (`23,976`, `38 GB`, `2h58`).

**Biblioteca (`GET /`)**
- Cards em grade, ordenados por nome. Nome da pasta em destaque; abaixo, numa linha: vídeos,
  tamanho, duração (ou "escaneie para ver"). Status como selo colorido; "mudou" chama mais atenção
  que "ok", porque pede ação.
- Sem pastas ou `/media` não montada: card central explicando para conferir o `HOST_MEDIA_DIR` no
  `.env`, com um exemplo da estrutura esperada.

```
Biblioteca
┌───────────────────────┐ ┌───────────────────────┐
│ Senhor dos Aneis  [OK]│ │ Friends T1   [MUDOU]  │
│ 3 vídeos · 38 GB      │ │ 24 vídeos · 52 GB     │
│ 9h18                  │ │ escaneie para ver     │
└───────────────────────┘ └───────────────────────┘
```

**Pasta (`GET /folders/{name}`)**
- Cabeçalho: voltar, nome, totais, botão "Escanear". Faixas acima da tabela: avisos agregados
  ("1 arquivo com aviso"), "Arquivos mudaram desde o último scan" e erro do scan inteiro (a tabela
  anterior continua visível).
- Nunca escaneada: mensagem e botão "Escanear" grande no lugar da tabela.
- Escaneando: botão desabilitado e "Escaneando... (pode levar alguns minutos)"; tabela antiga
  esmaecida.
- Tabela com **uma linha por arquivo**, ordem natural do caminho (S01E02 antes de S01E10):
  arquivo, duração, tamanho, vídeo ("1080p · H.264 · 23,976" + selo HDR), áudio resumido ("3
  faixas: por 5.1, eng 5.1, eng estéreo"), legendas ("4 (2 imagem)"), capítulos, ícone de aviso.
  Aspecto só aparece se não for 16:9.
- Detalhe por faixa (título, padrão, forçada, codec) num `<details>` nativo que expande a linha.
- Arquivo com erro: linha em vermelho claro com a mensagem, sem células vazias.

```
← Biblioteca
Senhor dos Aneis              3 vídeos · 38 GB · 9h18   [Escanear]
! 1 arquivo com aviso
Arquivo              Duração  Tamanho  Vídeo              Áudio          Leg.     Cap.
▸ A Sociedade...     2h58     12 GB    1080p H.264 23,976 por 5.1, eng…  3 (1 im) 41
▸ O Retorno... [HDR] 3h21     14 GB    2160p HEVC 23,976  ...            ...      ⚠
```

**Visual:** tema escuro "sala de cinema" sem exagero. Fundo `#121212`, superfície `#1c1c1e`,
borda `#2c2c2e`, texto `#ececec`, secundário `#9a9a9a` (contraste AA conferido), acento âmbar
`#e0a526` só no botão principal e no foco, verde `#4caf50` (ok), âmbar (avisos e "mudou"),
vermelho `#e5534b` (erro). Corpo em `system-ui`; nomes de pasta em `Georgia, serif`; números
com `tabular-nums`. Largura máxima ~1100 px; a tabela rola na horizontal.

### Web

- Rotas em `src/projeto_dvd/api/`:
  - `GET /`, `GET /folders/{name}`, `POST /folders/{name}/scan` (devolve só o fragmento da
    tabela), `GET /health` (igual).
- **`{name}`** precisa ser exatamente o nome (NFC) de uma subpasta real e não-link de `/media`;
  qualquer outra coisa (`..`, `a%2Fb`, arquivo, inexistente, link) dá 404, no GET e no POST.
  Templates usam `url_for` (nomes com acento, espaço, `#` e `?`).
- **CSS próprio** (`web/static/app.css`, ~150 a 200 linhas, cores como variáveis em `:root`),
  sem build e sem Tailwind. Motivo (recomendação do `designer`): para duas telas, o Tailwind
  standalone traria binário, checksum e estágio de build, e o app ficaria sem estilo fora do
  Docker. Ajusta a seção 6 do `CLAUDE.md`; reavaliar no editor de menus (Fase 4).
- HTMX servido localmente (`web/static/htmx.min.js`, versão fixada, checksum anotado).

## Docker e CI

- Dockerfile com estágios nomeados: `runtime` (a imagem da app) e `test` (`FROM runtime`, com
  dependências de dev e `tests/`, terminando em `USER app`). O compose usa `target: runtime`.
- `.dockerignore` passa a permitir `tests` (usado só no estágio `test`).
- CI, job `docker`: constrói o estágio `test` e roda
  `pytest -m slow --no-cov -p no:cacheprovider` com `--network none`, antes do `compose up`
  (reaproveitando o cache do `runtime`).
- Smoke test do CI passa a: criar `/tmp/ci/media/Disco Teste/x.mkv` (arquivo falso), conferir que
  `GET /` lista a pasta, que o `POST` do scan mostra "Não foi possível ler o arquivo", que `/data`
  aceita escrita, que `touch /media/ci-check` **falha** e que o CSS é servido.
- Testes `slow` nunca usam `skipif` por ferramenta ausente: se faltar ffmpeg, falham.

## Testes

`pytest` padrão roda com `-m "not slow"` (no `addopts`; o `-m slow` da linha de comando
prevalece) e `--cov-branch`, mínimo de 90%. Sem `pragma: no cover` em `library/`.

| Área | Testes |
|---|---|
| ffprobe | comando é a lista esperada com caminho absoluto |
| Resumo | por fixture: vídeo, capa ignorada, só capa = sem vídeo, HDR10, HLG, DV perfil 5 (fixture à mão), 2 áudios com idioma/`und`/ausente, legenda texto/imagem/desconhecida, capítulos; `0/0` no fps; sem `format.duration`; DAR `0:1`; rótulo de canais (1, 2, 6, 8, outro, `5.1(side)`); limites de resolução (1920x1080, 2048x858, 3840x2160) |
| Avisos | cada aviso e a ausência deles |
| Legendas externas | sem idioma, com idioma, `.idx` sem `.sub` ignorado, `.sup`, nome mais longo vence, só na mesma pasta, maiúsculas (`Filme.PT-BR.SRT`), mesmo nome com `.mkv` e `.mp4` |
| Pastas e status | vazia, só legendas (0 vídeos), não escaneada, ok, com avisos, mudou (adicionado, removido, alterado), arquivo na raiz ignorado, subpasta ilegível pulada, links ignorados (pasta, arquivo, laço), NFC |
| Scan incremental | novo, igual sem ffprobe, alterado, mtime para trás, removido, erro anterior é tentado de novo, arquivo crescendo (stat antes do probe), arquivo apagado antes do stat e antes do probe, ffprobe ausente aborta, erros parametrizados (código, timeout, JSON inválido), linhas órfãs removidas, upsert |
| Somente leitura | árvore de `/media` idêntica (caminho, tamanho, `mtime_ns`, nomes) antes e depois do scan e de todas as rotas; scan sobre pasta `chmod 555/444` (pulado se rodando como root) |
| Rotas | biblioteca, aviso de `/media` vazia, duração depois do scan, pasta com acento e espaço, 404 parametrizado (GET e POST), scan devolve fragmento sem `<html>`, scan em andamento, estáticos servidos |
| Banco | migração cria a tabela num banco vazio; modelos batem com as migrações (`compare_metadata`); startup migra banco vazio |
| Integração (`slow`, na imagem) | gera clipes `lavfi` (2 áudios com idioma, legenda, capítulos, capa, HDR, 4K pequeno, `dvd_subtitle`) e compara o resumo do ffprobe real com o das fixtures; scan ponta a ponta numa pasta real |

**Fixtures:** os JSON entram no git; os clipes não. Um script versionado
(`tests/fixtures/make_fixtures.sh`, rodado dentro da imagem) regenera os JSON a partir de
comandos `lavfi`. PGS e Dolby Vision não podem ser gerados (sem encoder): essas fixtures são
escritas à mão, com a origem documentada no próprio script.

## Ordem de entrega (grupos)

1. Configuração e banco (`config.py`, modelo, Alembic, volume `data`).
2. `library/probe.py` (comando e resumo) com fixtures e o script que as gera.
3. `library/scan.py` (pastas, legendas externas, incremental, status, somente leitura).
4. Web: rotas, templates, CSS, HTMX.
5. Docker e CI: estágios `runtime`/`test`, testes `slow` no CI, smoke ampliado.
6. Documentação: README (en e pt), `.env.example` (pasta `entrada`), `CLAUDE.md` (3.1, 5.3, 6,
   6.1, 7.1, 7.2, Estado atual, Log de decisões).

## Para o Log de decisões (fim da fase)

- Fluxo de entrada: pasta `entrada` com uma subpasta por disco; o app não varre o HD inteiro.
- `MEDIA_ROOTS` (lista) vira `MEDIA_DIR` (uma pasta); várias pastas adiadas.
- Entrada pode ficar no Windows ou no HD externo; montada `ro` (atualiza 5.3).
- Modelo: sem `SourceFolder` e sem tabelas de faixas; `media_file` com `probe_json` bruto;
  resumo e avisos calculados na hora (ajusta 7.1).
- Biblioteca sem match e sem filtros até a Fase 2 (ajusta 7.2).
- Scan síncrono com lock, sem fila.
- CSS próprio em vez de Tailwind (ajusta 6).
- Testes `slow` dentro do estágio `test` da imagem; Alembic no startup, só no `web` quando houver
  `worker`.
- HDR inclui Dolby Vision; perfil 5 com aviso próprio.

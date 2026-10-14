# Fase 1: Biblioteca (design)

- **Data:** 2026-10-14
- **Branch:** `feat/fase-1-biblioteca`
- **Status:** design aprovado pelo Vini no chat; spec em revisão pelos agentes.

## Contexto e intenção

O Vini não vai catalogar um HD inteiro. O fluxo dele é **um disco de cada vez**:

1. faz uma limpa nos arquivos;
2. coloca numa pasta do Windows (`entrada`) uma **subpasta por disco** (ex: os 3 filmes de
   O Senhor dos Anéis numa subpasta);
3. o app mostra cada subpasta como um disco em potencial, com os dados técnicos de cada vídeo.

Sem pressa e sem automatizar além do necessário: é um projeto feito com calma.

```
entrada\                          (HOST_MEDIA_DIR, montada em /media, somente leitura)
  Senhor dos Aneis\               → 1 pasta = 1 projeto de disco (ou box, decidido na Fase 4)
    A Sociedade do Anel.mkv
    As Duas Torres.mkv
    O Retorno do Rei.mkv
    O Retorno do Rei.pt-BR.srt    → legenda externa do vídeo acima
  Friends T1\
    Temporada 1\S01E01.mkv        → subpastas dentro da pasta do disco são permitidas
```

## Pronto quando

1. Com `HOST_MEDIA_DIR` apontando para uma pasta com subpastas, `GET /` lista cada subpasta
   com nome, quantidade de vídeos, tamanho total e status (não escaneada, ok, com avisos,
   mudou desde o último scan). Depois do scan, também a duração total.
2. Na página da pasta, "Escanear" roda o ffprobe e mostra uma tabela com os dados de cada vídeo
   (seção "Dados mostrados").
3. Um segundo scan sem mudanças **não roda o ffprobe** de novo. Arquivo novo ou alterado é
   reprocessado; arquivo removido sai do banco.
4. Um arquivo que o ffprobe não lê aparece com aviso e não interrompe o scan.
5. O app nunca escreve em `/media` (montagem `ro` e nenhum código de escrita lá).
6. CI verde, incluindo os testes de integração (`slow`) rodando **dentro da imagem**.
7. Definição de pronto da seção 2.5 do `CLAUDE.md`.

## Fora de escopo

| Item | Fase |
|---|---|
| Match no TMDB, nomes "bonitos", coleções | 2 |
| Perfil de disco, calculadora, escolha de faixas | 4 (a Fase 1 só guarda o ffprobe completo) |
| Fila de jobs, scan em segundo plano com progresso | 3, se precisar |
| Configurar pastas pela interface (tela de configurações), várias pastas de entrada | quando precisar |
| Tabela de pastas ou de projetos de disco (`DiscProject`) | 3/4 |

## Decisões

### Pasta de entrada

- Uma pasta de entrada só: `HOST_MEDIA_DIR` (no Windows, ex:
  `/mnt/c/Users/vinivaliati/Videos/projeto-dvd/entrada`) montada em `/media:ro`.
- Cada **subpasta imediata** de `/media` é uma "pasta de disco". Vídeos são procurados
  recursivamente dentro dela.
- A variável do app vira `MEDIA_DIR=/media` (um caminho), substituindo o `MEDIA_ROOTS` (lista) da
  seção 6.1 do `CLAUDE.md`. Registrar no Log de decisões.

### Arquivos reconhecidos

- Vídeo: `.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`, `.ts`, `.m2ts` (comparação sem diferenciar
  maiúsculas).
- Legenda externa: `.srt`, `.ass`, `.ssa`, `.idx` (com o `.sub` de mesmo nome) cujo nome começa
  com o nome do vídeo (sem extensão) seguido de `.`. O trecho do meio vira o idioma, quando
  existir: `Filme.srt` (sem idioma), `Filme.pt-BR.srt` (`pt-BR`), `Filme.en.forced.srt`
  (`en.forced`, mostrado como está).
- Todo o resto é ignorado (`Thumbs.db`, `desktop.ini`, `.nfo`, imagens).

### Scan (síncrono e incremental)

- Disparado pelo botão "Escanear" da pasta (`POST`, HTMX). A resposta volta quando termina; a
  tela mostra "escaneando..." enquanto isso. Decisão: abordagem A (síncrona), aprovada pelo Vini.
- Para cada vídeo da pasta, compara `(caminho relativo, tamanho, mtime_ns)` com o banco:
  - igual: não faz nada;
  - novo ou diferente: roda o ffprobe e grava o resultado (ou o erro);
  - no banco mas não mais no disco: remove a linha.
- O status "mudou desde o último scan" da biblioteca usa a mesma comparação, só com `stat` (sem
  ffprobe), por isso a lista de pastas abre na hora.

### ffprobe

- Comando (lista de argumentos, sem shell):
  `ffprobe -v error -print_format json -show_format -show_streams -show_chapters <arquivo>`,
  timeout de 60 s.
- Código de saída diferente de 0, timeout ou JSON inválido: grava o **erro** (mensagem curta) e
  segue para o próximo arquivo.
- O JSON bruto é guardado inteiro: as Fases 3 e 4 escolhem faixas a partir dele sem reprocessar.

### Dados mostrados (resumo calculado do JSON, função pura)

| Grupo | Campos |
|---|---|
| Arquivo | nome (caminho relativo à pasta), tamanho, duração |
| Vídeo (primeiro stream de vídeo que não seja capa) | codec, resolução, fps, aspecto de exibição, HDR (sim se `color_transfer` for `smpte2084` ou `arib-std-b67`) |
| Áudio (cada faixa) | idioma, codec, canais (ex: 5.1, estéreo), título, se é padrão |
| Legenda interna (cada faixa) | idioma, tipo (**texto**: subrip, ass, mov_text, webvtt; **imagem**: hdmv_pgs_subtitle, dvd_subtitle, dvb_subtitle), forçada, padrão |
| Legenda externa | arquivo, idioma (do nome) |
| Capítulos | quantidade |

Capas embutidas (stream de vídeo com `disposition.attached_pic = 1`) não contam como vídeo.

**Avisos** (texto simples, em português):
- "Não foi possível ler o arquivo" (erro do ffprobe);
- "Sem faixa de vídeo";
- "HDR: será convertido para SDR";
- "Resolução acima de 1080p: será reduzida".

### Banco

- SQLite com SQLModel; migrações com Alembic, aplicadas automaticamente quando o app sobe.
- Tabela única `media_file`:

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int | chave |
| `folder` | str | nome da pasta de disco, indexado |
| `path` | str | caminho relativo a `/media`, POSIX, único |
| `size` | int | bytes |
| `mtime_ns` | int | `st_mtime_ns` |
| `probe_json` | str ou nulo | saída bruta do ffprobe |
| `error` | str ou nulo | mensagem quando o ffprobe falha |
| `scanned_at` | datetime | UTC |

- Resumo e avisos são calculados do `probe_json` na hora de mostrar (sem colunas derivadas).
- Banco em `/data/projeto_dvd.db`, num volume nomeado `data` do compose. O Dockerfile cria
  `/data` com dono `app` para o volume nascer gravável pelo UID 1000.

### Configuração (`config.py`)

`Settings` (pydantic-settings), lido do ambiente:
- `MEDIA_DIR` (padrão `/media`);
- `DATABASE_URL` (padrão `sqlite:////data/projeto_dvd.db`).

### Web

- Rotas em `src/projeto_dvd/api/` (a pasta nasce agora, como previsto na seção 7):
  - `GET /`: biblioteca (cards das pastas);
  - `GET /folders/{name}`: página da pasta;
  - `POST /folders/{name}/scan`: roda o scan e devolve o fragmento da tabela (HTMX);
  - `GET /health`: continua igual.
- **Segurança:** `{name}` precisa ser exatamente o nome de uma subpasta existente de `/media`
  (comparação com a listagem real); qualquer outra coisa (`..`, barras, pasta inexistente) dá 404.
- Templates em `web/templates/` com um `base.html`; texto da interface em **português** (quem
  usa é o Vini e a família).
- HTMX servido localmente (arquivo versionado em `web/static/`, versão fixada).
- Tailwind pelo binário oficial standalone (sem Node), versão fixada e checksum, gerando o CSS
  num estágio do build da imagem. Fora do Docker o app funciona sem CSS (só para testes).
- Pasta de entrada vazia ou não montada: mensagem dizendo para conferir o `HOST_MEDIA_DIR`.

## Testes

| Comportamento | Teste |
|---|---|
| Comando do ffprobe é a lista esperada | unitário |
| Resumo do JSON (vídeo, HDR, áudios, legendas texto e imagem, capítulos, capa ignorada) | unitário com fixtures JSON reais, geradas pelo ffprobe da imagem a partir de clipes `lavfi` |
| Avisos | unitário |
| Legendas externas (sem idioma, com idioma, `.idx` com `.sub`, nome parecido que não é do vídeo) | unitário com `tmp_path` |
| Listagem de pastas e status (não escaneada, ok, avisos, mudou) | unitário com `tmp_path` e SQLite temporário |
| Scan incremental (novo, igual sem ffprobe, alterado, removido, erro do ffprobe) | unitário com ffprobe falso na fronteira |
| Rotas, incluindo 404 para `..` e pasta inexistente | unitário (`TestClient`) |
| Migração cria a tabela num banco vazio | unitário |
| ffprobe real sobre clipe `lavfi` com 2 áudios, legenda e capítulos; scan real ponta a ponta | integração `@pytest.mark.slow`, dentro da imagem |

- `pytest` padrão roda sem os `slow` (`-m "not slow"`), mantendo a cobertura mínima de 90%.
- O Dockerfile ganha um estágio `test` (dependências de dev e `tests/`); o CI constrói esse
  estágio e roda `pytest -m slow` dentro dele.

## Ordem de entrega (grupos)

1. Configuração e banco (`config.py`, modelo, Alembic, volume `data`).
2. `library/probe.py` (comando e resumo) com fixtures reais.
3. `library/scan.py` (pastas, legendas externas, incremental, status).
4. Web: rotas, templates, HTMX, Tailwind.
5. Docker e CI: estágio `test`, testes `slow` no CI, volume `data`.
6. README (pt e en) e `CLAUDE.md` (Estado atual, Log de decisões, roadmap).

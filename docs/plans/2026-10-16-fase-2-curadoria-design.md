# Fase 2: Curadoria (design)

- **Data:** 2026-10-16
- **Branch:** `feat/fase-2-curadoria`
- **Status:** abordagem aprovada pelo Vini no chat; revisada por `curador`, `revisor-codigo` e
  `designer` (achados incorporados); aguardando a revisão do Vini.

## Contexto e intenção

A curadoria existe para abastecer os menus (Fase 4) e as capas (Fase 5): para cada vídeo de uma
pasta de disco, saber **qual filme ou episódio ele é**, com nome em português, sinopse, ano,
elenco, duração e as artes baixadas.

O fluxo continua o das Fases 1 e 3: o Vini monta **uma pasta por disco** com os filmes ou
episódios daquele disco e trabalha **um disco por vez**. O app nunca vê o HD inteiro. O nome da
pasta é escolhido pelo próprio Vini (ex: "Senhor dos Aneis"), então é uma pista confiável, junto
com o nome de cada arquivo.

O app sugere e o Vini confirma, no mesmo espírito da calculadora: nada vira "confirmado" sem um
clique dele, e o que é ambíguo nunca é confirmado em lote.

O Vini ainda não tem a chave do TMDB. Tudo é construído e testado sem ela (a API é sempre mockada
nos testes); o token entra no `.env` no fim, e a tela explica como.

## Pronto quando

1. Sem `TMDB_TOKEN`, a tela da pasta mostra como configurar o token e todo o resto do app (scan,
   Gerar DVD) funciona como antes.
2. Com o token, numa pasta escaneada, "Buscar no TMDB" sugere um filme ou episódio para cada vídeo
   ainda sem match confirmado, usando o caminho do arquivo e, quando ele não diz nada, o nome da
   pasta. Sugestões ambíguas aparecem como "Confira".
3. O Vini confirma cada sugestão (ou todas as seguras de uma vez) e corrige qualquer uma pela
   busca, inclusive trocando filme por episódio e escolhendo temporada e episódio.
4. Ao confirmar, o app salva os dados do TMDB (pt-BR, com fallback para `en`) e baixa as artes
   padrão para `OUTPUT_DIR/covers/<pasta>/...`.
5. A biblioteca mostra, em cada cartão, quantos vídeos da pasta têm match confirmado.
6. O "Gerar DVD" usa o idioma original do TMDB para sugerir o áudio, quando o título está
   confirmado e existe uma faixa nesse idioma.
7. Abrir a biblioteca com o HD desligado não apaga nenhum match.
8. Testes cobrem parser, matching, cliente, escolha e download das artes e rotas, sem rede.
9. Definição de pronto da seção 2.5 do `CLAUDE.md`. A QA manual com o token real fica para o
   final do projeto, junto com a das outras fases (decisão do Vini).

## Fora de escopo

| Item | Quando |
|---|---|
| Tabela e tela de coleções; agrupar discos | Fase 7 (boxes); id e nome da "collection" do TMDB ficam no `tmdb_json` |
| Escolher entre várias artes por posição; pôster da temporada | Fase 5 (capas) |
| Servir as artes locais na interface | Fase 5; a tela usa a miniatura do próprio TMDB |
| Distribuir os filmes de uma collection entre arquivos de nome genérico | não fazer (frágil); o Vini corrige pela busca |
| Filtros na biblioteca | quando houver pastas demais |
| Tela de configurações (token pela interface) | fase futura; o token fica no `.env` |
| Ordem alternativa de episódios (DVD order, absolute) | fase futura; o aviso de duração ajuda a perceber |
| Usar o nome do TMDB no ISO ou no disco | Fase 4 (menus) |

## Decisões tomadas com o Vini

| Pergunta | Decisão |
|---|---|
| De onde vêm os nomes | De uma pasta por disco montada pelo Vini; o HD nunca é varrido |
| Como fazer o match | Sugestão automática por vídeo; o Vini confirma ou corrige (abordagem 1) |
| Coleções | Sem tabela agora; a collection do TMDB fica guardada com os detalhes |
| Artes | Um conjunto padrão por título; a escolha entre várias fica para a Fase 5 |
| Chave do TMDB | Ainda não existe; vai no `.env`, preenchida no final |

Detalhes decididos na revisão dos agentes (apresentados ao Vini junto com a spec): token no
cabeçalho em vez da chave na URL; status "Confira" para sugestões ambíguas; sem distribuição
automática de collection; match numa lista própria, fora da tabela técnica; arquivo que mudou volta
a "sugerido".

## Configuração

- `TMDB_TOKEN`: o **"Token de leitura da API"** (API Read Access Token, v4) da conta do TMDB, que
  funciona nos endpoints v3 pelo cabeçalho `Authorization: Bearer`. A URL nunca leva segredo, então
  o log do `httpx2` (que registra URLs) e as mensagens de exceção ficam limpos. No `Settings`,
  `tmdb_token: SecretStr | None = None` (o `repr` não mostra o valor).
- `TMDB_LANGUAGE`: `pt-BR` por padrão.
- O compose repassa as duas só ao `web` (`TMDB_TOKEN: ${TMDB_TOKEN:-}`); o `worker` não precisa.
- `.env.example` ganha as duas, com o passo a passo curto: criar a conta, Configurações, API,
  copiar o "Token de leitura da API".
- Sem token, a tela da pasta mostra um banner neutro (ver "Telas").

## Parser de nomes (`metadata/filename.py`, função pura)

`guess(path: str, folder: str, max_year: int) -> Guess`, com `path` relativo à pasta do disco
(o scan é recursivo: `Temporada 2/03.mkv`) e `Guess(kind, title, year, season, episode,
episode_end, warnings)`. `max_year` vem de fora para a função ser determinística.

1. **Normaliza** o nome do arquivo (sem extensão): troca `.` e `_` por espaço, exceto em números
   (`5.1`) e em siglas com pontos (`E.T.`, `S.W.A.T.` ficam como estão); mantém o hífen
   (`Spider-Man`); tira grupos entre colchetes e parênteses que não são ano (`(Dublado)`,
   `(Extended)`); tira o sufixo de grupo (`-RARBG`, `-YTS`).
2. **MakeMKV:** tira o sufixo `_t\d+` e os tokens `D\d`, `Disc \d`, `S\d_D\d`
   (`LORD_OF_THE_RINGS_D1_t00`, `Friends_S1_D1_t03`) e usa o que sobrar.
3. **Episódio**, com borda de palavra (para `1920x1080` e `720x480` nunca casarem): `S01E03`,
   `s1e3`, `1x03`, `T01E03`, `Temporada 1 Episódio 3`. `S01E01E02` e `S01E01-E02` preenchem
   `episode_end`. `S00` (especiais) vale. O título é o que vem antes do marcador.
4. **Episódio só com número:** se o arquivo é só um número, `E03`, `Ep 3`, `EP03`, `Episódio 3`
   ou `Episode 3`, e a subpasta mais próxima ou a pasta do disco diz a temporada, é o episódio N
   daquela temporada. `title_tNN` numa pasta de temporada **não** vira número de episódio (o `t00`
   costuma ser o "play all").
5. **Ano:** `(2001)` ou um número entre 1900 e `max_year`, **só se sobrar título antes dele**
   (`1917.mkv`, `1984.mkv` e `2012.mkv` são títulos; `1917 (2019)` e `2012 2009 1080p` dão o título
   e o ano certos). Vale o último ano antes do primeiro termo de release.
6. **Corta no primeiro termo de release.** A lista fica numa constante:
   - resoluções e formatos: `480p`, `576p`, `720p`, `1080p`, `1080i`, `2160p`, `4k`, `uhd`,
     `10bit`, `hdr`, `dv`, `imax`;
   - fontes: `bluray`, `bdrip`, `brrip`, `bdremux`, `remux`, `web-dl`, `webrip`, `hdtv`,
     `dvdrip`, e os serviços `nf`, `amzn`, `dsnp`, `hmax`, `atvp`;
   - codecs: `x264`, `x265`, `h264`, `hevc`, `avc`, `xvid`;
   - áudio: `dts`, `ac3`, `eac3`, `aac`, `flac`, `truehd`, `atmos`, `ddp5.1`, `dd5.1`, `5.1`,
     `2.0`;
   - edição: `extended`, `unrated`, `directors cut`, `remastered`, `remasterizado`,
     `versão estendida`, `proper`, `repack`;
   - idioma da release: `dublado`, `dub`, `legendado`, `leg`, `dual`, `dual audio`, `nacional`.
7. **Nome genérico** cai para o nome da pasta: vazio depois da limpeza, só números (fora de uma
   pasta de temporada), `title_tNN`, `disc N`, `faixa N`, ou menos de 2 letras.
8. **Pasta:** o nome da série vem da pasta do disco. A temporada vem da subpasta mais próxima ou da
   pasta do disco, só em `Temporada N`, `Season N`, `Nª Temporada`, ou `T\d+`/`S\d+` como
   **último** token (`Exterminador do Futuro T2` com um único filme não vira temporada: só vale
   quando o arquivo é um episódio).

## Cliente TMDB (`metadata/tmdb.py`)

- **`httpx2`** passa de dependência de desenvolvimento para dependência do app (já está no lock por
  causa do `TestClient`). Fecha o item do Log da Fase 0 ("decidir na Fase 2 qual cliente usar"):
  um cliente só. Nos testes, `httpx2.MockTransport` no lugar do `respx` (que mocka o `httpx`, não
  o `httpx2`); ajusta a seção 9 do `CLAUDE.md` e o `.claude/agents/curador.md`.
- **Tipos:** modelos Pydantic pequenos só com os campos lidos (resultado de busca, filme, série,
  temporada e episódio, imagem, tradução). Nada de `Any` vazando do `json.loads`. Os campos de data
  aceitam `""` (o TMDB manda vazio quando não sabe), e o ano sai `None`.
- `TmdbClient(token, language, transport=None)`: base `https://api.themoviedb.org/3`, timeout de
  10 s, `Authorization: Bearer`, `language` em toda chamada, sem seguir redirecionamentos. Criado
  **por requisição** dentro de um `with` (a dependência devolve `TmdbClient | None`, `None` sem
  token). Métodos, cada um uma chamada:
  - `search_movie(query, year)`: `search/movie` com `year` (casa qualquer data de lançamento,
    inclusive a brasileira);
  - `search_tv(query, year)`: `search/tv` com `first_air_date_year`;
  - `movie(id)`: `append_to_response=credits,images,translations`,
    `include_image_language=pt,en,null`;
  - `tv(id)`: idem;
  - `season(tv_id, n)`: `tv/{id}/season/{n}` com `append_to_response=translations`; traz todos
    os episódios com nome, sinopse, `still_path`, `runtime` e `air_date`.
- **Idioma:** os textos vêm em pt-BR; quando um campo vem vazio, ou o nome do episódio é só
  `Episódio N`/`Episode N`, ou o título não tem tradução pt-BR em `translations`, usa a tradução
  `en` da mesma resposta. Uma chamada só.
- **Erros** viram `TmdbError` com a mensagem em português: token recusado (401), não encontrado
  (404), limite de requisições (429: "tente de novo em alguns segundos"), fora do ar ou sem rede
  (timeout, conexão). Sem retry automático: o Vini clica de novo.
- **Cache:** os detalhes confirmados ficam inteiros no banco (`tmdb_json`, como o `probe_json` da
  Fase 1). Dentro de um mesmo clique, buscas e temporadas ficam num dicionário (a mesma série e a
  mesma temporada pedidas uma vez para dez episódios). Fora disso, nada é cacheado.

## Matching (`metadata/matching.py`)

`suggest(guess, duration, client) -> Suggestion`, com o status:

- **`suggested`** (segura): o título normalizado do palpite (sem acento, casefold, sem pontuação)
  é igual ao `title` ou ao `original_title` (série: `name` ou `original_name`) de **um único**
  resultado, e o ano bate (±1) quando o palpite tem ano.
- **`doubtful`** ("Confira"): há resultado, mas não passa na regra acima (vários com o mesmo nome,
  como "O Rei Leão" sem ano; nenhum com o ano do nome; nome só parecido). A sugestão é o primeiro
  resultado. Também é `doubtful` um arquivo com **menos de 40 min** sugerido como filme (pega
  "Making of.mkv").
- **`not_found`**: nenhum resultado, nem pelo nome do arquivo nem, em seguida, pelo nome da pasta
  ("Nada encontrado para 'xyz'. Use Corrigir."). Vários vídeos com nome genérico numa pasta que dá
  um filme só ficam todos `not_found` com "Os nomes dos arquivos não dizem qual filme é cada um.
  Use Corrigir."

Episódio: a busca acha a série pela mesma regra; a temporada (`season(...)`, no cache do clique)
confirma que o episódio existe. Se não existe, `doubtful` com "O episódio S01E09 não existe no
TMDB". Se a duração do arquivo diverge mais de 20% do `runtime` do episódio, aviso ("duração bem
diferente: episódio duplo, ordem do DVD ou play all?").

Filme: ao confirmar, aviso se a duração diverge mais de 15% do `runtime` ("versão estendida ou
filme errado?"). Avisos não mudam o status de um título confirmado.

## Banco (migração `0003`)

Tabela `title`, um registro por vídeo com sugestão ou match, **1 para 1** com `media_file`:

| Coluna | Tipo | Nota |
|---|---|---|
| `media_file_id` | int | pk e FK para `media_file` |
| `status` | str | `suggested`, `doubtful`, `confirmed`, `not_found` |
| `kind` | str | `movie` ou `episode` |
| `tmdb_id` | int ou nulo | id do filme ou da série |
| `season`, `episode`, `episode_end` | int ou nulo | só episódio; `episode_end` em arquivo com dois |
| `label` | str | o que a tela mostra ("O Senhor dos Anéis: A Sociedade do Anel (2001)") |
| `poster_path` | str ou nulo | caminho do TMDB, para a miniatura da tela |
| `message` | str ou nulo | aviso, motivo do `not_found` ou arte que falhou |
| `tmdb_json` | str ou nulo | detalhes do TMDB, só quando confirmado (filme; ou série + temporada) |

- `label` e `poster_path` são a exceção à regra "sem colunas duplicadas": uma sugestão ainda não
  tem `tmdb_json`. Nome, ano, sinopse, elenco (5 primeiros), duração, idioma original e collection
  de um confirmado são calculados na hora a partir do `tmdb_json` (`metadata/details.py`, função
  pura `title_info(...)`), como o resumo do ffprobe na Fase 1.
- **Apagar:** relação do SQLModel com `cascade_delete=True` no lado do `MediaFile`, para o
  `session.delete(media_file)` que o scan já faz levar o título junto. Sem `PRAGMA foreign_keys`:
  evita que um futuro batch do Alembic (que recria a tabela) apague os títulos. Teste do cascade e
  teste de que o upgrade 0003 não perde linhas.
- **HD desligado:** `purge_missing_folders` não roda quando a pasta de entrada não existe, não
  pode ser lida ou não tem nenhuma subpasta (hoje `list_disc_folders` devolve `{}` nesses casos e
  o `GET /` apagaria tudo). Teste "HD ausente não apaga títulos".
- **Arquivo que mudou** (tamanho ou `mtime`): um título `confirmed` volta a `suggested`, mantendo
  os dados; o Vini reconfirma com um clique. Pega o `title_t00.mkv` do MakeMKV reaproveitado numa
  pasta.

## Artes (`metadata/art.py`)

Escolha (função pura):

| Posição | De onde |
|---|---|
| Pôster | o `poster_path` dos detalhes pedidos em pt-BR (já é o pôster pt escolhido pelo TMDB); aviso "baixa resolução para impressão" abaixo de 1000 px de largura |
| Fundo | lista `backdrops`: **sem idioma** (sem texto), pela nota e pela largura; sem nenhum assim, o melhor de qualquer idioma com o aviso "fundo pode ter texto" |
| Logo | lista `logos`, só `.png`: `pt`, `en`, sem idioma |
| Still de episódio | `still_path` do episódio (da temporada) |

Download (`download_art`):

- Só de `https://image.tmdb.org/t/p/original<caminho>`, com o caminho validado pelo modelo
  (`^/[A-Za-z0-9]+\.(jpg|png)$`); sem seguir redirecionamentos; `Content-Type` de imagem; no
  máximo 30 MB.
- Grava `.part` e renomeia no fim (nunca um arquivo pela metade). Baixa só se o arquivo não existe;
  "Baixar artes de novo" sobrescreve.
- Sem credencial: a imagem é pública, o token não vai nessa requisição.

Pastas:

```
OUTPUT_DIR/covers/<pasta>/<Filme (ano)>/poster.jpg, backdrop.jpg, logo.png, metadata.json
OUTPUT_DIR/covers/<pasta>/<Série>/poster.jpg, backdrop.jpg, logo.png, S01E03.jpg, S01E03.json
```

- `safe_name(...)` (pura, testada) saneia **os dois** níveis (a pasta do disco também pode ter `:`
  no Linux): `<>:"/\|?*` e controles saem, sem ponto ou espaço no fim, `.`, `..`, vazio e nomes
  reservados (`CON`, `NUL`, `COM1`...) viram um nome padrão, no máximo 80 caracteres (o caminho
  inteiro cabe no MAX_PATH de 260 do Windows). Por último, o caminho final precisa estar dentro de
  `OUTPUT_DIR/covers` (`resolve().is_relative_to`).
- `metadata.json` (e `SxxEyy.json`) tem o `title_info` em JSON, para as Fases 4 e 5 e para quem
  abrir a pasta no Windows.
- Falta de permissão em `/output`: a mensagem da Fase 3 (o `chown`).
- Uma arte que falha não desfaz a confirmação: o título fica confirmado com "Arte não baixada:
  ..." em `message` e o botão "Baixar artes de novo".
- Limitação registrada: imagens `pt` incluem as de Portugal (o TMDB não separa o país).

## Ordem das operações e concorrência

- Rede e artes **primeiro**; depois **uma transação curta por título** (o worker grava progresso
  no mesmo SQLite, com busy timeout de 5 s). "Confirmar todas" faz commit a cada título.
- Um lock por processo para buscar e confirmar (o padrão do `_scan_lock`): um segundo clique
  recebe "Já existe uma busca no TMDB em andamento.". Buscar de novo só refaz o que não está
  `confirmed`.
- "Confirmar todas" com artes `original` de uma temporada inteira pode levar minutos. É aceitável
  no fluxo de um disco por vez, com o aviso na tela.

## Telas

Tudo na tela da pasta (sem tela nova de título por enquanto), com HTMX como no resto. A tabela
técnica **não muda**: ela tem `min-width` e rola de lado no celular.

**Ordem da página:** resumo, seção "Match no TMDB", tabela técnica, bloco do Gerar DVD.

**Seção "Match no TMDB"**:

- Sem token: um `.banner` neutro (o resto do app funciona): "Curadoria desligada. Para buscar os
  filmes no TMDB, coloque o token em `TMDB_TOKEN` no `.env` e rode `docker compose up -d`.", com o
  link para `https://www.themoviedb.org/settings/api`. Sem botões nos cartões.
- Com token, antes do scan: nada além do texto "Escaneie a pasta para buscar no TMDB.".
- Botões `.button.secondary` (o primário continua com o scan e o Gerar DVD): "Buscar no TMDB" e,
  quando há sugestões seguras, "Confirmar todas as sugestões". Com `hx-disabled-elt` nos dois,
  `hx-sync="this:drop"` e o texto "Confirmando e baixando artes... (pode levar alguns minutos)"
  na classe `.scanning`. O resultado sai num banner: "N títulos confirmados".
- Uma `<ul>` com **um cartão por vídeo**: o nome do arquivo pequeno e `muted` em cima, o label
  grande embaixo, a miniatura do pôster à esquerda e os botões à direita (no celular, quebrando
  para baixo). O nome da série aparece uma vez no cabeçalho da seção quando todos os vídeos são da
  mesma série, e cada cartão mostra "S01E03 · <nome do episódio>".

**Estados do cartão:**

| Estado | O que mostra |
|---|---|
| ainda não buscado | "Ainda não buscado" (`muted`) |
| buscando | indicador do HTMX no botão ("Buscando..."), botão desabilitado |
| `suggested` | badge "Sugestão", o label, "Confirmar" e "Corrigir" |
| `doubtful` | badge "Confira", o label, a mensagem, "Confirmar" e "Corrigir" com destaque |
| `confirmed` | badge `badge-ok` "Confirmado" (com texto `sr-only`), o label, "Corrigir" |
| confirmado com arte que falhou | o aviso e "Baixar artes de novo" |
| `not_found` | a mensagem e "Corrigir" com destaque |
| erro do TMDB | "Não foi possível falar com o TMDB: <motivo>. Tente de novo." |

Avisos (`message`) aparecem embaixo do label com o ícone de aviso. Os botões do cartão usam uma
variante nova `.button.small` (altura mínima de 36 px para o toque). Cada cartão tem
`aria-live="polite"`.

**Miniatura:** `https://image.tmdb.org/t/p/w92<poster_path>`, `loading="lazy"`, `width="46"`,
`height="69"` fixos; sem pôster, um retângulo vazio do mesmo tamanho com `var(--border)`. A URL
não leva o token, e o app não tem CSP que bloqueie.

**Corrigir** troca o cartão por um formulário: tipo em dois rádios ("Filme" / "Série"), texto da
busca preenchido com o palpite, ano opcional e, quando o tipo é Série, "Temporada" e "Episódio"
(`inputmode="numeric"`, preenchidos pelo parser). A busca roda ao abrir (com o palpite) e a cada
envio, nunca a cada tecla. Até 10 resultados, cada um um `<button>` (Tab e Enter funcionam) com a
miniatura, "Título (ano)", o título original em `muted` quando for diferente e a sinopse cortada
em cerca de 120 caracteres. Clicar num resultado confirma direto, filme ou série. "Cancelar"
restaura o cartão.

**HTMX:** o HTMX 2 não troca respostas 4xx/5xx (lição da Fase 1), então as rotas de match
respondem **200 com o erro dentro do fragmento**. As rotas de um vídeo devolvem só o `<li>` do
cartão (`hx-target="closest li"`, `hx-swap="outerHTML"`), para o Vini não perder a rolagem num disco
de 20 episódios; só buscar e confirmar todas devolvem a seção inteira.

**Biblioteca:** o cartão da pasta ganha uma linha `muted numbers`: "TMDB: 2 de 3 confirmados", ou
"TMDB: todos confirmados" em `var(--ok)`. Nada quando for zero ou sem token. Sem badge, para não
competir com o status do scan.

**Atribuição do TMDB** (exigida pelos termos e pela seção 11 do `CLAUDE.md`): `<footer
class="muted">` fora do `<main>` em `base.html`, com o logo aprovado do TMDB (SVG da página de
marca deles, versionado no repositório, menor que a marca do app), "Este produto usa a API do TMDB,
mas não é endossado nem certificado pelo TMDB." e o link para themoviedb.org. No README, a frase
oficial em inglês, o logo e a nota de uso não comercial.

### Rotas

| Método e caminho | O que faz | Devolve |
|---|---|---|
| `POST /folders/{name}/match` | sugere para os vídeos que não estão `confirmed` | a seção |
| `POST /folders/{name}/confirm` | confirma todas as `suggested` (pula `doubtful`) | a seção |
| `POST /files/{id}/search` | busca (`kind`, `q`, `year`, `season`, `episode`) | o formulário com resultados |
| `POST /files/{id}/choose` | confirma (`kind`, `tmdb_id`, `season`, `episode`); o "Confirmar" do cartão manda os valores da sugestão em campos ocultos | o cartão |
| `GET /files/{id}/card` | o cartão (o "Cancelar" do Corrigir) | o cartão |
| `POST /files/{id}/art` | baixa as artes de novo | o cartão |

`{id}` é o `media_file_id`, então o Corrigir funciona num vídeo que ainda não tem título. A busca
é `POST` para passar pela checagem de mesma origem (ela gasta cota do TMDB). Todas passam pelos
hosts confiáveis da Fase 3. O cliente vem de uma dependência em `api/deps.py`, trocada nos testes
por um com `MockTransport`.

## Integração com o DVD

`suggest_audio` (em `planner/dvd_plan.py`) recebe o idioma original como parâmetro opcional. A
rota do formulário passa o `original_language` do título confirmado do vídeo, e ele **só vale se
existir uma faixa** com aquele `dvd_language` (o TMDB tem códigos como `cn` e `xx`, e o arquivo
pode nem ter a faixa original). Senão, segue a regra da Fase 3 (a primeira faixa). Fecha o item
"Idioma original pelo TMDB" da spec da Fase 3.

## Erros e casos de borda

- Sem token: nenhuma chamada; botões escondidos; banner de configuração.
- Token recusado: "O TMDB recusou o token. Confira `TMDB_TOKEN` no `.env`."
- Vídeo que falhou no ffprobe: pode ter match (o nome ainda serve); sem duração, as regras de
  duração não se aplicam.
- Pasta renomeada: os vídeos viram linhas novas (Fase 1), então os títulos somem com as antigas; o
  Vini busca de novo. Aceitável no fluxo de um disco por vez.
- HD desligado: nada é apagado (ver "Banco").

## Testes

- **Unitários:**
  - parser, numa tabela de casos: release; nome limpo com ano; português com acento; MakeMKV
    (`title_t00`, `LORD_OF_THE_RINGS_D1_t00`, `Friends_S1_D1_t03`); `S01E03`, `1x03`, `T01E03`,
    `Temporada 1 Episódio 3`, `Ep 03`; `S01E01E02`; `S00E01`; `1920x1080` sem falso episódio;
    `Temporada 2/03.mkv`; `Exterminador do Futuro T2`; `1917.mkv`, `1917 (2019)`,
    `2012 2009 1080p`; `2001 A Space Odyssey 1968`; `E.T.`; `Spider-Man`; `(Dublado)`; nomes
    genéricos;
  - matching com cliente falso: segura, duas com o mesmo nome, ano que não bate, sem resultado,
    fallback para a pasta, episódio inexistente, duração curta, divergência de duração;
  - `title_info`: fallback `en` por `translations`, "Episódio N" tratado como vazio, elenco;
  - escolha de arte (logo `.svg` ignorado, fundo com texto, pôster de baixa resolução);
  - `safe_name` e o caminho dentro de `covers`;
  - `TmdbClient` com `MockTransport`: cabeçalho `Bearer`, parâmetros (`first_air_date_year`,
    `append_to_response`), datas `""`, erros 401/404/429, timeout, token fora de URL, `repr` e
    mensagens;
  - download: caminho inválido recusado, `.part`, tamanho máximo, tipo errado, não baixa de novo;
  - banco: cascade ao apagar o `media_file`, upgrade 0003 sem perder linhas, HD ausente não apaga,
    arquivo que mudou volta a `suggested`;
  - rotas com cliente falso: sem token, buscar, confirmar todas pulando `doubtful`, corrigir,
    cancelar, erro do TMDB com 200, lock, mesma origem;
  - formulário do DVD com o idioma original (com e sem faixa nesse idioma).
- JSON de teste do TMDB com dados **inventados**, nunca respostas reais copiadas.
- **Nunca** chamar a API real; o CI não tem token.
- Sem testes `slow` novos. O smoke do CI confere que a tela da pasta abre sem token e mostra o
  banner.
- Ficam para a QA final com o token real: a busca ignora acento ("Senhor dos Aneis" acha "Senhor
  dos Anéis")? O nome do episódio pt-BR vem mesmo como "Episódio N"? (Se a busca não ignorar
  acento, o Vini corrige pela busca, e o ajuste vira uma correção com teste.)

## Documentação

- `README.md` e `README.pt-BR.md`: status (Fase 2); seção "Matching with TMDB" / "Match no TMDB"
  (pegar o token, o fluxo, "Confira", onde ficam as artes); atribuição do TMDB com o logo;
  `httpx2` no stack.
- `CLAUDE.md`: 3.2 (sem coleções por enquanto; artes padrão; status "Confira"), 6 (`httpx2` como
  cliente), 6.1 (`TMDB_TOKEN` no lugar de `TMDB_API_KEY`, repassada ao `web`), 7 (árvore com
  `metadata/`), 7.1 (`Title` 1 para 1 com `MediaFile`, `tmdb_json`; `Collection` adiada para a
  Fase 7), 7.2 (match na tela da pasta), 9 (`MockTransport` no lugar do `respx`), 10 (pasta das
  artes por pasta de disco), 12, 13, Estado atual e Log de decisões.
- `.claude/agents/curador.md`: `MockTransport` no lugar do `respx`.
- `.env.example`: `TMDB_TOKEN` e `TMDB_LANGUAGE`.

## Ordem de entrega (grupos)

1. Puro: parser, `safe_name`, escolha de arte, modelos Pydantic do TMDB, `title_info`.
2. Cliente TMDB com `MockTransport`; matching.
3. Banco: migração 0003, modelo `Title` com cascade, purge protegido, arquivo que mudou.
4. Confirmação: detalhes, download das artes, `metadata.json`.
5. Telas e rotas; cartão da biblioteca; rodapé de atribuição.
6. Idioma original no formulário do DVD.
7. Smoke do CI, documentação.

## Para o Log de decisões (fim da fase)

- Curadoria na tela da pasta: sugestão automática por vídeo, o Vini confirma ou corrige; status
  "Confira" para o ambíguo, nunca confirmado em lote.
- Sem tabela de coleções até a Fase 7; sem distribuição automática de collection.
- `httpx2` como cliente do TMDB, com o token de leitura no cabeçalho `Bearer` (nada de segredo na
  URL); `MockTransport` nos testes no lugar do `respx`.
- Detalhes do TMDB inteiros no banco (`tmdb_json`), dados da tela calculados na hora; `title` 1
  para 1 com `media_file`, cascade pelo ORM (sem `PRAGMA foreign_keys`).
- O purge da biblioteca não roda com a pasta de entrada ausente ou vazia.
- Artes padrão por título em `OUTPUT_DIR/covers/<pasta>/`; escolha entre várias na Fase 5.
- Token do TMDB só no `.env`, repassado ao `web`.

# Fase 5: Capas (design)

- **Data:** 2026-10-17
- **Branch:** `feat/fase-5-capas`
- **Status:** desenho aprovado pelo Vini no chat; revisada por `designer` (com protótipo em
  Pillow), `curador` e `revisor-codigo`, achados incorporados; aprovada pelo Vini (sem CMYK e sem logo na
  frente).
- **Ordem:** o plano começa depois do merge do PR #7 (Fase 4b): a branch é rebaseada na `main`
  (só tem os commits da spec), o que evita os conflitos em `DiscChoices`, `api/dvd.py`, testes
  de rota, CLAUDE.md e READMEs.

## Contexto e intenção

Cada disco da coleção precisa de uma caixinha com capa e de um label, impressos em casa. A capa
é o que se vê na estante: tem que parecer uma caixa de verdade, ler bem impressa em jato de
tinta e durar. O app compõe a capa com as artes do TMDB que a curadoria trouxe; não gera arte.

## Pronto quando

1. A tela "Capa" de uma pasta mostra o preview da capa (verso, lombada e frente) e do label,
   com a arte da frente escolhida numa grade de pôsteres e fundos do TMDB.
2. "Gerar PDF" grava `OUTPUT_DIR/print/<pasta>.pdf`, em A4 e 300 DPI: página 1 com a capa
   deitada (sangria de 3 mm, marcas de corte e de dobra, régua de 50 mm, aviso de tamanho real),
   página 2 com a folha de 2 labels redondos.
3. As medidas ficam num arquivo de configuração, nunca espalhadas no código.
4. Sem token do TMDB e sem match, a capa funciona com fundo neutro e os nomes do menu.
5. Mudar o Montar DVD não apaga as escolhas da capa, e vice-versa.
6. `make lint`, `make test` (100%) e `make test-slow` verdes.

## Fora de escopo

- Lombadas que formam uma imagem contínua e "Disco 1 de 3" (Fase 7, boxes).
- Capa de Blu-ray (Fase 6), editor livre de layout, arte gerada.
- **CMYK e perfil ICC** (decisão desta revisão, a confirmar com o Vini): o `convert("CMYK")` do
  Pillow não usa preto (testado: um cinza escuro vira cerca de 275% de tinta, marrom e
  encharcado), e a impressora caseira espera RGB. Reavaliar com perfil ICC se for para gráfica.
- Logo do TMDB na frente (texto sempre nesta fase; o logo fica para a Fase 8, como no menu).

## Decisões tomadas com o Vini

- Impressão em casa, **A4**: a capa deitada numa folha com marcas; o label numa folha de
  etiqueta redonda A4 com 2 por folha (padrão Pimaco, medidas a conferir).
- A frente usa **uma arte só** em tela cheia, com o nome do disco e uma faixa no pé.
- A arte vem de **várias opções do TMDB** (grade de pôsteres e fundos de cada obra do disco).
- PDF desenhado com o **Pillow** (já é dependência), sem a reportlab prevista no CLAUDE.md.
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Medidas (`covers/sizes.py`)

Dataclasses congeladas, no estilo de `planner/profiles.py` (milímetros):

```python
A4 = (210.0, 297.0)              # em pé; a capa usa a página girada
DPI = 300

@dataclass(frozen=True)
class CaseSize:                  # caixa Amaray de DVD
    panel_width: float = 129.5   # frente e verso
    spine: float = 14.0
    height: float = 183.0
    bleed: float = 3.0
    safe: float = 5.0            # corte à mão (±1 mm) e a borda da luva plástica
    text_margin: float = 8.0     # margem lateral do texto na frente e no verso
    spine_safe: float = 2.0      # na largura da lombada (a dobra escorrega ±1 mm)
    spine_end: float = 10.0      # nas pontas da lombada

@dataclass(frozen=True)
class Marks:
    offset: float = 4.0          # do corte até a marca (sangria 3 + 1)
    length: float = 4.0          # com 5 a marca chega a 3 mm da borda do A4 e some
    fold_length: float = 3.0     # marcas de dobra nas duas linhas da lombada
    width: float = 0.2           # 3 px a 300 DPI

@dataclass(frozen=True)
class LabelSheet:                # etiqueta redonda A4, 2 por folha (padrão Pimaco, a conferir)
    diameter: float = 117.0
    hole: float = 41.0
    bleed: float = 2.0           # a arte passa 2 mm para fora do círculo
    hole_bleed: float = 2.0      # sem tinta só dentro de r = 41/2 − 2 = 18,5 mm
    safe_outer: float = 4.0      # texto dentro de r = 54,5 mm
    safe_hole: float = 3.0       # texto fora de r = 23,5 mm
    centers: tuple[tuple[float, float], ...] = ((105.0, 78.5), (105.0, 218.5))
```

- A capa ocupa `2 × 129,5 + 14 = 273 × 183 mm`, mais a sangria (279 × 189), centrada no A4
  deitado (297 × 210). Ordem, de fora: **verso | lombada | frente**.
- **Bordas calculadas uma vez só** em px a partir das posições acumuladas em mm (o protótipo
  deixou uma coluna branca de 1 px por arredondar cada painel separado; teste: nenhuma coluna
  branca dentro da área de corte).
- Marcas de corte nos quatro cantos e marcas de dobra nas duas linhas da lombada (em cima e
  embaixo), todas fora da sangria e a pelo menos 4 mm da borda do A4.
- Régua de 50 mm no pé, sob o verso (x = corte esquerdo + 10 mm, a 6 mm da borda de baixo da
  folha; traços a cada 10 mm, 2,5 mm nos extremos e 1,5 mm nos intermediários; "50 mm" em 6 pt,
  #5A5A5A). Aviso "Imprima em tamanho real (100%, sem ajustar à página)." em 7 pt, #5A5A5A,
  alinhado à direita do corte menos 10 mm, na linha da régua (na execução: no alto, centrado,
  ele cruzava as marcas de dobra da lombada).
- Uma função converte mm em px para um DPI; o layout é em mm, e o render recebe o DPI.

## Conteúdo (`covers/content.py`, puro)

`CoverContent` montado do `DiscChoices` salvo (Fase 4a), dos `DiscTitle` da pasta e **só dos
matches confirmados** (`confirmed_infos`; sugestão, "Confira" e "não encontrado" contam como sem
match, nunca o `label` de uma sugestão):

- **Nome do disco e linha secundária:** os do menu (`disc_name`).
- **Faixa da frente** (automática, editável): "3 filmes"; "Temporada 1 · 8 episódios";
  "Especiais" (temporada 0); "Temporadas 1 e 2" (mista); o ano para um filme só.
- **Lombada** (automática, editável): o nome do disco e o complemento: o ano (filme), "T1"
  (temporada única) ou nada.
- **Verso:**
  - um filme confirmado: a sinopse pt-BR (com o fallback em inglês da Fase 2) e o elenco (até 5);
  - vários filmes: título, ano e duração de cada um, e a sinopse curta (até 2 linhas);
  - série: a sinopse da série no alto (pt-BR, fallback em inglês; `TitleInfo.show_overview`
    novo) e a lista "1. Nome" com a duração; episódio duplo "1-2. Nome"; nome genérico vira só o
    número; sem elenco (o `credits` da série é o da temporada mais recente);
  - sem match ou disco misto: cada linha usa o TMDB quando tem e o nome do menu quando não;
  - durações sempre da duração real do arquivo (`summary.duration`), nunca do `runtime` do TMDB;
  - corte: no fim da última frase que cabe; se nenhuma couber, na palavra, com "…";
  - quadro técnico: Duração (total), Áudio (idiomas), Legendas, Vídeo ("DVD-Video · NTSC ·
    16:9", ou 4:3 se todos forem 4:3, por `geometry`), Disco (DVD-5/DVD-9). Sem a marca "DVD
    Video" (marca registrada);
  - atribuição do TMDB quando qualquer texto ou arte do TMDB está na capa (inclusive o pôster
    padrão): "Dados e imagens: TMDB. Este produto usa a API do TMDB, mas não é endossado nem
    certificado pelo TMDB."
- **Label:** nome do disco, linha secundária e o perfil.
- A capa segue as escolhas salvas do Montar DVD: refazer a capa se o disco mudar depois do ISO.

## Artes

**Modelos (só os títulos confirmados a partir desta fase terão os campos novos; os antigos
continuam válidos e precisam ser confirmados de novo para ganhá-los):**
- `CollectionRef.poster_path`; `Image.height` (o TMDB manda; sem ele, estima 2:3 para pôster e
  16:9 para fundo); `Season.poster_path`; `EpisodeDetails.season_poster_path` (preenchido em
  `fetch_details`, que já chama `client.season`; nenhuma chamada nova).
- `title_art_dir(output_dir, folder, details)` extraída do `_save` da Fase 2, usada nos dois
  lugares (a pasta do pôster já baixado).

**Opções da frente** (nenhuma chamada à API para listar; só `.jpg` e `.png`):
1. o pôster da temporada, quando todos os episódios do disco são da mesma temporada; o pôster
   da collection, quando 2 ou mais filmes confirmados do disco são dela;
2. para cada obra (filme ou série) na ordem do disco, os pôsteres `pt`, depois sem idioma, depois
   `en`; dentro de cada idioma, por (atinge 300 DPI, nota, largura);
3. por último, os fundos de todas as obras: sem idioma primeiro, depois com idioma ("pode ter
   texto").
- Sem repetir caminhos (os episódios de uma série trazem as mesmas imagens).
- **Resolução:** `print_dpi(width, height) = 300 / max(1600 / width, 2232 / height)` (o painel
  da frente com sangria tem 1600 × 2232 px a 300 DPI). Abaixo de 150 DPI fica fora da grade;
  entre 150 e 299 aparece com o selo "abaixo de 300 DPI"; sem tamanho conhecido (collection,
  temporada), "resolução desconhecida". Depois do download, mede o arquivo e avisa se ficar
  abaixo de 300.
- **Miniaturas:** CDN do TMDB, `w185` para pôster e `w300` para fundo, `loading="lazy"`, todas
  numa grade só (sem paginação).

**Escolha:**
- `POST /cover/art` aceita só um `file_path` igual a uma das opções calculadas na hora, baixa em
  `original` pelo `TmdbClient.image`, abre e verifica com o Pillow (só JPEG ou PNG), e grava em
  `OUTPUT_DIR/covers/<safe_name(pasta)>/front.jpg` (ou `.png`) com `save_art` (`.part` e
  rename). Nenhum nome de arquivo vem do TMDB ou do formulário. Falha: "A arte não pôde ser
  usada" e a frente anterior fica.
- `CoverChoices.front` guarda o caminho do TMDB (para marcar a opção na grade) e `front_language`
  o idioma dela.
- Toda leitura de arte da capa pega `(OSError, Image.DecompressionBombError)`.

**Padrão sem escolha:** o `poster.jpg` já baixado do primeiro título na ordem do disco (via
`title_art_dir`), senão o fundo neutro. Sem token, a grade mostra as opções, mas escolher uma
nova pede o token (com a explicação da Fase 2).

**Nome sobre a frente:** uma arte com idioma (um pôster com o título impresso) não recebe o nome
por cima, só a faixa do pé; arte sem idioma, fundo ou fundo neutro recebem o nome.
`CoverChoices.show_name: bool | None` (None = automático) deixa o Vini mudar.

**Label:** o fundo do menu (o `backdrop` do Montar DVD) recortado em círculo; sem fundo, o
gradiente neutro.

## Layout e render (`covers/layout.py` puro, `covers/render.py` com Pillow)

**Cores de impressão:** texto claro `#FFFFFF` (o branco do papel, borda nítida; o `#EBEBEB` do
menu vira retícula); secundário `#C8C8C8`; destaque: o hex resolvido do menu (`resolve_accent`).
Corpos mínimos com texto claro sobre escuro: regular ≥ 8 pt, negrito ≥ 7 pt, cinza ≥ 8 pt e
nunca abaixo de `#A0A0A0`; nenhum fio abaixo de 0,35 mm sobre escuro. Fontes: DejaVu Sans e Sans
Bold (as do menu).

**Frente** (129,5 × 183 mm, arte com sangria em cima, embaixo e à direita):
- arte em "cover", sem escurecer o todo;
- degradê de cima: preto a 0,80, sólido do topo da sangria até 6 mm abaixo do bloco do nome
  (cerca de 38 mm do corte), depois some em 30 mm, linear; degradê de baixo: preto a 0,85, sólido
  até 24 mm acima do corte inferior, some em 30 mm;
- nome: Sans Bold 28 pt, entrelinha 31 pt, centrado, até 2 linhas na largura útil de 113,5 mm;
  reduz de 1 em 1 pt até 20 pt, depois "…"; topo das maiúsculas a 16 mm do corte; linha
  secundária em Sans 12 pt `#C8C8C8`, 8 pt abaixo;
- faixa do pé: Bold 11 pt branco, centrado, linha de base a 12 mm do corte; fio de destaque de
  12 × 0,7 mm centrado, 4 mm acima.

**Lombada** (14 × 183 mm):
- fundo sólido `#141416` (o `NEUTRAL_NEAR` do menu; destaque escurecido fica lamacento impresso);
- texto desenhado na horizontal e girado com `rotate(90, expand=True)` (leitura de baixo para
  cima, padrão das caixas vendidas no Brasil);
- nome: Sans Bold branco, centrado na largura, de 18 pt até 12 pt (passo de 1 pt), depois "…",
  altura útil de 10 mm, começando a 10 mm da ponta de baixo;
- complemento (ano ou "T1"): Bold 12 pt na cor de destaque, a 10 mm da ponta de cima, com no
  mínimo 6 mm até o nome;
- o corpo é decidido em mm (medido com a fonte no DPI do render), para o preview e o PDF
  quebrarem o texto igual (teste a 50 e a 300 DPI).

**Verso** (texto de x = 8 a 121,5 mm do painel):
- fundo: o `backdrop` do menu (a frente, se não houver) em "cover", desfoque gaussiano de 4 mm
  feito numa cópia reduzida e ampliada (o desfoque a 300 DPI leva cerca de 1 s), brilho × 0,22
  (pior pixel com luma 56, contraste do branco de cerca de 11:1);
- de cima para baixo: nome em Bold 16 pt com o topo a 12 mm, secundário em 10 pt `#C8C8C8`
  (entrelinha 13 pt); fio de destaque de 12 × 0,7 mm, 3 mm abaixo; o conteúdo começa 5 mm abaixo
  do fio:
  - um filme: sinopse em Sans 9,5 pt, entrelinha 13,5 pt, alinhada à esquerda (sem justificar);
    "Elenco" em Bold 7,5 pt na cor de destaque e os nomes em 8,5 pt, entrelinha 11,5 pt;
  - vários filmes: título em Bold 10 pt, "2001 · 2h58" à direita em 8,5 pt `#C8C8C8`, sinopse em
    8,5 pt `#E1E1E1` (até 2 linhas), 4 mm entre os filmes;
  - série: "1. Nome" em 9 pt, entrelinha 12,5 pt, duração à direita em `#C8C8C8`; acima de 12
    episódios, 2 colunas com 6 mm de calha; se ainda não couber, "e mais N";
- quadro técnico preso ao pé: fio de 0,35 mm `#6E6E6E` 3 mm acima; rótulo em Bold 7,5 pt na cor
  de destaque e valor em 8,5 pt branco a partir de x + 20 mm, entrelinha 11,5 pt; termina 4 mm
  acima da atribuição;
- atribuição: Sans 7 pt `#B4B4B4`, linha de base a 10 mm do corte, entrelinha 9 pt.

**Label** (117 mm, furo de 41 mm):
- arte em "cover" no quadrado de 121 mm, cor × 0,85 e brilho × 0,35, de r = 18,5 mm até r =
  60,5 mm (sem tinta dentro de 18,5 mm: a alimentação da impressora desloca 0,5 a 1,5 mm);
- textos brancos centrados: nome em Bold 16 pt com a linha de base a 33 mm acima do centro
  (corda de 80 mm), reduzindo até 11 pt e depois "…"; secundário em Sans 9 pt a 27 mm acima do
  centro; perfil ("DVD-9") em Bold 9 pt a 30 mm abaixo do centro.

**Render:** `render_cover(content, art, dpi)` e `render_labels(content, art, dpi)` devolvem a
página; o PDF usa 300 DPI e o preview 50 (A4 com 585 × 413 px). PDF salvo com
`save_all=True, append_images=[labels], resolution=300, quality=95, subsampling=0` (o padrão do
Pillow é JPEG q75 com 4:2:0, que borra o texto colorido). Fontes injetáveis como no menu.

## Escolhas salvas

`DiscChoices` ganha `cover: CoverChoices = CoverChoices()` (default: projetos salvos continuam
válidos):

```python
class CoverChoices(BaseModel):
    model_config = ConfigDict(frozen=True)
    front: str | None = None           # caminho do TMDB da arte escolhida (marca a grade)
    front_language: str | None = None  # idioma dela (decide o nome sobre a frente)
    show_name: bool | None = None      # None = automático
    front_text: str | None = Field(default=None, max_length=80)  # None = automática
    spine_text: str | None = Field(default=None, max_length=80)
```

- O formulário do Montar DVD não tem os campos da capa: `parse_disc_form` copia `cover` das
  escolhas reconciliadas. As rotas da capa gravam `_choices(disc).model_copy(update={"cover":
  ...})`. Um teste em cada sentido. Efeito aceito: salvar a capa grava o `DiscProject` com a
  sugestão daquele momento.
- Texto vazio no formulário vira `None`; se `front.jpg` sumiu ou não abre, vale o padrão.

## Telas

- **Tela da pasta:** botão "Capa" ao lado de "Montar DVD", nas mesmas condições dele (pasta sem
  motivos de bloqueio); job ativo não bloqueia a capa.
- **Tela "Capa"** (`/folders/{name}/cover`), mesmo `_disc` do Montar DVD:
  1. preview da capa e do label (PNG a 50 DPI, aspecto corrigido no CSS);
  2. "N vídeos sem match confirmado", com link para a curadoria da pasta, quando houver;
  3. grade de artes com os selos de resolução e "pode ter texto"; rádio "Usar na frente";
  4. textos da faixa e da lombada (vazios = automáticos) e "Mostrar o nome na frente"
     (automático, sim, não); salvam no `change`;
  5. "Gerar PDF": grava o arquivo e mostra o caminho no Windows (como o ISO).

### Rotas

| Rota | O que faz |
|---|---|
| `GET /folders/{name}/cover` | a tela |
| `POST /folders/{name}/cover/choices` | salva textos e o nome na frente; devolve o preview (oob) |
| `POST /folders/{name}/cover/art` | baixa a arte escolhida (só uma das opções) e a usa na frente |
| `GET /folders/{name}/cover/preview.png?page=1\|2&v=…` | preview da capa ou do label (`def`) |
| `POST /folders/{name}/cover/pdf` | grava o PDF (`async` para o formulário, render no thread pool) |

- PDF em `OUTPUT_DIR/print/<safe_name(pasta)>.pdf`, substituído sem perguntar, `.part` e rename;
  `PermissionError` no rename (o PDF aberto num leitor do Windows): "Feche o PDF aberto e tente
  de novo."; pasta sem permissão: o `cannot_write` das outras fases.
- O `POST /cover/art` roda a rede no thread pool, com o lock da curadoria (Fase 2).

## Erros e casos de borda

- Pasta bloqueada ou sem escanear: a tela volta para a pasta.
- Textos longos: redução de corpo e "…" (frente, lombada, label); sinopse e listas cortadas.
- Arte que falha no download ou na verificação: aviso, a frente anterior fica.
- PDF aberto no Windows: mensagem própria.

## Testes

- **Unitários:**
  - mm → px; bordas acumuladas (nenhuma coluna branca entre os painéis); marcas de corte e de
    dobra a 4 mm ou mais da borda do A4; régua e aviso nas margens;
  - textos dentro da área segura; lombada dentro de 2 mm na largura e 10 mm das pontas, e o
    mesmo corte a 50 e a 300 DPI; furo do label sem tinta em r < 18,5 mm;
  - conteúdo: um filme, vários, série (duplo, especial, genérico, mista), sem match, misto,
    atribuição;
  - artes: ordem, deduplicação, collection com 1 e com 2 filmes, temporada, `print_dpi` (pôster
    1000, 1600 e 2000 px; fundo 1920 e 3840 px), `.svg` fora, `tmdb_json` antigo sem os campos
    novos ainda válido, listar sem rede (transport que falha em qualquer request);
  - escolhas: salvar no Montar DVD mantém a capa, salvar a capa mantém o disco;
  - PDF lido com `PIL.PdfParser.PdfParser`: 2 páginas, MediaBox 841,9 × 595,3 e 595,3 × 841,9 pt
    (±0,5); só um teste renderiza a 300 DPI, os outros em DPI baixo;
  - rotas com o TMDB simulado (`httpx2.MockTransport`, JSON inventado): salvar, escolher arte
    válida, recusar caminho fora das opções, download que não decodifica, preview, PDF, PDF
    aberto (rename com `PermissionError`).
- **`slow`:** o PDF gerado na imagem com as fontes reais (2 páginas A4).

## Ponto em aberto para o Vini (durabilidade)

Etiqueta adesiva em disco é desaconselhada para arquivo de longo prazo (pode desbalancear em
alta rotação, descolar com os anos, e o adesivo pode atacar a camada de cima). Vai para as
Decisões em aberto, junto com a compra da mídia: mídia **imprimível** (existe M-DISC imprimível)
com o mesmo label impresso direto no disco, ou etiqueta só nos discos de uso. O layout serve
para os dois.

## Documentação

- README (EN e pt-BR): capa e label; como imprimir (tamanho real, papel fosco de 108 a 135 g/m²,
  conferir a folha de etiquetas contra a luz antes).
- CLAUDE.md: 3.6 (CMYK sai), 6 (Pillow no lugar da reportlab), 7 (`covers/`), 10 (sangria de 3 mm
  na capa e 2 mm no label, área segura de 5 mm, RGB, papel), 12, 13 (etiqueta vs mídia
  imprimível), Estado atual e Log de decisões.

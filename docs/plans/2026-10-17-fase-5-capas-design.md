# Fase 5: Capas (design)

- **Data:** 2026-10-17
- **Branch:** `feat/fase-5-capas`
- **Status:** desenho aprovado pelo Vini no chat; aguardando a revisão dos agentes e do Vini.

## Contexto e intenção

Cada disco da coleção precisa de uma caixinha com capa e de um label no disco, impressos em
casa. A capa é o que se vê na estante: tem que parecer uma caixa de verdade, ler bem e durar.
O app compõe a capa com as artes do TMDB que a curadoria já trouxe; não gera arte.

## Pronto quando

1. A tela "Capa" de uma pasta mostra o preview da capa (verso, lombada e frente) e do label,
   com a arte da frente escolhida numa grade de pôsteres e fundos do TMDB.
2. "Gerar PDF" grava `OUTPUT_DIR/print/<pasta>.pdf`, em A4: página 1 com a capa deitada (com
   sangria de 3 mm e marcas de corte), página 2 com a folha de 2 labels redondos; 300 DPI.
3. As medidas (caixa, lombada, sangria, label, furo, posição das etiquetas na folha) ficam num
   arquivo de configuração, nunca espalhadas no código.
4. Sem token do TMDB e sem match, a capa funciona com fundo neutro e os nomes dos arquivos.
5. `make lint`, `make test` (100%) e `make test-slow` verdes.

## Fora de escopo

- Lombadas que formam uma imagem contínua e "Disco 1 de 3" (Fase 7, boxes).
- Capa de Blu-ray (Fase 6), editor livre de layout, arte gerada.
- Perfil ICC e prova de cor (o CMYK é a conversão simples do Pillow, opcional).

## Decisões tomadas com o Vini

- Impressão em casa, **A4**: a capa deitada numa folha com marcas de corte; o label numa folha
  de etiqueta redonda A4 com 2 por folha (padrão Pimaco).
- A frente usa **uma arte só** em tela cheia, com o nome do disco e uma faixa discreta no pé.
- A arte vem de **várias opções do TMDB** (grade de pôsteres e fundos de cada título).
- PDF desenhado com o **Pillow** (já é dependência), sem a reportlab prevista no CLAUDE.md.
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Medidas (`covers/sizes.py`)

Configuração em dataclasses, no estilo de `planner/profiles.py` (milímetros):

```python
@dataclass(frozen=True)
class CaseSize:          # caixa Amaray de DVD
    panel_width: float = 129.5   # frente e verso
    spine: float = 14.0
    height: float = 183.0
    bleed: float = 3.0
    safe: float = 4.0            # margem interna de segurança para texto
@dataclass(frozen=True)
class LabelSheet:        # etiqueta redonda A4, 2 por folha (padrão Pimaco, a conferir)
    diameter: float = 117.0
    hole: float = 41.0           # área sem impressão no centro
    centers: tuple[tuple[float, float], ...] = ((105.0, 78.5), (105.0, 218.5))  # mm na folha A4 em pé
PAGE_A4 = (297.0, 210.0)         # deitada para a capa
DPI = 300
```

- A capa ocupa `2 × 129,5 + 14 = 273 × 183 mm`, mais 3 mm de sangria em volta (279 × 189),
  centrada na folha A4 deitada (297 × 210); as marcas de corte ficam fora da sangria, com 5 mm
  e afastadas 1 mm.
- A ordem na folha é a da caixa aberta, de fora: **verso | lombada | frente**.
- Um texto pequeno fora da área cortada: "Imprima em tamanho real (100%, sem ajustar à
  página)." Uma régua de 50 mm na margem confere a escala.
- Os valores da etiqueta são de referência e serão conferidos com a folha comprada (já está nas
  decisões em aberto); mudar é editar este arquivo.

## Conteúdo (`covers/content.py`, puro)

`CoverContent` montado a partir do `DiscChoices` salvo (Fase 4a), dos `DiscTitle` da pasta e
dos detalhes do TMDB confirmados:

- **Nome do disco e linha secundária:** os mesmos do menu (`disc_name`).
- **Faixa da frente:** "3 filmes", "Temporada 1 · 8 episódios", ou o ano para um filme só;
  editável na tela.
- **Lombada:** nome do disco e, à direita, o ano (filme), "T1" (temporada) ou nada; editável.
- **Verso:**
  - um filme: a sinopse pt-BR do TMDB (cortada no limite com reticências), o elenco (até 5) e o
    ano;
  - vários filmes: a lista com título, ano e duração, e a sinopse curta de cada um (2 linhas);
  - série: a lista dos episódios numerados ("1. Nome", com a duração);
  - sem match: só os nomes como estão no menu;
  - quadro técnico: duração total, áudio (idiomas), legendas, "DVD-Video · NTSC · 16:9" (ou
    4:3) e o perfil (DVD-5/DVD-9);
  - a atribuição do TMDB (texto curto) quando há dado do TMDB.
- **Label:** nome do disco, linha secundária e o perfil.

## Artes

- **Opções da frente:** para cada título com match confirmado, os `posters` e `backdrops` que
  já estão no `tmdb_json` guardado (a Fase 2 pediu `images` com `pt,en,null`); para filmes de
  uma collection, também o pôster da collection quando o TMDB trouxer (`belongs_to_collection`
  com `poster_path`, campo novo opcional no modelo). Nenhuma chamada nova à API para listar.
- **Grade na tela:** miniaturas pelo CDN do TMDB (`w185`), como os cartões da Fase 2; ordem: o
  pôster da collection, depois os pôsteres `pt`, sem idioma, `en` de cada título por nota, e os
  fundos por último. Até 24 por página da grade.
- **Escolha:** baixa a imagem em tamanho `original` pelo `TmdbClient.image` (mesmas regras de
  caminho, tamanho e tipo da Fase 2) para `OUTPUT_DIR/covers/<pasta>/capa/<nome do arquivo do
  TMDB>`; o nome do arquivo guardado é o do TMDB (só `[A-Za-z0-9]+\.(jpg|png)`), nunca vindo
  do formulário sem validação.
- **Padrão sem escolha:** o pôster da collection, senão o pôster já baixado do primeiro título
  (`poster.jpg` da pasta de artes), senão o fundo neutro (o mesmo gradiente do menu).
- **Label:** usa o fundo do menu (o `backdrop` escolhido no Montar DVD) recortado em círculo,
  escurecido como o menu; sem fundo, o gradiente neutro.

## Layout e render (`covers/layout.py` puro, `covers/render.py` com Pillow)

- Canvas da página a 300 DPI (A4 deitada: 3508 × 2480 px); conversão mm → px numa função só.
- **Frente:** a arte em "cover" no painel com sangria; um degradê escuro no alto e no pé para
  o texto; o nome do disco (logo do TMDB quando houver `logo.png` claro, senão texto) no alto;
  a faixa no pé.
- **Lombada:** fundo da cor de destaque escurecida (ou um recorte da arte), texto de baixo
  para cima (padrão das caixas vendidas no Brasil), centrado, com o nome e o complemento; o
  texto cabe na largura útil (14 mm − margens) com redução de corpo e reticências.
- **Verso:** fundo escuro com um recorte desfocado da arte; blocos de texto na área segura; a
  cor de destaque nos títulos dos blocos (a mesma do menu do disco, para combinarem).
- **Label:** círculo com a arte, o furo em branco (sem tinta), texto reto (sem arco,
  centrado acima do furo); um contorno fino de corte opcional desligado (a etiqueta já vem
  recortada).
- Fontes: as mesmas do menu (DejaVu); valores de corpo e espaçamento definidos pelo `designer`
  na revisão.
- **Preview:** a mesma página renderizada em escala reduzida (PNG), servida por rota.
- **CMYK opcional:** um campo na tela; marcado, o PDF sai com `image.convert("CMYK")`.

## Escolhas salvas

`DiscChoices` ganha `cover: CoverChoices = CoverChoices()` (default: os projetos salvos
continuam válidos):

```python
class CoverChoices(BaseModel):
    front: str | None = None      # nome do arquivo em covers/<pasta>/capa/, ou None (padrão)
    front_text: str | None = None # faixa da frente; None = automática
    spine_text: str | None = None # lombada; None = automática
    cmyk: bool = False
```

A reconciliação (Fase 4a) volta `front` para `None` quando o arquivo sumiu.

## Telas

- **Tela da pasta:** botão "Capa" ao lado de "Montar DVD" (aparece quando a pasta foi escaneada).
- **Tela "Capa"** (`/folders/{name}/cover`):
  1. preview da capa e do label (a imagem inteira da página, com a escala corrigida no CSS);
  2. grade de artes (miniaturas, rádio "Usar na frente"), com "Ver mais" para a próxima página;
  3. textos da faixa e da lombada (vazios = automáticos);
  4. CMYK (desligado);
  5. "Gerar PDF": grava o arquivo e mostra o caminho no Windows (como o ISO).
- Toda mudança salva e atualiza o preview, como no Montar DVD.

### Rotas

| Rota | O que faz |
|---|---|
| `GET /folders/{name}/cover` | a tela |
| `POST /folders/{name}/cover/choices` | salva textos e CMYK; devolve o preview |
| `POST /folders/{name}/cover/art` | baixa a arte escolhida (caminho do TMDB validado contra as opções do disco) e a usa na frente |
| `GET /folders/{name}/cover/preview.png?page=1|2&v=…` | preview da capa ou do label |
| `POST /folders/{name}/cover/pdf` | grava o PDF em `OUTPUT_DIR/print/` (`.part` e rename) |

- O `POST /cover/art` só aceita um `file_path` que esteja nas opções calculadas para o disco
  (nunca um caminho livre); usa o `TmdbClient` (rota `async`, rede no thread pool, como a Fase 2).
- Sem token: a grade mostra as opções (o CDN é público), mas a escolha de uma arte nova pede o
  token, com a mesma explicação da Fase 2; o padrão e o fundo neutro funcionam.

## Erros e casos de borda

- Pasta sem escanear: a tela volta para a pasta (como o Montar DVD).
- Texto longo demais para a lombada: corpo reduzido até um mínimo, depois reticências.
- Sinopse longa: cortada no espaço do bloco com reticências.
- Arte que falha no download: a tela avisa e mantém a frente anterior.
- Pasta de saída sem permissão: a mensagem do `chown` das outras fases.

## Testes

- **Unitários:** mm → px; posições (sangria, marcas, lombada centrada, painéis); textos dentro da
  área segura; lombada que reduz e corta; conteúdo de um filme, de vários e de uma série, com e
  sem match; ordem e filtro das opções de arte; padrão da frente; render (tamanho da página,
  furo do label sem tinta); PDF com 2 páginas A4 a 300 DPI (lido de volta com o Pillow);
  CMYK; rotas (salvar, escolher arte válida e recusar caminho fora das opções, preview, PDF),
  com o TMDB simulado.
- **`slow`:** o PDF gerado dentro da imagem com as fontes reais (2 páginas, tamanho A4).

## Documentação

- README (EN e pt-BR): a capa e o label, como imprimir (tamanho real, papel, etiqueta).
- CLAUDE.md: 3.6, 6 (Pillow no lugar da reportlab), 7 (`covers/`), 10, 12, 13, Estado atual e
  Log de decisões.

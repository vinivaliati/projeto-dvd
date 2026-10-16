# Fase 4a: Montador + menus DVD (design)

- **Data:** 2026-10-16
- **Branch:** `feat/fase-4a-montador-menus`
- **Status:** abordagem aprovada pelo Vini no chat; revisada por `tech-lead-midia` (com testes
  na imagem: dvdauthor, IFO/PCI e navegação simulada na libdvdnav), `designer` e
  `revisor-codigo`, achados incorporados; aguardando a revisão do Vini.

## Contexto e intenção

A Fase 4 do roadmap foi dividida em duas entregas (decisão do Vini):

- **4a, Montador + menus** (esta spec): uma pasta com vários vídeos vira um DVD com menu.
- **4b, Robustez:** retomar job, reaproveitar encode, copiar o vídeo de rip de DVD sem recodificar.

O fluxo continua o mesmo: o Vini monta **uma pasta por disco** com os filmes ou os episódios que
quer naquele disco. A pasta é a seleção, então todos os vídeos dela entram; ele só escolhe a ordem.

O que importa, nesta ordem (seção 1 do CLAUDE.md): o disco toca em qualquer player daqui a 20
anos (DVD-Video à risca), uma criança ou um idoso navega só com o controle, e o menu é bonito.

## Pronto quando

1. A tela "Montar DVD" de uma pasta escaneada lista todos os vídeos dela, com o nome que vai
   para o menu (do match confirmado no TMDB ou do arquivo), duração e ordem editável, e salva as
   escolhas no banco.
2. O Vini escolhe os idiomas de áudio e legenda **uma vez para o disco**; o app pega em cada
   título a melhor faixa de cada idioma e avisa, antes de gerar, o título que não tem um idioma.
3. A calculadora mostra o disco inteiro (todos os títulos, mesma qualidade do começo ao fim, com
   o espaço dos menus descontado), sempre visível numa barra fixa, com os perfis, as faixas de
   qualidade e a confirmação no vermelho da Fase 3.
4. A tela mostra o **preview** de cada página do menu, e o Vini troca o fundo, a cor de destaque
   e o lado dos botões vendo o resultado na hora.
5. O job gera um ISO que, ao entrar no player, **abre o menu principal**:
   - disco de filmes: um botão por filme; o filme volta ao menu no fim, na página dele e com o
     botão dele destacado;
   - disco de série: "Tocar todos", "Episódios" (páginas de até 6) e os idiomas; um episódio
     escolhido segue até o fim do disco e depois volta ao menu com "Episódios" destacado;
   - os idiomas escolhidos no menu valem para o disco inteiro;
   - as teclas Menu e Title do controle levam ao menu principal em qualquer ponto, sem recomeçar
     nada.
6. O ISO passa na QA automática ampliada (todos os títulos e todas as páginas de menu), e o
   teste `slow` navega o disco gerado com a libdvdnav (a mesma navegação do VLC).
7. Sem token do TMDB tudo funciona, com fundo neutro e nomes tirados dos arquivos.
8. Uma pasta com um vídeo só também vira disco com menu: "Assistir" e, se houver o que escolher,
   os idiomas.
9. `make lint`, `make test` (cobertura de 100%) e `make test-slow` verdes.

## Fora de escopo

- Retomar job, reaproveitar encode, copiar rip de DVD (4b).
- Vários discos por pasta, boxes, dividir série em discos (Fase 7).
- Exceções de faixa por título (escolher a versão 2.0 em vez da 5.1 num título só).
- Menu de capítulos ("cenas"), menu com vídeo ou música, logo do título no menu (Fase 8).
- Miniaturas dos fundos na tela (a escolha de artes é da Fase 5; o preview já mostra o resultado).
- Tirar um vídeo da pasta pela tela (a pasta é a seleção; para tirar, o Vini move o arquivo).
- Mais de 60 títulos num disco (limite de comandos do DVD; ver Navegação).
- Blu-ray (Fase 6), capas (Fase 5), PAL.

## Decisões tomadas com o Vini

- Fase 4 dividida em 4a e 4b, começando pela 4a.
- Ao colocar o disco, **abre o menu** (inclusive com um título só).
- Série: "Tocar todos" + lista de episódios; um episódio escolhido **continua** até o fim do disco.
- Faixas **por idioma, no disco**, com aviso para o título sem aquele idioma.
- Tema **automático + 3 ajustes**: fundo, cor de destaque, lado dos botões, com preview.
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Dependências

- **Pillow** entra como dependência do app (previsto na seção 6 do CLAUDE.md), para o render dos
  menus e do preview. Nenhuma ferramenta de mídia nova: `ffmpeg`, `spumux` e `dvdauthor` já estão
  na imagem. A `libdvdnav` (já na imagem, dependência do ffmpeg) é usada só no teste `slow`, via
  `ctypes`.

## Projeto de disco (banco, migração `0004`)

Tabela nova `disc_project`, uma linha por pasta: `folder` (chave primária, NFC) e
`choices_json` (o `DiscChoices` inteiro, como o `plan_json` do job). Sem chave estrangeira para
`media_file`: a pasta pode ser escaneada de novo sem apagar o projeto.

`DiscChoices` (em `planner/disc_plan.py`):

```python
UND = "und"  # faixa sem idioma reconhecido: "Idioma não informado"
Accent = Literal["auto", "ambar", "vermelho", "azul", "verde", "lilas", "gelo"]

class Theme(BaseModel):
    backdrop: str | None      # nome da pasta de arte de um título (ver Tema), ou None
    accent: Accent
    side: Literal["left", "right"]

class DiscChoices(BaseModel):
    kind: Literal["movies", "series"]
    order: tuple[str, ...]    # caminhos dos vídeos (relativos a MEDIA_DIR)
    profile: str
    audio: tuple[str, ...]    # idiomas DVD ("pt", "en") ou UND, na ordem do disco; o 1º toca primeiro
    subtitles: tuple[str, ...]
    subtitle_on: str | None   # idioma ligado ao iniciar, ou None
    chapters: Literal["file", "every"]
    minutes: int
    theme: Theme
```

- `confirm_low` e `replace_iso` **não** fazem parte do `DiscChoices`: são lidos do formulário só
  no `POST /folders/{name}/dvd`, nunca gravados, e sempre desmarcados ao abrir a tela (a
  confirmação do vermelho vale para aquele disco, naquele momento).
- **Gravação:** cada mudança do formulário faz um `POST /choices` que valida e salva o
  `DiscChoices`. Os erros de regra (limites, não cabe) aparecem, mas não impedem salvar. Entre
  duas abas, a última gravação vence.
- **Leitura e reconciliação** (em memória; o `GET` nunca grava):
  - JSON que não valida (`ValidationError`, por exemplo depois de uma mudança de schema): usa a
    sugestão;
  - `order`: caminhos que sumiram saem, vídeos novos entram no fim, na ordem sugerida;
  - `profile` fora de `PROFILES`: a sugestão;
  - idiomas fora da união: saem; áudio vazio: a sugestão; `subtitle_on` fora de `subtitles`:
    `None`;
  - `backdrop` fora da lista de fundos disponíveis: `None`.
- **Validação do formulário:** `order` só é aceito se for uma permutação dos caminhos da pasta
  escaneada (o caminho é só uma chave para achar o `media_file`; o arquivo aberto é sempre o do
  scan); `backdrop` só se estiver na lista do servidor; idiomas só se estiverem na união.
- O `purge_missing_folders` também apaga o `disc_project` da pasta que sumiu, com o mesmo cuidado
  de não rodar com a entrada ausente ou vazia.
- Com um job ativo, o `GET` redireciona para o job (como hoje); o `POST /choices` continua
  salvando, porque o job tem a própria cópia do plano.

**Ordem sugerida:** episódios por temporada e episódio; filmes pelo ano do TMDB quando confirmado,
senão pelo nome do arquivo em ordem natural ("2" antes de "10").

**Tipo sugerido:** `series` quando todos os vídeos têm temporada e episódio (match confirmado ou
`S01E03` no nome); senão `movies`. O Vini troca.

## Nome de cada título e do disco

- **Título com match confirmado:** filme pelo título pt-BR do TMDB; episódio por "N. Nome do
  episódio" (o nome genérico "Episódio N" fica só "Episódio N").
- **Sem match confirmado:** o título que o parser (`metadata/filename.py`) tira do arquivo; se
  ele não tirar nada, o nome do arquivo sem extensão.
- **Nome do disco** (cabeçalho do menu): série confirmada: o nome da série, com "Temporada N" na
  linha secundária quando todos os episódios são da mesma temporada; filme único confirmado: o
  título; vários filmes da mesma collection do TMDB: o nome da collection; senão o nome da pasta.
- **Prefixo comum:** antes de cortar, um item que começa com o nome do disco perde esse prefixo
  ("O Senhor dos Anéis: A Sociedade do Anel" vira "A Sociedade do Anel" no disco "O Senhor dos
  Anéis").
- **Itens sempre numa linha:** Bold 28; se não couber na coluna, Bold 24; se ainda não couber,
  reticências. Episódio com o número alinhado à direita em 2 dígitos ("␣1.", "12.").
- A tela web mostra o texto exato de cada item no menu ("No menu: A Sociedade do Anel…").

## Faixas por idioma

- **Idiomas disponíveis:** a união dos idiomas das faixas de áudio de todos os títulos (código
  DVD por `dvd_language`; faixa sem idioma reconhecido entra como `und`, "Idioma não informado",
  e vai sem `lang` no XML). O mesmo para as legendas suportadas (texto).
- **Sugestão de áudio:** `pt` (se algum título tiver) e o idioma original (do TMDB do primeiro
  título confirmado; senão a primeira faixa do primeiro título), como a Fase 3 faz para um
  título. O primeiro da lista toca ao colocar o disco (português, se houver).
- **Sugestão de legenda:** `pt`, ligada ao iniciar só se o áudio que toca primeiro não for
  português.
- **Por título e idioma, a melhor faixa de áudio:** mais canais; empate, a de índice menor; faixa
  com "coment" ou "comment" no título só se não houver outra.
- **Por título e idioma, a legenda:** a de texto não forçada. Um título que só tem a forçada
  conta como **sem legenda** naquele idioma (ela só legenda as falas estrangeiras), com aviso.
- **Limites nesta fase:** até **4 idiomas de áudio e 4 de legenda** (cada página de idioma cabe
  em tamanho grande); até **60 títulos**. O formulário explica os limites.
- **Título sem um idioma escolhido:**
  - áudio: escolher esse idioma toca, naquele título, a primeira faixa do disco que ele tem;
    aviso "As Duas Torres não tem áudio em Inglês: toca em Português";
  - legenda: fica desligada naquele título, com aviso;
  - por dentro: o "mapa" de cada título (ver Navegação).
- **Botão Audio do controle** no meio de um título troca só aquele título; o próximo volta ao
  idioma escolhido no menu (o registrador do menu não muda). Comportamento aceito.
- O conversor de áudio é o da Fase 3 (`audio_output`): copiar AC-3 compatível, senão converter.

## Calculadora com vários títulos

Mesma qualidade do começo ao fim: um bitrate de vídeo só para todos os títulos.

```
capacidade_disco = capacidade_útil(perfil) − páginas_de_menu × 2 MiB
v = (capacidade_disco × 8 / 1,03 − Σ dur_i × (áudio_i + 10 × legendas_i)) / Σ dur_i
v ≤ 95% × min_i maxrate_i      (maxrate_i como na Fase 3, com as faixas do título i)
```

- `áudio_i` e `legendas_i` são os do título i (um título sem um idioma tem menos faixas).
- 2 MiB por página: o `tech-lead-midia` mediu de 90 KB a 1,2 MB por página no pior caso.
- `estimate_disc(profile, titles, menu_pages)` é a implementação única: com um título e
  `menu_pages=0` o resultado é idêntico ao do `estimate` atual (teste de regressão), e `estimate`
  passa a chamar `estimate_disc`. O `size_bytes` inclui os menus, então o preflight e o
  `size_checks` usam o valor com menus.
- As faixas Ótima, Aceitável, Baixa e Não cabe, a sugestão de perfil e a confirmação no vermelho
  ficam como estão.

## Tema (`menus/theme.py`)

- **Fundos disponíveis:** os `backdrop.jpg` que a Fase 2 baixou em
  `OUTPUT_DIR/covers/<pasta>/<Título (ano)>/`, listados pelo servidor (`sorted` dos nomes das
  pastas de arte que têm `backdrop.jpg`). `Theme.backdrop` guarda só esse nome, nunca um caminho;
  o caminho é sempre montado pelo servidor. Na tela, a escolha é uma lista de opções com o nome do
  título, mais "Sem arte". Sugestão: o do primeiro título (série: o da série).
- **Cor de destaque:** sempre uma das 6 da paleta fechada (legíveis sobre fundo escuro, canais
  entre 16 e 235):

  | valor | nome na tela | hex |
  |---|---|---|
  | `ambar` (padrão) | Âmbar | `#E0A526` |
  | `vermelho` | Vermelho | `#D9483B` |
  | `azul` | Azul | `#4C9BE0` |
  | `verde` | Verde | `#3DB894` |
  | `lilas` | Lilás | `#A685E0` |
  | `gelo` | Gelo | `#E6E6E6` |

  `auto` (a sugestão) escolhe a da paleta mais próxima em matiz da cor dominante do fundo: fundo
  reduzido para 64x36, `quantize(8, method=MEDIANCUT)`, peso `contagem × saturação`, ignorando
  cores com V < 0,25 ou S < 0,20; sem cor elegível ou sem fundo, Âmbar. A tela mostra "do fundo"
  ao lado da cor que o `auto` escolheu.
- **Textos:** principal `#EBEBEB`, secundário `#B4B4B4`, contorno `#101010`. As constantes já
  ficam com os canais entre 16 e 235; o fundo é gravado em RGB de faixa cheia, e a conversão para
  a faixa de TV é do ffmpeg (nunca comprimir duas vezes).
- **Lado:** botões à esquerda ou à direita.
- **Fonte:** DejaVu Sans (`fonts-dejavu-core`, já na imagem), Bold nos itens e no título,
  Regular no texto secundário. Todo texto sobre arte leva contorno de 2 px `#101010`. O caminho é
  uma constante única (a do `subtitles.py`); os testes unitários do render injetam
  `ImageFont.load_default(size=...)`, e só o `slow` usa o DejaVu real.

## Layout e render (`menus/layout.py` puro, `menus/render.py` com Pillow)

**Aspecto dos menus:** 16:9, a não ser que todos os títulos sejam 4:3.

**Geometria:** o fundo é desenhado em pixels quadrados (**854x480** no 16:9, **640x480** no 4:3;
o pixel do DVD não é quadrado) e reduzido só na horizontal para 720x480 com Lanczos. O destaque
(`highlight` e `select`) **nunca** é reduzido: é desenhado direto em 720x480, com o x convertido
por `round(x × 720 / largura / 2) × 2`. Todas as coordenadas e alturas de caixa são pares, nenhum
traço horizontal tem menos de 2 px (o menu é exibido entrelaçado), e as caixas de botão têm pelo
menos 4 px entre si.

**Grade em 480 linhas** (y igual nos dois aspectos):

- Área segura: y de 48 a 432; x de 85 a 769 (16:9, espaço quadrado) ou de 64 a 576 (4:3). O fundo
  vai até a borda; texto e botões ficam dentro.
- Coluna dos botões: 480 px no 16:9 (esquerda 85 a 565, direita 289 a 769); 448 px no 4:3
  (esquerda 64 a 512, direita 128 a 576). O texto começa 32 px depois da borda da coluna.
- **Cabeçalho**, y 48 a 120: o nome do disco em Bold 34 numa linha, se couber; senão até 2 linhas
  em Bold 28 (entrelinha 36), com reticências na 2ª.
- **Linha secundária**, y 124 a 148, opcional: Regular 22, `#B4B4B4` ("Temporada 1", "Episódios
  7 a 12 de 24").
- **Lista**, ancorada embaixo (o último item termina em y 396 com rodapé, ou 432 sem):
  - normal (5 ou 6 itens): passo 40, faixa 36, Bold 28 (maiúscula de 20 px, uns 22 mm numa TV
    de 42" a 3 m);
  - grande (até 4 itens, sem rodapé): passo 56, faixa 48, Bold 34.
- **Rodapé**, y 400 a 432: faixa 32, Bold 24, posições fixas ("◀ Anterior", "Voltar", "Próxima
  ▶"); um item que não existe deixa a posição vazia.

**Páginas:**

- **Principal de filmes:** até 4 filmes e sem paginação, a lista grande tem os filmes mais
  "Áudio" e "Legendas"; com mais filmes, a lista normal tem até 6 filmes por página e o rodapé tem
  "◀ Anterior", "Áudio", "Legendas" e "Próxima ▶". Foco inicial no primeiro filme.
- **Principal de série:** "Tocar todos", "Episódios", "Áudio", "Legendas" (lista grande). Foco
  inicial em "Tocar todos".
- **Episódios:** até 6 por página (lista normal), rodapé com "◀ Anterior", "Voltar" e "Próxima
  ▶". "Voltar" sempre leva ao menu principal.
- **Um título só:** "Assistir", "Áudio", "Legendas".
- **Áudio:** lista grande com os idiomas ("Português", "Inglês (original)" quando o TMDB diz
  que é o original) e "Voltar". **Legendas:** "Sem legenda", os idiomas e "Voltar".
- **Estado visível nos idiomas:** uma variante da página por opção, com "✓" desenhado no fundo
  ao lado do item ativo (até 4 de Áudio e 5 de Legendas). Ao entrar, o despachante mostra a
  variante do valor atual com o foco nele; Enter grava o registrador e mostra a variante nova,
  com o foco no mesmo item.
- "Áudio" some com 1 idioma de áudio; "Legendas" some com 0 legendas.

**Setas:** cima e baixo seguem a lista, sem dar a volta (cima no primeiro fica nele); baixo no
último item vai para o rodapé, no item do meio; esquerda e direita só andam no rodapé. Nenhuma
seta leva para fora.

**Destaque (subpicture):** duas imagens indexadas de 720x480 com **no máximo 4 cores** e alfa
só 0 ou 255 (o contraste parcial vai pela declaração das cores no XML do spumux):

- `highlight`: cor 0 transparente; cor 1, a de destaque, contraste 15 (o marcador, um retângulo
  de 8 px de largura com 16 px de folga antes do texto); cor 2, a de destaque, contraste 5 (uns
  33%, a faixa atrás do texto); cor 3 `#101010`, contraste 15 (borda de 2 px em volta do
  marcador).
- `select`: a mesma geometria, marcador `#EBEBEB`, faixa na cor de destaque com contraste 9.
- Nunca preencher opaco por cima do texto (o texto é desenhado no fundo).
- Plano B, se o contraste parcial não passar no teste `slow`: tudo opaco, marcador sólido mais um
  contorno de 2 px em volta da linha.

**Fundo com arte** (no espaço quadrado, nesta ordem):

1. recorte para preencher a tela (cover, centro);
2. brilho × 0,85 e saturação × 0,85;
3. gradiente preto do lado dos botões: alfa 0,85 da borda até o fim da coluna mais 40 px, caindo
   linear até 0 nos 35% seguintes da largura;
4. desfoque gaussiano de raio 4 só sob o gradiente;
5. checagem de contraste (função pura): no retângulo de cada texto, o percentil 95 da luma BT.601
   tem que ser ≤ 64; senão o alfa do gradiente sobe para 0,92 e depois 0,97;
6. texto;
7. filtro vertical [1, 2, 1]/4 no fundo final, contra a cintilação do entrelaçamento.

**Fundo neutro** (sem arte): gradiente diagonal de `#262B3A` (canto oposto aos botões) até
`#121216`, brilho radial da cor de destaque com 12% de opacidade no canto oposto, um filete de
120x4 px na cor de destaque sob o nome do disco e ruído de ±2 níveis contra degraus no MPEG-2.

`render.py` devolve, por página, `background.png` (720x480), `highlight.png`, `select.png` e as
coordenadas dos botões; o preview é o fundo com o destaque no botão de foco inicial.

## Navegação (`authoring/dvd/dvdauthor.py`)

Toda a navegação passa pelo **VMGM**, que pode pular para qualquer título do disco.
Testado pelo `tech-lead-midia` no dvdauthor 0.7.2 e na libdvdnav.

- **Registradores:** só g0 a g12 (g14 e g15 são usados pelo dvdauthor em botões com vários
  comandos).
  - `g0`: áudio escolhido (posição na lista do disco);
  - `g1`: legenda escolhida (0 sem legenda, senão a posição + 1);
  - `g2`: próximo título a tocar (número global, 0 = nenhum);
  - `g3`: botão a destacar ao voltar (**1024 × n**; nunca 0);
  - `g4`: auxiliar do despachante;
  - `g5`: página a mostrar ao voltar.
- **First play:** inicializa todos (`g0`, `g1` com as escolhas do formulário, `g2 = 0`,
  `g3 = 1024`, `g5` = a página principal) e pula para o menu 1.
- **Menu 1 do VMGM (`entry="title"`) é um despachante sem vídeo**, só com `<pre>`:
  `g4 = g2; g2 = 0; if (g4 == 1) jump title 1; ...; if (g5 == 3) jump menu 3; ...; jump menu 2;`.
  Ele **sempre zera `g2` antes de pular**: a tecla Title do controle entra direto aqui, e um `g2`
  antigo recomeçaria o episódio (bug reproduzido na libdvdnav com a versão anterior desta spec).
- **Páginas visíveis** começam no menu 2; o `<pre>` de cada uma faz `g5 = <ela>; button = g3;`.
  As variantes de Áudio e Legendas são escolhidas pelo despachante a partir de `g0` e `g1`.
- **Botões:** comandos como `g2 = <próximo>; jump title N;`, `g3 = ...; jump menu K;` e
  `g0 = i; g3 = ...; jump menu <variante>;`.
- **Títulos:** o `<pre>` aplica o "mapa" do título: converte `g0` e `g1` nas faixas que aquele
  título tem (`if (g0 == 1) audio = 0; ...`; legenda ligada = 64 + stream). O `<post>`:
  - filme: `g2 = 0; g3 = <botão dele>; g5 = <página dele>; call vmgm menu 1;`
  - episódio: `g2 = <próximo, ou 0 no último>; g3 = <botão "Episódios">; g5 = <principal>;
    call vmgm menu 1;`
- **Tecla Menu:** cada titleset tem um menu raiz só com comando (`g2 = 0; jump vmgm menu 1;`),
  sem vídeo (o dvdauthor aceita e não cria `VTS_xx_0.VOB`).
- **Um titleset por título.** O dvdauthor marca toda faixa declarada num titleset como presente
  em todos os títulos dele (e declara errado os canais quando os títulos diferem), então
  dividir titleset entre títulos com faixas diferentes faria o botão Audio oferecer uma faixa
  muda. Com um titleset por título, cada um declara exatamente as próprias faixas, e o número
  global do título (o de `jump title` e do `ffprobe -title`) é a posição dele no disco.
- **Limite de 60 títulos:** cada título no despachante custa 2 comandos, e uma PGC aceita 128
  (testado: 99 falha no dvdauthor). Teste unitário com o XML de 60; o `slow` roda o dvdauthor com
  60 títulos minúsculos.
- `<menus lang="pt">` no VMGM e nos titlesets (metadado do idioma do menu).
- O comportamento do dvdauthor 0.7.2 que a navegação usa (faixas sempre presentes, g14/g15, 128
  comandos) fica registrado em teste, para uma troca de versão quebrar o teste e não o disco.

## Menus 16:9 numa TV 4:3

Um menu 16:9 (`widescreen="nopanscan"`) leva **dois streams de subpicture**: o 0 (widescreen),
com as coordenadas normais, e o 1 (letterbox), com `y' = 60 + y × 3/4` arredondado para par e o
mesmo x. Os dois são gravados pelo spumux (`-s 0` e `-s 1`) e declarados em
`<subpicture><stream id="0" mode="widescreen"/><stream id="1" mode="letterbox"/></subpicture>`.
Sem o stream letterbox, o destaque fica fora do lugar numa TV 4:3 (verificado no PCI). O teste
unitário confere que o XML do letterbox é a transformação do widescreen; o `slow` confere os 2
grupos de botões no PCI. O comportamento numa TV 4:3 de verdade fica para o teste no player.

## Job e pipeline

- **`DiscPlan` substitui o `DvdPlan`** no `plan_json`: os campos do disco (pasta, perfil,
  bitrate, volume, nome do ISO, aspecto dos menus, tema resolvido e as páginas de menu já
  calculadas com os textos e os comandos) e uma tupla de `TitlePlan`. O `DvdPlan` vira o
  `TitlePlan` (os mesmos campos por título, mais o mapa de idiomas e o nome no menu); encode,
  mux e QA passam a receber `TitlePlan`.
- **Código da Fase 3 substituído e apagado**, sem duas versões convivendo: `Choices`,
  `suggest_choices`, `validate_choices`, `build_plan`, `suggested_plan`, `ONE_VIDEO` e a rota
  `/dvd/estimate`. O comando `python -m projeto_dvd.jobs.pipeline <pasta>` gera o disco da pasta
  inteira com a sugestão.
- **Jobs antigos (migração `0004`):** além de criar `disc_project`, converte o `plan_json` com
  operações de dicionário, **sem importar modelos do app**: os campos por título vão para
  `titles[0]` e `menu_pages` fica vazio. Jobs `queued` ou `running` no momento da migração viram
  `failed` com "Job criado numa versão anterior; gere de novo." O `DiscPlan` aceita `menu_pages`
  vazio só para exibir jobs antigos; o pipeline recusa um plano sem páginas. O `downgrade` apaga
  a tabela e não reconverte os planos (dito na docstring).
- **Classificação pelos quadros** (rips MPEG-2, até 120 s por título): roda só no
  `POST /folders/{name}/dvd`, por título, com o cache `_frames` atual. A tela, a calculadora e o
  preview usam só o resumo do ffprobe e o `check_video`. Quando há rip de DVD, a tela avisa que
  gerar pode levar alguns minutos.
- **Etapas:** para cada título, as etapas da Fase 3 (vídeo em 2 passes, pulldown, áudio, mux,
  legendas); depois "Menus", autoria, ISO, QA e cópia. `report(step, fraction, title)`; o
  `Job.step` grava `"<título>:<etapa>"` (ex.: `"2:video_pass2"`), sem coluna nova. A tela mostra
  "Título 2 de 3 · Vídeo: 2ª passada", trata o formato antigo sem prefixo, e o peso de cada
  título no progresso é proporcional à duração.
- **Fundo do menu em vídeo:**
  `ffmpeg -loop 1 -framerate 30000/1001 -i background.png -f lavfi -i anullsrc=r=48000:cl=stereo -t 1`
  com as opções de codec da Fase 3 (GOP fechado de 12, VBV 1835k), `-q:v 2 -qmin 1 -qmax 28
  -non_linear_quant 1` no lugar de `-b:v` (para um quadro parado, quantizador fixo dá o melhor
  último quadro; o I-frame mede uns 100 KB, abaixo dos 229 KB do VBV), `-flags +cgop+ilme+ildct
  -top 1` (sem isso sai `progressive_sequence = 1`, fora do padrão DVD), o `-aspect` do menu, tags
  BT.601 via `mpeg2_metadata`, `-c:a ac3 -b:a 192k` (áudio silencioso; custa quase nada e evita
  player que tropeça em menu sem áudio), `-f dvd -muxrate 10080k -packetsize 2048`. Depois
  `spumux -m dvd` com `force="yes"` e `start="00:00:00.00"`, e o `<vob>` do menu com
  `pause="inf"`.
- **Fonte que mudou:** cada título é conferido antes do encode, como hoje.
- **Espaço:** o pico continua perto de 2 vezes o disco (os `.mpg` de todos os títulos mais a
  estrutura do DVD na autoria); a checagem do formulário fica como está.

## QA automática

- **Estrutura:** `VIDEO_TS.IFO/BUP/VOB` e, para cada titleset do plano, `VTS_NN_0.IFO/BUP` e
  `VTS_NN_1.VOB`.
- **Por título** (`-title N`, global): os checks da Fase 3 (codec, resolução, aspecto, faixas com
  pacotes lidos, idiomas, duração, bitstream e a decodificação completa); o `sync_check` continua
  no mux de cada título.
- **Por página de menu** (`-menu 1 -menu_vts 0 -pgc K`, só nas PGCs com vídeo; a do despachante
  não tem célula e o ffprobe falha nela): codec, aspecto e o bitstream (`progressive_sequence`
  0, GOP).
- A navegação é garantida pelos testes unitários do gerador de XML e pelo teste `slow` com a
  libdvdnav (abaixo); o QA do ISO não simula navegação.

## Telas

- **Tela da pasta:** "Gerar DVD" vira "Montar DVD"; o bloqueio "um vídeo só" some. A pasta
  continua bloqueada por arquivo ilegível ou não suportado (o motivo cita o arquivo).
- **"Montar DVD"** (mesma rota `/folders/{name}/dvd`), nesta ordem:
  1. **Títulos:** o tipo do disco (Filmes / Série) no topo e uma `<ol>` na ordem do disco, com a
     posição, "T1E03" na série, o nome no menu, a duração e os avisos do título ("sem Inglês")
     como badge. Botões "Subir" e "Descer" de pelo menos 44x44 px, com `aria-label` ("Subir As
     Duas Torres"), desabilitados no primeiro e no último; depois da troca o foco volta ao mesmo
     botão do item movido.
  2. **Idiomas:** áudio e legenda por idioma, "toca primeiro", "ligada ao iniciar" e o resumo dos
     avisos.
  3. **Menu:** o preview e os ajustes. A imagem é o quadro final de 720x480, com o aspecto
     corrigido no CSS (`aspect-ratio: 16 / 9` ou `4 / 3`, `width: 100%`); `alt="Prévia do menu:
     <página>"`; `opacity: 0.5` durante o render. No desktop (≥ 900 px), preview à esquerda
     (`position: sticky`) e ajustes à direita; no celular, preview em cima. Ajustes: seletor de
     página (rádios), fundo (rádios com o nome do título e "Sem arte"), cor (6 rádios com amostra
     de 44x44 e o nome visível, a do `auto` com o badge "do fundo", a escolhida com anel e "✓") e
     lado ("Botões à esquerda" / "Botões à direita").
  4. **Capítulos:** do arquivo ou a cada N minutos, para o disco todo.
  5. **Disco:** os cartões de perfil da Fase 3 com o disco inteiro, as confirmações ("qualidade
     baixa", "substituir o ISO") e "Gerar".
- **Barra fixa da calculadora** (`position: sticky; bottom: 0`, `aria-live="polite"`): "DVD-9 ·
  Ótima · vídeo a 6,2 Mbps · Ver disco", atualizada a cada mudança.
- **Ordem dos títulos sem rota própria:** a ordem vai no formulário (inputs ocultos `order`); os
  botões são `<button name="move" value="<i>:up">` do próprio formulário, e o `/choices` aplica a
  troca antes de salvar. O formulário usa `hx-sync="this:queue all"`, para os pedidos saírem em
  ordem.
- **Resposta do `/choices`:** troca só os blocos de resultado (lista de títulos quando a ordem
  mudou, avisos, cartões de perfil, barra fixa e o `src` do preview) com `hx-swap-oob`, nunca o
  campo que o Vini está editando.
- Acessibilidade e estilo como nas telas atuais; 375 px sem rolagem horizontal; nomes longos com
  `overflow-wrap: anywhere`.

### Rotas

| Rota | O que faz |
|---|---|
| `GET /folders/{name}/dvd` | a tela "Montar DVD" |
| `POST /folders/{name}/dvd/choices` | valida e salva o formulário (inclusive a ordem); devolve os blocos de resultado |
| `GET /folders/{name}/dvd/menu.png?page=…&v=…` | o preview de uma página, desenhado a cada pedido a partir da linha salva |
| `POST /folders/{name}/dvd` | valida, classifica os quadros, faz o preflight e cria o job |

- O preview não tem cache no servidor: o `v` é o hash das escolhas na URL, para o navegador não
  reaproveitar a imagem velha; a resposta vai com `Cache-Control: no-cache`; `page` fora do
  intervalo devolve 404. Se o decode de um fundo grande passar de 300 ms, um `lru_cache` pequeno
  do fundo já reduzido, por `(caminho, mtime)`.
- As rotas que gravam já ficam protegidas pelo `TrustedHostMiddleware` e pela checagem de mesma
  origem da Fase 3; o `FolderDep` já impede traversal no `{name}`.

## Erros e casos de borda

- Título sem duração ou com vídeo não suportado: a pasta fica bloqueada com o motivo e o arquivo.
- Arte apagada depois de escolhida: o fundo some da lista, a reconciliação volta para `None`
  (fundo neutro) e a tela avisa.
- Pasta escaneada de novo com vídeo trocado: a ordem é reconciliada; o job usa tamanho e mtime.
- Faixas só "und": "Idioma não informado" funciona como qualquer idioma.
- Nenhum idioma de áudio em comum: o Vini escolhe qualquer um da união; os títulos sem ele tocam
  a própria primeira faixa do disco (aviso).
- Mais de 60 títulos, mais de 4 idiomas, nenhum áudio: erros no formulário, em português.
- Disco que não cabe: como hoje ("Não cabe" bloqueia; vermelho pede confirmação).

## Testes

- **Unitários:**
  - sugestão de ordem e tipo, nomes dos títulos e do disco, prefixo comum, corte de texto;
  - escolha de faixa por idioma, `und`, só forçada, o mapa;
  - `estimate_disc`, inclusive a regressão com um título e sem menus;
  - reconciliação do `DiscChoices` (JSON inválido, perfil sumido, idiomas, fundo fora da lista,
    permutação inválida da ordem);
  - layout: área segura, paginação, setas, caixas pares que nunca se tocam, nenhum botão fora
    da tela, coordenadas letterbox;
  - render: subpictures com no máximo 4 cores e alfa só 0 ou 255, contraste do fundo (imagem
    branca), cor `auto`;
  - XML do dvdauthor: despachante que zera `g2`, `pre`/`post` de filmes e episódios, mapas,
    menu raiz, um titleset por título, 60 títulos dentro de 128 comandos, e que todo botão leva
    a um título ou menu existente, sobre planos de exemplo (filmes 1, 4, 6 e 7; série 13;
    16:9 e 4:3 misturados);
  - migração `0004` (conversão dos jobs antigos, jobs ativos viram `failed`);
  - rotas: salvar, mover, preview, criar, confirmações não gravadas.
- **`slow`:**
  - 3 clipes `lavfi` (dois 16:9 e um 4:3, com faixas de idiomas diferentes) viram um disco de
    série com menus; o ISO passa na QA automática; o tamanho dos menus fica dentro de 2 MiB por
    página; o PCI dos menus 16:9 tem os dois grupos de botões;
  - **navegação na libdvdnav** (via `ctypes`, só no estágio `test`): inserir o disco abre o menu
    com o foco certo; um filme volta ao menu com o botão dele; um episódio continua e depois volta;
    Menu e Title no meio de um título levam ao menu sem recomeçar nada; áudio e legenda escolhidos
    valem no título. É a navegação do VLC, não um player físico;
  - dvdauthor com 60 títulos minúsculos.
- QA manual no VLC e no player físico: no fim do projeto (decisão do Vini), incluindo a TV 4:3
  e o comportamento do menu raiz só com comando.

## Documentação

- README (EN e pt-BR): o disco com menu, uma captura do preview, como a navegação funciona.
- CLAUDE.md: 3.3 e 3.4 (o que foi feito), 5.1 (menus: geometria, letterbox, despachante, um
  titleset por título, 60 títulos), 7 (módulos `menus/` e `disc_plan.py`), 7.1 (`DiscProject`),
  7.2 (tela Montar DVD), 9 (QA com menus e o teste de navegação), Estado atual e Log de
  decisões.

## Ordem de entrega (grupos)

1. `DiscChoices`, `disc_project`, a migração `0004` (com a conversão dos jobs antigos) e o purge.
2. Nomes, ordem, tipo, escolha de faixas por idioma e a reconciliação.
3. `estimate_disc`.
4. Tema, layout e render dos menus (Pillow).
5. XML do dvdauthor com menus, despachante e letterbox.
6. `DiscPlan`/`TitlePlan` e pipeline com vários títulos e menus; QA ampliada.
7. Tela "Montar DVD", rotas e preview.
8. Testes `slow` (disco com menus e navegação na libdvdnav), documentação e smoke.

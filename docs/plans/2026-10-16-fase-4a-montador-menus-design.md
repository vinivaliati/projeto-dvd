# Fase 4a: Montador + menus DVD (design)

- **Data:** 2026-10-16
- **Branch:** `feat/fase-4a-montador-menus`
- **Status:** abordagem aprovada pelo Vini no chat; aguardando a revisão dos agentes e do Vini.

## Contexto e intenção

A Fase 4 do roadmap foi dividida em duas entregas (decisão do Vini):

- **4a, Montador + menus** (esta spec): uma pasta com vários vídeos vira um DVD com menu.
- **4b, Robustez:** retomar job, reaproveitar encode, copiar o vídeo de rip de DVD sem recodificar.

O fluxo continua o mesmo: o Vini monta **uma pasta por disco** com os filmes ou os episódios que
quer naquele disco. A pasta é a seleção, então todos os vídeos dela entram; ele só escolhe a ordem.

O que importa, nesta ordem (seção 1 do CLAUDE.md): o disco toca em qualquer player daqui a 20
anos (DVD-Video à risca), uma criança ou um idoso navega só com o controle, e o menu é bonito.

## Pronto quando

1. A tela "Montar DVD" de uma pasta escaneada lista todos os vídeos dela, com nome (do match
   confirmado no TMDB ou do arquivo), duração e ordem editável, e salva as escolhas no banco.
2. O Vini escolhe os idiomas de áudio e legenda **uma vez para o disco**; o app pega em cada
   título a melhor faixa de cada idioma e avisa, antes de gerar, o título que não tem um idioma.
3. A calculadora mostra o disco inteiro (todos os títulos, mesma qualidade do começo ao fim, com
   o espaço dos menus descontado), com os mesmos perfis, faixas de qualidade e confirmação no
   vermelho da Fase 3.
4. A tela mostra o **preview** de cada página do menu como imagem, e o Vini troca o fundo, a cor
   de destaque e o lado dos botões vendo o resultado na hora.
5. O job gera um ISO que, ao entrar no player, **abre o menu principal**:
   - disco de filmes: um botão por filme (o filme volta ao menu no fim, com o botão dele
     destacado) e "Áudio e legendas";
   - disco de série: "Tocar todos", "Episódios" (páginas de até 6) e "Áudio e legendas"; um
     episódio escolhido segue até o fim do disco e depois volta ao menu;
   - "Áudio e legendas" vale para o disco inteiro;
   - o botão Menu do controle volta ao menu principal em qualquer ponto.
6. O ISO passa na QA automática ampliada (todos os títulos, menus presentes, navegação conferida
   pelo XML gerado).
7. Sem token do TMDB tudo funciona, com fundo neutro e nomes tirados dos arquivos.
8. Uma pasta com um vídeo só também vira disco com menu ("Assistir" e "Áudio e legendas").
9. `make lint`, `make test` (cobertura de 100%) e `make test-slow` verdes; o teste `slow` gera
   um disco real com 3 clipes e menus.

## Fora de escopo

- Retomar job, reaproveitar encode, copiar rip de DVD (4b).
- Vários discos por pasta, boxes, dividir série em discos (Fase 7).
- Exceções de faixa por título (escolher a versão 2.0 em vez da 5.1 num título só).
- Menu de capítulos ("cenas"), menu com vídeo ou música (Fase 8), editor livre de tema.
- Tirar um vídeo da pasta pela tela (a pasta é a seleção; para tirar, o Vini move o arquivo).
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
  na imagem.

## Projeto de disco (banco, migração `0004`)

Tabela nova `disc_project`, uma linha por pasta:

| coluna | tipo | |
|---|---|---|
| `folder` | str, chave primária | nome da pasta (NFC) |
| `choices_json` | str | `DiscChoices` inteiro (Pydantic), como o `plan_json` do job |
| `updated_at` | datetime | |

`DiscChoices` (em `planner/disc_plan.py`):

```python
class Theme(BaseModel):
    backdrop: str | None      # caminho relativo a OUTPUT_DIR/covers, ou None (fundo neutro)
    accent: str               # "#rrggbb", de uma paleta fechada (ver Tema)
    side: Literal["left", "right"]

class DiscChoices(BaseModel):
    kind: Literal["movies", "series"]
    order: tuple[str, ...]    # caminhos dos vídeos (relativos a MEDIA_DIR)
    profile: str
    audio: tuple[str, ...]    # idiomas DVD ("pt", "en"), na ordem do disco; o 1º toca primeiro
    subtitles: tuple[str, ...]
    subtitle_on: str | None   # idioma ligado ao iniciar, ou None
    chapters: Literal["file", "every"]
    minutes: int
    theme: Theme
    confirm_low: bool = False
    replace_iso: bool = False
```

- Sem linha salva, a tela usa a sugestão; a linha é gravada a cada mudança do formulário (o mesmo
  `hx-post` que hoje atualiza a calculadora), então sair da tela não perde nada.
- `order` é reconciliado com a pasta ao abrir: caminhos que sumiram saem, vídeos novos entram no
  fim, na ordem sugerida. A ordem sugerida: episódios por temporada e episódio; filmes pelo ano do
  TMDB quando confirmado, senão pelo nome do arquivo (ordem natural, "2" antes de "10").
- `kind` sugerido: `series` quando todos os vídeos têm temporada e episódio (match confirmado ou
  `S01E03` no nome); senão `movies`. O Vini troca.
- Sem chave estrangeira para `media_file`: a pasta pode ser escaneada de novo sem apagar o projeto.

## Nome de cada título

- Match confirmado: filme pelo título pt-BR do TMDB; episódio por "N. Nome do episódio" (o nome
  genérico "Episódio N" vira só "Episódio N").
- Sem match confirmado: o título que o parser de nomes (`metadata/filename.py`) tira do arquivo;
  se ele não tirar nada, o nome do arquivo sem extensão.
- Nome do disco (topo do menu): série confirmada: "Nome da série" e "Temporada N" (se todos os
  episódios forem da mesma temporada); filme único confirmado: o título; vários filmes da mesma
  collection do TMDB: o nome da collection; senão o nome da pasta.
- Textos longos: quebra em até 2 linhas e reticências depois; a tela avisa quando cortou.

## Faixas por idioma

- Idiomas disponíveis: a união dos idiomas (código DVD, `dvd_language`) das faixas de áudio
  de todos os títulos; o mesmo para as legendas suportadas (texto).
- Sugestão de áudio: `pt` (se algum título tiver) e o idioma original (TMDB do primeiro título
  confirmado; senão a primeira faixa do primeiro título), como a Fase 3 faz para um título.
  O primeiro da lista toca ao colocar o disco (português, se houver).
- Sugestão de legenda: `pt`, ligada ao iniciar só se o áudio que toca primeiro não for português.
- Por título e idioma, a melhor faixa de áudio: mais canais; empate, a de índice menor; faixa
  com "coment" ou "comment" no título só se não houver outra.
- Por título e idioma, a legenda: a de texto não forçada; se só houver forçada, a forçada.
- Limites do disco nesta fase: **até 4 idiomas de áudio e 4 de legenda** (o menu "Áudio e
  legendas" cabe numa página só; uma coleção de família raramente passa disso). O formulário
  explica o limite. O padrão do DVD (8 e 32) continua valendo como teto técnico.
- **Título sem um idioma escolhido:**
  - áudio: no menu, escolher esse idioma toca, naquele título, a primeira faixa do disco que ele
    tem; a tela avisa "As Duas Torres não tem áudio em Inglês: toca em Português";
  - legenda: fica desligada naquele título; a tela avisa;
  - como isso funciona por dentro está em Navegação (o "mapa" de cada título).
- O conversor de áudio é o da Fase 3 (`audio_output`): copiar AC-3 compatível, senão converter.

## Calculadora com vários títulos

Mesma qualidade do começo ao fim: um bitrate de vídeo só para todos os títulos.

```
capacidade_disco = capacidade_útil(perfil) − menus_bytes
v = (capacidade_disco × 8 / 1,03 − Σ dur_i × (áudio_i + 10 × legendas_i)) / Σ dur_i
v ≤ 95% × min_i maxrate_i      (maxrate_i como na Fase 3, com as faixas do título i)
```

- `áudio_i` e `legendas_i` são os do título i (um título sem um idioma tem menos faixas).
- `menus_bytes`: 2 MiB por página de menu (fundo parado de alguns segundos em MPEG-2 de bitrate
  baixo, mais os botões), medido no teste `slow` e corrigido lá se a medida passar.
- `calculator.estimate` ganha uma versão para vários títulos (`estimate_disc`); com um título,
  o resultado é o mesmo de antes (teste de regressão).
- As faixas Ótima, Aceitável, Baixa e Não cabe, a sugestão de perfil e a confirmação no vermelho
  ficam como estão.

## Tema (`menus/theme.py`)

- **Fundo:** o `backdrop.jpg` de um dos títulos da pasta (os que a Fase 2 baixou em
  `OUTPUT_DIR/covers/<pasta>/`); sugestão: o do primeiro título (série: o da série). Sem arte:
  fundo neutro (gradiente escuro) com o nome do disco.
- **Logo:** o `logo.png` do mesmo título, se existir; senão o nome do disco em texto.
- **Cor de destaque:** paleta fechada de 6 cores legíveis sobre fundo escuro e dentro da faixa
  de TV (16 a 235), mais a cor extraída do fundo (a mais saturada com luminância suficiente,
  levada para a faixa de TV). A sugestão é a extraída. Paleta fechada para não existir escolha
  ilegível.
- **Lado:** botões à esquerda ou à direita; o fundo é escurecido por um gradiente do lado dos
  botões para o texto ficar legível em qualquer arte.
- Fonte: DejaVu Sans (já está na imagem), negrito no título dos botões. O `designer` pode propor
  outra fonte livre na revisão, desde que entre na imagem por pacote apt fixado.

## Layout e render (`menus/layout.py` puro, `menus/render.py` com Pillow)

- Desenho em 720x480 para menus 4:3, ou desenhado em 854x480 e reduzido para 720x480 anamórfico
  nos menus 16:9 (ver Pontos para o `tech-lead-midia`).
- **Área segura:** tudo dentro de 10% de margem (72 px de cada lado, 48 em cima e embaixo).
- **Botões:** texto de pelo menos 26 px de altura de maiúscula em 480 linhas; até 6 itens por
  página mais a linha de navegação (Anterior, Próxima, Voltar); altura de linha que permite ler a
  3 metros. Texto dos botões desenhado no fundo; o destaque é o subpicture.
- **Subpicture dos botões:** duas imagens indexadas com **no máximo 4 cores** cada (transparente,
  destaque, contorno, e uma livre), sem antialias (o spumux não tem meio-termo): `highlight`
  (botão com o foco) e `select` (no instante do Enter). O destaque é uma barra ou sublinhado na
  cor escolhida, nunca o texto redesenhado.
- **Páginas:**
  - filmes: principal (filmes + "Áudio e legendas"; mais de 6 filmes pagina);
  - série: principal ("Tocar todos", "Episódios", "Áudio e legendas") e páginas de episódios;
  - "Áudio e legendas": uma página com "Áudio: Português, Inglês" e "Legenda: Desligada,
    Português" e "Voltar"; some do menu principal quando o disco tem 1 áudio e 0 legendas.
- **Navegação pelas setas:** cima e baixo seguem a lista; esquerda e direita trocam de coluna
  quando existe (Áudio e legendas, linha Anterior/Próxima); nenhuma seta leva para fora.
- `render.py` devolve três imagens por página (`background.png`, `highlight.png`, `select.png`)
  e o preview (fundo + destaque no primeiro botão) para a tela.

## Navegação (`authoring/dvd/dvdauthor.py`)

Toda a navegação passa pelo **VMGM**, que pode pular para qualquer título do disco:

- **Registradores:**
  - `g0` = idioma de áudio escolhido (posição na lista do disco);
  - `g1` = legenda escolhida (0 desligada, senão a posição + 1);
  - `g2` = próximo título a tocar (0 = nenhum), para "Tocar todos" e para a série;
  - `g3` = botão a destacar ao voltar ao menu principal.
- **First play:** define `g0` e `g1` com as escolhas do formulário e pula para o menu principal.
- **Menus do VMGM:** a página principal, as de episódios e a de "Áudio e legendas". Cada botão
  é um comando (`g2 = ...; jump title N;`, `jump menu K;`, `g0 = i; ...`). O `<pre>` da página
  principal confere `g2`: se houver um próximo, pula para ele (é como o "continuar" funciona com
  títulos em titlesets diferentes). Ao voltar, o botão de `g3` fica destacado.
- **Títulos:** o `<pre>` de cada título aplica o "mapa" dele: converte `g0` e `g1` nas faixas
  que aquele título tem (`if (g0 == 1) audio = 0; ...`), por isso um título sem um idioma toca a
  primeira faixa do disco que ele tem. O `<post>`:
  - filme: `g2 = 0; g3 = <botão dele>; call vmgm menu 1;`
  - episódio: `g2 = <próximo, ou 0 no último>; call vmgm menu 1;`
- **Botão Menu do controle:** cada titleset tem um menu raiz só com comando, que volta ao menu
  principal do VMGM (`g2 = 0`).
- **Titlesets:** um por formato de vídeo. Os títulos 16:9 ficam num, os 4:3 noutro (o DVD exige o
  mesmo formato dentro de um titleset). Na prática, quase sempre um só.
- Até 99 títulos (limite do DVD); acima disso o formulário bloqueia.

## Job e pipeline

- `DiscPlan` substitui o `DvdPlan` no `plan_json`: os campos do disco (pasta, perfil, bitrate,
  volume, nome do ISO, tema, páginas de menu já calculadas com os textos) e uma tupla de
  `TitlePlan` (os campos por título do `DvdPlan` atual: caminho, tamanho, mtime, modo, aspecto,
  faixas, capítulos, mapa de idiomas).
- **Jobs antigos:** a migração `0004` converte o `plan_json` dos jobs existentes para o formato
  novo (um título, sem menu). A tela do job e a lista continuam abrindo jobs da Fase 3.
- **Etapas:** para cada título, as etapas da Fase 3 (vídeo em 2 passes, pulldown, áudio, mux,
  legendas); depois "Menus" (render, MPEG-2 do fundo, spumux dos botões), autoria, ISO, QA e
  cópia. A tela mostra "Título 2 de 3 · Vídeo: 2ª passada", e o peso de cada título no progresso
  é proporcional à duração.
- **Fundo do menu em vídeo:** o ffmpeg codifica o `background.png` como alguns segundos de
  MPEG-2 parado, com áudio AC-3 silencioso (players antigos tropeçam em menu sem áudio); o
  `spumux` adiciona os botões; o `<vob>` do menu fica em pausa infinita.
- **Fonte que mudou:** cada título é conferido antes do encode, como hoje.
- **Espaço:** o pico continua perto de 2 vezes o disco (os `.mpg` de todos os títulos mais a
  estrutura do DVD na autoria); a checagem do formulário fica como está.
- **QA automática**, além do que já existe (por título):
  - número de títulos no ISO igual ao do plano, e o `VIDEO_TS.VOB` dos menus presente;
  - para cada título: codec, resolução, aspecto, faixas, idiomas e duração (os checks da Fase 3,
    com `-title N`);
  - a navegação gerada: todo botão leva a um título ou menu que existe, toda página tem saída,
    e o `post` de cada título volta ao menu (conferido sobre o XML gerado, função pura);
  - a decodificação completa continua cobrindo o disco inteiro.

## Telas

- **Tela da pasta:** o botão "Gerar DVD" vira "Montar DVD"; o bloqueio "um vídeo só" some. A pasta
  continua bloqueada por arquivo ilegível ou não suportado (o motivo cita o arquivo).
- **"Montar DVD"** (substitui o formulário da Fase 3, mesma rota `/folders/{name}/dvd`):
  1. **Títulos:** lista na ordem do disco, com nome, duração, botões "subir" e "descer" (HTMX) e
     o tipo do disco (Filmes / Série).
  2. **Idiomas:** áudio e legenda por idioma, "toca primeiro", "ligada ao iniciar" e os avisos dos
     títulos sem um idioma.
  3. **Capítulos:** do arquivo ou a cada N minutos, para o disco todo.
  4. **Menu:** preview da página escolhida (imagem servida por rota, com cache pelo hash das
     escolhas), com o seletor de página, os fundos disponíveis (miniaturas), a paleta de cores e
     o lado.
  5. **Disco:** os cartões de perfil da Fase 3, agora com o disco inteiro, e "Gerar".
- Toda mudança salva o `DiscChoices` e atualiza a calculadora e o preview sem recarregar.
- Acessibilidade e estilo como nas telas atuais (rótulos, `aria-invalid`, 375 px sem rolagem
  horizontal).

### Rotas

| Rota | O que faz |
|---|---|
| `GET /folders/{name}/dvd` | a tela "Montar DVD" |
| `POST /folders/{name}/dvd/choices` | salva o formulário, devolve calculadora, avisos e preview |
| `POST /folders/{name}/dvd/move` | sobe ou desce um título |
| `GET /folders/{name}/dvd/menu.png?page=…&v=…` | o preview de uma página |
| `POST /folders/{name}/dvd` | valida, faz o preflight e cria o job |

## Erros e casos de borda

- Título sem duração ou com vídeo não suportado: a pasta fica bloqueada com o motivo e o arquivo.
- Arte apagada da pasta de saída depois de escolhida: o preview e o job caem no fundo neutro, com
  aviso no formulário.
- Pasta escaneada de novo com vídeo trocado: o `order` é reconciliado; o job usa tamanho e mtime.
- Nenhum idioma de áudio em comum: o Vini escolhe qualquer um da união; os títulos sem ele tocam
  a própria primeira faixa (aviso).
- Mais de 99 títulos, mais de 4 idiomas, nenhum áudio: erros no formulário, em português.
- Disco que não cabe: como hoje ("Não cabe" bloqueia; vermelho pede confirmação).

## Testes

- **Unitários:** sugestão de ordem e tipo; nomes dos títulos e do disco; escolha de faixa por
  idioma e o mapa; `estimate_disc` (inclusive a regressão com um título); layout (área segura,
  paginação, setas, nenhum botão fora da tela); subpictures com no máximo 4 cores e sem
  antialias; XML do dvdauthor (registradores, `pre`/`post`, titlesets por formato, menu raiz);
  checagem da navegação; migração `0004` dos jobs antigos; rotas (salvar, mover, preview, criar).
- **`slow`:** 3 clipes `lavfi` (dois 16:9 e um 4:3, com faixas de idiomas diferentes) viram um
  disco de série com menus; o ISO passa na QA automática; o tamanho dos menus confere com
  `menus_bytes`.
- QA manual no VLC e no player físico: no fim do projeto (decisão do Vini).

## Pontos para o `tech-lead-midia` confirmar na revisão

1. Menus 16:9 (com `widescreen="nopanscan"`) versus 4:3: botões do spumux corretos numa TV 4:3.
2. `call vmgm menu 1` no `post` dos títulos e o dispatch por `g2` no `pre` do menu principal.
3. Menu raiz de titleset só com comando (sem `vob`) aceito pelo dvdauthor e pelos players.
4. Mapa de idiomas no `pre` do título quando o titleset declara mais faixas que o VOB tem.
5. Fundo do menu: duração, GOP e bitrate do MPEG-2 parado; áudio silencioso.

## Documentação

- README (EN e pt-BR): o disco com menu, uma captura do preview, como a navegação funciona.
- CLAUDE.md: 3.3 e 3.4 (o que foi feito), 7 (módulos `menus/`, `disc_plan.py`), 7.1
  (`DiscProject`), 7.2 (tela Montar DVD), 9 (QA com menu), Estado atual e Log de decisões.

## Ordem de entrega (grupos)

1. `DiscChoices`, `disc_project` e a migração `0004` (com a conversão dos jobs antigos).
2. Nomes, ordem, tipo e escolha de faixas por idioma.
3. `estimate_disc`.
4. Tema, layout e render dos menus (Pillow).
5. XML do dvdauthor com menus e a checagem da navegação.
6. `DiscPlan` e pipeline com vários títulos e menus; QA ampliada.
7. Tela "Montar DVD", rotas e preview.
8. Teste `slow`, documentação e smoke.

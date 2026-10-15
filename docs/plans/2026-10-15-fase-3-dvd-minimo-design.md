# Fase 3: DVD mínimo (design)

- **Data:** 2026-10-15
- **Branch:** `feat/fase-3-dvd-minimo`
- **Status:** design aprovado pelo Vini no chat, seção por seção; aguardando a revisão dos agentes
  e do Vini.
- **Base técnica:** estudo do `tech-lead-midia`, com experimentos na imagem do projeto (Ryzen 5
  5500, 12 threads). Os parâmetros abaixo foram validados nesses experimentos.

## Contexto e intenção

O Vini quer ter um disco de verdade o quanto antes (por isso a Fase 3 vem antes da 2). O fluxo
continua o da Fase 1, **1 pasta = 1 disco**, com calma e um disco por vez. O app sugere tudo e o
Vini decide antes de gerar.

A Fase 3 entrega o caso mais simples completo: **uma pasta com um vídeo vira um ISO de DVD-Video
sem menu**, que toca o filme direto ao colocar o disco, com o perfil (DVD-5 ou DVD-9), os áudios,
as legendas e os capítulos escolhidos pelo Vini. O acervo dele mistura rips de Blu-ray 1080p e de
DVD 480p. Não há 4K, e o Vini decidiu que 4K/HDR não é necessário.

## Pronto quando

1. Numa pasta escaneada com um vídeo suportado, "Gerar DVD" abre o formulário com perfil,
   áudios, legendas e capítulos já sugeridos, e a calculadora mostra os dois perfis lado a lado.
2. "Gerar" cria um job; o serviço `worker` roda o pipeline e a tela do job mostra a etapa, o
   progresso, o tempo estimado e o log. "Cancelar" interrompe o ffmpeg.
3. O ISO aparece em `OUTPUT_DIR/iso/<pasta>.iso` **só depois de passar na QA automática**.
4. Fontes não suportadas são recusadas antes de criar o job, com o motivo na tela.
5. Teste `slow`: um clipe 1080p 23,976 com áudio AAC e SRT vira um ISO que passa na QA
   automática (inclusive soft pulldown, idiomas e capítulos); um clipe 480i 4:3 também.
6. **QA manual:** um ISO de um filme real do Vini abre no VLC e cumpre o checklist da seção 9 do
   `CLAUDE.md` (itens 1 a 3 automáticos; 4 e 5 adaptados a um disco sem menu, ver "QA manual").
7. Definição de pronto da seção 2.5 do `CLAUDE.md`.

O teste num player físico é a segunda etapa da fase e fica para quando o gravador for comprado.

## Fora de escopo

| Item | Quando |
|---|---|
| Menu, vários títulos por disco, episódios | Fase 4 |
| Retomar job e reaproveitar encode já feito | Fase 4 |
| Legendas PGS (imagem) e ASS/SSA com estilo | fase futura (receita do tech-lead registrada) |
| HDR10, HLG e Dolby Vision (tonemap para SDR) | fase futura, se aparecer 4K no acervo |
| PAL, 25 fps, 24 fps exato, fps variável, 1080i | fase futura, se aparecer |
| Blu-ray | Fase 6 |
| Gravar o disco | nunca (o Vini grava o ISO no Windows) |

## Decisões tomadas com o Vini

| Pergunta | Decisão |
|---|---|
| De onde sai o disco | Só de pasta com **um** vídeo; o botão "Gerar DVD" só aparece nela |
| Áudio e legendas | O app sugere português e o idioma original (legenda em português quando houver); o Vini ajusta antes de gerar |
| PGS | Fora da Fase 3; aparece como "ainda não suportada" |
| Margem de capacidade | 97% da capacidade mínima da mídia, menos 4 MiB (ajusta a seção 4 do `CLAUDE.md`, que dizia 95%) |
| PAL / 25 fps | Fora da Fase 3, com aviso |
| Legenda sem menu | O Vini escolhe por disco entre "ligada ao iniciar" e "só pelo controle"; o app sugere conforme o áudio padrão |
| Nome do ISO | `iso/<nome da pasta>.iso`, sem sobrescrever sem confirmação |
| HDR / 4K | Fora: "acho que não precisamos de 4K" |
| Execução | Worker em processo separado (abordagem 1) |

## Fontes suportadas

O formulário só abre (e o botão só fica habilitado) quando a fonte passa em todas as regras. Cada
recusa tem um texto na tela.

| Regra | Aceita | Recusa (texto na tela) |
|---|---|---|
| Vídeos na pasta | exatamente 1 | "Na Fase 3 o disco tem um vídeo só; vários títulos chegam com o menu" |
| Estado do scan | escaneado, sem erro, sem mudança | "Escaneie a pasta antes de gerar o disco" / "Arquivos mudaram: escaneie de novo" |
| Faixa de vídeo | existe | "Sem faixa de vídeo" |
| Cor | SDR | "HDR ainda não suportado" (inclui HLG e Dolby Vision) |
| Resolução | até 1920x1080 | "Acima de 1080p ainda não suportado" |
| Taxa de quadros | 24000/1001 progressivo; 30000/1001 (progressivo ou entrelaçado, este só em 720x480) | "25 fps (PAL) ainda não suportado", "24 fps exato ainda não suportado", "fps variável ainda não suportado", "1080i ainda não suportado" |
| Duração | conhecida | "Duração desconhecida" |
| Áudio | ao menos 1 faixa | "Sem faixa de áudio" |

**Detecção:**
- fps pelo `r_frame_rate` e pelo `avg_frame_rate`. Taxa variável quando os dois diferem em mais
  de 0,1%.
- Entrelaçado pelo `field_order` (`tt`, `bb`, `tb`, `bt`); `progressive` ou ausente conta como
  progressivo.
- 24 fps exato, 25 e 50 fps recusados pelo valor.

**Legendas** não bloqueiam o disco. Entram as de texto (SRT externa, `subrip`/`mov_text`/`text`
interna). PGS, `dvd_subtitle`, ASS/SSA, `.sup` e `.idx` aparecem cinzas, com "ainda não
suportada".

## Perfis e calculadora

### Perfis (`planner/profiles.py`)

Objetos de configuração imutáveis; adicionar um perfil é adicionar uma entrada.

| Campo | DVD-5 | DVD-9 |
|---|---|---|
| Setores (menor valor entre −R e +R) | 2.295.104 | 4.171.712 |
| Bytes | 4.700.372.992 | 8.543.666.176 |
| Margem | 97% | 97% |
| Reserva fixa (IFO, BUP, sistema de arquivos) | 4 MiB | 4 MiB |
| Overhead de mux | 3% | 3% |
| Verde / amarelo / vermelho | ≥ 5 / 3,5 a 5 / < 3,5 Mbps | igual |

### Fórmulas (`planner/calculator.py`, funções puras)

```
capacidade_util = 0,97 × bytes − 4 MiB
maxrate_video   = min(9000, 10080 − Σaudio_kbps − 40 × n_legendas − 300)        [kbps]
video_kbps      = (capacidade_util × 8 / 1,03 / duração_s) / 1000 − Σaudio_kbps − 10 × n_legendas
video_kbps      = min(video_kbps, maxrate_video)
tamanho_estimado = (video_kbps + Σaudio_kbps + 10 × n_legendas) × 1000 × duração_s × 1,03 / 8 + 4 MiB
```

- `Σaudio_kbps` usa o bitrate de saída de cada faixa: o da origem quando é cópia, 448 ou 192
  quando é conversão.
- A cor sai do `video_kbps`. Se `video_kbps` for menor que 1000, o perfil é inviável ("não cabe")
  e não pode ser escolhido.
- **Perfil sugerido:** o primeiro verde na ordem DVD-5, DVD-9; se nenhum ficar verde, o DVD-9.
- **Exemplo de referência (teste):** filme de 2 h com uma faixa AC-3 de 448k: DVD-5 ≈ 4,46 Mbps
  (amarelo), DVD-9 ≈ 8,48 Mbps (verde).

## Plano do disco (`planner/dvd_plan.py`)

`DvdPlan` é um valor imutável e serializável (vai inteiro para o job). Contém:

- pasta, caminho relativo do vídeo, `size` e `mtime_ns` no momento da criação;
- perfil escolhido e `video_kbps` calculado;
- modo de vídeo: `film` (23,976 com soft pulldown), `progressive` (29,97 progressivo) ou
  `interlaced` (29,97 entrelaçado, só fonte 720x480), com o `field_order`;
- aspecto de saída (`16:9` ou `4:3`) e a altura útil `H` (letterbox);
- áudios: índice do stream, idioma (código de 2 letras do DVD), ação (`copy` ou `ac3`), canais e
  bitrate de saída; o padrão vai **primeiro** (no DVD sem menu, a primeira faixa é a que toca);
- legendas: origem (stream interno ou arquivo externo), idioma, e se a primeira fica ligada ao
  iniciar;
- capítulos em segundos (o `0` sempre incluso);
- `confirmed_red` (o Vini confirmou o vermelho);
- nome do volume e caminho final do ISO.

### Regras de sugestão

- **Áudio:** marcar as faixas em português (`por`, `pt`, `pt-BR`) e as do idioma original
  (aproximado como o idioma da primeira faixa de áudio da origem). Sem nenhuma em português, a
  sugestão é só a original. Padrão sugerido: português, se houver. Faixas com o mesmo idioma: só
  a de mais canais é marcada. Máximo de 8 faixas no DVD.
- **Ação do áudio:** `copy` se o codec é `ac3`, 48 kHz, até 448 kbps e até 6 canais. Senão,
  `ac3` com 448k e 6 canais quando a origem tem 3 canais ou mais, e 192k com 2 canais nos outros
  casos. Uma fonte estéreo nunca vira 5.1.
- **Legenda:** marcar as em português. "Ligada ao iniciar" é sugerido quando o áudio padrão não é
  português; "só pelo controle" quando é. Máximo de 32 faixas.
- **Capítulos:** os do arquivo, se houver pelo menos 2; senão, a cada 5 minutos. Mais de 99: os
  do arquivo viram "a cada N minutos" com o menor N inteiro que cabe em 99 (e o formulário avisa).
- **Idiomas:** os códigos de 3 letras do ffprobe (`por`, `eng`, `spa`...) viram os de 2 letras
  que o dvdauthor espera, por uma tabela pequena (ISO 639-2 → 639-1). Desconhecido ou `und`: a
  faixa entra sem `lang`. Em legenda externa, o trecho do nome (`pt-BR`, `en`) é lido da mesma
  forma.
- **Nome do volume:** nome da pasta sem acentos (NFKD), maiúsculas, tudo que não for `A-Z0-9`
  vira `_`, `_` repetidos colapsados, até 32 caracteres; vazio vira `DVD`.

## Pipeline de mídia

Todas as linhas de comando saem de **funções puras** (`encode/`, `authoring/dvd/`) que devolvem
listas de argumentos; o `jobs/pipeline.py` só executa. Nunca shell. Intermediários em
`WORK_DIR/jobs/<id>/`.

### 1. Vídeo (MPEG-2, 2 passes)

Passe 1 com `-pass 1 -f null -`, passe 2 com `-pass 2`, saída `video.m2v`:

```
-vf "<escala>,<cor>,pad=720:480:(720-W)/2:(480-H)/2:black,setsar=<sar>"
-c:v mpeg2video -b:v <video_kbps>k -maxrate <maxrate_video>k -bufsize 1835k
-g 12 -bf 2 -flags +cgop -sc_threshold 1000000000
-dc 10 -intra_vlc 1 -non_linear_quant 1 -qmin 1 -qmax 28
-mbd rd -trellis 1 -cmp 2 -subcmp 2 -aspect <16:9|4:3>
-bsf:v mpeg2_metadata=colour_primaries=6:transfer_characteristics=6:matrix_coefficients=6
-an -sn -progress pipe:1
```

- **Proibido `-target ntsc-dvd`**: ele duplica quadros inteiros (tranco a cada 4º quadro).
- **Escala:** `scale=W:H:flags=lanczos+accurate_rnd+full_chroma_int`.
  - DAR ≥ 1,5: saída 16:9 (SAR 32/27); `W = 720`, `H = round(480 × (16/9) / DAR)`, par, no
    máximo 480. Ex.: 1920x800 (2,40:1) dá H = 356; 1920x1080 dá H = 480.
  - DAR < 1,5: saída 4:3 (SAR 8/9); `H = round(480 × (4/3) / DAR)` limitado a 480; se DAR < 4/3,
    `H = 480` e `W = round(720 × DAR / (4/3))`, par (pillarbox).
- **Cor:** fonte HD (altura > 576) recebe `colorspace=all=smpte170m:iall=bt709` **depois** da
  escala (antes custaria 10 vezes mais tempo). Fonte SD já é BT.601 e não leva o filtro.
- **Modo `film`** (23,976): encode a 24000/1001; depois o patcher (abaixo).
- **Modo `progressive`** (29,97p): encode a 30000/1001, sem patch.
- **Modo `interlaced`** (480i): sem escala vertical, encode com `-flags +ilme+ildct` e `-top 1`
  (TFF) ou `-top 0` (BFF), conforme o `field_order`.

### 2. Soft pulldown (`encode/pulldown.py`)

O ffmpeg sozinho não grava as flags RFF. Patcher próprio no estilo DGPulldown, sobre o `.m2v`
**in-place via `mmap`** (o arquivo pode ter 8 GB; o tamanho não muda):

- no `sequence_header`: `frame_rate_code` de 1 (23,976) para 4 (29,97);
- no `sequence_extension`: `progressive_sequence = 0`;
- em cada `picture_coding_extension`: `top_field_first` e `repeat_first_field` no ciclo
  `T1 B0 B1 T0` (TFF=1,RFF=1; TFF=0,RFF=0; TFF=0,RFF=1; TFF=1,RFF=0), indexado pela **ordem de
  exibição** (`temporal_reference` mais a base do GOP), não pela ordem no arquivo.

Validação: 1439 imagens viram 720 com RFF, 3598 campos, nenhuma quebra de paridade; o dvdauthor
lê 29,97. Plano B, se um player físico falhar: hard telecine (custa bitrate e mostra pente em TV
sem IVTC). O `time_code` do GOP fica na escala de 24p (players ignoram; conferir no player
físico).

### 3. Áudio (`encode/audio.py`)

Um arquivo `.ac3` por faixa: `-map 0:<índice> -c:a copy` ou
`-c:a ac3 -b:a <448k|192k> -ar 48000 -ac <6|2>`, com `-vn -sn`.

### 4. Legendas (`authoring/dvd/spumux.py`)

- Legenda interna de texto: extraída com `-map 0:<índice> -c:s srt`.
- SRT externa: lida como UTF-8 (com ou sem BOM); se não for UTF-8 válido, como Windows-1252
  (comum em legendas brasileiras). Regravada em UTF-8 no diretório do job; o arquivo original
  nunca é tocado.
- `spumux -s <n>` uma vez por faixa, depois do mux, com:

```xml
<subpictures format="NTSC"><stream>
  <textsub filename="sub<n>.srt" characterset="UTF-8"
    font="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    fontsize="26.0" fill-color="white" outline-color="black" outline-thickness="2.5"
    horizontal-alignment="center" vertical-alignment="bottom"
    left-margin="72" right-margin="72" top-margin="48" bottom-margin="48"
    movie-fps="29.97" subtitle-fps="29.97" movie-width="720" movie-height="478"
    aspect="<16:9|4:3>"/>
</stream></subpictures>
```

  Os dois fps ficam iguais: os tempos do SRT são absolutos, e um fps diferente esticaria as
  legendas (com 23,976 contra 29,97, 25% de erro).
- Tags como `<i>` são descartadas pelo spumux (texto sem itálico).

### 5. Mux

```
ffmpeg -fflags +genpts -i video.m2v -i audio1.ac3 [...] -map 0 -map 1 [...] -c copy
       -f dvd -muxrate 10080k -packetsize 2048 movie.mpg
```

Sem `+genpts` o ffmpeg grava só 2 nav packs e todos os capítulos caem em 0.

### 6. dvdauthor (`authoring/dvd/dvdauthor.py`)

```xml
<dvdauthor dest="dvd">
  <vmgm>
    <fpc>jump title 1;</fpc>
    <menus><video format="ntsc" aspect="16:9"/></menus>
  </vmgm>
  <titleset><titles>
    <video format="ntsc" aspect="16:9" widescreen="nopanscan"/>
    <audio lang="pt"/> ...
    <subpicture lang="pt"/> ...
    <pgc>
      <pre>subtitle=64;</pre>            <!-- só com "ligada ao iniciar" -->
      <vob file="movie.mpg" chapters="0,5:00,10:00,..."/>
    </pgc>
  </titles></titleset>
</dvdauthor>
```

- O `<vmgm>` sempre declara o formato (regra da seção 5.1 do `CLAUDE.md`).
- Fonte 4:3: `aspect="4:3"` e sem `widescreen`.
- Faixa sem idioma: `<audio/>` ou `<subpicture/>` sem `lang`.
- `subtitle=64` liga a primeira legenda (64 = exibir + faixa 0). Com "só pelo controle", não há
  `<pre>`. **A confirmar no VLC** (item da QA manual); se o VLC ignorar, conferir no player
  físico antes de mudar.
- Capítulos no formato `h:mm:ss.fff`; o dvdauthor alinha ao VOBU mais próximo (~0,5 s).

### 7. ISO

`genisoimage -dvd-video -udf -V <VOLUME> -o work/<id>/disc.iso work/<id>/dvd`. O ISO fica no
diretório do job até passar na QA.

### 8. QA automática (`jobs/qa.py`)

Roda sobre o ISO no diretório do job. Qualquer item reprovado faz o job terminar como `failed`,
com o motivo; o ISO fica em `/work` para inspeção e **não** é copiado para `/output`.

1. Tamanho do ISO ≤ setores do perfil × 2048 (limite duro da mídia, não a margem).
2. Árvore: `VIDEO_TS.IFO`, `VIDEO_TS.BUP`, `VTS_01_0.IFO`, `VTS_01_0.BUP`, ao menos um
   `VTS_01_1.VOB`, e nada de VOB acima de 1 GiB.
3. `ffprobe -f dvdvideo -title 1 disc.iso` (JSON): `mpeg2video`, 720x480, DAR do plano,
   `30000/1001`, uma faixa `ac3` por áudio e uma `dvd_subtitle` por legenda, na ordem e com o
   idioma do plano; capítulos com os inícios do plano (tolerância de 1 s); duração igual à da
   origem com tolerância de 1 s.
4. Bitstream do `video.m2v` (funções puras, lendo em streaming): `frame_rate_code=4`,
   `aspect_ratio_information` do plano, GOP fechado com no máximo 12 imagens, e no modo `film` a
   continuidade de campos sem quebra de paridade.
5. Decode completo: `ffmpeg -v error -f dvdvideo -i disc.iso -f null -`; qualquer linha em stderr
   reprova.

Aprovado: o ISO é copiado para `OUTPUT_DIR/iso/<pasta>.iso.part` e renomeado para
`<pasta>.iso` no fim (nunca fica um ISO pela metade com o nome final). O resultado de cada item
fica no job.

### Progresso e tempo estimado

- O ffmpeg roda com `-progress pipe:1 -nostats`; o worker lê `out_time_us` e calcula a fração da
  etapa pela duração da origem. O tempo estimado vem da velocidade média da etapa.
- Etapas e peso no progresso geral: `video_pass1` (35), `video_pass2` (45), `pulldown` (2),
  `audio` (5), `subtitles` (2), `mux` (4), `author` (2), `iso` (2), `qa` (3). Etapas sem
  progresso próprio contam inteiras ao terminar.
- O worker grava `step` e `progress` no banco no máximo uma vez por segundo.

### Tempo esperado

| Fonte | Filme de 2 h |
|---|---|
| 1080p H.264 | 20 a 30 min |
| DVD 480p | menos de 15 min |

## Jobs e worker

### Banco (migração `0002`)

Tabela `job`:

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int | chave |
| `folder` | str | pasta de disco (NFC), indexado |
| `path` | str | caminho relativo do vídeo |
| `size`, `mtime_ns` | int | do vídeo quando o job foi criado |
| `plan_json` | str | o `DvdPlan` completo, inclusive `confirmed_red` |
| `status` | str | `queued`, `running`, `done`, `failed`, `canceled` |
| `cancel_requested` | bool | pedido de cancelamento pela tela |
| `step` | str ou nulo | etapa atual |
| `progress` | float | 0 a 1 |
| `eta_seconds` | int ou nulo | |
| `error` | str ou nulo | motivo da falha, em português |
| `qa_json` | str ou nulo | resultado de cada item da QA |
| `iso_path` | str ou nulo | caminho final no `/output` |
| `created_at`, `started_at`, `finished_at` | datetime | UTC |

Log de cada job em `WORK_DIR/jobs/<id>/job.log` (comandos, stderr do ffmpeg, saída do
dvdauthor e do genisoimage). O banco guarda só o estado.

### SQLite com dois processos

`journal_mode=WAL` e `busy_timeout=5000` em toda conexão (evento `connect` do engine). WAL
funciona porque o banco está no volume `data` (ext4), não em `/mnt/c`.

### Worker (`python -m projeto_dvd.jobs.worker`)

- Espera a migração do `web` (confere a revisão do Alembic a cada 2 s); o worker nunca migra.
- **No startup:** jobs `running` viram `failed` com "O worker reiniciou no meio do job"
  (retomar fica para a Fase 4).
- **Loop:** a cada 2 s pega o job `queued` mais antigo com um `UPDATE ... WHERE status =
  'queued'` atômico; um job por vez.
- **Antes de começar:** confere `size` e `mtime_ns` do vídeo; diferente ou sumido (HD
  desconectado), falha com "O arquivo mudou ou não está acessível desde que o job foi criado".
- **Cancelar:** enquanto um processo roda, o worker confere `cancel_requested` a cada segundo;
  se pedido, manda SIGTERM, espera 10 s e manda SIGKILL. O job vira `canceled`, o log fica, o
  `.iso.part` é apagado. Um job `queued` cancelado vira `canceled` na hora, pela própria rota.
- **Erro de ferramenta:** código de saída diferente de 0 vira `failed` com a etapa e as últimas
  linhas do stderr.
- **SIGTERM no worker** (`docker compose stop`): cancela o processo filho e marca o job como
  `failed` ("worker parado").
- Processos filhos com `start_new_session=True`, para o kill alcançar o grupo inteiro.

### Compose e imagem

- Serviço `worker`: mesma imagem (`target: runtime`), `command: python -m
  projeto_dvd.jobs.worker`, `init: true`, mesmos volumes (`/media:ro`, `/work`, `/output`,
  `data`), sem porta.
- `Dockerfile`: `genisoimage=9:1.1.11-4`. Sem mjpegtools e sem lsdvd.
- `Settings` ganha `work_dir` (padrão `/work`) e `output_dir` (padrão `/output`).

### Checagens antes de criar o job

- `WORK_DIR` e `OUTPUT_DIR` existem e aceitam escrita (cria e apaga um arquivo de teste). Falha:
  "Não dá para gravar em /work. A pasta foi criada pelo Docker como root? Veja o README".
- Espaço livre em `WORK_DIR` ≥ 3 × tamanho estimado + 1 GiB (m2v, mpg e VIDEO_TS convivem até o
  ISO, e o ISO é mais uma cópia). Espaço livre em `OUTPUT_DIR` ≥ tamanho estimado + 100 MiB.
  Falha mostra quanto falta.
- Já existe job `queued` ou `running` para a pasta: a tela da pasta e o formulário levam a ele em
  vez de criar outro.
- `OUTPUT_DIR/iso/<pasta>.iso` já existe: o formulário exige marcar "Substituir o ISO existente".

## Telas

Mesmo visual da Fase 1 (CSS próprio, tema escuro, HTMX, sem build). Textos em português.

### Tela da pasta (`GET /folders/{name}`)

- Fonte suportada: botão principal **"Gerar DVD"**.
- Fonte recusada: botão desabilitado com o motivo ao lado.
- Mais de um vídeo: a frase "Na Fase 3 o disco tem um vídeo só; vários títulos chegam com o
  menu".
- Job existente da pasta: link "Ver o job (status)".

### Formulário (`GET /folders/{name}/dvd`, `POST /folders/{name}/dvd`)

- Topo: nome do arquivo, duração, resolução, fps.
- **Perfil:** dois cartões (DVD-5, DVD-9) com tamanho estimado, bitrate de vídeo e cor; selo
  "sugerido"; escolha obrigatória (radio, já marcado no sugerido).
- **Áudio:** checkbox por faixa (idioma, canais, codec, "copiar" ou "converter para AC-3
  448k/192k"), radio do padrão.
- **Legendas:** checkbox por faixa suportada; as não suportadas cinzas com o motivo; radio
  "ligada ao iniciar" / "só pelo controle".
- **Capítulos:** "do arquivo (N)" ou "a cada [5] minutos".
- **Calculadora** no rodapé do formulário, atualizada por HTMX
  (`POST /folders/{name}/dvd/estimate`, `hx-trigger="change"`) sem recarregar a página.
- **Vermelho:** checkbox obrigatória "Entendo que a qualidade vai ficar baixa e quero gerar mesmo
  assim".
- Erros de validação (nenhum áudio, mais de 8, perfil inviável, espaço insuficiente, vermelho
  sem confirmação, ISO existente sem confirmação) voltam o formulário com a mensagem, sem perder
  as escolhas.
- Sucesso: redireciona (`303`) para `/jobs/{id}`.

### Job (`GET /jobs/{id}`)

- Lista de etapas (feita, em andamento, a fazer), barra de progresso, tempo estimado.
- Enquanto `queued` ou `running`: o fragmento se atualiza a cada 2 s
  (`hx-get` + `hx-trigger="every 2s"`), parando quando o job termina.
- `queued` há mais de 1 minuto: "Aguardando o worker. Confira se o serviço está rodando
  (`docker compose ps`)".
- Log num `<details>` com as últimas 200 linhas.
- Botão **Cancelar** (`POST /jobs/{id}/cancel`, com `hx-confirm`).
- `done`: caminho do ISO no Windows (montado a partir de `HOST_OUTPUT_DIR`, se definido; senão o
  caminho do container), resultado da QA automática e o checklist manual.
- `failed`: o motivo e a etapa.
- Terminado (qualquer status): botão **"Apagar intermediários (X GB)"**
  (`POST /jobs/{id}/clean`, com `hx-confirm`); apaga `WORK_DIR/jobs/<id>/` inteiro menos o
  `job.log`.

### Lista (`GET /jobs`)

Tabela com pasta, perfil, status, data e link. Link "Jobs" no topo de todas as telas.

## Segurança

- **Mesma origem nos POSTs que gravam** (criar job, cancelar, apagar intermediários, estimar):
  aceita se `Sec-Fetch-Site` é `same-origin` ou `none`; sem esse cabeçalho, se o `Origin` bate
  com o host da requisição; senão `403`. Protege contra um site aberto no navegador disparando
  ações no app local. Fecha a reavaliação de CSRF da Fase 1.
- Pastas resolvidas como na Fase 1 (nome exato de subpasta real, não-link, de `/media`).
  Arquivos e índices de faixa vêm do banco e do ffprobe, nunca de caminho enviado pelo
  formulário: o formulário manda só índices, validados contra o resumo.
- `jobs/<id>` resolvido a partir do `id` inteiro do banco; a limpeza só apaga dentro de
  `WORK_DIR/jobs/<id>/`.
- Comandos sempre por lista de argumentos e caminhos absolutos.
- `/media` continua `ro`.

## Erros e casos de borda

| Caso | Comportamento |
|---|---|
| Arquivo mudou entre o formulário e o worker | job `failed` com motivo claro |
| HD externo desconectado no meio do encode | ffmpeg falha; job `failed` com a etapa e o stderr |
| Disco do WSL cheio no meio | ferramenta falha; `failed` com o stderr ("No space left") |
| `/output` cheio na cópia do ISO | `.iso.part` apagado; `failed`; o ISO continua em `/work` |
| Dois cliques em "Gerar" | o segundo POST encontra o job ativo da pasta e redireciona para ele |
| Worker não está rodando | job fica `queued` com o aviso da tela |
| SRT com encoding estranho | UTF-8, senão Windows-1252 (sempre decodifica) |
| SRT vazia ou inválida | spumux falha; `failed` com a saída do spumux |
| Capítulos do arquivo depois do fim do vídeo | descartados |

## Testes

`pytest` padrão continua com `-m "not slow"`, cobertura com ramos, mínimo de 90% (meta 100%).

| Área | Testes |
|---|---|
| Perfis e calculadora | exemplo de 2 h nos dois perfis; fronteiras 3,5 e 5 Mbps; teto do maxrate; inviável; sugestão |
| `Summary` | campos novos (`field_order`, `pix_fmt`, `r_frame_rate`, `avg_frame_rate`, `color_*`, índice, `sample_rate`, `bit_rate`, canais) pelas fixtures |
| Suporte da fonte | cada recusa da tabela e o caso aceito; 1080p 23,976, 480i 29,97, 480p 23,976 |
| `DvdPlan` | sugestão de áudio (pt + original, sem pt, idiomas repetidos, limite 8), copiar vs converter (cada condição), estéreo nunca vira 5.1, legendas, capítulos (do arquivo, automáticos, mais de 99, depois do fim), idiomas 3→2 letras, nome do volume (acento, símbolos, 32 caracteres, vazio), serialização ida e volta |
| Comandos | listas de argumentos dos 2 passes por modo (`film`, `progressive`, `interlaced`), escala e letterbox (2,40, 1,85, 16:9, 4:3, mais estreito que 4:3), cor só em HD, áudio, extração de legenda, mux, genisoimage |
| Pulldown | bytes sintéticos: frame_rate_code, progressive_sequence, ciclo por ordem de exibição com B-frames, GOPs consecutivos, arquivo sem sequence header falha |
| XML | dvdauthor (16:9, 4:3, sem idioma, legenda ligada ou não, capítulos) e spumux; XML escapado |
| SRT | UTF-8, UTF-8 com BOM, Windows-1252 |
| QA | cada item aprovando e reprovando, sobre JSON e bytes de fixture |
| Worker | pega o mais antigo, um por vez, recuperação no startup, arquivo mudou, cancelar queued e running, erro de ferramenta, SIGTERM, progresso (parser do `-progress`) |
| Rotas | botão por estado da pasta, formulário com sugestões, estimate, validações, mesma origem (403), redirecionamento, job em cada status, cancel, clean, lista; nada escrito em `/media` |
| Banco | migração 0002, modelos batem com as migrações, WAL ligado |
| Integração (`slow`, na imagem) | clipe 1080p 23,976 com 2 áudios (AAC 5.1 e AC-3 2.0), SRT externa em Windows-1252 e capítulos vira ISO pelo pipeline real e passa na QA (inclusive paridade de campos); clipe 720x480 entrelaçado 4:3 idem; um job cancelado no meio do passe 1 deixa o processo morto e o status `canceled` |

CI: o job `docker` passa a rodar os novos testes `slow`, e o smoke do compose sobe também o
`worker` (confere que ele está de pé e que o `web` mostra a lista de jobs vazia).

### QA manual (fecha a primeira etapa da fase)

Com um filme real do Vini, numa pasta de teste:
1. o VLC abre o ISO (Mídia, Abrir disco, "sem menus de disco" desmarcado) e o filme começa
   sozinho;
2. capítulos pulam com "próximo";
3. áudio e legenda trocam pelos menus do VLC; a legenda começa ligada ou desligada conforme a
   escolha;
4. panorâmicas sem tranco nem pente (soft pulldown);
5. cores e faixas pretas corretas; legenda legível e dentro da tela;
6. a duração bate com a do arquivo original.

## Documentação

- `README.md` e `README.pt-BR.md`: como gerar um DVD, o serviço `worker`, o que é suportado na
  Fase 3, onde o ISO aparece, como gravar no Windows, a pasta de trabalho e a limpeza.
- `CLAUDE.md`: seção 4 (margem de 97% e capacidades em setores), 5.1 (parâmetros validados,
  soft pulldown resolvido), 6 (`genisoimage` entra), 6.1 (`WORK_DIR`, `OUTPUT_DIR`), 13 (soft
  pulldown, checagem de escrita e campos do `Summary` resolvidos), Estado atual e Log de
  decisões.
- `.env.example`: `HOST_WORK_DIR` precisa estar no ext4 do WSL (já documentado) e ter espaço
  (até ~3 vezes o tamanho do disco).

## Ordem de entrega (grupos)

1. Perfis, calculadora, campos novos do `Summary`, suporte da fonte e `DvdPlan` (puro).
2. Comandos de encode, patcher de pulldown, XMLs, SRT e QA (puros), com o teste `slow` de ponta
   a ponta chamando um pipeline síncrono; `genisoimage` no Dockerfile.
3. Jobs: migração 0002, WAL, worker, cancelamento, recuperação; serviço no compose.
4. Telas: botão na pasta, formulário com calculadora, job, lista, mesma origem.
5. CI, documentação e QA manual com o Vini.

## Para o Log de decisões (fim da fase)

- MPEG-2 pelo ffmpeg em 2 passes com os parâmetros desta spec; proibido `-target ntsc-dvd`.
- Soft pulldown por patcher próprio (estilo DGPulldown, `mmap` in-place, testado por paridade
  de campos); mpeg2enc descartado (lento, sem alvo de tamanho). Fecha o item da seção 13.
- 29,97i (só 480i) codificado entrelaçado, sem patch.
- Cor: escala com lanczos e depois `colorspace` para BT.601 só em fonte HD; tags via
  `mpeg2_metadata`.
- Áudio só AC-3: copiar se ≤ 448k, 48 kHz e ≤ 6 canais; senão 448k 5.1 ou 192k 2.0.
- Mux com `ffmpeg -f dvd -fflags +genpts`; ISO com `genisoimage -dvd-video -udf`.
- Capacidade pelo menor valor entre −R e +R, em setores, com margem de 97% menos 4 MiB.
- Legendas SRT/texto via spumux; PGS, HDR, PAL e 4K adiados.
- Worker em processo separado, SQLite em WAL, um job por vez; retomar fica para a Fase 4.
- ISO só vai para `/output` depois de passar na QA automática.
- POSTs que gravam conferem a mesma origem.

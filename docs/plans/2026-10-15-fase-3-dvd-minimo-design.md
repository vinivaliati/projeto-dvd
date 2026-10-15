# Fase 3: DVD mínimo (design)

- **Data:** 2026-10-15
- **Branch:** `feat/fase-3-dvd-minimo`
- **Status:** design aprovado pelo Vini no chat, seção por seção; revisado por `tech-lead-midia`,
  `qa`, `revisor-codigo`, `designer` e `organizador` (achados incorporados); aguardando a revisão
  do Vini.
- **Base técnica:** estudo do `tech-lead-midia`, com experimentos na imagem do projeto (Ryzen 5
  5500, 12 threads). Os parâmetros abaixo foram validados nesses experimentos e na revisão.

## Contexto e intenção

O Vini quer ter um disco de verdade o quanto antes (por isso a Fase 3 vem antes da 2). O fluxo
continua o da Fase 1, **1 pasta = 1 disco**, com calma e um disco por vez. O app sugere tudo e o
Vini decide antes de gerar.

A Fase 3 entrega o caso mais simples completo: **uma pasta com um vídeo vira um ISO de DVD-Video
sem menu**, que toca o filme direto ao colocar o disco, com o perfil (DVD-5 ou DVD-9), os áudios,
as legendas e os capítulos escolhidos pelo Vini. O acervo dele mistura rips de Blu-ray 1080p e de
DVD 480. Não há 4K, e o Vini decidiu que 4K/HDR não é necessário.

Para entregar isso, a fase traz para frente uma parte do que o roadmap punha na Fase 4: a
calculadora com os dois perfis (para um título), a escolha de faixas e a fila de jobs com
progresso. A Fase 4 fica com vários títulos, menus, retomar e reaproveitar encode (ver
"Documentação", seção 12).

## Pronto quando

1. Numa pasta escaneada com um vídeo suportado, "Gerar DVD" abre o formulário com perfil,
   áudios, legendas e capítulos já sugeridos, e os cartões dos dois perfis mostram a qualidade de
   cada um.
2. "Gerar DVD" cria um job; o serviço `worker` roda o pipeline e a tela do job mostra a etapa, o
   progresso, o tempo restante e o log. "Cancelar" interrompe a geração.
3. O ISO aparece em `OUTPUT_DIR/iso/<pasta>.iso` **só depois de passar na QA automática**.
4. Fontes não suportadas são recusadas antes de criar o job, com todos os motivos na tela.
5. Testes `slow` (na imagem): os clipes da seção "Testes" viram ISOs pelo pipeline real e passam
   na QA automática; um ISO estragado de propósito reprova.
6. CI: o smoke do compose gera um ISO de verdade pela tela, com `web` e `worker` juntos.
7. **QA manual** (dois momentos, ver "QA manual"): um filme real do Vini (um rip de Blu-ray e,
   se houver, um rip de DVD) abre no VLC e cumpre o checklist; o resultado fica registrado no PR.
8. Definição de pronto da seção 2.5 do `CLAUDE.md`.

O teste num player físico é a segunda etapa da fase e fica para quando o gravador for comprado.

## Fora de escopo

| Item | Quando |
|---|---|
| Menu, vários títulos por disco, episódios | Fase 4 |
| Retomar job e reaproveitar encode já feito | Fase 4 |
| Copiar sem recodificar o vídeo de um rip de DVD (evita perder uma geração) | Fase 4 ou antes (registrado no Log) |
| Idioma original pelo TMDB (hoje: o da primeira faixa de áudio) | Fase 2 |
| Legendas PGS, VobSub (`dvd_subtitle`, `.idx/.sub`), ASS/SSA com estilo | fase futura, junto com o PGS |
| HDR10, HLG e Dolby Vision (tonemap para SDR), acima de 1080p | fase futura, se aparecer 4K no acervo (receita do tech-lead registrada) |
| PAL, 25 fps, 24 fps exato, 29,97 progressivo, 59,94, fps variável, 1080i | fase futura, se aparecer |
| Blu-ray | Fase 6 |
| Gravar o disco | nunca (o Vini grava o ISO no Windows) |

## Decisões tomadas com o Vini

| Pergunta | Decisão |
|---|---|
| De onde sai o disco | Só de pasta com **um** vídeo; o "Gerar DVD" só aparece nela |
| Áudio e legendas | O app sugere português e o idioma original (legenda em português quando houver); o Vini ajusta antes de gerar |
| PGS | Fora da Fase 3; aparece como "ainda não suportada" |
| Margem de capacidade | 97% da capacidade mínima da mídia, menos 4 MiB (ajusta a seção 4 do `CLAUDE.md`, que dizia 95%) |
| PAL / 25 fps | Fora da Fase 3, com aviso |
| Legenda sem menu | O Vini escolhe por disco qual legenda liga ao iniciar, ou nenhuma; o app sugere conforme o áudio |
| Nome do ISO | `iso/<nome da pasta>.iso`, sem sobrescrever sem confirmação |
| HDR / 4K | Fora: "acho que não precisamos de 4K" |
| Execução | Worker em processo separado (abordagem 1) |
| VobSub e ASS | Fora da Fase 3, como o PGS; para esses filmes, um SRT em português na pasta |

Detalhes decididos na revisão (apresentados ao Vini junto com a spec): recusar também 24 fps
exato, 29,97 progressivo, 59,94, 1080i e fps variável; capítulos automáticos a cada 5 min;
checagem de mesma origem; SRT em Windows-1252; intermediários apagados ao longo do pipeline.

## Fontes suportadas

O botão fica disponível quando a fonte passa em todas as regras. Quando não passa, a tela mostra
**todos** os motivos de uma vez.

| Regra | Aceita | Texto da recusa |
|---|---|---|
| Vídeos na pasta | exatamente 1 | "Por enquanto o app gera disco com um vídeo só (discos com vários vídeos chegam com o menu). Para gerar agora, deixe este vídeo sozinho numa pasta." |
| Scan | escaneado e sem mudança | "Escaneie a pasta antes de gerar o disco." / "Os arquivos mudaram desde o último scan. Escaneie de novo." |
| Leitura | sem erro do ffprobe | "Não foi possível ler o arquivo. Escaneie de novo; se continuar, o arquivo pode estar danificado." |
| Vídeo | existe (ignorando capas `attached_pic`) | "O arquivo não tem imagem, só áudio." |
| Áudio | ao menos 1 faixa | "O vídeo não tem áudio." |
| Duração | conhecida | "Não foi possível ler a duração do vídeo. Escaneie de novo; se continuar, o arquivo pode estar danificado." |
| Cor | SDR | "O vídeo está em HDR (HDR10, HLG ou Dolby Vision), e o app ainda não converte HDR para DVD." |
| Resolução | até 1920x1080 | "O vídeo é maior que 1080p (4K?), e o app ainda não converte essa resolução." |
| Quadros | ver abaixo | ver abaixo |

### Classificação de quadros (modo de vídeo)

**Origem MPEG-2 em 720x480 ou 704x480** (rip de DVD NTSC, por exemplo do MakeMKV): a taxa do
stream não é confiável (um filme com soft telecine pode aparecer como 29,97, 23,976 ou um valor
como 179/6). A classificação é pelos quadros, com
`ffprobe -read_intervals` em 3 janelas de ~20 s (10%, 50% e 90% da duração) e
`-show_entries frame=repeat_pict,interlaced_frame,top_field_first`:

| Padrão nas janelas | Modo |
|---|---|
| cadência 3:2 de `repeat_pict` com `interlaced_frame=0` em todas | `film` |
| sem `repeat_pict` e entrelaçado | `interlaced` |
| mistura (híbrido, comum em série de TV) | `hybrid`: `interlaced` com `-vf repeatfields` antes do encode (hard telecine na saída) |
| sem `repeat_pict` e progressivo | recusa: "O vídeo está em 29,97 quadros por segundo progressivos. Ainda não suportado." |

Essa leitura roda ao abrir o formulário (alguns segundos, só para origem MPEG-2 SD). Na tela da
pasta, origem MPEG-2 SD não é recusada por taxa de quadros.

**Outras origens** (H.264, HEVC, VC-1...), pelo `r_frame_rate` e `avg_frame_rate`:

| Caso | Resultado |
|---|---|
| 24000/1001, progressivo | `film` |
| `r` e `avg` diferem mais de 0,1% | "O vídeo tem taxa de quadros variável (comum em gravação de celular ou de tela). Ainda não suportado." |
| 25 ou 50 | "O vídeo está em 25 quadros por segundo (padrão PAL, europeu). Por enquanto só NTSC." |
| 24 exato | "O vídeo está em 24 quadros por segundo exatos. Por enquanto só 23,976 ou 29,97." |
| 30000/1001 entrelaçado acima de 480 linhas | "O vídeo é entrelaçado em 1080i (gravação de TV). Ainda não suportado." |
| 30000/1001 progressivo | "O vídeo está em 29,97 quadros por segundo progressivos. Ainda não suportado." |
| 60000/1001 | "O vídeo está em 59,94 quadros por segundo. Ainda não suportado." |
| outro | "Taxa de quadros X ainda não suportada." |

Entrelaçado pelo `field_order`: a **primeira letra** dá o campo de cima (`tt` e `tb` são TFF,
`bb` e `bt` são BFF; o ffprobe chama de `tb` um MPEG-2 TFF). `progressive` ou ausente conta como
progressivo.

### Legendas

Não bloqueiam o disco. Entram as de **texto**: SRT externa e `subrip`/`mov_text`/`text` internas.
As outras aparecem cinzas, com o tipo: "Legenda em imagem (PGS): ainda não suportada",
"Legenda em imagem (VobSub): ainda não suportada", "Legenda ASS/SSA: ainda não suportada".

## Perfis e calculadora

### Perfis (`planner/profiles.py`)

Objetos de configuração imutáveis; adicionar um perfil é adicionar uma entrada.

| Campo | DVD-5 | DVD-9 |
|---|---|---|
| Descrição | "camada única, 4,7 GB" | "dupla camada, 8,5 GB" |
| Setores (menor valor entre −R e +R) | 2.295.104 | 4.171.712 |
| Bytes | 4.700.372.992 | 8.543.666.176 |
| Margem | 97% | 97% |
| Reserva fixa (IFO, BUP, sistema de arquivos) | 4 MiB | 4 MiB |
| Overhead de mux | 3% | 3% |
| Ótima / Aceitável / Baixa | ≥ 5 / 3,5 a 5 / < 3,5 Mbps | igual |

### Fórmulas (`planner/calculator.py`, funções puras)

```
capacidade_util  = 0,97 × bytes − 4 MiB
maxrate_video    = min(9000, 10080 − Σaudio_kbps − 40 × n_legendas − 300)        [kbps]
video_kbps       = capacidade_util × 8 / 1,03 / duração_s / 1000 − Σaudio_kbps − 10 × n_legendas
video_kbps       = min(video_kbps, maxrate_video)
tamanho_estimado = (video_kbps + Σaudio_kbps + 10 × n_legendas) × 1000 × duração_s × 1,03 / 8 + 4 MiB
```

- `Σaudio_kbps` usa o bitrate de saída: o da origem quando é cópia, o da conversão nos outros
  casos.
- A qualidade sai do `video_kbps`. Abaixo de 1000 kbps o perfil é "Não cabe" e não pode ser
  escolhido.
- **Perfil sugerido:** o primeiro "Ótima" na ordem DVD-5, DVD-9; se nenhum for, o DVD-9.
- **Exemplo de referência (teste, ±0,01 Mbps):** filme de 2 h com uma faixa AC-3 de 448k:
  DVD-5 ≈ 4,47 Mbps (Aceitável), DVD-9 ≈ 8,49 Mbps (Ótima).
- Invariante testada: `tamanho_estimado ≤ capacidade_util` quando o bitrate não bate no teto.
- O teto de 9,0 Mbps (abaixo dos 9,8 da especificação) deixa folga para o pico do VBV com o mux
  a 10,08; registrar na seção 5.1.

## Plano do disco (`planner/dvd_plan.py`)

`DvdPlan` é um `pydantic.BaseModel` congelado (`frozen=True`), serializado com
`model_dump_json` e validado ao reler do banco. Contém:

- pasta, caminho relativo do vídeo, índice do stream de vídeo, `size` e `mtime_ns` no momento da
  criação;
- perfil escolhido e `video_kbps`;
- modo de vídeo (`Literal["film", "interlaced", "hybrid"]`), campo de cima (TFF/BFF) quando
  entrelaçado;
- aspecto de saída (`16:9` ou `4:3`) e a área útil `W x H` (letterbox ou pillarbox);
- áudios, na ordem do disco: índice do stream, idioma (2 letras ou nenhum), ação
  (`Literal["copy", "ac3"]`), canais e bitrate de saída, `start_time` relativo ao vídeo; a faixa
  que toca ao colocar o disco vai **primeiro**;
- legendas, na ordem do disco: origem (stream interno ou arquivo externo), idioma; e qual liga ao
  iniciar (vai primeiro) ou nenhuma;
- capítulos em segundos (o `0` sempre incluso);
- `confirmed_red` (o Vini confirmou a qualidade baixa) e `replace_existing` (confirmou substituir
  o ISO);
- nome do volume e nome do ISO.

### Regras de sugestão

- **Áudio:** marcar as faixas em português (`por`, `pt`, `pt-BR`) e as do idioma original
  (aproximado como o idioma da primeira faixa de áudio da origem, até a Fase 2). Sem português,
  só a original. Faixas com o mesmo idioma: só a de mais canais. A que toca ao colocar o disco:
  português, se houver. Máximo de 8 faixas.
- **Ação do áudio:** `copy` se o codec é `ac3`, 48 kHz, `bit_rate` conhecido e até 448 kbps, e
  até 6 canais. Senão `ac3` a 48 kHz: 3 a 6 canais mantêm o layout da origem a 448k; mais de 6
  viram 5.1 (`-ac 6`) a 448k; estéreo 192k; mono 96k (`-ac 1`). Uma fonte estéreo nunca vira 5.1.
- **Legenda:** marcar as em português. Liga ao iniciar: a primeira em português **não forçada**
  quando o áudio que toca primeiro não é português; nenhuma quando é. Máximo de 32 faixas.
- **Capítulos:** os do arquivo, se houver pelo menos 2; senão, a cada 5 minutos. Capítulos a
  menos de 1 s do anterior ou do fim são descartados (o dvdauthor alinha ao VOBU, ~0,5 s, e
  criaria cells vazias). Mais de 99 (do arquivo, ou automáticos num vídeo muito longo): vira "a
  cada N minutos" com o menor N inteiro que cabe em 99, e o formulário avisa.
- **Idiomas:** os códigos do ffprobe (`por`, `eng`, `spa`...) viram os de 2 letras do dvdauthor por
  uma tabela pequena (ISO 639-2 → 639-1). Desconhecido ou `und`: a faixa entra sem idioma. Em SRT
  externa, o trecho do nome (`pt-BR`, `en`) é lido da mesma forma.
- **Nome do volume:** nome da pasta sem acentos (NFKD), maiúsculas, o que não for `A-Z0-9` vira
  `_`, `_` repetidos colapsados, até 32 caracteres; vazio vira `DVD`.

### `Summary` com valores crus

O planner não pode decidir comparando texto de tela. O `Summary` (Fase 1) passa a guardar os
valores como o ffprobe dá, e a tradução para o português sai para `api/formatting.py` (filtros
Jinja), que já é o lugar disso:
- faixas: `index`, `language: str | None`, `channel_count: int | None`, `channel_layout`,
  `sample_rate`, `bit_rate`, `start_time`, `kind: Literal["text", "image", "unknown"]`;
- vídeo: `index`, `r_frame_rate`, `avg_frame_rate` (frações), `field_order`, `start_time`.

Só entram campos que a Fase 3 lê; `pix_fmt` e `color_primaries` ficam fora (o HDR já usa
`color_transfer`). O item da seção 13 sobre esses campos fica resolvido assim. As fixtures da Fase
1 continuam valendo; o teste `slow` de fixtures compara também os campos novos.

## Pipeline de mídia

Todas as linhas de comando saem de **funções puras** (`encode/`, `authoring/dvd/`) que devolvem
listas de argumentos. Uma única função `run_pipeline(plan, job_dir, run, should_cancel)` executa
as etapas; o `run(cmd, step)` injetável roda um comando e informa o progresso. O worker, o comando
de desenvolvimento e os testes usam a mesma função.

**Higiene de todo comando:** `-y -nostdin`, caminhos absolutos, `cwd=job_dir`, `stdin=DEVNULL`,
stderr direto no `job.log` (arquivo aberto, nunca PIPE, para não travar com o buffer cheio), e só
o stdout do `-progress` lido pelo worker.

**Intermediários apagados ao longo do pipeline**, assim que a etapa seguinte dá certo: o pico de
espaço em `/work` fica em ~2 vezes o tamanho do disco (sem isso seriam até 5 vezes mais uma cópia
por legenda). O botão "Apagar arquivos temporários" do fim limpa o que sobrar (falha, cancelamento,
ISO reprovado).

### 1. Vídeo (MPEG-2, 2 passes)

Passe 1 com `-pass 1 -f null -`, passe 2 com `-pass 2` e saída `video.m2v`; os dois com
`-passlogfile <job_dir>/pass` e os mesmos filtros:

```
-map 0:<índice do vídeo> -r <24000/1001|30000/1001> -fps_mode cfr
-vf "[repeatfields,]<escala>,<cor>,format=yuv420p,pad=720:480:(720-W)/2:(480-H)/2:black,setsar=<sar>"
-c:v mpeg2video -b:v <video_kbps>k -maxrate <maxrate_video>k -bufsize 1835k
-g 12 -bf 2 -flags +cgop -sc_threshold 1000000000
-dc 10 -intra_vlc 1 -non_linear_quant 1 -qmin 1 -qmax 28
-mbd rd -trellis 1 -cmp 2 -subcmp 2 -aspect <16:9|4:3>
-bsf:v mpeg2_metadata=colour_primaries=6:transfer_characteristics=6:matrix_coefficients=6
-an -sn -dn -progress pipe:1 -nostats
```

- **Proibido `-target ntsc-dvd`**: duplica quadros inteiros (tranco a cada 4º quadro).
- **`-r` sempre explícito** (24000/1001 no `film`, 30000/1001 nos outros): sem ele o ffmpeg
  escolhe a taxa pelo `r_frame_rate` e duplica quadros de um rip de DVD com soft telecine.
- **Escala** (`scale=W:H:flags=lanczos+accurate_rnd+full_chroma_int`), com
  DAR = largura × SAR / altura (vale para origem anamórfica como 1440x1080 ou 720x480):
  - DAR ≥ 1,5: saída 16:9 (SAR 32/27).
    - DAR ≥ 16/9: `W = 720`, `H = 480 × (16/9) / DAR`.
    - DAR < 16/9: `H = 480`, `W = 720 × DAR / (16/9)` (pillarbox no 16:9, ex.: 1,66:1).
  - DAR < 1,5: saída 4:3 (SAR 8/9), pelas mesmas regras com 4/3 no lugar de 16/9.
  - `H` arredondado para múltiplo de 4 (faixas pretas iguais em cima e embaixo), `W` para par.
    Ex.: 1920x800 (2,40:1) dá H = 356; 1920x1080 dá 720x480.
  - Origem 720x480 com o mesmo aspecto de saída: sem `scale`. 704x480: sem `scale`, só o `pad`.
- **Cor:** origem HD (altura > 576) recebe `colorspace=all=smpte170m:iall=bt709` **depois** da
  escala (antes custaria 10 vezes mais tempo). Origem SD já é BT.601 e não leva o filtro.
- **`film`:** encode a 24000/1001; depois o patcher.
- **`interlaced`:** sem escala vertical; `-flags +ilme+ildct -top <1|0>` pelo campo de cima.
- **`hybrid`:** `repeatfields` antes de tudo, depois como `interlaced`.

### 2. Bitstream MPEG-2 (`encode/mpeg2.py`)

Um módulo só lê os start codes e os campos (`sequence_header`, `sequence_extension`, GOP,
`picture_header`, `picture_coding_extension`). O patcher e a QA usam o mesmo leitor.

**Patcher de soft pulldown** (modo `film`), estilo DGPulldown, **in-place via `mmap`** (o arquivo
pode ter 8 GB; o tamanho não muda):
- recusa um arquivo que já tenha `frame_rate_code=4` (não aplica duas vezes);
- `frame_rate_code` de 1 (23,976) para 4 (29,97);
- `progressive_sequence = 0`;
- em cada `picture_coding_extension`: `top_field_first` e `repeat_first_field` no ciclo
  `T1 B0 B1 T0` (TFF=1,RFF=1; TFF=0,RFF=0; TFF=0,RFF=1; TFF=1,RFF=0), pela **ordem de exibição**
  (`temporal_reference` mais a base do GOP). Com GOP de 12 (múltiplo de 4), todo GOP começa em T1.

Validação do estudo: 1439 imagens viram 720 com RFF, 3598 campos, nenhuma quebra de paridade; o
dvdauthor lê 29,97. Pontos a confirmar no player físico: o `time_code` do GOP fica na escala de
24p (players ignoram), e o VBV modelado a 41,7 ms por imagem (se der problema, `bufsize` ~1700k
só no `film`). Plano B: hard telecine.

### 3. Áudio (`encode/audio.py`)

Um `.ac3` por faixa: `-map 0:<índice> -c:a copy` ou
`-c:a ac3 -b:a <kbps>k -ar 48000 [-ac <n>]`, com `-vn -sn -dn`.

### 4. Legendas (`authoring/dvd/subtitles.py`)

- Interna de texto: extraída com `-map 0:<índice> -c:s srt`.
- SRT externa: UTF-16 se tiver BOM UTF-16; senão UTF-8 (com ou sem BOM); senão Windows-1252
  (comum em legendas brasileiras). Regravada em UTF-8 com quebras `\n` no diretório do job; o
  arquivo original nunca é tocado. Um SRT sem nenhum bloco válido reprova antes do spumux, com
  "A legenda X está vazia ou inválida".
- `spumux -s <n>` uma vez por faixa, depois do mux:

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

  - Os dois fps ficam iguais: os tempos do SRT são absolutos (testado: legenda em 2 s ficou
    alinhada ao início do vídeo).
  - `movie-height="478"` é um contorno conhecido do spumux (comentário no código explica, para
    ninguém "corrigir" para 480).
  - Tags como `<i>` são descartadas (texto sem itálico).
  - Num filme 2,40:1 a legenda fica parte sobre a faixa preta, parte sobre a imagem: esperado.
  - Teste: uma fala de 2 linhas com 42 caracteres cada, em 16:9 e em 4:3, continua em 2 linhas e
    sem letras esticadas (QA manual). Se quebrar: margens laterais de 54, depois fonte 24.
- `fonts-dejavu-core` fixado no Dockerfile (hoje a fonte vem só por dependência).

### 5. Mux

```
ffmpeg -fflags +genpts -i video.m2v -itsoffset <X1> -i audio1.ac3 [...] -map 0 -map 1 [...]
       -c copy -f dvd -muxrate 10080k -packetsize 2048 movie.mpg
```

- Sem `+genpts`, o ffmpeg grava só 2 nav packs e todos os capítulos caem em 0.
- **`-itsoffset` por faixa:** o m2v cru começa depois do áudio (preload e B-frames: 39 ms em
  29,97 e 55 ms com pulldown, já perceptível). `Xn` = pts do primeiro quadro do `video.m2v`
  (`ffprobe -fflags +genpts ... -read_intervals %+#1`) mais o `start_time` do áudio menos o do
  vídeo na origem (preserva o atraso de áudio do rip).

### 6. dvdauthor (`authoring/dvd/dvdauthor.py`)

```xml
<dvdauthor dest="/work/jobs/<id>/dvd">
  <vmgm>
    <fpc>jump title 1;</fpc>
    <menus><video format="ntsc" aspect="16:9"/></menus>
  </vmgm>
  <titleset><titles>
    <video format="ntsc" aspect="16:9" widescreen="nopanscan"/>
    <audio lang="pt"/> ...
    <subpicture lang="pt"/> ...
    <pgc>
      <pre>audio=0;subtitle=<64|0>;</pre>
      <vob file="/work/jobs/<id>/movie.mpg" chapters="0:00:00.000,0:05:00.000,..."/>
      <post>exit;</post>
    </pgc>
  </titles></titleset>
</dvdauthor>
```

- O `<vmgm>` sempre declara o formato (regra da seção 5.1 do `CLAUDE.md`).
- `audio=0` sempre: sem ele, o player escolhe pela preferência de idioma dele (muitos vêm com
  inglês). `subtitle=64` liga a primeira legenda (bit 6 = exibir, faixa 0); `subtitle=0` quando
  nenhuma liga (as forçadas continuam aparecendo). Conferido com `dvdunauthor`.
- Origem 4:3: `aspect="4:3"` e sem `widescreen`.
- Faixa sem idioma: `<audio/>` ou `<subpicture/>` sem `lang`.
- `dest` absoluto e diretório vazio (o dvdauthor acrescenta ao que existe).

### 7. ISO

`genisoimage -dvd-video -udf -V <VOLUME> -o <job_dir>/disc.iso <job_dir>/dvd`. O ISO fica no
diretório do job até passar na QA.

### 8. QA automática (`authoring/dvd/qa.py`, checagens puras; o `jobs/` só chama)

Qualquer item reprovado faz o job terminar como `failed`, com o motivo em palavras; o ISO fica em
`/work` para inspeção e **não** vai para `/output`.

1. **Tamanho:** reprova se o ISO passar de setores do perfil × 2048 (o limite físico da mídia).
   Acima da capacidade útil (97%) só avisa. O `qa_json` grava o estimado e o real. Ajusta a seção
   9 do `CLAUDE.md`, que dizia "≤ capacidade útil".
2. **Árvore, lida do ISO** (`isoinfo -l`, do pacote `genisoimage`): `VIDEO_TS.IFO/BUP`,
   `VTS_01_0.IFO/BUP`, ao menos um `VTS_01_1.VOB`, nenhum VOB acima de 1 GiB, e `AUDIO_TS`.
3. **Streams pelo ffprobe** (`-f dvdvideo -title 1 -count_packets`): `mpeg2video`, 720x480, DAR do
   plano, `30000/1001`; uma faixa `ac3` por áudio e uma `dvd_subtitle` por legenda, na ordem e com
   o idioma do plano, **cada uma com mais de 0 pacotes**; inícios dos capítulos do plano (±1 s);
   duração igual à do **stream de vídeo** da origem (±1 s).
4. **Bitstream, extraído do ISO** (`ffmpeg -f dvdvideo -i disc.iso -map 0:v -c copy -f mpeg2video
   pipe:1`, lido em streaming, sem decodificar): `frame_rate_code=4`, `progressive_sequence=0`,
   `aspect_ratio_information` do plano, GOP fechado com até 12 imagens, e no `film` a continuidade
   de campos sem quebra de paridade.
5. **Sincronia:** no `movie.mpg`, o primeiro pts de vídeo e o de áudio diferem no máximo 5 ms
   (conferido antes de apagar o mpg).
6. **Encode:** `dup_frames=0` e `drop_frames=0` no fim do `-progress` do passe 2; nada de
   "buffer underflow" no stderr do mux nem de "ERR" no do dvdauthor.
7. **Decode completo:** `ffmpeg -v error -f dvdvideo -i disc.iso -map 0:v -map 0:a -f null -`;
   qualquer linha em stderr reprova.

Aprovado: copia para `OUTPUT_DIR/iso/<pasta>.iso.part`, confere de novo se o destino apareceu
(sem `replace_existing`, falha), renomeia com `os.replace` para `<pasta>.iso` e apaga o ISO de
`/work`.

### Comando de desenvolvimento

`python -m projeto_dvd.jobs.pipeline "<pasta>"` roda o pipeline síncrono com o plano sugerido,
dentro do container. Serve para a primeira QA manual com filme real antes das telas, e para
depuração. Fica no README (seção de desenvolvimento).

### Progresso e tempo

- O worker lê `out_time_us` do `-progress` (ignorando `N/A`; `progress=end` fecha a etapa) e
  calcula a fração pela duração da origem.
- Etapas, pesos e nomes na tela:

| Etapa | Peso | Na tela |
|---|---|---|
| `video_pass1` | 35 | Vídeo: 1ª passada (análise) |
| `video_pass2` | 45 | Vídeo: 2ª passada (codificação) |
| `pulldown` | 2 | Ajuste de quadros para TV |
| `audio` | 5 | Áudio |
| `subtitles` | 2 | Legendas |
| `mux` | 4 | Juntando vídeo, áudio e legendas |
| `author` | 2 | Montando a estrutura do DVD |
| `iso` | 2 | Criando o ISO |
| `qa` | 3 | Conferindo o disco |

- O banco guarda `step` e `progress` (geral, 0 a 1), gravados no máximo uma vez por segundo. O
  tempo restante é calculado na tela: `decorrido × (1 − p) / p`, arredondado ("cerca de 15
  min"), e "calculando..." até 2% de progresso.

### Tempo esperado

| Fonte | Filme de 2 h |
|---|---|
| 1080p H.264 | 20 a 30 min |
| DVD 480 | menos de 15 min |

## Jobs e worker

### Banco (migração `0002`)

Tabela `job`, só com o que é consultado (o resto fica no `plan_json`):

| Coluna | Tipo | Nota |
|---|---|---|
| `id` | int | chave |
| `folder` | str | pasta de disco (NFC), indexado |
| `plan_json` | str | o `DvdPlan` |
| `status` | str | `queued`, `running`, `done`, `failed`, `canceled` (`StrEnum`) |
| `cancel_requested` | bool | |
| `step` | str ou nulo | etapa atual |
| `progress` | float | 0 a 1 |
| `error` | str ou nulo | frase em português |
| `qa_json` | str ou nulo | resultado de cada item da QA (modelo Pydantic) |
| `iso_path` | str ou nulo | caminho final em `/output` |
| `created_at`, `started_at`, `finished_at` | datetime | UTC |

- **Índice único parcial** `ix_job_active_folder` em `folder` onde `status IN ('queued',
  'running')`: dois cliques quase simultâneos não criam dois jobs da pasta (o `IntegrityError`
  vira o redirecionamento para o job existente).
- Datas lidas do SQLite chegam sem fuso: um helper único normaliza para UTC ao ler.
- Log em `WORK_DIR/jobs/<id>/job.log` (comandos, stderr das ferramentas). O banco guarda só o
  estado.

### SQLite com dois processos

`PRAGMA journal_mode=WAL` no evento `connect` e `timeout=5` no `connect_args` (é o busy timeout
do `sqlite3`). Cada escrita do worker é um comando curto, sem ler e depois escrever na mesma
transação. WAL funciona porque o banco está no volume `data` (ext4).

**Transições atômicas** (SQL com vírgula à esquerda):
- claim:
  `UPDATE job SET status = 'running', started_at = ? WHERE id = (SELECT id FROM job WHERE status
  = 'queued' ORDER BY id LIMIT 1) AND status = 'queued' RETURNING id`;
- cancelar pela tela: `UPDATE ... SET status = 'canceled' WHERE id = ? AND status = 'queued'`; se
  nenhuma linha mudar, `cancel_requested = 1`;
- toda transição final do worker leva `WHERE status = 'running'`.

### Worker (`python -m projeto_dvd.jobs.worker`)

- `run_once(engine, settings, run)` pega e processa um job e devolve se havia job; `main()` tem o
  laço, o `sleep` e os sinais. Relógio e `sleep` injetáveis nos testes.
- Espera a migração do `web` (compara `alembic_version` com o head a cada 2 s); nunca migra.
- **No startup:** jobs `running` viram `failed` ("O worker reiniciou no meio da geração. Gere de
  novo.") e `.iso.part` que tenham sobrado em `/output/iso` são apagados.
- **Laço:** a cada 2 s, um claim; um job por vez.
- **Antes de começar:** confere `size` e `mtime_ns` do vídeo contra o plano.
- **Cancelar:** `should_cancel()` é conferido logo depois do claim, entre as etapas, durante o
  patcher e a cópia para `/output`, e a cada segundo enquanto um processo roda. Num processo:
  `terminate()`, espera, `kill()` (prazos injetáveis; padrão 5 s). O job vira `canceled`, o log
  fica, o `.iso.part` é apagado. As ferramentas não criam netos, então não há
  `start_new_session`.
- **Erro de ferramenta:** código diferente de 0 vira `failed` com a etapa; as últimas linhas do
  stderr saem do fim do `job.log`.
- **SIGTERM no worker** (`docker compose stop`): o handler só liga uma flag; o laço mata o
  processo com prazo de 3 s, grava `failed` ("O worker foi parado no meio da geração. Gere de
  novo.") e sai. `stop_grace_period: 30s` no compose dá folga.

### Compose, imagem e configuração

- Serviço `worker`: mesma imagem (`target: runtime`), `command: python -m
  projeto_dvd.jobs.worker`, `init: true`, `stop_grace_period: 30s`, mesmos volumes (`/media:ro`,
  `/work`, `/output`, `data`), sem porta.
- `Dockerfile`: `genisoimage=9:1.1.11-4` e `fonts-dejavu-core` fixados. Sem mjpegtools e sem
  lsdvd.
- `Settings` ganha `work_dir` (padrão `/work`) e `output_dir` (padrão `/output`).
- `.gitignore`: `*.part` e `ffmpeg2pass-*`.

### Checagens antes de criar o job

- `WORK_DIR` e `OUTPUT_DIR` existem e aceitam escrita (cria e apaga um arquivo de teste). Falha:
  "Não dá para gravar na pasta de trabalho (/work). Ela pode ter sido criada pelo Docker como
  root. Para corrigir, no WSL: `sudo chown 1000:1000 <a pasta do HOST_WORK_DIR>`." (o mesmo para
  `/output`). `/data` não precisa: a migração no startup do `web` já falha de forma explícita.
- Espaço livre em `WORK_DIR` ≥ 2 × tamanho estimado + 1 GiB; em `OUTPUT_DIR` ≥ tamanho estimado +
  100 MiB. Texto: "Falta espaço na pasta de trabalho: precisa de 18,2 GB livres e há 12,0 GB."
  (GB decimal, como o resto da tela).
- Job `queued` ou `running` da pasta: a tela leva a ele em vez de criar outro.
- ISO com o mesmo nome em `/output/iso`: o formulário exige "Substituir o ISO existente (gerado em
  <data>, <tamanho>)".

## Telas

Mesmo visual da Fase 1 (CSS próprio, tema escuro, HTMX, sem build). Textos em português, com o
termo técnico acompanhado de palavra simples.

**Base:** cabeçalho com "Biblioteca · Jobs" em todas as telas. CSS ganha `.button` (vale para
`a` e `button`) e `.secondary`; só um botão primário por tela.

### Rotas e dependências

- `templates`, sessão, `disc_folder` e `WEB_DIR` saem de `api/library.py` para `api/deps.py`.
- Rotas novas em `api/dvd.py` e `api/jobs.py`; a criação do job passa por `jobs.enqueue(session,
  plan)`.
- Erros de validação voltam com status 200 e as mensagens (o HTMX 2 não troca respostas de erro).

### Tela da pasta (`GET /folders/{name}`)

O bloco "Gerar DVD" fica dentro de `_folder_body.html`, para o scan renderizá-lo de novo.
- Fonte suportada e scan em dia: **"Gerar DVD"** é o primário; "Escanear" vira secundário.
- Fonte recusada: aviso "Não dá para gerar o DVD desta pasta" com todos os motivos em lista (sem
  botão desabilitado).
- Job ativo da pasta: "Gerando DVD: 42%" com link. Último job pronto: "Último ISO: <data>" com
  link.
- Card da biblioteca ganha o selo "gerando DVD" enquanto houver job ativo.

### Formulário (`GET` e `POST /folders/{name}/dvd`)

- **Topo:** "Entrada: 1080p, 23,976 quadros/s, 2h01" e "Saída: DVD NTSC 16:9 com faixas pretas
  (o filme é 2,40:1)". "Leva cerca de 20 a 30 min."
- **Áudio:** checkbox por faixa com idioma, título, selos "padrão no arquivo" e "forçada", canais
  ("5.1", "estéreo"), codec com nome comercial ("Dolby Digital (AC-3)") e a ação ("copiar sem
  perda" ou "converter para Dolby Digital 5.1 (448 kbps)"). Radio **"Toca ao colocar o disco"**
  ("as outras trocam pelo botão Áudio do controle").
- **Legendas:** checkbox por faixa suportada (com título e selos); as não suportadas cinzas, com o
  tipo. Radio **"Legenda ligada ao iniciar"** por faixa, mais "Nenhuma (liga pelo botão Legenda
  do controle)".
- **Capítulos:** "do arquivo (N)" (desabilitado com "o arquivo não tem capítulos" quando N < 2)
  ou "a cada [5] minutos".
- **Perfil (os cartões são a calculadora),** logo acima do botão, renderizados de novo por
  `POST /folders/{name}/dvd/estimate` (`hx-trigger="change"`, só esse bloco). Cada cartão:
  - "DVD-5 · camada única, 4,7 GB";
  - qualidade em palavra, com ícone e cor: "Ótima", "Aceitável", "Baixa", "Não cabe" (radio
    desabilitado);
  - "Usa 4,4 de 4,7 GB" com uma barrinha;
  - "vídeo a 4,5 Mbps" em texto discreto;
  - selo "sugerido".
  - O escolhido tem borda de 2px na cor do texto e "Escolhido" (não o âmbar do botão, para não
    confundir com "Aceitável").
  - Ajuda: "A qualidade depende de quanto espaço sobra para a imagem. Ótima a partir de 5 Mbps."
    Quando o sugerido é o DVD-9: "A mídia de dupla camada é mais cara."
- **Qualidade baixa:** checkbox obrigatória "Entendo que a qualidade vai ficar baixa e quero gerar
  mesmo assim" (fica fora do bloco re-renderizado, ou é reenviada e mantida).
- **Validações** (lista no topo e `aria-invalid` no campo): nenhum áudio; mais de 8 áudios; mais
  de 32 legendas; "toca ao colocar o disco" ou "ligada ao iniciar" numa faixa desmarcada;
  intervalo de capítulos vazio, 0 ou negativo; perfil que não cabe; espaço; qualidade baixa sem
  confirmação; ISO existente sem confirmação. As escolhas não se perdem. Mais de 99 capítulos
  não é erro: "O arquivo tem 140 capítulos, e o DVD aceita até 99. Vão ser usados capítulos a
  cada 2 minutos."
- Sucesso: `303` para `/jobs/{id}`.

### Job (`GET /jobs/{id}`)

- **Bloco de status** (o único que se atualiza, a cada 2 s, por `hx-trigger="every 2s"`; a
  resposta final sai sem o gatilho): lista das etapas com marcação (feita, em andamento, a
  fazer), `<progress>` com o percentual em texto, "Começou às 14:05 · decorrido 12 min · faltam
  cerca de 15 min".
- Frase fixa: "Pode fechar esta página. A geração continua e você pode voltar pela lista de
  Jobs."
- **Log** fora do bloco de status: `<details>` que carrega ao abrir (`hx-trigger="toggle"`) as
  últimas 200 linhas, com botão "Atualizar log".
- **Estados:**
  - `queued` com outro job rodando: "Na fila. Começa quando o job #N (pasta X) terminar.";
  - `queued` há mais de 1 min sem nenhum rodando: "Aguardando o worker. Confira se o serviço está
    rodando (`docker compose ps`); para subir: `docker compose up -d worker`.";
  - cancelando: "Cancelando..." (o botão some);
  - `canceled`: "Cancelado por você às HH:MM. Nada foi gravado na pasta de saída." e "Gerar de
    novo";
  - `failed`: frase humana primeiro ("Falhou na etapa Vídeo (2ª passada).", ou o item da QA que
    reprovou e que o ISO ficou na pasta de trabalho), casos comuns traduzidos ("Acabou o espaço
    na pasta de trabalho. Libere espaço ou apague os arquivos temporários de outros jobs.";
    "O vídeo mudou ou ficou inacessível depois que o job foi criado (o HD externo foi
    desconectado?). Escaneie a pasta e gere de novo."), e o stderr em "Detalhes técnicos". Botão
    "Gerar de novo";
  - `done`: "Pronto! O ISO passou na conferência automática.", o caminho
    `iso\<pasta>.iso` dentro da pasta de saída (o README explica onde ela fica no Windows), o
    tamanho do ISO e o uso do disco, o resultado da QA, o checklist manual em passos e uma linha
    de como gravar no ImgBurn.
- **Cancelar** (`POST /jobs/{id}/cancel`), `hx-confirm`: "Cancelar a geração? O que já foi feito
  se perde (ainda não dá para retomar)."
- **"Apagar arquivos temporários (X GB)"** (`POST /jobs/{id}/clean`), só em job terminado (outros
  status: 409), `hx-confirm`: "Apagar X GB de arquivos temporários deste job? O log fica." (em
  `done`: "O ISO na pasta de saída não é afetado."; em reprovado: "O ISO reprovado que ficou na
  pasta de trabalho também será apagado."). Apaga com `os.scandir` sem seguir links, só dentro de
  `WORK_DIR/jobs/<id>/` (conferido com `is_relative_to`), menos o `job.log`.

### Lista (`GET /jobs`)

Tabela com pasta, perfil, status (com o percentual quando roda), data e link.

## Segurança

- `TrustedHostMiddleware(allowed_hosts=["localhost", "127.0.0.1"])`: fecha o DNS rebinding (um
  site que resolve para 127.0.0.1). Fecha o item da Fase 1.
- **Mesma origem**, um middleware para todo método não seguro (inclui o scan da Fase 1), no
  algoritmo do `CrossOriginProtection` do Go: com `Sec-Fetch-Site`, só `same-origin` ou `none`;
  sem ele, `Origin` (se houver) tem que bater com o `Host`; sem nenhum dos dois, a requisição não
  veio de navegador e passa. Senão `403`. Testes: `cross-site` e `same-site` (outra porta do
  localhost) dão 403.
- Pastas resolvidas como na Fase 1. O formulário manda só índices, validados contra o resumo;
  nenhum caminho vem do formulário.
- Diretório do job a partir do `id` inteiro; limpeza só dentro dele.
- Comandos por lista de argumentos e caminhos absolutos; `/media` continua `ro`.

## Erros e casos de borda

| Caso | Comportamento |
|---|---|
| Arquivo mudou entre o formulário e o worker | `failed` com a frase do HD externo |
| HD desconectado no meio do encode | ferramenta falha; `failed` com a etapa |
| Disco do WSL cheio no meio | `failed` com "Acabou o espaço na pasta de trabalho..." |
| `/output` cheio na cópia | `.iso.part` apagado; `failed`; o ISO continua em `/work` |
| ISO apareceu no destino durante o job | sem `replace_existing`, `failed` sem sobrescrever |
| Dois cliques em "Gerar" | índice único; o segundo vai para o job existente |
| Cancelar enquanto o worker pega o job | transições condicionais; vale `cancel_requested` |
| Worker não está rodando | `queued` com o aviso da tela |
| SRT em UTF-16, UTF-8 com BOM, CRLF, Windows-1252 | decodificado e normalizado |
| SRT vazia ou inválida | reprova antes do spumux, com o nome da legenda |
| Capítulos colados ou depois do fim | descartados |

## Testes

`pytest` padrão continua com `-m "not slow"`, cobertura com ramos, mínimo de 90% (meta 100%). O
pipeline e o worker são cobertos sem ferramentas pelo `run` injetável.

| Área | Testes |
|---|---|
| Calculadora | exemplo de 2 h (±0,01); fronteiras 3,5 e 5 Mbps; teto do maxrate; "não cabe"; sugestão; invariante de tamanho |
| `Summary` | valores crus novos pelas fixtures; tradução em `formatting` |
| Suporte da fonte | cada recusa e cada texto; 1080p 23,976; 480i TFF e BFF (`tb`/`bt`); 704x480; 59,94; taxa genérica; classificação MPEG-2 por quadros (film, interlaced, hybrid, 29,97p) sobre saídas de ffprobe de fixture |
| `DvdPlan` | sugestões de áudio (pt + original, sem pt, idioma repetido, limite 8), copiar vs converter (cada condição, `bit_rate` ausente, 3 a 6 canais, mono), legendas (forçada não liga), capítulos (do arquivo, automáticos, colados, depois do fim, mais de 99, vídeo de 9 h), idiomas, volume, ida e volta JSON |
| Comandos | os 2 passes por modo, `-r`, `-passlogfile`, `-map`, escala (2,40, 1,85, 1,66, 16:9, 4:3, mais estreito que 4:3, anamórfico 1440x1080, 720x480, 704x480), cor só em HD, `repeatfields`, áudio, legenda, mux com `itsoffset`, genisoimage |
| MPEG-2 | leitor e patcher sobre bytes sintéticos: campos, ciclo por ordem de exibição com B-frames, GOPs seguidos, sem sequence header, patch repetido recusado |
| XML | dvdauthor (16:9, 4:3, sem idioma, `audio=0`, `subtitle=64/0`, capítulos, `post`) e spumux; escape |
| SRT | UTF-8, BOM, CRLF, UTF-16, Windows-1252, vazia |
| QA | cada item aprovando e reprovando, sobre JSON e bytes de fixture; contagem de pacotes 0 |
| Execução | runner com subprocessos baratos (`python -c`): grava PID e dorme (cancelar mata), ignora SIGTERM (escala para kill), escreve muito no stderr (não trava); parser do `-progress` (`N/A`, `end`) |
| Pipeline (run falso) | ordem das etapas, pesos, falha numa etapa, cancelar entre etapas, intermediários apagados, QA reprovada não copia, falha na cópia apaga `.iso.part`, rename final, destino que apareceu |
| Worker | `run_once` com o mais antigo, recuperação no startup (inclui `.iso.part`), arquivo mudou, corrida claim e cancel, SIGTERM pelo handler, relógio falso no limite de escrita |
| Rotas | bloco da pasta por estado (inclusive depois do scan), formulário com sugestões, estimate, cada validação, mesma origem e TrustedHost, `303`, job em cada estado (job antigo: datas com fuso), cancel, clean (409 se ativo), lista; nada escrito em `/media` |
| Banco | migração 0002, índice parcial, modelos batem com as migrações, WAL ligado |

### Integração (`slow`, na imagem)

Clipes gerados numa fixture de sessão com `ffmpeg -f lavfi`, curtos para caber no CI:
- **1080p:** 1920x800 (letterbox), 23,976, 12 s; áudio AAC 5.1 a 44,1 kHz (testa `-ar 48000`) e
  AC-3 2.0 a 192k (cópia); capítulos por ffmetadata em 0, 4 e 8 s; SRT externa gravada em
  Windows-1252 (o teste afirma que os bytes não são UTF-8 válido); áudio com `start_time`
  deslocado. Afirma: QA completa, `cropdetect` no ISO dá H = 356, sincronia ≤ 5 ms.
- **Rip de DVD de filme:** m2v 24p passado pelo patcher, VOB, remux para MKV (como o MakeMKV);
  afirma que a classificação dá `film`, sem duplicar quadros.
- **480i:** MPEG-2 entrelaçado TFF de verdade (`-flags +ilme+ildct -top 1`), 4:3; afirma
  `field_order=tb` na origem e a QA.
- **Estimativa:** um perfil de teste com capacidade pequena (bitrate abaixo do teto); afirma
  `|real − estimado| / estimado < 3%`.
- **Negativo:** um ISO sem o patch de pulldown reprova na QA.
- **Cancelamento:** cancela depois de `step == "video_pass1"` e `progress > 0`; nenhum ffmpeg
  sobra no `/proc`; status `canceled`.
- **Ambiente:** a fonte DejaVu existe no caminho do XML.
- O teste de fixtures do ffprobe compara também os campos novos; fixtures novas no
  `make_fixtures.sh`: 480i TFF e BFF, 25 fps, 24 fps exato, VFR, 59,94, 1080i, rip de DVD.

### CI

- O job `docker` roda os `slow` novos; o `timeout-minutes` é ajustado depois de medir no primeiro
  PR.
- **Smoke de ponta a ponta:** sobe `web` e `worker`; gera um clipe de 3 s com a própria imagem em
  `/tmp/ci/media/Disco DVD`; scan; `POST` de criação com `Sec-Fetch-Site: same-origin`; consulta
  `/jobs/{id}` até `done` (até 3 min); confere `/tmp/ci/output/iso/Disco DVD.iso` com o UID 1000.

### QA manual

**Primeiro momento** (depois do grupo 2c, pelo comando de desenvolvimento) e **segundo momento**
(no fim, pela tela). Com um rip de Blu-ray do Vini e, se houver, um rip de DVD:
1. o VLC abre o ISO como disco e o filme começa sozinho;
2. "Menu" e "Title" não travam nem tiram o filme do lugar;
3. capítulos pulam com "próximo";
4. áudio e legenda trocam pelo VLC; a faixa que toca e a legenda ligada (ou nenhuma) são as
   escolhidas;
5. panorâmicas sem tranco nem pente;
6. cores e faixas pretas corretas; legenda legível, em até 2 linhas, sem letras esticadas;
7. áudio sincronizado com a boca no começo, no meio e no fim;
8. no fim do filme o disco para, sem loop nem travar;
9. a duração bate com a do original; tamanho estimado contra real anotado.

O resultado (checklist, `qa_json`, nome e tipo da fonte) vai no PR. O `tech-lead-midia` também
registra o `ffprobe` de um rip de DVD real, para confirmar como o MakeMKV o descreve.

## Documentação

- `README.md` e `README.pt-BR.md`: como gerar um DVD, o serviço `worker`, o que é suportado,
  onde fica a pasta de saída no Windows e o `iso\`, como gravar no ImgBurn, a pasta de trabalho
  (espaço: ~2 vezes o tamanho do disco), arquivos temporários, o comando de desenvolvimento.
- `CLAUDE.md`:
  - 3.5: retomar e reaproveitar ficam para a Fase 4;
  - 4: margem de 97% menos 4 MiB, capacidades em setores, overhead de 3%, teto de 9 Mbps, 10 kbps
    por legenda;
  - 5.1: parâmetros validados, teto de vídeo de 9,0 Mbps e o porquê, áudio só AC-3, soft
    pulldown;
  - 6: `genisoimage` entra; 6.1: `WORK_DIR` e `OUTPUT_DIR` entram, `DEFAULT_DVD_STANDARD` sai
    (PAL ficou fora); 6.2: o `worker` entra, com `init: true`, e o Alembic só no `web`;
  - 7: árvore com `planner/dvd_plan.py`, `encode/mpeg2.py`, `authoring/dvd/qa.py`,
    `jobs/pipeline.py`, `jobs/worker.py`, `api/deps.py`; 7.1: o `Job` carrega o `plan_json` no
    lugar de um `DiscProject`, sem hash de reaproveitamento por enquanto; 7.2: a tela 8 (Jobs)
    entra, e o formulário é um montador mínimo;
  - 9: item 1 (limite físico reprova, capacidade útil avisa) e o checklist de disco sem menu;
  - 12: a Fase 3 inclui calculadora de um título, escolha de faixas e jobs com progresso; a Fase
    4 fica com vários títulos, menus, retomar e reaproveitar;
  - 13: soft pulldown "resolvido no VLC e no ffprobe; confirmar `time_code`, `subtitle=64` e
    pulldown no player físico"; checagem de escrita resolvida para `/work` e `/output` (`/data`
    falha na migração); campos do `Summary` resolvidos; NTSC vs PAL continua aberto;
  - Estado atual e Log de decisões.
- `.env.example`: `HOST_WORK_DIR` no ext4 do WSL, com espaço de ~2 vezes o tamanho do disco.

## Ordem de entrega (grupos)

1. `Summary` com valores crus; perfis, calculadora, suporte da fonte (inclusive a classificação
   MPEG-2), `DvdPlan` (puro).
2. **2a.** `Settings`, comandos de vídeo e áudio, leitor MPEG-2 e patcher, mux com `itsoffset`,
   dvdauthor, ISO, `run_pipeline` com `run` injetável, comando de desenvolvimento, `genisoimage`
   no Dockerfile; `slow` sem legenda até o ISO.
   **2b.** SRT e spumux, `fonts-dejavu-core`.
   **2c.** QA automática; **primeira QA manual com filme real do Vini**.
3. Jobs: migração 0002, WAL, transições atômicas, worker, cancelamento, recuperação; serviço no
   compose.
4. Telas: `api/deps.py`, botão na pasta, formulário com os cartões, job, lista, checagens antes
   de criar, segurança.
5. CI (smoke de ponta a ponta), documentação e a segunda QA manual pela tela.

## Para o Log de decisões (fim da fase)

- MPEG-2 pelo ffmpeg em 2 passes com os parâmetros desta spec; proibido `-target ntsc-dvd`; `-r`
  sempre explícito.
- Soft pulldown por patcher próprio (estilo DGPulldown, `mmap` in-place, um leitor MPEG-2 só
  para patcher e QA); mpeg2enc descartado (lento, sem alvo de tamanho). Fecha a parte do VLC do
  item da seção 13.
- Rip de DVD classificado pelos quadros (film, interlaced, hybrid com hard telecine); 480i
  codificado entrelaçado.
- Cor: escala com lanczos e depois `colorspace` para BT.601 só em origem HD; tags via
  `mpeg2_metadata`.
- Áudio só AC-3: copiar se ≤ 448k, 48 kHz e ≤ 6 canais; senão converter mantendo o layout.
  `-itsoffset` no mux corrige o atraso do m2v e preserva o atraso da origem.
- `audio=0` sempre e `subtitle=64/0` no `<pre>` do título.
- Mux com `ffmpeg -f dvd -fflags +genpts`; ISO com `genisoimage -dvd-video -udf`.
- Capacidade pelo menor valor entre −R e +R, em setores, com margem de 97% menos 4 MiB; a QA
  reprova acima do limite físico e avisa acima da margem.
- Legendas SRT/texto via spumux; PGS, VobSub, ASS, HDR, PAL e 4K adiados. Copiar o vídeo de rip de
  DVD sem recodificar fica para a Fase 4 ou antes.
- Worker em processo separado, SQLite em WAL, transições atômicas, índice único por pasta ativa,
  um job por vez; retomar e reaproveitar ficam para a Fase 4.
- Intermediários apagados ao longo do pipeline (pico de ~2 vezes o disco); o botão do fim limpa
  o resto.
- ISO só vai para `/output` depois de passar na QA automática.
- `TrustedHostMiddleware` e checagem de mesma origem em todo método não seguro.

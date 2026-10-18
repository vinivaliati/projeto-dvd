# Fase 6a: Blu-ray de um título, sem menu (design)

- **Data:** 2026-10-17
- **Branch:** `feat/fase-6a-bluray`
- **Status:** desenho aprovado pelo Vini no chat; revisada por `tech-lead-midia` (testes reais
  com ffmpeg 7.1.5, libx264 164, libbluray 1.3, libudfread e tsMuxeR 2.7.0 na imagem) e
  `revisor-codigo`; achados incorporados. Escopo reduzido a **um título por disco** por decisão
  do Vini depois da revisão (ver "Decisões").
- **Divisão da Fase 6:** 6a (esta spec); 6b, spike de menus de Blu-ray com recomendação; depois,
  vários títulos por Blu-ray com a estrutura que o spike indicar.

## Contexto e intenção

O DVD guarda a coleção em 480 linhas. Para os filmes em alta definição, o Vini quer o mesmo
fluxo (uma pasta vira um disco) em Blu-ray, com a qualidade do arquivo de origem sempre que
possível (prioridade 1 do projeto): vídeo de remux copiado, áudio sem perda copiado, PGS
copiado; o que não é compatível é recodificado dentro do padrão BDMV, para tocar num player
comum daqui a 20 anos.

## Pronto quando

1. Na tela "Montar disco" de uma pasta com **um vídeo**, os perfis **BD-25** e **BD-50**
   aparecem ao lado do DVD-5 e do DVD-9, com a calculadora; origem HD sugere Blu-ray.
2. "Gerar" cria um ISO de Blu-ray (UDF 2.50, BDMV e CERTIFICATE) sem menu: o disco começa
   sozinho, com os capítulos do arquivo (ou a cada N minutos).
3. Remux de Blu-ray (H.264 dentro do padrão) tem o vídeo copiado; o resto SDR 1080p/720p a
   23,976 é recodificado com o x264 em modo Blu-ray. 4K, HDR, PAL, entrelaçado e SD são
   recusados com o motivo na tela.
4. Áudio sem perda copiado quando o padrão aceita; PGS copiado; SRT vira PGS.
5. A QA automática lê o ISO pela libbluray e pela libudfread e reprova o que não está certo;
   o job reprova se o tsMuxeR avisar algo, mesmo saindo com código 0.
6. Retomar, cache do encode e preflight de espaço valem para o Blu-ray.
7. `make lint`, `make test` (100%) e `make test-slow` verdes.

## Fora de escopo

- **Vários títulos por Blu-ray** (depois do spike 6b; o `+` do tsMuxeR exige conformar áudio,
  legendas e resolução, testado na revisão, e pode não ser a estrutura de um disco com menu).
- Menus, pop-up menu, BD-J.
- 4K/HDR com tonemap (fase própria, calibrada com arquivo real); origem SD em Blu-ray.
- PAL (25/50), 24 exato, 29,97, 59,94, 1080i, VFR, HEVC copiado.
- VobSub e ASS; áudio secundário.
- Capa da caixa de Blu-ray (a capa da Fase 5 continua, com "BD-25"/"BD-50" no quadro técnico).

## Decisões tomadas com o Vini

- Fase 6 dividida em 6a e 6b; origens ainda indefinidas, o desenho cobre remux, WEB-DL e rips.
- Cópia do vídeo quando compatível; x264 no resto; 4K/HDR recusado por agora.
- A mesma tela "Montar DVD" vira "Montar disco", com os quatro perfis.
- **Um título por disco Blu-ray na 6a** (opção C, depois da revisão do `tech-lead-midia`).
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Meio e perfis (`planner/profiles.py`)

`DiscProfile` ganha `medium: Literal["dvd", "bluray"]` e os limites viram campos do perfil. O
meio de um plano ou de uma escolha sai sempre de `PROFILES[profile].medium`: **nenhum campo novo
em `DiscPlan` ou `DiscChoices`**, sem migração; planos e projetos antigos continuam válidos.

| Campo | DVD-5 / DVD-9 | BD-25 / BD-50 |
|---|---|---|
| setores (2048 B) | 2.295.104 / 4.171.712 | 12.219.392 / 24.438.784 (nominais do BD-R, conferidos) |
| margem | 97% | 97% |
| reserva | 4 MiB | 64 MiB (o ISO acrescenta ~1,7 MB fixos; folga barata) |
| sobrecarga do mux | 3% | 6% (medido: 5,1% a 23 Mbps, 5,9% a 8,6 Mbps) |
| vídeo máximo | 9.000 kbps | 35.000 kbps |
| mux máximo | 10.080 kbps | 48.000 kbps |
| pico por legenda | 40 kbps (spumux) | 500 kbps (PGS) |
| verde / amarelo | ≥ 5.000 / ≥ 3.500 | ≥ 15.000 / ≥ 8.000 |
| não cabe abaixo de | 1.000 kbps | 3.000 kbps |

- Calculadora: `maxrate = min(vídeo máximo, mux/(1 + sobrecarga) − Σáudio − pico × legendas)`
  (no BD: `min(35000, 48000/1,06 − Σáudio − 500 × PGS)`); alvo limitado a 95% do maxrate.
- Áudio sem perda conta pela taxa do PCM equivalente: canais × bits × 48 kHz (DTS-HD MA 7.1 de
  24 bits ≈ 9,2 Mbps); AC-3 e DTS core pelo `bit_rate` (ou 640/1536 kbps se faltar).
- Título copiado entra pelo tamanho real do vídeo (como na 4b): copia sempre que é elegível;
  se o disco não comporta, o cartão diz "Não cabe com o vídeo copiado: marque Recodificar".
- `MAX_TITLES` (60, do VMGM) e o pico do spumux continuam só do DVD.
- **Sugestão:** origem HD (altura > 576) aceita pelo Blu-ray sugere o primeiro perfil BD com
  qualidade ótima (BD-25, depois BD-50); senão, a ordem de hoje (DVD-5, DVD-9). Ninguém escolhe
  sozinho: é só a marca de "sugerido".

## Quando os cartões BD aparecem

- A pasta continua bloqueada pelas regras do DVD (`folder_reasons` não muda; tudo que o
  Blu-ray aceita o DVD também aceita).
- Os cartões BD-25 e BD-50 **só aparecem** quando a pasta tem um vídeo e ele passa no
  `check_video` do Blu-ray; senão, uma linha diz por quê ("Blu-ray: um título por disco nesta
  fase" ou "Blu-ray: rip de DVD (480i), use DVD"). `disc_estimates` só calcula os perfis BD nesse
  caso.
- Uma escolha salva com perfil BD que deixa de valer (a pasta ganhou um segundo vídeo) volta à
  sugestão no `reconcile`.

## Origem aceita (`planner/source.py`)

`check_video(summary, medium)`; o DVD não muda. Blu-ray:

- 1920x1080, 1920x(menos de 1080) com pad, 1440x1080 com SAR 4:3, ou 1280x720;
- 23,976 progressivo (`24000/1001`), SDR (sem PQ, HLG ou Dolby Vision), 8 ou 10 bits (10 bits
  sempre recodifica para 8);
- recusado, cada um com o motivo em português: acima de 1080p, HDR, 24 exato, 25/50, 29,97,
  59,94, entrelaçado, VFR, altura até 576 (SD).

## Vídeo

**Cópia** (`planner/bd_source.py`) quando tudo vale:
- H.264 High ou Main, level ≤ 4.1, 8 bits 4:2:0, 23,976 progressivo;
- 1920x1080 SAR 1:1, ou 1440x1080 SAR 4:3 (resolução legal de BD; aceita como `format 6`);
- lido com `-bsf:v trace_headers` nos primeiros segundos: `nal_hrd_parameters_present_flag = 1`,
  4 slices ou mais por quadro, `max_dec_frame_buffering ≤ 4`;
- GOP de até 24 quadros na amostra de quadros (a mesma da 4b);
- tamanho do vídeo conhecido (tag `NUMBER_OF_BYTES` do MakeMKV, ou o arquivo menos o áudio);
- "Recodificar o vídeo" desmarcado (`DiscChoices.reencode_rips` reaproveitado; o texto da
  caixa muda pelo meio).
Na prática só remux de Blu-ray passa; WEB-DL (keyint 250, 1 slice, sem HRD) recodifica, mesmo
o tsMuxeR aceitando sem reclamar.

Extração da cópia: `ffmpeg -i <mkv> -map 0:<v> -c copy -bsf:v h264_mp4toannexb -f h264
video.h264`. O tsMuxeR sempre recebe `.h264` Annex B, **sem `insertSEI` e sem `contSPS`**
(com eles o SPS não se repete em todo quadro I, e as SEI são reescritas).

**Encode** (`encode/x264.py`, ffmpeg + libx264, 2 passes), parâmetros testados:

```
-c:v libx264 -preset slow -profile:v high -level 4.1 -pix_fmt yuv420p
-b:v <alvo>k -maxrate <max>k -bufsize 30000k -pass N -passlogfile <dir>/x264
-x264-params bluray-compat=1:keyint=24:min-keyint=1:slices=4:b-pyramid=strict:open-gop=0:
             nal-hrd=vbr:aud=1:colorprim=bt709:transfer=bt709:colormatrix=bt709
-r 24000/1001 -fps_mode cfr -f h264
```

- `vbv-maxrate`/`vbv-bufsize` **fora** do `-x264-params` (brigam com `-maxrate`/`-bufsize`);
  `-pix_fmt yuv420p` sempre (10 bits sem ele sai High 10, inválido); GOP fechado (`open-gop=0`,
  conservador, como a lição dos capítulos no DVD).
- Geometria: 1920x(menos de 1080) ganha `pad` preto centrado até 1920x1080; 1440x1080 SAR 4:3
  recodificado é escalado com lanczos para 1920x1080 SAR 1:1; 720p fica 1280x720.
- Cor: HD para HD, sem conversão de matriz; tags BT.709.
- Cache da 4b: a chave é o comando da 2ª passada e a versão do ffmpeg (a libx264 é fixada pelo
  apt); `jobs/cache.py` passa a aceitar `.h264` além de `.m2v` (contagem, despejo e chave
  escolhem pelo meio).

## Áudio

Cada faixa escolhida vira um arquivo elementar no `WORK_DIR`, alinhado ao vídeo (o tsMuxeR
ignora o atraso do MKV, testado: áudio com `start_time 0.5` foi muxado junto do vídeo):

- **Copiado** (`-c copy` para ES): AC-3 até 640 kbps a 48 kHz; DTS core; DTS-HD MA e HRA;
  LPCM 48 kHz 16/24 bits (vai como `.wav`, ordem dos canais conferida no 5.1).
  - Atraso diferente de 0: LPCM ganha silêncio no início (sem perda); AC-3, DTS e DTS-HD com
    atraso de mais de 1 quadro viram AC-3 640k com `adelay` (o corte num quadro de 32 ms não
    alinha certo).
- **Convertido para AC-3** mantendo o layout (640k de 3 a 6 canais, 7.1 vira 5.1; 256k
  estéreo; 128k mono): TrueHD (sem o núcleo AC-3 que o padrão exige: declarado como `A_AC3` o
  tsMuxeR grava um stream 0x84 vazio; como `A_MLP` ele avisa que não toca em player), E-AC-3,
  AAC, Opus, FLAC, MP3 e o resto.
- **TrueHD com faixa AC-3 irmã**: o MakeMKV costuma trazer o núcleo AC-3 separado, no mesmo
  idioma; ela tem prioridade sobre a conversão (a `best_audio` prefere a compatível).
- Idiomas escolhidos uma vez para o disco (Fase 4a), até 4; com um título, faltar um idioma
  significa não ter a faixa (avisado como hoje). Idioma no `.meta` em ISO 639-2 (`por`, `eng`).
- **DTS-HD MA copiado: a confirmar com um trecho real** (o ffmpeg não gera DTS-HD). Até lá, o
  teste unitário cobre o `.meta`; a QA confere o `profile` do ffprobe no disco.

## Legendas

- `subtitle_options` passa a saber o meio: no Blu-ray, PGS (`hdmv_pgs_subtitle`) é suportado;
  no DVD continua não. A lista de idiomas da tela muda com o perfil, e o `reconcile` tira da
  escolha os idiomas que o meio novo não tem. Legenda só forçada continua contando como ausente.
- **PGS**: extraído para `.sup` com `-c copy -f sup`.
- **SRT externo e texto do MKV**: extraídos para `.srt` em UTF-8 **sem BOM** e **terminado em
  linha em branco** (sem ela o tsMuxeR descarta a última legenda, testado) e entregues como
  `S_TEXT/UTF8` com `font-name="DejaVu Sans", font-size=58, font-border=4, bottom-offset=108,
  video-width=1920, video-height=1080, fps=23.976` (o DVD escalado; ajuste fino do `designer`
  na revisão visual). Em 720p, `video-width=1280, video-height=720` e tamanhos × 2/3.
- `SubtitleChoice` ganha `codec: Literal["text", "pgs"]` (único campo novo de plano).
- Até 4 idiomas.

## Estrutura do disco (`authoring/bluray/meta.py`)

`.meta` gerado por função pura e comparado como texto nos testes:

```
MUXOPT --blu-ray --vbr --label="NOME_ASCII" --custom-chapters=00:00:00.000;00:05:00.000;...
V_MPEG4/ISO/AVC, "/work/jobs/7/video.h264", fps=23.976
A_AC3, "/work/jobs/7/a1.ac3", lang=por, default
A_DTS, "/work/jobs/7/a2.dts", lang=eng
A_LPCM, "/work/jobs/7/a3.wav", lang=eng
S_HDMV/PGS, "/work/jobs/7/s1.sup", lang=por
S_TEXT/UTF8, "/work/jobs/7/s2.srt", font-name="DejaVu Sans", ..., lang=eng, default=all
```

- Saída direto em `.iso` (UDF 2.50); playlist `00000.mpls`; `First Playback` toca a playlist.
- `--label`: o nome do volume em **ASCII, sem acento, até 30 caracteres** (o tsMuxeR grava
  UTF-8 e corta em 32 bytes, partindo o "é").
- Capítulos: os do arquivo ou a cada N minutos (`plan_chapters`, sem o limite de 99 do DVD; o
  BD aceita 999), em `HH:MM:SS.mmm`.
- `default` na faixa de áudio que toca primeiro e `default=all` na legenda ligada (gravam
  `SetStream` no `MovieObject.bdmv`, conferido); sem legenda ligada, o player escolhe pelo
  idioma configurado nele.
- Caminhos só do plano e do `WORK_DIR`, nunca do formulário.

## Job (`jobs/bluray.py`)

- O worker escolhe: `run = run_bluray if medium == "bluray" else run_pipeline`.
- `jobs/bluray.py` é fino e importa o que é comum do `pipeline.py` (verificação da origem, etapa
  de ferramenta, publicação, notas, preflight, `CacheUse`) e o `size_checks` da QA do DVD; esses
  nomes viram públicos (sem módulo "common"). Os construtores de comando e o leitor de progresso
  do tsMuxeR são funções puras.
- Etapas: reaproveitam o enum `Step` (`VIDEO_COPY` com rótulo "Vídeo copiado da origem",
  `VIDEO_PASS1`, `VIDEO_PASS2`, `AUDIO`, `SUBTITLES`, `ISO` = tsMuxeR, `QA`, `COPY`); uma função
  `steps_for(plan)` dá as tuplas e os pesos por meio, usada pelo worker (`overall_progress`) e
  pela tela do job.
- `menu is None` hoje marca job da Fase 3 (`OLD_PLAN`, `_can_resume`, etapa MENUS): passa a ser
  "DVD e `menu is None`". Um job de Blu-ray tem `menu=None`, roda, mostra as etapas certas e
  pode ser retomado.
- **Log do tsMuxeR**: o job reprova se a saída tiver `Warning`, `bad frame`, `Invalid` ou
  `Can't`, mesmo com código 0 (o tsMuxeR devolve 0 em discos quebrados, testado).
- Preflight: ~3 vezes o disco livre na pasta de trabalho com o cache ligado (a tela diz quanto
  falta) e escrita em `/work` e `/output`.
- Nome do ISO: `<pasta> (BD).iso`, para não pedir "Substituir" depois do DVD da mesma pasta.
- Tempo estimado: ×1,0 da duração para o x264 slow em 1080p; cópia ×0,02 (a calibrar);
  `ENCODE_SECONDS_PER_SECOND` passa a ser chaveado pelo meio.

## QA automática (`authoring/bluray/qa.py`)

Por **ctypes** nas bibliotecas que já estão na imagem `runtime` (dependências do ffmpeg), como a
4a faz com a libdvdnav; o protocolo `bluray:` do ffmpeg não serve (recusa playlist de menos de
180 s, não dá idiomas nem capítulos e estima a duração pelo bitrate). `argtypes` declarados em
todas as funções (sem eles, segfault).

1. Tamanho do ISO ≤ capacidade física (reprova); acima da útil, só avisa.
2. Estrutura pela `libudfread.so.0`: `BDMV/index.bdmv`, `MovieObject.bdmv`,
   `PLAYLIST/00000.mpls`, `CLIPINF`, `STREAM`, `BACKUP` e `CERTIFICATE`.
3. Pela `libbluray.so.2` (`bd_open`, `bd_get_disc_info`, `bd_get_playlist_info`): Blu-ray
   detectado, `first_play` presente, duração da playlist igual à do vídeo (±1 quadro),
   capítulos iguais aos do plano (±1 quadro), e cada faixa (tipo, formato, idioma) igual ao
   plano, na ordem.
4. O `00000.m2ts` lido pela libudfread e passado ao ffmpeg por pipe: decodificação completa do
   vídeo sem erro e quadros contados; cada faixa de áudio e PGS cobrindo a playlist (primeiro e
   último pts).
5. Vídeo: o sha256 do H.264 extraído do m2ts igual ao do `.h264` entregue ao tsMuxeR (vale para
   copiado e recodificado; no copiado, prova que é a origem byte a byte).

## Tela

- Título "Montar disco"; a rota e os nomes internos ficam. Mudam os textos: o botão da pasta
  ("Montar disco"), "Gerando disco", "Não dá para montar o disco desta pasta", o botão "Gerar
  disco"; a tela do job diz o meio.
- Perfil Blu-ray escolhido:
  - a seção **Menu** dá lugar ao aviso "Sem menu por enquanto: o disco começa sozinho e os
    capítulos pulam pelo filme."; o tema salvo continua guardado;
  - o título mostra "vídeo copiado do Blu-ray" ou "recodificado: motivo";
  - a caixa vira "Recodificar o vídeo (em vez de copiar o original)";
  - os idiomas de legenda incluem os PGS.

## Erros e casos de borda

- tsMuxeR que falha ou avisa: o log completo no job, a última linha de erro na tela.
- Origem sem tamanho de vídeo conhecido: recodifica (motivo na tela).
- Pasta que ganhou um segundo vídeo depois de escolher BD: o `reconcile` volta à sugestão.
- Rótulo do volume vazio depois de tirar acentos: "DISC".

## Testes

- **Unitários:**
  - perfis BD na calculadora (maxrate pelo áudio, sobrecarga de 6%, PCM equivalente, faixas,
    não cabe, cópia pelo tamanho real) e a sugestão HD;
  - `check_video` do Blu-ray (cada recusa e cada aceite);
  - regra de cópia (cada condição do `trace_headers`, GOP, tamanho, caixa marcada);
  - regras de áudio (cópia, atraso, TrueHD com irmã AC-3, conversões) e de legendas por meio;
  - argumentos do x264 (dois passes, pad, escala, 720p, 10 bits);
  - o `.meta` comparado como texto; o rótulo ASCII; os capítulos;
  - leitor de progresso e detector de aviso do tsMuxeR;
  - `jobs/bluray.py` com `Tools` falso (100% de cobertura, como o `pipeline.py`);
  - cache com `.h264`; `steps_for`; retomar job de Blu-ray; plano antigo ainda válido;
  - rotas: cartões BD, linha de motivo, aviso do menu, sugestão, reconcile.
- **`slow`** (na imagem, sem rede):
  - clipe 1080p 23,976 H.264 + AC-3 + SRT gerado com lavfi → BD-25 recodificado, QA aprovada;
  - clipe H.264 feito com o x264 em modo Blu-ray num MKV → vídeo copiado, sha256 igual;
  - clipe com LPCM e atraso de áudio → alinhado (cobertura e início conferidos);
  - QA reprova um ISO com uma faixa a menos que o plano.
- O teste num **player de Blu-ray físico** fica para a QA do fim do projeto.

## Pontos em aberto (QA no fim do projeto)

- DTS-HD MA copiado, com um trecho de 3 min de um remux do Vini (`-c copy -f dts`, conferir
  `profile=DTS-HD MA` e a decodificação completa).
- No player físico: o disco sem menu (teclas Menu/Title), o GOP do remux copiado, a legenda
  ligada pelo `SetStream`.
- Mídia BD-R: capacidade conferida com a mídia comprada; para durabilidade, BD-R inorgânica (HTL)
  ou M-DISC. Gravar como imagem (ImgBurn "Write image file" ou "Gravar imagem de disco"), sem
  formatar o BD-R com área sobressalente.

## Documentação

README (EN e pt-BR) com o Blu-ray; CLAUDE.md: 3.3, 4, 5.2 (parâmetros finais), 6.1, 7, 9, 12,
13, Estado atual e Log de decisões.

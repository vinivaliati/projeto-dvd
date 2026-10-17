# Fase 6a: Blu-ray sem menu (design)

- **Data:** 2026-10-17
- **Branch:** `feat/fase-6a-bluray`
- **Status:** desenho aprovado pelo Vini no chat (partes 1 e 2); a revisar por `tech-lead-midia`
  (com testes reais do x264, do tsMuxeR e da libbluray) e `revisor-codigo`.
- **Divisão da Fase 6** (decisão do Vini): 6a é o BDMV sem menu (esta spec); 6b é um spike de
  menus de Blu-ray que termina numa recomendação. O menu de verdade, se viável, vira fase própria.

## Contexto e intenção

O DVD guarda a coleção em 480 linhas. Para os filmes em alta definição, o Vini quer o mesmo
fluxo (uma pasta vira um disco) em Blu-ray, com a qualidade do arquivo de origem sempre que
possível. A prioridade 1 do projeto é a qualidade de imagem: quando o vídeo já é compatível com
Blu-ray, ele é copiado; quando não é, o x264 recodifica dentro do padrão BDMV, para tocar num
player comum daqui a 20 anos.

## Pronto quando

1. Na tela "Montar disco" de uma pasta, os perfis **BD-25** e **BD-50** aparecem ao lado do
   DVD-5 e do DVD-9, com a calculadora e a sugestão de sempre.
2. "Gerar" cria um ISO de Blu-ray (UDF 2.50, BDMV e CERTIFICATE) sem menu: o disco começa
   sozinho, toca os títulos em sequência e tem um capítulo no início de cada título.
3. Vídeo H.264 compatível é copiado; o resto SDR 1080p ou 720p é recodificado com o x264 em
   modo Blu-ray. 4K, HDR, PAL, entrelaçado e SD são recusados com o motivo na tela.
4. Áudio sem perda copiado quando o padrão aceita; PGS copiado; SRT vira PGS.
5. A QA automática lê o ISO pela libbluray e reprova o que não está certo.
6. Retomar, cache do encode e preflight de espaço valem para o Blu-ray.
7. `make lint`, `make test` (100%) e `make test-slow` verdes.

## Fora de escopo

- **Menus de Blu-ray** (spike 6b) e pop-up menu.
- **4K/HDR com tonemap**: fase própria, calibrada com um arquivo real do Vini (risco de cor).
- **Origem SD** (480i/576i) em Blu-ray: o lugar dela é o DVD.
- PAL (25/50), 29,97 progressivo, 59,94, 1080i, VFR, HEVC copiado (o BDMV comum não aceita).
- VobSub e ASS; áudio secundário, PiP, BD-J.
- Capa da caixa de Blu-ray (medidas a conferir com a caixa comprada); a capa da Fase 5 continua
  sendo a de DVD, com "BD-25"/"BD-50" no quadro técnico.

## Decisões tomadas com o Vini

- Fase 6 dividida em 6a (BDMV sem menu) e 6b (spike de menus).
- Origens: o Vini ainda não sabe quais vai usar; o desenho cobre remux, WEB-DL e rips 1080p.
- **Cópia do vídeo** quando compatível e cabe; x264 no resto; 4K/HDR recusado por agora.
- A mesma tela "Montar DVD" vira "Montar disco", com os quatro perfis.
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Perfis (`planner/profiles.py`)

`DiscProfile` ganha `medium: Literal["dvd", "bluray"]` e os limites viram campos de cada perfil
(adicionar um perfil continua sendo só adicionar uma entrada):

| Campo | DVD-5 / DVD-9 | BD-25 / BD-50 |
|---|---|---|
| setores (2048 B) | 2.295.104 / 4.171.712 | 12.219.392 / 24.438.784 (BD-R, a conferir com a mídia) |
| margem | 97% | 97% |
| reserva | 4 MiB | 64 MiB (CLPI, MPLS, BACKUP, UDF 2.50) |
| sobrecarga do mux | 3% | 5% (MPEG-TS de 192 bytes, a medir num disco real) |
| vídeo máximo no app | 9.000 kbps | 35.000 kbps (o padrão permite 40.000) |
| mux máximo | 10.080 kbps | 48.000 kbps |
| verde / amarelo | ≥ 5.000 / ≥ 3.500 | ≥ 15.000 / ≥ 8.000 |
| não cabe abaixo de | 1.000 kbps | 3.000 kbps |

- A calculadora (`planner/calculator.py`) usa os campos do perfil; o alvo continua limitado a
  95% do maxrate. Legenda PGS conta 40 kbps por faixa (texto convertido é bem menos; a QA mede).
- Título copiado entra pelo tamanho real do vídeo (como o rip de DVD da 4b).
- A sugestão continua sendo o primeiro perfil com qualidade ótima, na ordem DVD-5, DVD-9, BD-25,
  BD-50. Uma pasta com origem que o Blu-ray recusa (ex.: rip de DVD) e o DVD aceita nunca é
  sugerida para Blu-ray, e vice-versa (4K SDR que só o Blu-ray reduziria fica recusada nos dois
  por enquanto).

## Origem aceita (`planner/source.py`)

`check_video(summary, medium)`; as regras do DVD não mudam. Para o Blu-ray:

- 1080p (até 1920x1080, inclusive 1920x800 e 1440x1080 anamórfico) ou 720p (até 1280x720);
- 23,976 progressivo (`24000/1001`), SDR (sem PQ, HLG ou Dolby Vision);
- recusado: acima de 1080p, HDR, 24 exato, 25/50, 29,97 e 59,94, entrelaçado, VFR, e altura
  até 576 (SD), cada um com o motivo em português, como na Fase 3.

## Vídeo (`encode/x264.py`, `planner/bd_source.py`)

**Cópia** (sem recodificar) quando tudo vale:
- H.264 High (ou Main), level até 4.1, 1920x1080 a 23,976 progressivo, SAR 1:1, 8 bits 4:2:0;
- tamanho do vídeo conhecido (tag `NUMBER_OF_BYTES` do MakeMKV, ou o arquivo menos o áudio);
- o disco inteiro cabe com a cópia (o bitrate dos títulos recodificados fica na faixa
  aceitável ou melhor);
- "Recodificar os vídeos" desmarcado (uma caixa por disco, como na 4b).
O tsMuxeR lê o H.264 direto do MKV. 1920x800 copiado não existe (o BDMV exige o quadro
inteiro): recodifica.

**Encode** (ffmpeg + libx264, 2 passes, parâmetros a validar pelo `tech-lead-midia`):
- `-preset slow -profile:v high -level 4.1`, `x264-params` com `bluray-compat=1`,
  `vbv-maxrate=40000`, `vbv-bufsize=30000`, `keyint=24`, `min-keyint=1`, `slices=4`,
  `b-pyramid=strict`, `open-gop=1`, `nal-hrd=vbr`, `aud=1`, `colorprim/transfer/colormatrix=
  bt709`; alvo do 2 passes pelo bitrate da calculadora, `maxrate` = vídeo máximo do perfil;
- `-r 24000/1001` sempre explícito; `-fps_mode cfr`;
- 1920x800 e outros ganham `pad` até 1920x1080 (preto, centrado); 1440x1080 anamórfico é
  escalado para 1920x1080 com lanczos; 720p fica 1280x720;
- cor: origem sem tag de cor é tratada como BT.709; nenhuma conversão de matriz (HD para HD).
- Cache da 4b: chave pelo comando da 2ª passada, a versão do ffmpeg e da libx264.

## Áudio (`encode/audio.py`)

- **Copiado**: AC-3 até 640 kbps e 48 kHz; DTS (core); DTS-HD MA e HRA; LPCM 48 kHz 16/24 bits.
- **Convertido para AC-3** mantendo o layout (640k de 3 a 6 canais, 7.1 vira 5.1; 256k estéreo;
  128k mono): TrueHD (no MKV vem sem o núcleo AC-3 que o padrão exige), E-AC-3,
  AAC, Opus, FLAC, MP3 e o resto.
- **Vários títulos**: o tsMuxeR junta os títulos num fluxo só (ver Estrutura), então cada idioma
  precisa do mesmo formato em todos os títulos. Se os formatos copiáveis diferem entre os títulos
  (ex.: DTS-HD num, AC-3 noutro), esse idioma vira AC-3 640k em todos e a tela avisa
  ("Inglês convertido para AC-3: os títulos têm formatos diferentes").
- Idiomas escolhidos uma vez para o disco (Fase 4a), até 4; faixa que falta num título usa a
  primeira faixa do título, como no DVD (no Blu-ray o "buraco" é uma faixa de silêncio AC-3 do
  tamanho do título, para manter o número de faixas igual).

## Legendas

- **PGS copiado** da origem (`hdmv_pgs_subtitle`); legenda só forçada continua contando como
  ausente.
- **SRT e texto do MKV** viram PGS pelo próprio tsMuxeR (`S_TEXT/UTF8`), com DejaVu Sans, tamanho
  e margens equivalentes às do DVD, contorno preto; os parâmetros vêm do `tech-lead-midia`.
- VobSub e ASS: fora, como no DVD.
- Faixa que falta num título: um PGS vazio do tamanho do título (mesmo motivo do áudio).
- Até 4 idiomas; a legenda ligada ao iniciar marcada no `.meta` (a confirmar no player).

## Estrutura do disco (`authoring/bluray/meta.py`)

- **Uma playlist** (`00000.mpls`) com os títulos em sequência, gerada pelo tsMuxeR juntando os
  arquivos com `+`; capítulos no início de cada título e os internos (os do arquivo, ou a cada N
  minutos), passados por `--custom-chapters`.
- `First Playback` toca a playlist; sem menu, as teclas Menu/Title não fazem nada (comportamento
  normal de disco sem menu; a confirmar no player).
- `--blu-ray --label=<volume>` e saída direto em `.iso` (UDF 2.50, verificado na Fase 0).
- `.meta` gerado por função pura (comparado como texto nos testes), com caminhos só do plano.

## Plano e job

- `DiscPlan` ganha `medium`; os campos de DVD (`mode`, `top_field_first`, pulldown) ficam
  ignorados no Blu-ray. `TitlePlan` ganha a ação de vídeo (`copy` ou `x264`), a geometria de
  saída (`pad`/`scale`) e, por faixa, a ação de áudio (`copy` ou `ac3`) e de legenda (`copy`,
  `srt`, `empty`). Jobs antigos continuam válidos (`medium="dvd"` por padrão, sem migração).
- **Pipeline do Blu-ray** num módulo próprio (`jobs/bluray.py`), com as mesmas peças da Fase 3/4
  (runner, progresso, cancelamento, log, retomar, cache):
  1. vídeo de cada título (2 passes ou extração por cópia, conferida por sha256);
  2. áudio convertido, quando precisa (copiado vai direto do MKV para o tsMuxeR);
  3. legendas: SRT extraída do MKV quando é faixa de texto;
  4. tsMuxeR (`.meta` → ISO) com progresso lido da saída dele;
  5. QA;
  6. cópia do ISO para `OUTPUT_DIR/iso/` (etapa própria, como no DVD).
- Preflight: espaço livre na pasta de trabalho de ~3 vezes o disco com o cache ligado (um BD-50
  pode pedir 150 GB; a tela diz quanto falta) e escrita em `/work` e `/output`.
- Tempo estimado: ×1,0 da duração para o x264 slow em 1080p (a calibrar com um filme real).

## QA automática (`authoring/bluray/qa.py`)

Lida pela libbluray (protocolo `bluray:` do ffmpeg, a mesma biblioteca do VLC), sem montar o ISO:

1. tamanho do ISO ≤ capacidade física (reprova); acima da útil, só avisa;
2. estrutura: `BDMV/index.bdmv`, `MovieObject.bdmv`, `PLAYLIST/00000.mpls`, `CLIPINF`,
   `STREAM` e `CERTIFICATE` (o xorriso não lê UDF 2.50; a ferramenta que lista os arquivos do
   ISO, ou a abertura pela libbluray como prova suficiente, é definida pelo `tech-lead-midia`
   na revisão);
3. a playlist principal: duração somada dos títulos (±1 s), número de capítulos;
4. ffprobe dos streams: H.264 1920x1080 (ou 1280x720) a 23,976, faixas de áudio e PGS na ordem e
   com os idiomas do plano;
5. decodificação completa do vídeo sem erro (como no DVD) e quadros contados;
6. título copiado: o H.264 extraído do ISO idêntico ao da origem (sha256).

## Tela

- "Montar DVD" vira **"Montar disco"** (rota e nomes internos mantidos; só o texto muda) com os
  quatro cartões de perfil. O botão da pasta continua o mesmo.
- Perfil Blu-ray escolhido:
  - a seção **Menu** dá lugar ao aviso "Sem menu por enquanto: o disco começa sozinho e os
    capítulos pulam entre os títulos."; o tema salvo continua guardado (volta ao trocar para DVD);
  - cada título mostra "vídeo copiado do Blu-ray" ou "recodificado: motivo";
  - a caixa "Recodificar os vídeos" aparece quando algum título seria copiado;
  - os avisos de áudio convertido por formato diferente entre títulos.
- Pasta com origem que um meio recusa e o outro aceita: os cartões do meio recusado ficam
  desabilitados com o motivo (ex.: "Blu-ray: rip de DVD (480i), use DVD"); se os dois recusam,
  a pasta mostra os motivos como hoje.
- Tela do job: etapas do Blu-ray; o resto igual.

## Erros e casos de borda

- tsMuxeR que falha: o log completo no job, a mensagem da última linha de erro na tela.
- Origem sem tamanho de vídeo conhecido: recodifica (motivo na tela).
- Disco com 1 título: playlist com 1 item, sem conversão por formato.
- Título copiado com áudio que não cabe no orçamento: recodifica só o áudio (o vídeo segue
  copiado se o disco comporta).
- Origem 1080p com SAR diferente de 1:1 que não é 1440x1080: recusada (raro).

## Testes

- **Unitários:**
  - perfis BD na calculadora (bitrate, faixas, não cabe, cópia pelo tamanho real);
  - `check_video` do Blu-ray (cada recusa e cada aceite);
  - regras de cópia do vídeo e do áudio, e a conversão por formato diferente entre títulos;
  - lista de argumentos do x264 (os dois passes, pad, escala, 720p);
  - o `.meta` do tsMuxeR comparado como texto;
  - plano antigo (sem `medium`) ainda válido;
  - rotas: cartões BD, aviso do menu, cartão desabilitado com motivo, sugestão.
- **`slow`** (na imagem, sem rede):
  - clipe 1080p 23,976 H.264 gerado com lavfi + AC-3 + SRT → BD-25 recodificado, QA aprovada;
  - clipe H.264 compatível (feito com o próprio x264 em modo Blu-ray) → copiado, vídeo idêntico;
  - dois títulos com formatos de áudio diferentes → um fluxo só, AC-3 nos dois, capítulos certos;
  - o ISO lido pela libbluray: playlist, duração e capítulos.
- O teste num **player de Blu-ray físico** fica para a QA do fim do projeto (gravador a comprar).

## Ponto em aberto para o Vini

- Mídia BD-R: a capacidade exata em setores sai da mídia comprada; até lá, os valores da tabela.
- Para durabilidade, BD-R comum (orgânica, inorgânica HTL) ou M-DISC BD-R.

## Documentação

README (EN e pt-BR) com o Blu-ray; CLAUDE.md: 3.3, 4, 5.2 (parâmetros finais), 7, 9, 12, 13,
Estado atual e Log de decisões.

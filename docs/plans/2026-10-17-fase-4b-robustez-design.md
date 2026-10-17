# Fase 4b: Robustez (design)

- **Data:** 2026-10-17
- **Branch:** `feat/fase-4b-robustez`
- **Status:** desenho aprovado pelo Vini no chat; aguardando a revisão dos agentes e do Vini.

## Contexto e intenção

A 4a fez a pasta inteira virar um DVD com menu. Um disco de série ou de trilogia leva horas de
encode, e duas coisas jogam essas horas fora hoje:

- **Uma queda no meio** (o WSL já caiu por falta de memória neste projeto, um reinício do PC,
  falta de espaço, um cancelamento): o job falha e "Gerar de novo" recomeça do zero.
- **Uma mudança pequena depois** (outra cor no menu, outro fundo, a ordem dos títulos): o disco
  inteiro é codificado de novo.

E um rip de DVD (MPEG-2 do MakeMKV) é recodificado mesmo já estando no formato do DVD, perdendo
uma geração de qualidade sem motivo.

O objetivo afetivo continua mandando: qualidade de imagem primeiro (a cópia do rip preserva o
original) e disco que toca em qualquer player (a cópia só entra quando segue o padrão).

## Pronto quando

1. Um job interrompido (worker caiu), com falha ou cancelado tem o botão **Retomar** na tela
   dele; retomar devolve o mesmo job à fila e ele pula os títulos cujo vídeo já está no cache.
2. Gerar de novo um disco mudando só o tema, as páginas do menu, a ordem ou os capítulos
   reaproveita o vídeo de todos os títulos (nenhuma passada de encode).
3. O cache fica em `WORK_DIR/cache`, limitado por `CACHE_LIMIT_GB` (padrão 50); acima do
   limite, os arquivos usados há mais tempo saem primeiro, nunca o que o job atual usa. A lista
   de jobs mostra o tamanho do cache e um botão "Limpar cache".
4. Um rip de DVD compatível entra no disco com o vídeo copiado (sem recodificar); a calculadora
   conta o tamanho real dele. Se o disco não couber com as cópias, a tela avisa e oferece
   "Recodificar os rips para caber" (salvo no projeto do disco).
5. O ISO com título copiado passa na QA automática (com as regras de GOP do padrão para
   material original).
6. `make lint`, `make test` (100%) e `make test-slow` verdes.

## Fora de escopo

- Vários jobs em paralelo; retomar automático sem clique (decisão do Vini: botão).
- Copiar vídeo que não seja MPEG-2 de DVD NTSC (PAL, 704x480 com outro aspecto, MPEG-1).
- Cache de áudio e legendas (são rápidos; refeitos a cada job).
- Copiar áudio de outros formatos (o AC-3 compatível já é copiado desde a Fase 3).

## Decisões tomadas com o Vini

- Cache por **limite de espaço** (`CACHE_LIMIT_GB`, padrão 50 GB), mais antigos saem primeiro.
- Rip compatível **copiado quando cabe**; quando não cabe, a tela oferece recodificar.
- Job interrompido fica parado com o botão **Retomar** (nada volta sozinho para a fila).
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Cache do vídeo codificado (`jobs/cache.py`)

**O que guarda:** o vídeo MPEG-2 elementar de cada título recodificado, depois das duas
passadas e do soft pulldown (o `title{n}.m2v` de hoje). As passadas são cerca de 80% do tempo
de um job; áudio, legendas e mux são refeitos (minutos).

**Onde:** `WORK_DIR/cache/<chave>.m2v`, com `<chave>.json` ao lado (pasta, caminho do vídeo,
tamanho, criado e último uso), para a tela e para o despejo. O `.m2v` só aparece no cache
depois de completo (gravado como `.part` e renomeado), então uma queda no meio nunca deixa um
vídeo pela metade com nome válido.

**Chave:** `sha256` do JSON canônico de:
- a origem: caminho relativo, tamanho e `mtime_ns` (os mesmos que o job já confere);
- os parâmetros de vídeo do `TitlePlan`: `video_index`, `mode`, `top_field_first`, `aspect`,
  `width`, `height`, `scale`, `hd_color`;
- o bitrate: `video_kbps` e `maxrate_kbps` do disco;
- `ENCODER_VERSION` (constante em `encode/video.py`; sobe a cada mudança de parâmetro de
  encode, invalidando o cache antigo sem apagar nada à mão).

**O bitrate não pode depender do menu.** Hoje o espaço dos menus é `páginas × 2 MiB`, então
mudar os idiomas do menu ou o tipo do disco muda o bitrate em alguns kbps e invalidaria o
cache. Passa a ser **`max(páginas, 20) × 2 MiB`** (40 MiB fixos para até 20 páginas, cerca de
0,5% de um DVD-9): trocar cor, fundo, lado, ordem ou páginas de menu não muda o vídeo. Mudar
faixas de áudio ou de legenda muda o bitrate (é outro disco) e recodifica, como deve.

**Uso no pipeline:** antes das passadas de um título, `cache.lookup(key)`; se existe, copia
(hard link quando a pasta do job e o cache estão no mesmo sistema de arquivos, cópia senão)
para `title{n}.m2v`, marca o último uso e pula para o áudio. A tela do job mostra
"Título 2 de 3 · Vídeo reaproveitado". Depois do pulldown de um título novo, `cache.store`
grava a cópia (hard link) e roda o despejo.

**Despejo:** depois de cada `store` e ao abrir a tela de jobs, se o total passar de
`CACHE_LIMIT_GB`, apaga pelo último uso mais antigo, sem tocar nas chaves do job em andamento.
`CACHE_LIMIT_GB=0` desliga o cache (nada é guardado).

**Espaço:** o pico da pasta de trabalho continua perto de 2 vezes o disco mais o cache; o
preflight passa a somar o que o cache vai precisar para os títulos novos (o despejo libera o
resto). A checagem continua só avisando quando falta espaço livre.

**Tela:** a lista de jobs mostra "Cache: 23,4 GB de 50 GB" e "Limpar cache" (confirmação;
recusado com um job ativo). `POST /jobs/cache/clean`.

## Retomar (`jobs/store.py`, `api/jobs.py`)

- Quando o worker reinicia, o job que estava `running` continua virando `failed`, mas com um
  campo novo `interrupted = True` (migração `0005`), para a tela dizer "O worker parou no meio
  (o WSL ou o PC reiniciou?)".
- **Retomar** aparece em job `failed` ou `canceled` (inclusive interrompido), quando não há
  outro job ativo da mesma pasta. `POST /jobs/{id}/resume`:
  - confere de novo que os vídeos não mudaram (o pipeline já faz isso no início);
  - volta o job para `queued` limpando `error`, `step`, `progress`, `cancel_requested`,
    `interrupted`, `qa_json` e `finished_at`; o log continua (o worker escreve "Retomado em
    ..." nele);
  - recusa se a pasta já tiver um job ativo (o índice único por pasta ativa já garante).
- O pipeline não muda por causa do retomar: ele começa do zero, e o cache faz os títulos
  prontos passarem rápido. O título que estava no meio recomeça (as passadas do ffmpeg não são
  retomáveis).
- "Gerar de novo" continua existindo (abre o Montar DVD para mudar algo); "Retomar" é o mesmo
  plano.

## Copiar o vídeo do rip de DVD

**Compatível** quando o vídeo de origem é MPEG-2 720x480 (o `_is_dvd_mpeg2` de hoje, só a
largura 720), com aspecto 4:3 ou 16:9 marcado, e:
- a leitura dos quadros (frame scan, que já roda ao gerar) classifica como filme com soft
  pulldown ou entrelaçado (o híbrido também, já que a cópia preserva as flags de origem);
- o pico de bitrate cabe no mux com as faixas escolhidas: `máximo de vídeo do arquivo +
  Σ áudio escolhido + 40 kbps × legendas ≤ 10.080 − 300 kbps`, onde o máximo de vídeo é o
  `max_bit_rate` do ffprobe quando existe, ou 9.800 kbps (o teto do padrão) quando não (ponto
  para o `tech-lead-midia`);
- o tamanho do vídeo é conhecido: a tag `NUMBER_OF_BYTES` que o MakeMKV grava por stream
  (o ffprobe a mostra em `tags`); sem ela, o tamanho do arquivo menos o áudio estimado pelo
  bitrate de cada faixa e a duração (ponto para o `tech-lead-midia`).

Um rip incompatível é recodificado como hoje, e a tela diz o motivo no título ("recodificado:
pico de bitrate alto demais para 3 faixas de áudio").

**Plano:** `TitlePlan` ganha `copy_video: bool` e `video_bytes: int | None` (o tamanho do vídeo
copiado). O `DiscChoices` ganha `reencode_rips: bool = False`.

**Calculadora:** `TitleLoad` ganha `video_bytes: int | None`. `estimate_disc` reserva o espaço
dos vídeos copiados (`× (1 + overhead)`) e resolve o bitrate só sobre a duração dos títulos
recodificados. Sem nenhum título recodificado, o disco é "Ótima" se couber (é o original) e o
cartão diz "vídeo copiado do DVD". Se não couber com as cópias, o cartão do perfil mostra "Não
cabe com o vídeo copiado" e a tela oferece a caixa "Recodificar os rips para caber"; marcada, a
calculadora trata os rips como hoje.

**Pipeline:** para um título com `copy_video`, no lugar das passadas e do pulldown:
`ffmpeg -i <origem> -map 0:<video> -c copy -f mpeg2video title{n}.m2v` (as flags de pulldown e
os tags de cor vêm do original). Áudio, legendas, mux, menus e autoria seguem iguais. O cache
não guarda vídeo copiado (extrair é rápido).

**QA de um título copiado:**
- `bitstream`: `frame_rate_code` 4, `progressive_sequence` 0 e aspecto, como hoje;
- `gop`: GOP de até 18 quadros (36 campos, o limite do NTSC) e GOP aberto aceito (o padrão só
  exige GOP fechado no começo das células, e o mux do DVD cuida disso) (ponto para o
  `tech-lead-midia`);
- `fields`: a continuidade dos campos (quebras de paridade são comuns em cortes de rip híbrido;
  aceitar até um limite, ponto para o `tech-lead-midia`);
- os outros checks (faixas, duração, sincronia, decodificação) como hoje.

## Telas

- **Montar DVD:** cada título copiado mostra o badge "vídeo copiado do DVD" (ou o motivo de não
  copiar); o bloco Disco mostra a caixa "Recodificar os rips para caber" quando há rip copiável;
  o cartão de perfil diz quanto do disco é cópia.
- **Job:** "Retomar" ao lado de "Gerar de novo"; a mensagem do job interrompido; "Vídeo
  reaproveitado" e "Vídeo copiado do DVD" no lugar das passadas.
- **Jobs:** tamanho do cache e "Limpar cache".

## Configuração

- `CACHE_LIMIT_GB=50` (app; o compose repassa ao `web` e ao `worker`); `0` desliga o cache.
- `.env.example` e CLAUDE.md 6.1 atualizados.

## Erros e casos de borda

- Cache corrompido ou apagado à mão no meio: `lookup` só aceita um `.m2v` com o `.json` ao lado
  e tamanho igual ao registrado; senão descarta e recodifica.
- Pasta de cache sem espaço: o `store` falha em silêncio no log (o job continua; perde só o
  reaproveitamento).
- Hard link impossível (sistemas de arquivos diferentes): cópia.
- Retomar com o vídeo mudado: o job falha de novo na conferência, com a mensagem de hoje.
- Rip com legenda VobSub: continua não suportada (a cópia é só do vídeo).

## Testes

- **Unitários:** chave do cache (o que muda e o que não muda a chave; o menu não muda o
  bitrate); `lookup`/`store`/despejo com arquivos falsos e relógio injetado; job em andamento
  protegido; `CACHE_LIMIT_GB=0`; migração `0005`; `resume` (estados aceitos e recusados, campos
  limpos); compatibilidade do rip (cada regra); `estimate_disc` com vídeo copiado (só cópias,
  misto, não cabe, `reencode_rips`); pipeline com cache hit (sem passadas), com cópia (sem
  passadas nem pulldown), QA de título copiado (GOP 15 aberto aceito); rotas (retomar, limpar
  cache, badges).
- **`slow`:**
  - gerar o mesmo disco duas vezes: a segunda não roda nenhuma passada de vídeo (pelo log) e o
    ISO passa na QA;
  - cancelar no meio do título 2, retomar: o título 1 é reaproveitado e o ISO passa na QA;
  - um rip MPEG-2 com GOP 15 aberto e soft pulldown (gerado com ffmpeg + o patcher atual) é
    copiado e passa na QA, e o vídeo do ISO tem os mesmos bytes do original.

## Pontos para o `tech-lead-midia` confirmar na revisão

1. A regra de pico de bitrate para copiar (usar `max_bit_rate` ou 9.800 kbps) e a folga do mux.
2. O tamanho do vídeo no MKV do MakeMKV (`NUMBER_OF_BYTES`) e o fallback.
3. GOP aberto e GOP de até 18 quadros num título copiado; o que o `dvdauthor` faz nas fronteiras
   de célula (capítulos) de um vídeo com GOP aberto.
4. Quebras de paridade de campo aceitáveis num rip híbrido copiado.
5. O cache do `.m2v` depois do pulldown: alguma informação do job (capítulos, `-itsoffset`) que
   dependa do encode e precise entrar na chave.

## Documentação

- README (EN e pt-BR): retomar, cache, cópia do rip.
- CLAUDE.md: 3.5, 5.1 (cópia), 6.1 (`CACHE_LIMIT_GB`), 7.1 (`Job.interrupted`, cache), 9, 12,
  13, Estado atual e Log de decisões.

## Ordem de entrega (grupos)

1. Reserva fixa dos menus na calculadora; chave e módulo do cache com despejo.
2. Pipeline com cache (hit e store), etapa "reaproveitado" na tela do job.
3. Migração `0005`, `interrupted`, `resume` e o botão Retomar; tamanho e limpeza do cache.
4. Compatibilidade do rip, `TitlePlan.copy_video`, calculadora com vídeo copiado,
   `reencode_rips`.
5. Pipeline e QA do título copiado; telas.
6. Testes `slow`, documentação e smoke.

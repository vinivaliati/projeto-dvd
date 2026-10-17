# Fase 4b: Robustez (design)

- **Data:** 2026-10-17
- **Branch:** `feat/fase-4b-robustez`
- **Status:** desenho aprovado pelo Vini no chat; revisada por `tech-lead-midia` (com testes na
  imagem: cópia do vídeo de ponta a ponta, GOP aberto em fronteira de célula, sequence headers,
  underflow do mux) e `revisor-codigo`, achados incorporados; aprovada pelo Vini.

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
original) e disco que toca em qualquer player (a cópia só entra quando segue o padrão; na
dúvida, o rip é recodificado como hoje).

## Pronto quando

1. Um job com falha ou cancelado (inclusive o que o worker deixou pela metade) tem o botão
   **Retomar** na tela dele, quando é o último job da pasta; retomar devolve o mesmo job à fila
   e ele pula os títulos cujo vídeo já está no cache.
2. Gerar de novo um disco mudando só o tema, as páginas do menu, a ordem ou os capítulos
   reaproveita o vídeo de todos os títulos (nenhuma passada de encode).
3. O cache fica em `WORK_DIR/cache`, limitado por `CACHE_LIMIT_GB` (padrão 50); acima do
   limite, o worker apaga os arquivos usados há mais tempo, nunca os do job atual. A lista de
   jobs mostra o tamanho do cache e um botão "Limpar cache".
4. Um rip de DVD compatível entra no disco com o vídeo copiado byte a byte (sem recodificar); a
   calculadora conta o tamanho real dele. A caixa "Recodificar os rips" aparece sempre que há
   rip copiável; quando o disco não cabe com as cópias, o cartão diz "Não cabe com o vídeo
   copiado" e sugere marcá-la.
5. O ISO com título copiado passa na QA automática, que confere que o vídeo no disco é idêntico
   ao do rip.
6. `make lint`, `make test` (100%) e `make test-slow` verdes.

## Fora de escopo

- Vários jobs em paralelo; retomar automático sem clique (decisão do Vini: botão).
- Copiar vídeo que não seja MPEG-2 de DVD NTSC 720x480 (PAL, 704x480, MPEG-1, captura de TV).
- Cache de áudio e legendas (são rápidos; refeitos a cada job).
- Capítulos "a cada N minutos" num título copiado (ver Capítulos).

## Decisões tomadas com o Vini

- Cache por **limite de espaço** (`CACHE_LIMIT_GB`, padrão 50 GB), mais antigos saem primeiro.
- Rip compatível **copiado quando cabe**; a tela oferece recodificar.
- Job interrompido fica parado com o botão **Retomar** (nada volta sozinho para a fila).
- Autonomia: depois de aprovar esta spec, o plano é escrito e executado até o fim sem parar.

## Cache do vídeo codificado (`jobs/cache.py`)

**O que guarda:** o vídeo MPEG-2 elementar de cada título recodificado, depois das duas
passadas e do soft pulldown (o `title{n}.m2v` de hoje). As passadas são cerca de 80% do tempo
de um job; áudio, legendas e mux são refeitos.

**Onde:** `WORK_DIR/cache/<chave>.m2v` e `<chave>.json`. O JSON guarda só o tamanho do `.m2v`
e o `progress` final da 2ª passada (`frame`, `dup_frames`, `drop_frames`, `out_time_us`),
que a QA usa. O último uso é o `mtime` do `.m2v` (`os.utime` a cada uso).

**Chave:** `sha256` do JSON canônico de:
- a identidade da origem: caminho relativo, tamanho e `mtime_ns`;
- a lista de argumentos da 2ª passada (`video_pass_command`), montada com caminhos fixos
  (`/media/<caminho relativo>` e `/job`), o que cobre sozinho `CODEC_OPTIONS`, filtros, `-r`,
  modo, ordem dos campos, bitrate e maxrate sem enumerar campos;
- `PULLDOWN_VERSION` (constante em `encode/mpeg2.py`, sobe quando o patcher mudar);
- a versão do ffmpeg (a mesma linha que o `/health` mostra); atualizar o ffmpeg no Dockerfile
  invalida o cache inteiro, de propósito.

Capítulos e `-itsoffset` ficam fora do `.m2v` (dvdauthor e mux), por isso fora da chave.
Renomear a pasta do disco muda o caminho e invalida o cache (aceito).

**O bitrate não pode depender do menu.** O espaço dos menus na calculadora passa a ser
`max(páginas, 20) × 2 MiB` (40 MiB fixos até 20 páginas, cerca de 0,5% de um DVD-9): trocar
cor, fundo, lado, ordem ou páginas de menu não muda o vídeo. O `maxrate` do disco passa a ser o
menor só entre os títulos **recodificados**. Mudar as faixas de áudio ou de legenda muda o
bitrate e recodifica (é outro disco).

**Uso no pipeline**, por título recodificado:
1. `title{n}.m2v` é apagado (`unlink(missing_ok=True)`) antes de tudo: nenhum passo pode
   escrever num arquivo que seja hard link do cache (o ffmpeg abre com truncamento e o patcher
   edita no lugar).
2. `lookup(key)`: se `<chave>.m2v` e `<chave>.json` existem e o tamanho bate, faz
   `os.link(cache, title{n}.m2v)`, atualiza o `mtime` e devolve o `RunResult` da 2ª passada
   montado do JSON. Qualquer `OSError` (inclusive o arquivo sumir no meio) conta como não
   encontrado. O título pula as passadas **e o pulldown**; o log diz "vídeo reaproveitado do
   cache".
3. Sem cache: passadas e pulldown como hoje; `apply_soft_pulldown` recusa arquivo com
   `st_nlink > 1`. Depois, `store(key, m2v, pass2)`: `os.link` para o cache e o JSON ao lado;
   um `OSError` vai para o log e o job segue sem cache.

Hard link sempre (cache e jobs estão no mesmo `WORK_DIR`), sem cópia de fallback e sem `.part`
(o link é atômico; o `.m2v` do job só é ligado depois de completo).

**Despejo, só no worker** (no início de cada job e depois de cada `store`): se o total passar
de `CACHE_LIMIT_GB`, apaga pelo `mtime` mais antigo, sem tocar nas chaves do plano em andamento
(o worker conhece o próprio plano). Uma entrada maior que o limite pode deixar o cache acima
dele até o próximo job. `CACHE_LIMIT_GB=0` desliga `lookup` e `store`, e o próximo despejo
esvazia o cache. O web só lê o tamanho.

**Vídeo ruim:** em `QaFailed`, o worker apaga as entradas do cache do plano do job, para
retomar ou gerar de novo não reprovar pelo mesmo vídeo.

**Espaço:** com o cache ligado, o preflight pede `3 × estimated_bytes + 1 GiB` livres na pasta
de trabalho (o hard link mantém os blocos do vídeo enquanto o `.mpg` e o ISO existem), sem
contar o que o despejo poderia liberar.

**Tela:** a lista de jobs mostra "Cache: 23,4 GB de 50 GB" e "Limpar cache". `POST
/cache/clean` (rota `clean_cache`, fora de `/jobs/{id}` para não colidir), com confirmação e
recusado quando há job ativo; apaga só arquivos regulares de `WORK_DIR/cache` com nome
`^[0-9a-f]{64}\.(m2v|json)$`, via `os.scandir`, sem seguir links. A corrida com um job que
começa logo depois é inofensiva: o job ligado ao cache mantém o próprio link.

## Retomar (`jobs/store.py`, `api/jobs.py`)

- O worker continua marcando o job pela metade como `failed`; as mensagens mudam: "O worker
  parou no meio (o WSL ou o PC reiniciou?). Use Retomar." e, para o `docker compose stop`, "O
  worker foi parado no meio da geração. Use Retomar." (sem campo novo, sem migração).
- **Retomar** aparece em job `failed` ou `canceled` que é o último da pasta (`latest_job`) e tem
  plano com menu (jobs da Fase 3 não). `POST /jobs/{id}/resume`:
  1. roda o `preflight` do plano (espaço e ISO existente com `replace_existing`); erros voltam
     para a tela do job;
  2. `clean_job_dir` (fica o log; sai, por exemplo, o ISO reprovado de 8 GB);
  3. um `UPDATE` atômico: `status='queued'`, `error`, `step`, `qa_json`, `finished_at` nulos,
     `progress=0`, `cancel_requested=0`, `created_at=now`, `WHERE id=:id AND status IN
     ('failed','canceled')`; o `IntegrityError` do índice único vira redirecionamento para o
     job ativo da pasta. Nunca limpar depois do `UPDATE`: o worker pode já ter pego o job.
- O pipeline não muda por causa do retomar: começa do zero, confere os vídeos como hoje, e o
  cache faz os títulos prontos passarem rápido. O título que estava no meio recomeça.
- O worker escreve "Início em <data>" no `job.log` toda vez que pega um job.

## Copiar o vídeo do rip de DVD

### Quando um rip é copiado

Decidido em `title_plan` (puro, só com o resumo do ffprobe e as escolhas), para a tela e o job
concordarem; o job pode depois recusar pela amostra dos quadros (abaixo), e então o título é
recodificado. Exige tudo:

- **Vídeo de DVD:** MPEG-2 720x480, `geometry(video).scale is False`, aspecto 4:3 ou 16:9, e o
  sequence header de DVD: no `side_data_list` do stream, a entrada "CPB properties" com
  `max_bitrate ≤ 9.800.000` e `buffer_size ≤ 1.835.008` (o `max_bit_rate` do ffprobe vem `N/A`
  para MPEG-2). Isso recusa MPEG-2 que não veio de DVD.
- **Orçamento herdado do disco original:** `Σ kbps do áudio que entra + 40 × legendas do disco
  ≤ Σ kbps de todo o áudio do arquivo + 40 × legendas dvd_subtitle do arquivo`. O vídeo já cabia
  no mux de 10,08 Mbps com pelo menos esse tanto de outros fluxos. Faixa da origem sem
  `bit_rate` conta 0 (conservador).
- **Tamanho conhecido:** a tag `NUMBER_OF_BYTES` ou `NUMBER_OF_BYTES-<idioma>` do vídeo (o
  MakeMKV grava; o ffmpeg não), quando é um inteiro menor que o arquivo; senão, o tamanho do
  arquivo menos Σ(`bit_rate` × duração) das faixas de áudio (limite superior, testado com erro
  de 0,08%). O `Summary`/`Video` passa a expor isso (`stream_bytes`) e o "CPB properties".
- `reencode_rips` desmarcado no `DiscChoices`.

O título que não copia mostra o motivo na tela ("recodificado: as faixas escolhidas pedem mais
espaço que o disco original").

**Amostra dos quadros (ao clicar em Gerar):** o frame scan de hoje ganha `key_frame` nas
entradas (custo zero). Num rip copiável, a amostra também estima o maior GOP em campos exibidos
(soma de `2 + repeat_first_field` entre quadros-chave). Acima de 36 campos, o título passa a ser
recodificado no plano (o plano é refeito ali mesmo, e a calculadora e os erros de "Baixa" ou
"Não cabe" valem como sempre).

### Capítulos

Num título copiado entram os capítulos do arquivo (as células do DVD original); sem capítulos no
arquivo, só o início. A opção "a cada N minutos" não vale para ele (a tela diz). Motivo, testado:
o dvdauthor leva a célula para o GOP mais próximo sem aviso, e um GOP aberto ali mostra dois
quadros com blocos ao pular para o capítulo. Por isso, depois de extrair o vídeo, o pipeline
move cada capítulo para o início do GOP **fechado** mais próximo, até 1 s de distância; um
capítulo sem GOP fechado nessa distância sai do disco, com aviso no log.

### Pipeline do título copiado

No lugar das passadas e do pulldown, a etapa `VIDEO_COPY` ("Vídeo copiado do DVD"):
1. `ffmpeg -i <origem> -map 0:<video> -c copy -progress pipe:1 -nostats -f mpeg2video
   title{n}.m2v` (as flags de pulldown e a cor vêm do original); o `progress` faz o papel da 2ª
   passada para a QA;
2. **conferência imediata** (`inspect_stream` ampliado): `frame_rate_code` = {4},
   `progressive_sequence` = {0}, um só código de aspecto igual ao do plano, um sequence header
   antes de cada GOP, primeiro GOP fechado (ou com `broken_link`), maior GOP ≤ 36 campos,
   bitrate e VBV do header de DVD; e o `.m2v` não passa de `video_bytes` em mais de 1%. Falha
   vira `PipelineError` "O vídeo do rip <arquivo> não segue o padrão do DVD (<motivo>). Marque
   Recodificar os rips e gere de novo.";
3. os capítulos levados para GOP fechado (acima);
4. áudio, legendas e mux como hoje; no mux de um título copiado, `buffer underflow` no stderr
   falha na hora: "O vídeo copiado do rip não cabe no fluxo do DVD com estas faixas. Tire uma
   faixa de áudio ou marque Recodificar os rips.".

O cache não guarda vídeo copiado (extrair é rápido).

**Plano:** `TitlePlan` ganha `copy_video: bool = False` e `video_bytes: int | None = None`
(defaults: os planos guardados continuam válidos). `DiscChoices` ganha `reencode_rips: bool =
False`. `StreamReport` ganha `max_gop_fields`, o flag de GOP fechado e o tempo de cada GOP, e a
contagem de sequence headers por GOP.

### Calculadora

`TitleLoad` ganha `video_bytes: int | None`. `estimate_disc` reserva os vídeos copiados (`×
(1 + overhead)`) e resolve o bitrate só sobre a duração dos recodificados; o `maxrate` é o menor
só entre os recodificados. Sem nenhum recodificado: `video_kbps = 0` e `maxrate_kbps = 0` no
`Estimate` e no `DiscPlan` (não usados), qualidade "Ótima" se couber, senão "Não cabe"; o cartão
diz "vídeo copiado do DVD".

### QA do título copiado

- `same_video`: o vídeo extraído do ISO tem o mesmo tamanho e o mesmo `sha256` do `.m2v` extraído
  do rip (reprova se diferir; o `sha256` do rip é guardado na hora da extração);
- `gop`: maior GOP ≤ 36 campos, GOP aberto aceito; e toda célula de capítulo começa num GOP
  fechado;
- `fields`: as quebras de paridade iguais às do `.m2v` da origem (iguais com quebras viram aviso
  "N quebras, já existiam no DVD original"; diferentes reprovam);
- `bitstream`, faixas, duração, sincronia e decodificação como hoje.

## Telas

- **Montar DVD:** badge "vídeo copiado do DVD" (ou o motivo de recodificar) no título; a caixa
  "Recodificar os rips" no bloco Disco sempre que há rip copiável; o cartão de perfil diz quanto
  do disco é cópia e "Não cabe com o vídeo copiado" quando for o caso; nos capítulos, a nota de
  que título copiado usa os capítulos do DVD.
- **Job:** "Retomar" ao lado de "Gerar de novo"; a etapa "Vídeo copiado do DVD" nos títulos
  copiados; o reaproveitamento do cache só aparece no log (as passadas ficam concluídas na hora).
- **Jobs:** tamanho do cache e "Limpar cache".

## Configuração

- `CACHE_LIMIT_GB=50` (`cache_limit_gb: float`, ≥ 0; o compose repassa ao `web` e ao `worker`);
  `0` desliga o cache.
- `.env.example` e CLAUDE.md 6.1 atualizados.

## Erros e casos de borda

- Cache apagado à mão ou pelo despejo no meio de um `lookup`: conta como não encontrado.
- Retomar com o vídeo mudado: o job falha de novo na conferência, com a mensagem de hoje.
- Rip com legenda VobSub: continua não suportada (a cópia é só do vídeo).
- Rip que muda de aspecto no meio (4:3 e 16:9): a conferência imediata recusa.

## Testes

- **Unitários:** chave do cache (o menu e a ordem não mudam a chave; bitrate, filtros, versão do
  ffmpeg e `PULLDOWN_VERSION` mudam); `lookup`/`store`/despejo com arquivos de verdade em
  `tmp_path` (`os.utime` para o tempo); job atual protegido; `CACHE_LIMIT_GB=0`; limpeza só dos
  nomes válidos; `resume` (estados aceitos e recusados, preflight, campos limpos, colisão com job
  ativo); compatibilidade do rip (cada regra); `estimate_disc` com vídeo copiado (só cópias,
  misto, não cabe, `reencode_rips`); pipeline com cache (sem passadas nem pulldown, QA com o
  `progress` guardado), com cópia (sem passadas, conferência imediata, underflow no mux); capítulos
  levados para GOP fechado; QA do título copiado; rotas (retomar, limpar cache, badges).
- **`slow`:**
  - gerar o mesmo disco duas vezes: a segunda não roda nenhuma passada de vídeo (pelo log) e o
    ISO passa na QA;
  - cancelar de forma determinística no início do título 2 (um `should_cancel` que liga no
    `VIDEO_PASS1` do título 2), retomar: o título 1 vem do cache e o ISO passa na QA;
  - um rip MPEG-2 estilo DVD comercial (GOP aberto de 12 quadros, 30 campos com pulldown,
    capítulos no meio de GOPs) é copiado, os capítulos vão para GOP fechado, o ISO passa na QA e
    o vídeo é idêntico (`-c copy -f framemd5`); dois MKV, um com `NUMBER_OF_BYTES-eng` e um sem;
  - o "CPB properties" do ffprobe lido de um `.m2v` de referência (avisa se o ffmpeg mudar o
    nome).

## A confirmar com os rips reais do Vini (QA no final do projeto)

- O nome exato da tag de tamanho num MKV do MakeMKV (olhar o `probe_json` no banco, sem tocar
  no HD).
- O maior GOP em campos de 3 rips de filme reais: se 37 ou 38 campos forem comuns, a regra dos
  36 é revista e registrada no Log de decisões (hoje, na dúvida, o rip é recodificado).
- Se o demuxer `dvdvideo` devolve bytes idênticos num título copiado com várias células.
- Pular de capítulo num título copiado no player físico.

## Documentação

- README (EN e pt-BR): retomar, cache, cópia do rip.
- CLAUDE.md: 3.5, 5.1 (cópia, GOP em campos, capítulos em GOP fechado), 6.1 (`CACHE_LIMIT_GB`),
  7.1 (cache), 9, 12, 13, Estado atual e Log de decisões.

## Ordem de entrega (grupos)

1. Reserva fixa dos menus e `maxrate` só dos recodificados na calculadora; chave e módulo do
   cache com despejo.
2. Pipeline com cache (hit, store, proteção do hard link, QA com o `progress` guardado, limpeza
   em `QaFailed`).
3. Retomar (rota, preflight, `UPDATE` atômico, mensagens do worker); tamanho e limpeza do cache.
4. Probe ampliado (`stream_bytes`, "CPB properties"), compatibilidade do rip em `title_plan`,
   calculadora com vídeo copiado, `reencode_rips`, amostra de GOP no frame scan.
5. `StreamReport` ampliado; pipeline do título copiado (extração, conferência imediata,
   capítulos em GOP fechado, underflow no mux) e QA do título copiado; telas.
6. Testes `slow`, documentação e smoke.

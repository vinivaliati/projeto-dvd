# CLAUDE.md: projeto-dvd

Este arquivo é a memória do projeto. Leia ele inteiro no início de cada sessão.
Antes de encerrar uma sessão, atualize as seções **Estado atual** e **Log de decisões**.

---

## 1. O que é o projeto

App web local para transformar a coleção pessoal de filmes e séries do Vini em **discos físicos
com menu navegável** (DVD e Blu-ray) e em **capas impressas** para as caixinhas. Os arquivos de
entrada são filmes e séries que ele comprou e guarda num HD externo.

O objetivo é afetivo: montar uma coleção para deixar de herança para os filhos. Isso define as
prioridades, nesta ordem:

1. **Qualidade de imagem** vem antes de economizar disco.
2. **Menus bonitos e fáceis de usar.** Uma criança ou um idoso precisa conseguir navegar só com o
   controle remoto.
3. **Durabilidade e compatibilidade.** O disco tem que tocar num player comum daqui a 20 anos.
   Seguir os padrões oficiais (DVD-Video e BDMV) à risca, sem atalhos que só funcionam no VLC.
4. **Qualidade de portfólio.** O repositório `vinivaliati/projeto-dvd` é público no GitHub, então
   código limpo, testes, README e Docker importam.

### Fora do escopo

- Ripar discos ou quebrar DRM. Os arquivos de entrada já estão no HD.
- Gravar o disco direto pelo app. O WSL não acessa o gravador, então o app entrega um `.iso` e a
  gravação é feita no Windows (ImgBurn ou o gravador nativo do Windows).
- Gerar arte do zero com IA. A arte é **pesquisada e baixada** do TMDB; o app só faz a composição
  (layout, lombada, verso, label).
- Qualquer alteração nos arquivos originais do HD. O HD é somente leitura para o app.

---

## 2. Regras de trabalho para o Claude Code

### 2.1 Skills obrigatórias

Este projeto usa dois plugins. Se não estiverem instalados, peça para o Vini rodar (cada linha em
um prompt separado, nesta ordem):

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

**Superpowers** (processo): toda funcionalidade nova ou fase do roadmap segue o fluxo
1. `/superpowers:brainstorm` para fechar o que vai ser feito e tirar dúvidas com o Vini;
2. `/superpowers:write-plan` para gerar o plano, salvo em `docs/plans/AAAA-MM-DD-<tema>.md`;
3. `/superpowers:execute-plan` para executar, com testes escritos antes do código (TDD) sempre que
   fizer sentido.
Use as skills de debugging sistemático e de verificação antes de dizer que algo está pronto.

**Ponytail** (simplicidade): prefira sempre a menor solução que resolve o problema. Nada de
dependência, abstração ou camada extra "para o futuro".

Quando as duas puxarem para lados diferentes, vale isto: o Ponytail manda no *tamanho da solução*,
mas **nunca** justifica pular testes, desrespeitar as especificações de DVD/Blu-ray, ou abrir mão das
exigências de portfólio deste arquivo.

### 2.2 Estilo de escrita

- **Não use travessão (—) na escrita.** Em texto corrido, use vírgula, ponto, dois-pontos ou
  parênteses. Em listas e tópicos ele pode aparecer de vez em quando, mas não como padrão. Vale
  para respostas, documentação, README, comentários e mensagens de commit.
- Converse com o Vini em **português**. Código, nomes de variáveis, commits, README e docstrings
  ficam em **inglês** (portfólio).
- Seja direto. Explique o *porquê* das decisões técnicas, principalmente as que envolvem mídia.

### 2.3 Preferências do Vini

- Mostrar **arquivos completos**, não patches ou diffs.
- Trabalhar **um arquivo por vez**: apresentar, esperar o ok, seguir para o próximo.
- SQL com **vírgula à esquerda** (leading comma).
- Antes de qualquer ação demorada ou irreversível (encode de horas, apagar intermediários,
  reescrever muita coisa), avisar e pedir confirmação.

### 2.4 Ritual de sessão

**No início:** ler este arquivo, rodar `git status` e `git log --oneline -15`, ler a seção Estado atual
e o plano ativo em `docs/plans/`, e resumir em 3 linhas onde paramos.

**No fim:** atualizar Estado atual e Log de decisões, marcar o roadmap, e fazer commit
(`docs: update session state`). O agente `organizador` pode fazer isso.

### 2.5 Definição de pronto

Uma tarefa só está pronta quando:
- `ruff check`, `ruff format --check`, `mypy` e `pytest` passam;
- tem teste cobrindo o comportamento novo;
- a documentação relevante foi atualizada (README, docstrings, este arquivo);
- se gera disco: o `.iso` passou no checklist de QA (seção 9).

---

## 3. Funcionalidades

### 3.1 Biblioteca
- Uma pasta de entrada (`HOST_MEDIA_DIR`) com **uma subpasta por disco** (ex: "Senhor dos Aneis"
  com os três filmes). O app não varre o HD inteiro; subpastas dentro da pasta do disco valem.
- Escanear recursivamente os vídeos da pasta do disco (`.mkv`, `.mp4`, `.m4v`, `.avi`, `.mov`,
  `.ts`, `.m2ts`), ignorando links simbólicos.
- Ler com `ffprobe`: duração, resolução, fps, codec, HDR (inclusive Dolby Vision, com aviso
  próprio para o perfil 5), faixas de áudio (idioma, canais, codec), legendas (idioma, tipo:
  texto ou imagem), capítulos.
- Detectar legendas externas (`.srt`, `.ass`, `.ssa`, `.sup`, `.idx` com o seu `.sub`) ao lado do
  vídeo.
- Rescan incremental por `(caminho, tamanho, mtime_ns)`, sem reprocessar tudo.

### 3.2 Curadoria
- Sugerir automaticamente filme, série, temporada e episódio pelo nome do arquivo
  (ex: `S01E03`, `1x03`, ano entre parênteses), confirmando no **TMDB**.
- Permitir corrigir o match manualmente pela busca.
- O app sugere e o Vini confirma (Fase 2): **Sugestão** quando o título (e o ano) bate exatamente
  com um resultado só; **Confira** quando é ambíguo, e esse nunca é confirmado em lote.
- Agrupar em **coleções** (ex: "O Senhor dos Anéis", "Friends: Temporada 1"). Usar a "collection"
  do TMDB quando existir. Fase 2: sem tabela de coleções; o id e o nome da collection ficam nos
  detalhes do título, para a Fase 7.
- Baixar as artes para uma pasta local (pôster, fundo, logo, still de episódio) e salvar sinopse,
  elenco, ano e duração. Idioma preferido `pt-BR`, com fallback para `en`. Fase 2: um conjunto
  padrão por título; escolher entre várias artes fica para a Fase 5.

### 3.3 Montador de disco (núcleo do app)

**O Vini escolhe o tipo de disco em cada caso.** O app nunca decide sozinho: ele sugere e alerta.

- Criar um **projeto de disco** e escolher o **perfil** dele (DVD-5, DVD-9, BD-25, BD-50).
- O perfil pode ser trocado a qualquer momento, e a calculadora se atualiza na hora.
- Adicionar títulos: vários filmes num disco, ou episódios de uma série.
- Reordenar títulos, definir capítulos (do arquivo de origem ou automáticos a cada N minutos).
- Escolher, por título, as faixas de áudio e as legendas que entram no disco, e qual é o padrão.
- **Calculadora de capacidade**, sempre visível:
  - tamanho estimado vs. capacidade do perfil;
  - bitrate de vídeo resultante e um indicador de qualidade (verde / amarelo / vermelho);
  - sugestão quando ficar ruim: "trocar para BD-25", "dividir em 2 discos" ou "remover faixas
    de áudio extras". **A sugestão nunca é aplicada sem o Vini clicar.**
  - se ele quiser seguir mesmo no vermelho, o app pede confirmação explícita e registra a escolha.
- **Boxes (conjuntos de discos):** agrupar vários projetos de disco de uma coleção, com tema visual
  único e numeração ("Disco 1 de 3"). **Cada disco do box tem o próprio perfil**, então é possível
  misturar (ex: os filmes em BD-50 e os extras em DVD-9).
- Assistente "dividir série em discos": dado o perfil escolhido, distribui os episódios em N discos
  respeitando a qualidade mínima. O Vini revisa e ajusta antes de confirmar.
- Fase 4a (feito): a tela **Montar DVD** de uma pasta: todos os vídeos dela, em ordem editável,
  tipo Filmes ou Série, **idiomas escolhidos uma vez para o disco** (cada título usa a melhor
  faixa de cada idioma; o que falta é avisado), capítulos, tema do menu com preview e a
  calculadora do disco inteiro (o mesmo bitrate para todos os títulos). As escolhas ficam salvas
  em `disc_project`; as confirmações (qualidade baixa, substituir ISO) nunca são salvas. Limites:
  60 títulos, 4 idiomas de áudio e 4 de legenda.

### 3.4 Menus
- Menu principal com os títulos do disco; submenu de episódios para séries; submenus de áudio e de
  legendas.
- **Tema por coleção**: fundo (arte do TMDB tratada), tipografia, cores, estilo dos botões.
- Preview do menu como imagem na interface, antes do encode.
- Navegação completa pelo controle remoto (cima, baixo, esquerda, direita, enter); o botão "menu"
  sempre volta para o menu principal.
- Fase futura: menu com vídeo de fundo e música em loop.
- Fase 4a (feito): ao colocar o disco abre o menu principal. Filmes: um botão por filme (mais de
  6 ganham páginas) e o filme volta à própria página e botão. Série: "Tocar todos", páginas de
  até 6 episódios (o episódio escolhido segue até o fim do disco). "Áudio" e "Legendas" são
  páginas com ✓ no item ligado. Tema: fundo do TMDB (ou neutro), paleta fechada de 6 cores (ou
  a tirada do fundo) e lado dos botões. Logo e menu de capítulos ficam para a Fase 8.

### 3.5 Geração do disco
- Fila de jobs: encode → render do menu → authoring → `.iso`.
- Progresso em tempo real (lido da saída do ffmpeg), tempo estimado, log completo de cada etapa.
- Cancelar job (Fase 3). Fase 4b (feito): **Retomar** (o mesmo job volta à fila, depois do
  preflight e da limpeza da pasta) e o **cache do vídeo codificado** em `WORK_DIR/cache` (hard
  link do `.m2v` depois do pulldown, chave = sha256 do comando da 2ª passada, da origem, da
  versão do ffmpeg e da `PULLDOWN_VERSION`; despejo pelo uso mais antigo, só no worker, acima de
  `CACHE_LIMIT_GB`; uma QA reprovada apaga o vídeo do cache).
- Antes de começar, checar o espaço livre na pasta de trabalho (um BD-50 pode precisar de >100 GB
  de intermediários).
- Limpar os intermediários ao final, **com confirmação**.

### 3.6 Capas
- Para cada disco ou box: montar a **capa completa da caixinha** (frente + lombada + verso) e o
  **label do disco**, em PDF pronto para imprimir.
- Frente: pôster ou arte escolhida e título (sem logo, decisão da Fase 5). Lombada: título,
  número do disco, padrão visual que forma uma imagem contínua quando os discos do box ficam lado
  a lado (desejável, Fase 7). Verso: sinopse, lista de títulos/episódios, duração, áudio,
  legendas, perfil do disco.
- Fase 5: uma arte só para a frente, escolhida numa grade com todas as do TMDB; o verso usa o
  fundo do menu e o label também.
- Saída em 300 DPI, sRGB (CMYK descartado na Fase 5), com sangria e marcas de corte.

---

## 4. Perfis de disco

| Perfil | Capacidade | Vídeo | Áudio | Uso típico |
|---|---|---|---|---|
| DVD-5 | 4,7 GB | MPEG-2 720x480 (NTSC) | AC-3 | 1 filme curto, ou 3 a 4 episódios de 45 min |
| DVD-9 | 8,5 GB | MPEG-2 720x480 (NTSC) | AC-3 | 1 filme longo, ou 6 a 8 episódios |
| BD-25 | 25 GB | H.264 1080p | AC-3 / DTS / LPCM | 1 a 3 filmes com boa qualidade |
| BD-50 | 50 GB | H.264 1080p | AC-3 / DTS / LPCM | trilogia estendida, temporada inteira |

Cada perfil é um objeto de configuração (não código espalhado): capacidade útil, resolução, codec,
limites de bitrate, faixas de qualidade (verde/amarelo/vermelho), formato de legenda e ferramenta
de authoring. Adicionar um perfil novo tem que ser só adicionar uma entrada.

**Calculadora** (`planner/calculator.py`, DVD na Fase 3):
- capacidade pelo **menor** valor entre −R e +R, em setores de 2048 bytes: DVD-5 2.295.104,
  DVD-9 4.171.712 (a mídia ainda não foi comprada);
- `capacidade_útil = 97% dos bytes − 4 MiB` (IFO, BUP e sistema de arquivos);
- `bitrate_vídeo = capacidade_útil × 8 / 1,03 / duração − Σáudio − 10 kbps × legendas`
  (3% de overhead de mux medido), limitado a 95% do `maxrate = min(9000, 10080 − Σáudio − 40 ×
  legendas − 300)` kbps (alvo igual ao maxrate transformaria o 2 passes em CBR);
- abaixo de 1 Mbps o perfil "não cabe".
As faixas de qualidade (palavras na tela: Ótima, Aceitável, Baixa, Não cabe), a calibrar com
testes reais:
- DVD: verde ≥ 5 Mbps, amarelo entre 3,5 e 5, vermelho < 3,5.
- Blu-ray: verde ≥ 15 Mbps, amarelo entre 8 e 15, vermelho < 8.

**Exemplo de referência:** a trilogia de O Senhor dos Anéis tem ~9h20 na versão de cinema e ~11h45
na estendida. Num DVD-9 ficaria com ~2 Mbps (vermelho). Num BD-50 fica verde. O app mostra isso,
mas quem decide é o Vini.

---

## 5. Especificações técnicas de mídia

Estas regras ficam a cargo do agente `tech-lead-midia`. Tudo que for "a confirmar" tem que ser
validado com teste antes de virar padrão.

### 5.1 DVD-Video
- Vídeo: MPEG-2, 720x480 NTSC (padrão dos DVDs brasileiros, região 4), PAL 720x576 opcional.
- Aspecto: 16:9 anamórfico (flag correta) ou 4:3, conforme a origem.
- Bitrate: vídeo ≤ 9,0 Mbps no app (o padrão permite 9,8; a folga cobre o pico do VBV dentro do
  mux de 10,08 Mbps). **Encode em 2 passes** pelo ffmpeg com os parâmetros de
  `encode/video.py` (GOP fechado de 12, VBV 1835k, cor BT.601 com tags via `mpeg2_metadata`,
  `-r` sempre explícito). **Proibido `-target ntsc-dvd`**: duplica quadros (tranco).
- Fontes em 23,976 fps: **soft pulldown** por um patcher próprio no estilo DGPulldown
  (`encode/mpeg2.py`, edita o `.m2v` no lugar). Fontes 480i ficam entrelaçadas; rips de DVD são
  classificados pelos quadros (filme, entrelaçado ou híbrido, este com hard telecine).
- Áudio: só AC-3 48 kHz. Copiar se a origem já for AC-3 de até 448 kbps e 6 canais; senão
  converter mantendo o layout (448k de 3 a 6 canais, 192k estéreo, 96k mono). DTS é opcional na
  especificação do DVD e LPCM gasta bitrate demais. Até 8 faixas de áudio por título.
- Legendas: bitmap (subpicture). SRT e texto do MKV viram subpicture com `spumux` (DejaVu Sans
  26, contorno, margens de ~10%). PGS, VobSub e ASS ainda não. Até 32 faixas.
- Limites da estrutura: até 99 títulos e 99 capítulos por título.
- Menus: 720x480; respeitar a **área segura** (~10% de margem) porque TVs cortam as bordas;
  o destaque dos botões é um subpicture com **paleta de no máximo 4 cores** (restrição real para o
  designer); até 36 botões por menu.
- Menus (Fase 4a, testados na libdvdnav):
  - fundo desenhado em pixels quadrados (854x480 no 16:9, 640x480 no 4:3) e reduzido para
    720x480; o destaque é desenhado direto em 720x480, sem antialias, com coordenadas pares;
  - menu 16:9 com `widescreen="nopanscan"` e **dois streams de botões** (o 1 é o letterbox, com
    `y' = 60 + 3y/4`), senão o destaque fica fora do lugar numa TV 4:3;
  - cada página é 1 s de MPEG-2 parado com `-q:v 2` e `+ilme` (sem ele sai
    `progressive_sequence = 1`), `-maxrate` junto do `-bufsize`, AC-3 silencioso e
    `pause="inf"`;
  - **um titleset por título** (o dvdauthor marca toda faixa declarada como presente em todos os
    títulos do titleset);
  - toda a navegação passa pelo VMGM: menu 1 (entry title, onde caem Title e Menu) mostra a
    página principal; menu 2 despacha o próximo título (`g2`, zerado antes do pulo); menu 3
    mostra a página do `g5`; páginas a partir do menu 4. Registradores só g0 a g12 (g14 e g15
    são do dvdauthor); `button = 1024 × n`;
  - **até 60 títulos**: o despachante custa 2 comandos por título, e uma PGC aceita 128.
- **Cópia do rip de DVD** (Fase 4b): MPEG-2 720x480 sem escala, com o sequence header de DVD
  ("CPB properties": `max_bitrate ≤ 9,8 Mbps`, `buffer ≤ 1.835.008`), copiado byte a byte
  quando o áudio escolhido cabe no orçamento do disco original (Σ kbps escolhidos + 40 por
  legenda ≤ Σ kbps do arquivo + 40 por VobSub) e o tamanho é conhecido (tag `NUMBER_OF_BYTES`
  do MakeMKV, ou arquivo menos áudio). GOP até **36 campos exibidos** (a amostra de quadros ao
  gerar e a conferência logo depois de extrair recusam acima). Capítulos do rip, levados ao GOP
  **fechado** mais próximo (até 1 s; o dvdauthor põe a célula em GOP aberto sem avisar, e pular
  para ela mostra blocos). Underflow no mux de um título copiado para o job na hora. A QA confere
  o vídeo idêntico (sha256), GOP e células, e as quebras de campo iguais às do original (aviso).
- Ferramentas: `ffmpeg` para o encode, `dvdauthor` para VIDEO_TS e navegação, `spumux` para
  botões e legendas, `genisoimage -dvd-video -udf` para o ISO (ver Log de decisões: o `xorriso`
  não gera a ponte UDF 1.02 que o DVD-Video exige).
- O XML do `dvdauthor` sempre declara o formato de vídeo também no `<vmgm>`; sem isso ele falha
  com "no video format specified for VMGM".

### 5.2 Blu-ray (BDMV)
- Vídeo: H.264 1080p 23,976 fps, com x264 em modo de compatibilidade Blu-ray (`--bluray-compat`,
  level 4.1, GOP e VBV dentro do padrão, slices). Parâmetros exatos a confirmar e testar.
- Origem em HDR/4K: converter para SDR 1080p (tonemapping), porque o BDMV comum não aceita HDR.
- Áudio: AC-3 até 640 kbps, DTS ou LPCM. Copiar sem recodificar quando a origem for compatível.
- Legendas: PGS. O `tsMuxeR` converte SRT para PGS.
- Estrutura: `tsMuxeR` gera BDMV/CERTIFICATE e também o próprio `.iso` em UDF 2.5x (o `xorriso`
  não faz UDF 2.50). Verificado na Fase 0 com o tsMuxeR 2.7.0.
- **Menus de Blu-ray: principal risco do projeto.** Não existe ferramenta aberta madura. A Fase 6
  é um spike para comparar:
  1. menus HDMV (IGS), gerando o stream de menu;
  2. menus BD-J (Java), que são programáveis mas complexos;
  3. plano B: disco sem menu interativo, com playlist e capítulos (toca em sequência, e os
     capítulos permitem pular entre filmes);
  4. plano C: usar uma ferramenta externa só para o menu.
  O spike termina com uma decisão registrada no Log de decisões.

### 5.3 Armazenamento e performance no WSL
- O HD externo aparece no WSL em `/mnt/<letra>/...`. A pasta de entrada pode ficar no `C:` ou no
  próprio HD externo, e é montada no Docker como **somente leitura** (`/media:ro`).
- Ler do `/mnt` é mais lento, mas serve para o encode. Os **intermediários** ficam no sistema de
  arquivos do WSL (ext4), que é bem mais rápido.
- O `.iso` final e os PDFs vão para uma pasta no lado do Windows (ex:
  `/mnt/c/Users/<usuario>/Videos/projeto-dvd/`) para gravar e imprimir com facilidade.

---

## 6. Stack

| Camada | Escolha |
|---|---|
| Linguagem | Python 3.12, gerenciado com **uv** |
| Qualidade | **ruff** (lint e format), **mypy** (strict no projeto todo), **pytest** + pytest-cov |
| API | **FastAPI** + **Pydantic** v2 |
| Banco | **SQLite** com **SQLModel**; migrações com **Alembic** |
| Frontend | **Jinja2 + HTMX + CSS próprio** (sem build; a Fase 4a manteve: o tema tem 3 ajustes, sem editor livre) |
| Jobs | tabela `jobs` no SQLite + processo worker separado. Sem Celery/Redis a menos que fique necessário |
| Mídia | `ffmpeg`/`ffprobe`, `dvdauthor`, `spumux`, `genisoimage`, `tsMuxeR`, `xorriso` |
| Imagens e PDF | **Pillow** para menus, capas e o PDF de impressão (sem reportlab, Fase 5) |
| Metadados | **TMDB API** via `httpx2` (token no cabeçalho `Bearer`), detalhes confirmados guardados no banco |
| Infra | **Docker** + **docker-compose**; CI no **GitHub Actions** |

### 6.1 Variáveis de ambiente (`.env`, nunca commitar; manter `.env.example`)

Variáveis do **compose** (caminhos no host, WSL), existentes desde a Fase 0:
```
HOST_MEDIA_DIR=/mnt/c/Users/<usuario>/Videos/entrada   # uma subpasta por disco; /media (ro)
HOST_WORK_DIR=/home/<usuario>/projeto-dvd-work      # montada em /work (ext4, nunca /mnt/c)
HOST_OUTPUT_DIR=/mnt/c/Users/<usuario>/Videos/projeto-dvd   # montada em /output
```
As pastas precisam existir antes do `up` (o Docker cria as que faltam como root).

Variáveis do **app** (caminhos dentro do container), entram quando forem usadas:
```
MEDIA_DIR=/media                # Fase 1; a pasta de entrada (uma só)
DATABASE_URL=sqlite:////data/projeto_dvd.db   # Fase 1; volume data
WORK_DIR=/work                  # Fase 3; intermediários e logs dos jobs
OUTPUT_DIR=/output              # Fase 3; ISOs em OUTPUT_DIR/iso
ALLOWED_HOSTS=["localhost","127.0.0.1"]   # Fase 3; hosts aceitos (TrustedHost)
HOST_OUTPUT_DIR=                # Fase 3; o compose repassa ao web só para mostrar o caminho do ISO no Windows
TMDB_TOKEN=                     # Fase 2; o "Token de leitura da API" (Bearer); vazio desliga a curadoria
TMDB_LANGUAGE=pt-BR             # Fase 2; o compose repassa as duas só ao web
CACHE_LIMIT_GB=50               # Fase 4b; vídeo codificado guardado (GB decimais); 0 desliga
```

### 6.2 Docker
- `Dockerfile` com todas as ferramentas de mídia: base por digest, pacotes apt por versão,
  tsMuxeR e uv por checksum/digest. Usuário não root `app` (UID 1000).
- Estágios `runtime` (a imagem do app, também o padrão de um `docker build .`) e `test` (runtime
  + dependências de dev + `tests/`, para os testes `slow` com as ferramentas reais, sem rede).
- `docker-compose.yml` com o serviço `web` (porta só em `127.0.0.1:8000`, `target: runtime`), o
  serviço `worker` (mesma imagem, `python -m projeto_dvd.jobs.worker`, `init: true`,
  `stop_grace_period: 30s`, sem porta), os volumes acima e o volume nomeado `data` (banco
  SQLite em WAL; `docker compose down -v` apaga). O Alembic roda só no `web`; o worker espera a
  migração.
- `make dev`, `make test`, `make test-slow`, `make lint`, `make format` e `make fixtures`
  documentados no README.

---

## 7. Arquitetura

```
src/projeto_dvd/
  api/            # rotas FastAPI (fragments HTMX), deps compartilhadas, mesma origem
  web/            # templates Jinja, estáticos
  library/        # scan, ffprobe, detecção de legendas externas
  metadata/       # parser de nomes, modelos e cliente TMDB, matching, artes, curadoria (banco e disco)
  planner/        # perfis, calculadora, fontes suportadas, disco da pasta (disc), modelos do
                  # plano (disc_plan), escolhas → plano (disc_build), faixas por título (dvd_plan)
  encode/         # comandos ffmpeg por perfil (funções puras); mpeg2.py: soft pulldown e leitura
  authoring/
    dvd/          # mux, menus (MPEG-2 parado, spumux), dvdauthor XML, QA automática do ISO
    bluray/       # tsMuxeR meta, (menus após o spike)
  menus/          # páginas (pages), paleta e fundos (theme), geometria (layout), Pillow (render)
  covers/         # medidas (sizes), conteúdo, opções de arte, layout em mm, render e PDF
  jobs/           # runner de processos, pipeline, fila (store), worker, arquivos do job
  db/             # modelos SQLModel, sessão, migrações
  app.py          # fábrica create_app (uvicorn --factory)
  config.py       # settings via pydantic-settings
  tools.py        # versões das ferramentas de mídia (/health)
tests/
  unit/
  integration/    # usam clipes curtos gerados com ffmpeg -f lavfi
  fixtures/
docs/
  plans/          # planos do superpowers
  decisions/      # ADRs curtas quando a decisão for grande
docker/
.claude/agents/
```

**Pipeline:**
`scan → probe → curadoria (TMDB) → projeto de disco (perfil escolhido) → encode → render do menu → authoring → ISO → gravação no Windows`
Em paralelo: `artes → composição da capa → PDF`.

### 7.1 Modelo de domínio
- `MediaFile` (tabela `media_file`, Fase 1): arquivo físico; pasta do disco, caminho, tamanho,
  `mtime_ns`, saída bruta do ffprobe (`probe_json`) ou o erro. Resumo, faixas e avisos são
  calculados na hora a partir do JSON (sem tabelas de faixas e sem `SourceFolder` por enquanto).
- `Title` (tabela `title`, Fase 2): 1 para 1 com `MediaFile` (a chave é o `media_file_id`, cascade
  pelo ORM); status (`suggested`, `doubtful`, `confirmed`, `not_found`), tipo, `tmdb_id`,
  temporada/episódio, o `label` da tela e os detalhes do TMDB inteiros em `tmdb_json` (nome,
  sinopse, elenco, duração e collection calculados na hora).
- `Collection`: agrupamento (franquia ou temporada), com tema visual. Adiada para a Fase 7.
- `DiscProject` (tabela `disc_project`, Fase 4a): um por pasta; o `DiscChoices` inteiro em
  `choices_json` (tipo, ordem, perfil, idiomas, capítulos, tema), salvo a cada mudança e
  reconciliado com a pasta ao abrir. Sem chave estrangeira (um rescan não apaga o projeto).
- `DiscSet`: box com vários `DiscProject` (cada um com o próprio perfil).
- `Job` (tabela `job`, Fase 3): uma geração de disco; o `DiscPlan` inteiro em `plan_json` (um
  `TitlePlan` por vídeo e o `MenuPlan` com as páginas; jobs da Fase 3 convertidos pela migração
  `0004`), status, etapa (`"2:video_pass2"` por título), progresso, erro, QA e caminho do ISO;
  log em `WORK_DIR/jobs/<id>/job.log`. Fase 4b: retomar devolve o mesmo job à fila; o cache
  do vídeo (`WORK_DIR/cache/<chave>.m2v` e `.json`) não tem tabela no banco.
- `ArtAsset`: arte baixada; tipo (poster, backdrop, logo, still), caminho, origem, idioma.
- `CoverLayout`: escolhas de arte e texto de uma capa, e o PDF gerado.

### 7.2 Telas
1. **Biblioteca** (Fase 1): um card por pasta de disco, com status (vazia, não escaneada, ok,
   com avisos, mudou). A **tela da pasta** mostra a tabela dos vídeos e o botão Escanear. Fase 2:
   o cartão da pasta mostra quantos vídeos têm match confirmado (filtros ficam para depois).
2. **Título**: dados técnicos, match TMDB (buscar/corrigir), artes. Fase 2: o match fica na tela
   da pasta, numa lista de cartões acima da tabela técnica (sem tela própria por enquanto).
3. **Coleções**: criar, agrupar, definir tema.
4. **Montador de disco**: títulos, **seletor de perfil**, calculadora, ordem, capítulos, áudio/legenda.
   Fase 4a: a tela **Montar DVD** (`/folders/{pasta}/dvd`) com Títulos, Idiomas, Menu (preview e
   ajustes), Capítulos e Disco, e a barra fixa da calculadora; a tela 6 (Menu) fica nela.
5. **Box**: discos do conjunto, perfil de cada um, numeração.
6. **Menu**: tema e preview.
7. **Capa**: escolha das artes, preview, gerar PDF.
8. **Jobs** (Fase 3): lista e tela do job (etapas, progresso, tempo restante, log, cancelar,
   apagar temporários, resultado da QA). Com vários títulos, só o título atual mostra as
   etapas. Retomar fica para a Fase 4b.
9. **Configurações**: pastas, chave TMDB, padrões (NTSC/PAL, idioma).

---

## 8. Time de agentes (`.claude/agents/`)

Criar na Fase 0, cada um com `name`, `description` (quando usar) e instruções. Todos seguem este
CLAUDE.md, inclusive a regra do travessão.

| Agente | Papel | Quando chamar |
|---|---|---|
| `tech-lead-midia` | Especialista em ffmpeg, x264, MPEG-2, DVD-Video, BDMV, dvdauthor, spumux, tsMuxeR. Define e revisa parâmetros de encode e authoring. Conservador: padrão oficial primeiro. | Qualquer código em `encode/`, `authoring/`, perfis de disco, bug de player. |
| `organizador` | Product owner. Mantém roadmap, quebra fases em tarefas, conduz o brainstorm do superpowers, atualiza este arquivo e o log de decisões no fim da sessão. | Início e fim de sessão, planejamento de fase, quando o escopo mudar. |
| `designer` | Senso estético. Temas de menu por coleção, tipografia, paleta, composição de capa, lombada e label. Pensa em legibilidade na TV a 3 metros e nas restrições técnicas (área segura, 4 cores de destaque no DVD). | `menus/`, `covers/`, escolha de artes, telas da UI. |
| `curador` | Metadados. Parser de nomes, matching no TMDB, ordem de episódios, escolha das melhores artes (resolução, idioma, sem texto quando for fundo). | `metadata/`, matches errados, montar coleções. |
| `qa` | Testes e validação. Escreve testes, roda o checklist de QA do ISO, verifica tamanho vs. capacidade e estrutura VIDEO_TS/BDMV. | Antes de declarar pronto qualquer coisa que gere disco; revisão de cobertura. |
| `revisor-codigo` | Qualidade de portfólio. Legibilidade, tipos, simplicidade (alinhado ao Ponytail), segurança (nada de mídia, artes ou chaves no git), README. | Antes de cada commit relevante ou PR. |

---

## 9. Testes e QA

- **Unitários**: parser de nomes, calculadora, construtores de comando (comparar a lista de
  argumentos gerada, sem rodar o ffmpeg), geração do XML do dvdauthor, layout de capa (medidas).
- **Integração**: gerar clipes de 10 a 30 s com `ffmpeg -f lavfi` (testsrc + sine), montar um
  disco de verdade e validar a estrutura. Marcar como `@pytest.mark.slow` e rodar no CI.
- **Cache, retomar e cópia** (Fase 4b): os testes `slow` montam o mesmo disco duas vezes (a
  segunda sem nenhuma passada), retomam um job cancelado no título 2 e copiam um rip estilo DVD
  comercial (GOPs abertos, capítulos no meio de GOP), com o vídeo do ISO idêntico ao do rip.
- **Navegação** (Fase 4a): os testes `slow` navegam o ISO com a **libdvdnav** (a VM do VLC, via
  `ctypes`, só na imagem de teste): inserir abre o menu, "Tocar todos" encadeia, Title e Menu
  voltam ao principal, a escolha de idioma vale no título, o filme volta à página dele. Os
  unitários desenham os menus com a fonte do Pillow; a imagem de teste usa o DejaVu
  (`REAL_FONTS=1`).
- **TMDB**: mockar com `httpx2.MockTransport` (o `respx` mocka o `httpx`, não o `httpx2`); nunca
  chamar a API real nos testes; JSON de teste inventado, nunca copiado de respostas reais.
- **Checklist de QA do ISO** (agente `qa`), antes de gravar qualquer disco:
  1. tamanho do ISO ≤ capacidade física da mídia (reprova); acima da capacidade útil de 97%
     só avisa;
  2. estrutura válida (VIDEO_TS com IFO/BUP/VOB, um titleset por título e o VIDEO_TS.VOB dos
     menus, ou BDMV/CERTIFICATE);
  3. `ffprobe` nos streams de cada título (`-title N`) e de cada página de menu
     (`-menu 1 -menu_vts 0 -pgc K`): codec, resolução, aspecto, faixas e idiomas corretos;
  4. abre no VLC pelo menu, cada botão leva ao título certo, "menu" volta (disco sem menu, Fase
     3: o filme começa sozinho, "Menu" e "Title" não travam, no fim o disco para);
  5. áudio e legendas trocam pelo menu (sem menu: pelo VLC/controle; a faixa e a legenda do
     início são as escolhidas);
  6. primeiro disco de cada perfil: testar num **player físico** antes de gravar em lote
     (preferir mídia regravável para os testes).

---

## 10. Capas: especificações

- Saída: PDF A4 em 300 DPI (sRGB, JPEG q95 sem subamostragem de cor), sangria de 3 mm, marcas
  de corte e de dobra, régua de 50 mm e o aviso "Imprima em tamanho real" no pé da folha.
- Medidas em `covers/sizes.py` (Fase 5), **a conferir** com a caixa e a folha compradas: caixa
  Amaray 2 × 129,5 + 14 = 273 x 183 mm; etiqueta redonda Pimaco de 117 mm com furo de 41 mm, 2
  por folha A4. Blu-ray fica para a Fase 6.
- Texto da capa em português; usar a sinopse `pt-BR` do TMDB.
- Pasta de artes (Fase 2): `OUTPUT_DIR/covers/<pasta do disco>/<Título (ano)>/` com `poster.jpg`,
  `backdrop.jpg`, `logo.png`, `metadata.json`; episódios em `<Série>/` com `S01E03.jpg` e
  `S01E03.json`. Nomes saneados para o Windows. PDFs em `OUTPUT_DIR/print/`.

---

## 11. Segurança, direitos e repositório

- **Nunca commitar**: arquivos de mídia, `.iso`, intermediários, artes baixadas, `.env`, o banco
  SQLite. O `.gitignore` cobre tudo isso desde o primeiro commit.
- O README traz a atribuição exigida pelo TMDB (uso da API sem endosso do TMDB) e o logo
  conforme as regras deles.
- As artes são para uso pessoal (imprimir as capas da própria coleção).
- O README em inglês (com versão em português em `README.pt-BR.md`, mantida em sincronia) explica: o que o app faz, screenshots, arquitetura, como rodar com Docker,
  decisões técnicas interessantes (calculadora, perfis, spike de Blu-ray).
- Commits pequenos no padrão **Conventional Commits** (`feat:`, `fix:`, `docs:`, `test:`,
  `refactor:`, `chore:`). Branch principal `main`; trabalho de cada fase em branch própria
  (`feat/fase-1-biblioteca`) com PR.

---

## 12. Roadmap

Cada fase começa com `/superpowers:brainstorm` e um plano em `docs/plans/`.

Ordem de execução: 1 → 3 → 2 → 4 → 5 → 6 → 7 → 8 (aprovada em 2026-10-15). Os números das fases
não mudam; a Fase 3 vem antes da 2 para ter um disco de verdade o quanto antes.

- [x] **Fase 0: Setup.** Estrutura do repo, `pyproject` com uv, ruff/mypy/pytest, `.gitignore`,
      `.env.example`, Dockerfile com as ferramentas de mídia, docker-compose, CI, README inicial,
      agentes em `.claude/agents/`. Pronto quando: `docker compose up` sobe a página "hello" e o
      CI fica verde.
- [x] **Fase 1: Biblioteca.** Pasta de entrada com uma subpasta por disco, scan, ffprobe,
      catálogo, tela de biblioteca e tela da pasta.
- [ ] **Fase 3: DVD mínimo.** 1 filme → ISO sem menu, com perfil DVD-5/DVD-9 escolhido, que passa
      no checklist. Inclui a calculadora de um título, a escolha de faixas e os jobs com
      progresso (worker). Pronto em duas etapas: agora, ISO validado no VLC; depois, o teste num
      player físico, quando o gravador for comprado.
- [ ] **Fase 2: Curadoria.** Parser de nomes, TMDB, correção manual, download de artes (coleções
      na Fase 7). Implementada; falta a QA com o token real, no final do projeto.
- [ ] **Fase 4: Montador + menus DVD.** Dividida em duas entregas (2026-10-16):
  - [ ] **4a: Montador + menus.** Vários títulos, episódios, menus com tema, páginas de áudio e
        legenda. Implementada; falta a QA no VLC e no player físico, no final do projeto.
  - [ ] **4b: Robustez.** Retomar job, cache do encode, cópia do vídeo de rip de DVD.
        Implementada; falta conferir com os rips reais do Vini (QA no final do projeto).
- [ ] **Fase 5: Capas.** Composição frente/lombada/verso, label, PDF. Implementada; falta
      imprimir uma de teste com a caixa e as etiquetas compradas.
- [ ] **Fase 6: Blu-ray.** BDMV sem menu com perfil BD-25/BD-50 + spike de menus e decisão.
- [ ] **Fase 7: Boxes.** Conjuntos de discos com perfis independentes, tema unificado, lombadas
      contínuas, assistente para dividir série.
- [ ] **Fase 8: Polimento.** Menus com vídeo/música, README final com screenshots, demo.

---

## 13. Decisões em aberto

- **Gravador e mídia:** o Vini ainda vai comprar. Recomendação: gravador de **Blu-ray**, que grava
  DVD também. Para durabilidade, avaliar mídia **M-DISC** (existe em DVD e BD). A segunda etapa
  do pronto da Fase 3 (teste num player físico) depende dessa compra.
- **Menus de Blu-ray:** resolver no spike da Fase 6.
- **Soft pulldown no DVD:** resolvido no VLC e no ffprobe (patcher próprio, Fase 3). Falta
  confirmar no **player físico**: o `time_code` do GOP na escala de 24p, o `subtitle=64` que liga
  a legenda e a suavidade do pulldown.
- **Volume `data`:** a checagem de escrita da Fase 3 cobre `/work` e `/output` (o formulário
  explica o `chown`); o `/data` falha de forma explícita na migração do startup. O volume mantém
  o dono antigo se já existia ou se o `UID` da imagem mudar.
- **Cópia de rip com os rips reais** (Fase 4b, QA no final): o nome exato da tag de tamanho do
  MakeMKV (ver o `probe_json` no banco); o maior GOP em campos de 3 rips de filme (se 37 ou 38
  forem comuns, rever o limite de 36); se o `dvdvideo` devolve bytes idênticos num título de
  várias células; pular de capítulo num título copiado no player físico.
- **Menus no player físico** (Fase 4a, testados só na libdvdnav): a camada letterbox numa TV
  4:3, a PGC só de comandos (despachantes e menu raiz) e o contraste parcial da faixa de
  destaque (alfa da paleta do PNG virando contraste 5/15 e 9/15 no spumux).
- **HDR/4K, PGS, VobSub, PAL:** fora da Fase 3; a receita de tonemap do `tech-lead-midia` está na
  spec da Fase 3.
- **Medidas exatas das capas e do label:** confirmar com o material comprado (Fase 5: imprimir
  uma folha de teste, conferir a régua de 50 mm, o encaixe na luva da caixa e o furo da
  etiqueta). Durabilidade: tinta pigmentada ou impressão em gráfica; etiqueta adesiva pode
  desequilibrar o disco em alta rotação (avaliar mídia printable).
- **TMDB com o token real** (QA no final): a busca ignora acento ("Senhor dos Aneis" acha "Senhor
  dos Anéis")? O nome do episódio pt-BR vem mesmo como "Episódio N" quando falta tradução?
  Pôsteres `pt` incluem os de Portugal (o TMDB não separa o país).
- **NTSC vs PAL:** padrão NTSC; confirmar com o player que vai ser usado.

---

## 14. Estado atual

_Atualizar ao fim de cada sessão._

- 2026-10-14: **Fase 0 implementada** na branch `feat/fase-0-setup` (spec e plano em
  `docs/plans/2026-10-14-fase-0-setup*.md`). App mínimo (`/` e `/health` com as versões das
  ferramentas), imagem Docker com toolchain fixada, compose, CI (quality + smoke Docker), README,
  LICENSE e os 6 agentes. Cada task foi revisada pelos agentes antes do ok do Vini.
  `make lint` e `make test` verdes (30 testes, 100% de cobertura). PR #1 mergeado em
  `main` com CI verde (`quality` e `docker`). README também em português (`README.pt-BR.md`).
  Fase 0 concluída.
- 2026-10-15: **Fase 1 implementada** na branch `feat/fase-1-biblioteca` (spec e plano em
  `docs/plans/2026-10-14-fase-1-biblioteca*.md`). Biblioteca com um card por pasta de disco, tela
  da pasta com a tabela dos vídeos, scan incremental com ffprobe, banco SQLite no volume `data`,
  testes `slow` dentro da imagem e smoke do CI ampliado. Cada task revisada pelos agentes antes do
  ok do Vini. `make lint`, `make test` (216 testes, 100% de cobertura) e `make test-slow` (7)
  verdes. PR #3 mergeado em `main` com CI verde (`quality` e `docker`). Fase 1 concluída.
  **Próximo passo:** Fase 3 (DVD mínimo), começando por `/superpowers:brainstorm`.
- 2026-10-16: **Fase 3 implementada** na branch `feat/fase-3-dvd-minimo` (spec e plano em
  `docs/plans/2026-10-15-fase-3-dvd-minimo*.md`, ledger em `.superpowers/sdd/`). Uma pasta com
  um vídeo vira um ISO de DVD-Video sem menu (DVD-5 ou DVD-9), gerado pelo serviço `worker` com
  progresso, cancelamento e QA automática; formulário "Gerar DVD" com sugestões, tela do job e
  lista de jobs. 17 tasks, cada uma revisada pelos agentes. `make lint` e `make test` (560
  testes, 100% de cobertura), `make test-slow` (15) e o smoke de ponta a ponta no CI verdes. PR
  #4 mergeado em `main`. Falta a **QA manual com um filme real no VLC** (o Vini testa tudo no
  final do projeto); depois, o teste no player físico quando o gravador for comprado.
  Pequenos adiados: idiomas mostrados como código ("eng") em vez do nome; o botão "Escanear"
  continua primário depois de um scan na mesma página.
- 2026-10-16: **Fase 2 implementada** na branch `feat/fase-2-curadoria` (spec e plano em
  `docs/plans/2026-10-16-fase-2-curadoria*.md`, revisados por `curador`, `revisor-codigo` e
  `designer`). Na tela da pasta, "Buscar no TMDB" sugere um filme ou episódio por vídeo (parser de
  nomes de release, MakeMKV e português), o Vini confirma ou corrige pela busca, e a confirmação
  baixa as artes padrão para `OUTPUT_DIR/covers/`. Sem token, a tela explica como configurar.
  O "Gerar DVD" usa o idioma original do TMDB. `make lint` e `make test` verdes com 100% de
  cobertura. Falta a QA com o token real (no final do projeto, decisão do Vini).
- 2026-10-16: **Fase 4 dividida** em 4a (montador + menus) e 4b (retomar job, reaproveitar encode,
  copiar rip). **Fase 4a implementada** na branch `feat/fase-4a-montador-menus` (spec e plano em
  `docs/plans/2026-10-16-fase-4a-montador-menus*.md`, spec revisada por `tech-lead-midia` com
  testes reais no dvdauthor e na libdvdnav, `designer` e `revisor-codigo`). Uma pasta inteira
  vira um DVD com menu: tela "Montar DVD" (ordem, idiomas do disco, tema com preview,
  calculadora do disco), menus desenhados com o Pillow, navegação pelo VMGM com um titleset por
  título, QA por título e por página de menu. `make lint`, `make test` (100% de cobertura) e
  `make test-slow` (19, com a navegação na libdvdnav) verdes; tela conferida em 375 px e 1100
  px. Falta a QA manual no VLC e no player físico (no final do projeto).
- 2026-10-16: PR #6 (Fase 4a) mergeado em `main`.
- 2026-10-17: **Fase 4b implementada** na branch `feat/fase-4b-robustez` (spec e plano em
  `docs/plans/2026-10-17-fase-4b-robustez*.md`, spec revisada por `tech-lead-midia`, com testes
  reais da cópia de rip, e `revisor-codigo`). Botão Retomar, cache do vídeo codificado por
  limite de espaço e cópia do vídeo de rips de DVD compatíveis. `make lint`, `make test` (100%)
  e `make test-slow` (24) verdes. Falta conferir a cópia com os rips reais do Vini.
- 2026-10-17: PR #7 (Fase 4b) mergeado em `main`.
- 2026-10-17: **Fase 5 implementada** na branch `feat/fase-5-capas` (spec e plano em
  `docs/plans/2026-10-17-fase-5-capas*.md`, spec revisada por `designer`, `curador` e
  `revisor-codigo`). Tela "Capa" da pasta: encarte da caixa Amaray (verso, lombada e frente) e
  duas etiquetas redondas em A4, grade com as artes do TMDB, textos editáveis e PDF em
  `OUTPUT_DIR/print/`. `make lint`, `make test` (100%) e `make test-slow` (28) verdes. Falta imprimir
  uma de teste com o material comprado.
- Os agentes de `.claude/agents/` só são reconhecidos pelo nome a partir de uma sessão nova; na
  sessão em que foram criados, rodam como agente genérico lendo o próprio arquivo.

---

## 15. Log de decisões

- 2026-10-14: App web local (FastAPI + HTMX) em vez de app desktop. Aproveita a stack Python e roda
  no WSL/Docker.
- 2026-10-14: Suporte a DVD **e** Blu-ray via perfis de disco. **O Vini escolhe o perfil de cada
  disco**; o app só sugere e alerta. Num box, cada disco tem o próprio perfil.
- 2026-10-14: O app gera o `.iso`; a gravação acontece no Windows (o WSL não acessa o gravador).
- 2026-10-14: Capas com arte pesquisada no TMDB e composição própria, sem geração por IA.
- 2026-10-14: Processo com Superpowers (brainstorm → plano → execução com TDD) e Ponytail
  (menor solução que funciona).
- 2026-10-14: Sem travessão na escrita (ok de vez em quando em tópicos).
- 2026-10-14 (Fase 0): serviço `worker` adiado para a Fase 3 (sem job, seria código morto).
- 2026-10-14 (Fase 0): `config.py`, variáveis do app, TMDB e volume `data` adiados para as Fases
  1 e 2; pastas de módulo da seção 7 criadas só na fase que as usa; `app.py` na raiz do pacote
  até a Fase 1 (templates já em `web/templates/`).
- 2026-10-14 (Fase 0): variáveis `HOST_*` do compose separadas dos caminhos do container.
- 2026-10-14 (Fase 0): Debian trixie (ffmpeg 7.1) com apt fixado por versão e base por digest;
  tsMuxeR 2.7.0 por sha256; uv por digest. O build quebra de propósito em atualização de
  segurança, para a atualização ser consciente.
- 2026-10-14 (Fase 0): container com usuário não root UID 1000; porta só em 127.0.0.1.
- 2026-10-14 (Fase 0): `/health` com as versões das ferramentas, base do smoke test do CI.
  `dvdauthor` e `spumux` não têm flag de versão (saem com 1 e 255, versão no stderr): o código de
  saída é ignorado e a versão é lida por regex.
- 2026-10-14 (Fase 0): `httpx2` no lugar de `httpx` para o `TestClient` (o Starlette 1.8 deprecou
  o `httpx`). Decidir na Fase 2 qual cliente usar para o TMDB, para não manter os dois.
- 2026-10-14 (Fase 0): ISO de DVD com `genisoimage -dvd-video -udf` (o `xorriso` não gera a ponte
  UDF 1.02); ISO de Blu-ray gerado pelo próprio tsMuxeR (UDF 2.5x). Testado pelo
  `tech-lead-midia`; entra no código nas Fases 3 e 6.
- 2026-10-14 (Fase 0): licença MIT; `mypy --strict` no projeto todo; cobertura mínima de 90%;
  actions de terceiros no CI fixadas por SHA; `GITHUB_TOKEN` só leitura.
- 2026-10-15 (Fase 1): fluxo de entrada com uma pasta `entrada` e **uma subpasta por disco**; o
  app não varre o HD inteiro. `MEDIA_ROOTS` (lista) virou `MEDIA_DIR` (uma pasta); várias pastas
  ficam para depois, se fizerem falta.
- 2026-10-15 (Fase 1): a entrada pode ficar no `C:` ou no HD externo, sempre montada `ro`.
- 2026-10-15 (Fase 1): modelo mínimo: só `media_file` com o JSON bruto do ffprobe; resumo, faixas
  e avisos calculados na hora. Sem `SourceFolder` e sem tabelas de faixas (ajusta 7.1).
- 2026-10-15 (Fase 1): biblioteca sem match e sem filtros até a Fase 2 (ajusta 7.2).
- 2026-10-15 (Fase 1): scan síncrono com lock (um por vez, por processo, um worker do uvicorn),
  sem fila; durante o scan as telas mostram "escaneando" em vez de "mudou". O resultado mostra
  quantos arquivos o ffprobe leu ("Scan concluído: N arquivos lidos pelo ffprobe."). O HTMX 2 não
  troca respostas de erro, então a tela da pasta tem um aviso próprio para scan que falhou.
- 2026-10-15 (Fase 1): CSS próprio em vez de Tailwind (sem build; ajusta 6). HTMX 2.0.11
  versionado no repositório, com sha256 no README.
- 2026-10-15 (Fase 1): app criado pela fábrica `create_app(settings)`, com o uvicorn em
  `--factory`; o Alembic roda no startup (só no `web` quando existir o `worker`).
- 2026-10-15 (Fase 1): testes `slow` no estágio `test` da imagem, sem rede: comparam as fixtures
  do ffprobe pelo resumo (não pelo JSON bruto, que muda com versões de encoder) e fazem um scan
  de ponta a ponta. O CI confere a montagem `ro` do `/media` em `/proc/mounts`, porque um
  `touch` que falha também passaria por simples falta de permissão.
- 2026-10-15 (Fase 1): banco SQLite em volume nomeado (`data`), não em bind mount: o SQLite tem
  problemas de lock em `/mnt/c`.
- 2026-10-15 (Fase 1): HDR inclui Dolby Vision; perfil 5 com aviso próprio. A fixture DV5 é
  escrita à mão: depois de atualizar o ffmpeg, conferir se o ffprobe ainda chama o side data de
  "DOVI configuration record".
- 2026-10-15 (Fase 1): `find_videos` conta uma vez só dois nomes iguais em NFC e NFD (fica com o
  primeiro); antes, o segundo derrubava o scan com erro de banco.
- 2026-10-15 (Fase 1): sem `TrustedHostMiddleware` e sem proteção CSRF por enquanto: o app é
  local, a porta só abre em 127.0.0.1 e o scan só lê. Reavaliar quando houver ação que grava
  (Fase 3).
- 2026-10-15: roadmap reordenado para 1 → 3 → 2 → 4 → 5 → 6 → 7 → 8 (números mantidos), para ter
  um disco de verdade antes da curadoria. A Fase 3 fica pronta em duas etapas: ISO validado no VLC
  agora; teste num player físico quando o gravador for comprado (ver 13).
- 2026-10-16 (Fase 3): MPEG-2 pelo ffmpeg em 2 passes com os parâmetros de `encode/video.py`;
  proibido `-target ntsc-dvd`; `-r` sempre explícito. Alvo de vídeo limitado a 95% do maxrate
  (alvo igual ao maxrate virava CBR e o ffmpeg avisava "impossible bitrate constraints").
- 2026-10-16 (Fase 3): soft pulldown por patcher próprio (estilo DGPulldown, `mmap` no lugar, um
  leitor MPEG-2 só para o patcher e a QA); `mpeg2enc` descartado (lento, sem alvo de tamanho).
- 2026-10-16 (Fase 3): rip de DVD classificado pelos quadros (filme, entrelaçado, híbrido com hard
  telecine); 480i codificado entrelaçado. Cor: escala com lanczos e `colorspace` para BT.601 só
  em origem HD, tags via `mpeg2_metadata`.
- 2026-10-16 (Fase 3): áudio só AC-3: copiar se ≤ 448k, 48 kHz e ≤ 6 canais; senão converter
  mantendo o layout. `-itsoffset` no mux corrige o atraso do m2v e preserva o da origem.
  `audio=0` sempre e `subtitle=64/0` no `<pre>` do título.
- 2026-10-16 (Fase 3): mux com `ffmpeg -f dvd -fflags +genpts`; ISO com `genisoimage -dvd-video
  -udf`. Capacidade pelo menor valor entre −R e +R, em setores, com margem de 97% menos 4 MiB; a
  QA reprova acima do limite físico e avisa acima da margem.
- 2026-10-16 (Fase 3): legendas SRT e texto do MKV via `spumux`; PGS, VobSub, ASS, HDR, PAL e 4K
  adiados.
- 2026-10-16 (Fase 3): worker em processo separado, SQLite em WAL, transições atômicas, índice
  único por pasta ativa, um job por vez. Intermediários apagados ao longo do pipeline (pico de ~2
  vezes o disco); o ISO só vai para `/output` depois de passar na QA, numa etapa própria "Copiando
  o ISO" (copiar 8 GB para o `/mnt/c` leva minutos e precisa de progresso e cancelamento).
- 2026-10-16 (Fase 3): `TrustedHostMiddleware` e checagem de mesma origem (`Sec-Fetch-Site`) em
  todo método não seguro. Formulário lido com `parse_qs` (sem `python-multipart`).
- 2026-10-16 (Fase 3): tolerâncias da QA automática: até max(2, quadros/1000) quadros duplicados
  ou perdidos (o `-fps_mode cfr` duplica o último quadro por arredondamento; tranco real é 1 a
  cada 5); 0 capítulos no ffprobe aceito quando o plano tem um só; avisos do próprio muxer `null`
  ignorados na decodificação completa.
- 2026-10-16 (Fase 3): tela do job com tempos relativos ("há 12 min"): o container é UTC sem
  `tzdata`. Tempo de encode estimado pela duração (×0,2 em HD, ×0,1 em SD), a calibrar com um
  filme real.
- 2026-10-16 (Fase 2): curadoria na tela da pasta: sugestão automática por vídeo, o Vini confirma
  ou corrige; status "Confira" para o ambíguo, nunca confirmado em lote. Nome genérico ao lado de
  outros vídeos também vira "Confira" (costuma ser um extra).
- 2026-10-16 (Fase 2): sem tabela de coleções até a Fase 7; sem distribuição automática dos filmes
  de uma collection entre arquivos de nome genérico (frágil).
- 2026-10-16 (Fase 2): `httpx2` como cliente do TMDB, com o "Token de leitura da API" no cabeçalho
  `Bearer` (a URL nunca leva segredo; o `httpx2` loga URLs); `TMDB_TOKEN` no lugar de
  `TMDB_API_KEY`, `SecretStr` no `Settings`; `MockTransport` nos testes no lugar do `respx`. Fecha
  o item da Fase 0 sobre qual cliente usar.
- 2026-10-16 (Fase 2): detalhes do TMDB inteiros no banco (`tmdb_json`), dados da tela calculados
  na hora; `title` 1 para 1 com `media_file`, cascade pelo ORM (sem `PRAGMA foreign_keys`, que
  apagaria os títulos num batch do Alembic).
- 2026-10-16 (Fase 2): o purge da biblioteca não roda com a pasta de entrada ausente ou vazia (HD
  desligado não apaga nenhum match); um arquivo que mudou volta de "confirmado" para "Confira"
  (pode ser outro filme com o mesmo nome; nunca reconfirmado em lote).
- 2026-10-16 (Fase 2): artes padrão por título em `OUTPUT_DIR/covers/<pasta>/`, gravadas como
  `.part` e renomeadas; caminho de imagem validado, sem redirecionamento, só `image/*`, até 30 MB.
  Arte que falha não desfaz a confirmação. Escolha entre várias na Fase 5.
- 2026-10-16 (Fase 2): rede primeiro, depois uma transação curta por título; um lock por processo
  para as ações do TMDB; rotas com formulário são `async` e rodam o TMDB no thread pool.
- 2026-10-16 (Fase 2): nome em inglês quando falta a tradução pt-BR (filme pelas `translations`;
  episódio por uma segunda chamada da temporada em `en-US`, só quando precisa).
- 2026-10-16 (Fase 2): atribuição do TMDB no rodapé de todas as páginas, com o logo oficial "blue
  short" versionado, e no README com a frase oficial e o uso não comercial.
- 2026-10-16 (Fase 4a): Fase 4 dividida em 4a e 4b; o disco abre no menu (mesmo com um título);
  série com "Tocar todos" e episódio que segue até o fim; idiomas escolhidos uma vez para o
  disco; tema automático com 3 ajustes (fundo, cor, lado); "Áudio" e "Legendas" em páginas com ✓
  (proposta do `designer`, aprovada pelo Vini).
- 2026-10-16 (Fase 4a): um titleset por título (o dvdauthor 0.7.2 marca toda faixa declarada
  como presente e declara errado os canais quando os títulos de um titleset diferem); toda a
  navegação pelo VMGM com despachantes só de comandos; Title e Menu sempre no menu principal
  (o despachante de títulos zera `g2` antes de pular: sem isso a tecla Title recomeçava o
  episódio); limite de 60 títulos pelos 128 comandos da PGC.
- 2026-10-16 (Fase 4a): menus em pixel quadrado reduzidos para 720x480, destaque de 4 cores
  desenhado direto em 720x480; menu 16:9 com stream letterbox; fundo em MPEG-2 parado com
  `-q:v 2`, `+ilme` e AC-3 silencioso; 2 MiB por página na calculadora (medido até 1,2 MB).
- 2026-10-16 (Fase 4a): `disc_project` guarda o `DiscChoices` em JSON, reconciliado com a pasta
  ao abrir; as confirmações nunca são salvas; o caminho do fundo nunca vem do formulário (só o
  nome de uma pasta de arte que o servidor lista). A migração `0004` converte os planos da
  Fase 3 com dicionários e falha os jobs ativos. O preview é desenhado a cada pedido, sem cache.
- 2026-10-16 (Fase 4a): a classificação pelos quadros (rips MPEG-2) só roda ao gerar; a tela usa
  só o ffprobe. Faixa sem idioma vira "Idioma não informado"; legenda só forçada conta como
  ausente; título sem nenhum idioma escolhido toca a própria primeira faixa.
- 2026-10-16 (Fase 4a): navegação testada com a libdvdnav (a VM do VLC) nos testes `slow`;
  o player físico continua sendo o teste final.
- 2026-10-17 (Fase 4b): cache do vídeo codificado por **limite de espaço** (`CACHE_LIMIT_GB`,
  padrão 50, GB decimais), mais antigos saem primeiro, só o worker despeja; hard link (sem
  cópia); chave pelo próprio comando da 2ª passada (mais a versão do ffmpeg e a do patcher);
  a QA continua com o `progress` da 2ª passada guardado no JSON. Reserva fixa dos menus
  (`max(páginas, 20) × 2 MiB`) para o bitrate não mudar com o menu. Com o cache, o preflight pede
  3 vezes o disco na pasta de trabalho.
- 2026-10-17 (Fase 4b): job parado fica com o botão **Retomar** (decisão do Vini: nada volta
  sozinho para a fila); retomar roda o preflight, limpa a pasta do job e volta o mesmo job à
  fila num `UPDATE` atômico; só o último job da pasta, e não os da Fase 3. Sem migração nova.
- 2026-10-17 (Fase 4b): rip de DVD **copiado quando cabe** (decisão do Vini), com "Recodificar
  os rips" por disco. A regra do pico de bitrate foi trocada pelo orçamento herdado do disco
  original (o ffprobe não mostra o pico real); capítulos levados ao GOP fechado (testado: o
  dvdauthor não corrige); GOP contado em campos exibidos (36); conferência logo depois de
  extrair e QA de vídeo idêntico.
- 2026-10-17 (Fase 5): capa desenhada com o **Pillow** e o PDF salvo por ele (reportlab
  descartado); A4 a 300 DPI, sRGB, sem CMYK e sem logo na frente (decisões do Vini). Medidas em
  mm num arquivo só; as bordas dos painéis arredondadas uma vez (nenhuma coluna branca); o texto
  medido sempre a 300 DPI, para a prévia de 50 DPI quebrar igual ao PDF.
- 2026-10-17 (Fase 5): escolhas da capa dentro do `DiscChoices` (`cover`), preservadas pelo
  formulário do Montar DVD; uma arte só na frente, baixada como `covers/<pasta>/front.jpg|png`;
  opções listadas dos detalhes salvos, sem chamar a API (pôster da temporada ou da coleção
  primeiro, depois pt, sem idioma e en; abaixo de 150 DPI fica fora). Pôster com idioma não
  recebe o nome por cima.
- 2026-10-17 (Fase 5): o aviso "Imprima em tamanho real" foi para o pé da folha (no alto cruzava
  as marcas de dobra); o furo da etiqueta é pintado de branco no centro exato, com 1 px de folga.

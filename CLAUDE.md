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
- Agrupar em **coleções** (ex: "O Senhor dos Anéis", "Friends: Temporada 1"). Usar a "collection"
  do TMDB quando existir.
- Baixar as artes para uma pasta local (pôster, fundo, logo, still de episódio) e salvar sinopse,
  elenco, ano e duração. Idioma preferido `pt-BR`, com fallback para `en`.

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

### 3.4 Menus
- Menu principal com os títulos do disco; submenu de episódios para séries; submenus de áudio e de
  legendas.
- **Tema por coleção**: fundo (arte do TMDB tratada), tipografia, cores, estilo dos botões.
- Preview do menu como imagem na interface, antes do encode.
- Navegação completa pelo controle remoto (cima, baixo, esquerda, direita, enter); o botão "menu"
  sempre volta para o menu principal.
- Fase futura: menu com vídeo de fundo e música em loop.

### 3.5 Geração do disco
- Fila de jobs: encode → render do menu → authoring → `.iso`.
- Progresso em tempo real (lido da saída do ffmpeg), tempo estimado, log completo de cada etapa.
- Retomar ou cancelar job. Se um título já foi codificado com os mesmos parâmetros, reaproveitar.
- Antes de começar, checar o espaço livre na pasta de trabalho (um BD-50 pode precisar de >100 GB
  de intermediários).
- Limpar os intermediários ao final, **com confirmação**.

### 3.6 Capas
- Para cada disco ou box: montar a **capa completa da caixinha** (frente + lombada + verso) e o
  **label do disco**, em PDF pronto para imprimir.
- Frente: pôster ou arte escolhida, título, logo. Lombada: título, número do disco, padrão visual
  que forma uma imagem contínua quando os discos do box ficam lado a lado (desejável). Verso:
  sinopse, lista de títulos/episódios, duração, áudio, legendas, perfil do disco.
- Permitir escolher entre várias artes do TMDB para cada posição.
- Saída em 300 DPI, CMYK opcional, com sangria e marcas de corte.

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

**Calculadora:**
`bitrate_vídeo = (capacidade_útil - soma_áudio - soma_legendas - menus - overhead) / duração_total`,
com capacidade útil de cerca de 95% da nominal. As faixas de qualidade iniciais (calibrar com
testes reais):
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
- Bitrate: vídeo ≤ 9,8 Mbps, mux total ≤ 10,08 Mbps. Usar **encode em 2 passes** (VBR) para
  aproveitar a capacidade.
- Fontes em 23,976 fps: usar **soft pulldown** (flags de repetição) em vez de converter para
  29,97 de verdade. A confirmar como fazer isso de forma confiável com ffmpeg.
- Áudio: AC-3 48 kHz, até 448 kbps (5.1) ou 192 kbps (estéreo). Se a origem já for AC-3
  compatível, copiar sem recodificar. Até 8 faixas de áudio por título.
- Legendas: bitmap (subpicture). Converter SRT para subpicture com `spumux`. Até 32 faixas.
- Limites da estrutura: até 99 títulos e 99 capítulos por título.
- Menus: 720x480; respeitar a **área segura** (~10% de margem) porque TVs cortam as bordas;
  o destaque dos botões é um subpicture com **paleta de no máximo 4 cores** (restrição real para o
  designer); até 36 botões por menu.
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
| Frontend | **Jinja2 + HTMX + CSS próprio** (sem build; reavaliar no editor de menus, Fase 4) |
| Jobs | tabela `jobs` no SQLite + processo worker separado. Sem Celery/Redis a menos que fique necessário |
| Mídia | `ffmpeg`/`ffprobe`, `dvdauthor`, `spumux`, `tsMuxeR`, `xorriso` (`genisoimage` entra na Fase 3) |
| Imagens e PDF | **Pillow** para menus e artes; **reportlab** para o PDF de impressão |
| Metadados | **TMDB API** via `httpx`, com cache local das respostas |
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
WORK_DIR=/work                  # Fase 3
OUTPUT_DIR=/output              # Fase 3
TMDB_API_KEY=                   # Fase 2
TMDB_LANGUAGE=pt-BR             # Fase 2
DEFAULT_DVD_STANDARD=NTSC       # Fase 3
```

### 6.2 Docker
- `Dockerfile` com todas as ferramentas de mídia: base por digest, pacotes apt por versão,
  tsMuxeR e uv por checksum/digest. Usuário não root `app` (UID 1000).
- Estágios `runtime` (a imagem do app, também o padrão de um `docker build .`) e `test` (runtime
  + dependências de dev + `tests/`, para os testes `slow` com as ferramentas reais, sem rede).
- `docker-compose.yml` com o serviço `web` (porta só em `127.0.0.1:8000`, `target: runtime`), os
  volumes acima e o volume nomeado `data` (banco SQLite; `docker compose down -v` apaga). O
  serviço `worker` entra na Fase 3 (considerar `init: true` para recolher processos do ffmpeg).
- `make dev`, `make test`, `make test-slow`, `make lint`, `make format` e `make fixtures`
  documentados no README.

---

## 7. Arquitetura

```
src/projeto_dvd/
  api/            # rotas FastAPI (JSON + fragments HTMX)
  web/            # templates Jinja, estáticos
  library/        # scan, ffprobe, detecção de legendas externas
  metadata/       # cliente TMDB, parser de nome de arquivo, matching, download de artes
  planner/        # perfis de disco, calculadora, montador, divisor de série
  encode/         # construtores de comando ffmpeg por perfil (funções puras)
  authoring/
    dvd/          # dvdauthor XML, spumux
    bluray/       # tsMuxeR meta, (menus após o spike)
  menus/          # temas, layout, render de fundo e botões
  covers/         # layout de capa, lombada, verso, label, PDF
  jobs/           # fila, worker, progresso
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
- `Title`: filme ou episódio; `tmdb_id`, tipo, temporada/episódio, nome, sinopse, duração; ligado a 1 `MediaFile`.
- `Collection`: agrupamento (franquia ou temporada), com tema visual.
- `DiscProject`: um disco; **perfil escolhido**, títulos em ordem, faixas selecionadas, capítulos, tema do menu, status.
- `DiscSet`: box com vários `DiscProject` (cada um com o próprio perfil).
- `Job`: etapa da geração; tipo, status, progresso, log, parâmetros (hash para reaproveitar encode).
- `ArtAsset`: arte baixada; tipo (poster, backdrop, logo, still), caminho, origem, idioma.
- `CoverLayout`: escolhas de arte e texto de uma capa, e o PDF gerado.

### 7.2 Telas
1. **Biblioteca** (Fase 1): um card por pasta de disco, com status (vazia, não escaneada, ok,
   com avisos, mudou). A **tela da pasta** mostra a tabela dos vídeos e o botão Escanear. Status
   de match e filtros entram na Fase 2.
2. **Título**: dados técnicos, match TMDB (buscar/corrigir), artes.
3. **Coleções**: criar, agrupar, definir tema.
4. **Montador de disco**: títulos, **seletor de perfil**, calculadora, ordem, capítulos, áudio/legenda.
5. **Box**: discos do conjunto, perfil de cada um, numeração.
6. **Menu**: tema e preview.
7. **Capa**: escolha das artes, preview, gerar PDF.
8. **Jobs**: fila, progresso, logs, cancelar/retomar.
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
- **TMDB**: mockar com `respx`; nunca chamar a API real nos testes.
- **Checklist de QA do ISO** (agente `qa`), antes de gravar qualquer disco:
  1. tamanho do ISO ≤ capacidade útil do perfil;
  2. estrutura válida (VIDEO_TS com IFO/BUP/VOB ou BDMV/CERTIFICATE);
  3. `ffprobe` nos streams: codec, resolução, aspecto, faixas e idiomas corretos;
  4. abre no VLC pelo menu, cada botão leva ao título certo, "menu" volta;
  5. áudio e legendas trocam pelo menu;
  6. primeiro disco de cada perfil: testar num **player físico** antes de gravar em lote
     (preferir mídia regravável para os testes).

---

## 10. Capas: especificações

- Saída: PDF em 300 DPI, sangria de 3 mm, marcas de corte, CMYK opcional.
- **Medidas a confirmar** com a caixa e o papel comprados antes de fixar no código. Referências
  comuns: capa de DVD (caixa Amaray) em torno de 273 x 183 mm com lombada de ~14 mm; capa de
  Blu-ray menor e mais baixa; label de disco com 120 mm de diâmetro e furo central. As medidas
  ficam num arquivo de configuração, nunca hardcoded.
- Texto da capa em português; usar a sinopse `pt-BR` do TMDB.
- Pasta de artes: `OUTPUT_DIR/covers/<colecao>/<titulo>/` com `poster.jpg`, `backdrop.jpg`,
  `logo.png`, `metadata.json`. PDFs em `OUTPUT_DIR/print/`.

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
      no checklist. Pronto em duas etapas: agora, ISO validado no VLC; depois, o teste num player
      físico, quando o gravador for comprado.
- [ ] **Fase 2: Curadoria.** Parser de nomes, TMDB, correção manual, coleções, download de artes.
- [ ] **Fase 4: Montador + menus DVD.** Vários títulos, episódios, calculadora com seletor de perfil,
      menus com tema, áudio/legenda, jobs com progresso.
- [ ] **Fase 5: Capas.** Composição frente/lombada/verso, label, PDF.
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
- **Soft pulldown no DVD** para fontes 23,976 fps: o ffmpeg não grava as flags RFF de forma
  confiável. Candidato para a Fase 3: `mpeg2enc` (pacote `mjpegtools`) ou pós-processamento.
- **Checagem de escrita em `/work`, `/output` e `/data`** no app (Fase 3): o Docker Desktop ignora
  `create_host_path: false`, então uma pasta que falte vira root e o erro só aparece ao gravar. O
  volume `data` mantém o dono antigo se já existia ou se o `UID` da imagem mudar.
- **Campos de mídia da Fase 3 no resumo do ffprobe** (`field_order`, `pix_fmt`, `sample_rate`,
  `color_primaries`): precisam entrar no `Summary` para que os testes `slow` comparem as fixtures
  também nesses campos.
- **Medidas exatas das capas e do label:** confirmar com o material comprado.
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

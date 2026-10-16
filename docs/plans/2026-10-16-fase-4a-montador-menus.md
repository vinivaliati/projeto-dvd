# Fase 4a: Montador + menus DVD (plano de implementação)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uma pasta com vários vídeos vira um ISO de DVD-Video com menu (filmes ou série,
páginas de Áudio e Legendas com ✓), montado na tela "Montar DVD" com preview e calculadora do
disco inteiro.

**Architecture:** o `DiscChoices` (salvo em `disc_project`) é a vontade do Vini; `planner/disc.py`
o sugere e reconcilia com a pasta; `planner/disc_plan.py` o transforma no `DiscPlan` do job (um
`TitlePlan` por vídeo e um `MenuPlan` com as páginas lógicas). `menus/` desenha as páginas com o
Pillow; `authoring/dvd/` gera o MPEG-2 dos menus, o XML do spumux (widescreen e letterbox) e o
XML do dvdauthor com o despachante no VMGM e um titleset por título. O pipeline codifica título
por título, depois os menus, autoria, ISO e QA por título e por página.

**Tech Stack:** Python 3.12, FastAPI + HTMX + Jinja, SQLModel/Alembic, Pillow, ffmpeg, spumux,
dvdauthor 0.7.2, genisoimage; testes `slow` com libdvdnav via `ctypes`.

**Spec:** `docs/plans/2026-10-16-fase-4a-montador-menus-design.md` (aprovada pelo Vini).

## Global Constraints

- Conversa em português; código, commits, docstrings e README em inglês; **sem travessão (—)**.
- Conventional Commits; todo commit termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `make lint` (ruff check, ruff format --check, mypy strict) e `make test` (cobertura ≥ 90%, alvo
  100%) verdes a cada task; `make test-slow` nas tasks que tocam ferramentas reais (cuidado com a
  RAM: 8 GB, rodar só os testes da task com `-k` quando possível).
- Nunca chamar a API real do TMDB; nunca commitar mídia, ISO, `.env`, banco ou artes.
- Textos da tela e do menu em português; limites: até 60 títulos, 4 idiomas de áudio, 4 de legenda.
- Registradores do DVD só g0 a g12 (g14 e g15 são do dvdauthor); uma PGC com no máximo 128 comandos.
- Menus: fundo em pixel quadrado (854x480 no 16:9, 640x480 no 4:3) reduzido para 720x480 com
  Lanczos; subpicture desenhado direto em 720x480, no máximo 4 cores, sem antialias (alfa só o da paleta),
  coordenadas pares, caixas com 4 px entre si.
- Paleta: ambar `#E0A526`, vermelho `#D9483B`, azul `#4C9BE0`, verde `#3DB894`, lilas `#A685E0`,
  gelo `#E6E6E6`; texto `#EBEBEB`, secundário `#B4B4B4`, contorno `#101010`.
- Rotas que gravam já passam pela checagem de mesma origem; nenhum caminho de arquivo vem do
  formulário (o servidor monta todos).

## Review Focus

1. Pasta com faixas só `und` (MP4 sem idioma): o disco precisa sair, com "Idioma não informado".
2. Tecla Title ou Menu no meio de um episódio que veio do "continuar": deve abrir o menu, nunca
   recomeçar o episódio (teste unitário do XML e cenário libdvdnav).
3. `disc_project` salvo antes de um rescan que tirou um vídeo, trocou a arte ou mudou o schema: a
   tela abre com a reconciliação, sem 500.
4. 7 filmes (paginação no principal): o filme da página 2 volta para a página 2 com o botão dele.
5. Título 4:3 num disco 16:9 com um título sem o segundo idioma: titleset próprio, mapa certo, e o
   aviso na tela.

Cada linha tem teste na task dona (Tasks 2, 7, 2, 7/10, 7/10).

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `pyproject.toml`, `uv.lock` | `pillow` como dependência |
| `src/projeto_dvd/db/models.py` | `DiscProject` |
| `src/projeto_dvd/db/migrations/versions/0004_disc_project.py` | tabela e conversão dos jobs antigos |
| `src/projeto_dvd/library/scan.py` | o purge também apaga `disc_project` |
| `src/projeto_dvd/planner/disc_plan.py` | modelos: `Theme`, `DiscChoices`, `TitlePlan`, `MenuItem`, `MenuPage`, `MenuPlan`, `DiscPlan` (reescrito a partir do `dvd_plan.py`) |
| `src/projeto_dvd/planner/dvd_plan.py` | fica só com o que é por título (`audio_output`, `subtitle_options`, `plan_chapters`, `volume_name`, `AudioChoice`, `SubtitleChoice`); o resto sai na Task 9 |
| `src/projeto_dvd/planner/disc.py` | entrada do disco (`DiscTitle`), nomes, ordem, tipo, faixas por idioma, sugestão, reconciliação, avisos e erros |
| `src/projeto_dvd/planner/calculator.py` | `estimate_disc` |
| `src/projeto_dvd/menus/pages.py` | páginas lógicas do menu (puro) |
| `src/projeto_dvd/menus/theme.py` | paleta, cor `auto`, fundos disponíveis |
| `src/projeto_dvd/menus/layout.py` | geometria (puro) |
| `src/projeto_dvd/menus/render.py` | Pillow: fundo, highlight, select, preview |
| `src/projeto_dvd/authoring/dvd/menus.py` | comando ffmpeg do fundo, XML do spumux |
| `src/projeto_dvd/authoring/dvd/dvdauthor.py` | XML com menus, despachantes, um titleset por título |
| `src/projeto_dvd/authoring/dvd/qa.py`, `mux.py`, `encode/video.py`, `encode/audio.py` | recebem `TitlePlan`/`DiscPlan`, `-title N`, menus |
| `src/projeto_dvd/jobs/pipeline.py`, `worker.py`, `store.py` | vários títulos, etapa "Menus", `report(step, fraction, title)` |
| `src/projeto_dvd/api/dvd.py`, `api/jobs.py` | tela Montar DVD, preview, job com títulos |
| `src/projeto_dvd/web/templates/dvd_form.html`, `_disc_results.html`, `_dvd_block.html`, `job.html`, `jobs.html`, `_job_status.html` | telas |
| `src/projeto_dvd/web/static/app.css` | estilos novos |
| `tests/plans.py` | `make_title_plan`, `make_disc_plan` |
| `tests/integration/navigation.py` | driver libdvdnav |
| `tests/integration/test_dvd.py`, `clips.py` | disco com menus, navegação, 60 títulos |

---

### Task 1: Pillow, `DiscProject`, modelos do disco e migração `0004`

**Files:**
- Modify: `pyproject.toml` (`"pillow>=11.0.0"` em `dependencies`; `uv lock`), `src/projeto_dvd/db/models.py`, `src/projeto_dvd/library/scan.py`
- Create: `src/projeto_dvd/planner/disc_plan.py`, `src/projeto_dvd/db/migrations/versions/0004_disc_project.py`
- Test: `tests/unit/test_disc_plan.py`, `tests/unit/test_db.py`, `tests/unit/test_scan.py`

**Interfaces:**
- Produces (`planner/disc_plan.py`):

```python
UND = "und"
ACCENTS = ("ambar", "vermelho", "azul", "verde", "lilas", "gelo")
Accent = Literal["auto", "ambar", "vermelho", "azul", "verde", "lilas", "gelo"]

class Theme(BaseModel):  # frozen
    backdrop: str | None = None
    accent: Accent = "auto"
    side: Literal["left", "right"] = "left"

class DiscChoices(BaseModel):  # frozen
    kind: Literal["movies", "series"]
    order: tuple[str, ...]
    profile: str
    audio: tuple[str, ...]
    subtitles: tuple[str, ...]
    subtitle_on: str | None
    chapters: Literal["file", "every"]
    minutes: int
    theme: Theme = Theme()

class TitlePlan(BaseModel):  # frozen; os campos por título do antigo DvdPlan
    path: str; video_index: int; size: int; mtime_ns: int; duration: float
    mode: VideoMode; top_field_first: bool; aspect: Literal["16:9", "4:3"]
    width: int; height: int; scale: bool; hd_color: bool
    audio: tuple[AudioChoice, ...]       # as faixas deste título, na ordem dos idiomas do disco
    subtitles: tuple[SubtitleChoice, ...]
    chapters: tuple[float, ...]
    audio_map: tuple[int, ...]           # por idioma de áudio do disco: o stream deste título
    subtitle_map: tuple[int | None, ...] # por idioma de legenda do disco: stream ou None
    menu_name: str

Action = Literal["play", "play_all", "page", "audio", "subtitle", "back"]

class MenuItem(BaseModel):  # frozen
    label: str
    action: Action
    target: int = 0  # play: número global do título (1..N); page: índice da página; audio/subtitle: opção

class MenuPage(BaseModel):  # frozen
    kind: Literal["main", "episodes", "audio", "subtitles"]
    heading: str
    secondary: str | None = None
    items: tuple[MenuItem, ...]
    footer: tuple[MenuItem | None, MenuItem | None, MenuItem | None] = (None, None, None)
    focus: int = 1           # botão destacado ao entrar pela primeira vez (1-based)
    checked: int | None = None  # índice do item com ✓ (variantes de Áudio e Legendas)
    large: bool = False

class MenuPlan(BaseModel):  # frozen
    aspect: Literal["16:9", "4:3"]
    backdrop: str | None     # caminho absoluto no container, montado pelo servidor
    accent: str              # hex final
    side: Literal["left", "right"]
    pages: tuple[MenuPage, ...]  # pages[0] é o principal

class DiscPlan(BaseModel):  # frozen
    folder: str; profile: str; video_kbps: int; maxrate_kbps: int; estimated_bytes: int
    confirmed_low: bool; replace_existing: bool; volume: str; iso_name: str
    subtitle_on: int  # valor inicial de g1 (0 = sem legenda)
    titles: tuple[TitlePlan, ...]
    menu: MenuPlan | None  # None só em jobs convertidos da Fase 3
```

  `AudioChoice` e `SubtitleChoice` continuam em `dvd_plan.py` e são importados.
- Produces (`db/models.py`): `class DiscProject(SQLModel, table=True)` com `__tablename__ = "disc_project"`, `folder: str = Field(primary_key=True)`, `choices_json: str`.
- Produces (`scan.py`): `purge_missing_folders` também apaga `DiscProject` cujo `folder` não está em `names`.

- [ ] **Step 1: testes que falham**

```python
# tests/unit/test_disc_plan.py
def test_theme_defaults_to_auto_accent_on_the_left() -> None:
    assert Theme() == Theme(backdrop=None, accent="auto", side="left")

def test_theme_rejects_a_hex_accent() -> None:
    with pytest.raises(ValidationError):
        Theme(accent="#ffffff")

def test_disc_plan_round_trips_through_json() -> None:
    plan = make_disc_plan()
    assert DiscPlan.model_validate_json(plan.model_dump_json()) == plan
```

```python
# tests/unit/test_db.py
def test_migration_creates_the_disc_project_table(engine: Engine) -> None:
    columns = {c["name"] for c in inspect(engine).get_columns("disc_project")}
    assert columns == {"folder", "choices_json"}

def test_0004_converts_phase_3_jobs(database_url: str) -> None:
    config = _config(database_url)
    command.upgrade(config, "0003")
    old = make_plan().model_dump_json()  # o DvdPlan da Fase 3 (tests/plans.py antigo, copiado como dict literal no teste)
    with make_engine(database_url).begin() as conn:
        conn.execute(text("INSERT INTO job (folder, plan_json, status, cancel_requested, progress, created_at) "
                          "VALUES ('Filme', :p, 'done', 0, 1.0, '2026-10-16 00:00:00')"), {"p": old})
        conn.execute(text("INSERT INTO job (folder, plan_json, status, cancel_requested, progress, created_at) "
                          "VALUES ('Outro', :p, 'queued', 0, 0.0, '2026-10-16 00:00:00')"), {"p": old})
    command.upgrade(config, "head")
    with make_engine(database_url).connect() as conn:
        rows = conn.execute(text("SELECT plan_json, status, error FROM job ORDER BY id")).all()
    plans = [DiscPlan.model_validate_json(r[0]) for r in rows]
    assert plans[0].menu is None and plans[0].titles[0].path == "Filme/Filme.mkv"
    assert plans[0].titles[0].audio_map == (0, 1) and plans[0].subtitle_on == 0
    assert rows[1][1:] == ("failed", "Job criado numa versão anterior; gere de novo.")
```

  O plano antigo do teste é um dict literal (o JSON da Fase 3), não o `make_plan`, porque o
  `DvdPlan` sai na Task 9. Em `test_scan.py`: `purge_missing_folders` apaga o `DiscProject` de
  uma pasta que sumiu e mantém o de outra.

- [ ] **Step 2:** `uv run pytest tests/unit/test_disc_plan.py tests/unit/test_db.py tests/unit/test_scan.py -q` → FAIL (import).
- [ ] **Step 3: implementação.** Modelos acima. Migração `0004` (docstring: o downgrade apaga a
  tabela e não reconverte planos):

```python
def upgrade() -> None:
    op.create_table("disc_project",
        sa.Column("folder", sa.String(), primary_key=True),
        sa.Column("choices_json", sa.String(), nullable=False))
    conn = op.get_bind()
    for job_id, plan_json, status in conn.execute(sa.text("SELECT id, plan_json, status FROM job")).all():
        conn.execute(sa.text("UPDATE job SET plan_json = :p WHERE id = :i"),
                     {"p": json.dumps(_convert(json.loads(plan_json))), "i": job_id})
    conn.execute(sa.text("UPDATE job SET status = 'failed', error = :e, finished_at = CURRENT_TIMESTAMP "
                         "WHERE status IN ('queued', 'running')"), {"e": OLD_JOB})

TITLE_KEYS = ("path", "video_index", "size", "mtime_ns", "duration", "mode", "top_field_first",
              "aspect", "width", "height", "scale", "hd_color", "audio", "subtitles", "chapters")
DISC_KEYS = ("folder", "profile", "video_kbps", "maxrate_kbps", "estimated_bytes",
             "confirmed_low", "replace_existing", "volume", "iso_name")

def _convert(old: dict[str, Any]) -> dict[str, Any]:
    if "titles" in old:
        return old
    title = {key: old[key] for key in TITLE_KEYS}
    title["audio_map"] = list(range(len(old["audio"])))
    title["subtitle_map"] = list(range(len(old["subtitles"])))
    title["menu_name"] = old["folder"]
    disc = {key: old[key] for key in DISC_KEYS}
    return {**disc, "subtitle_on": 1 if old["subtitle_on"] else 0, "titles": [title], "menu": None}
```

  Em `test_models_match_the_migrations` a tabela nova precisa bater com o modelo.
  `tests/plans.py` ganha `make_title_plan(**overrides)` e `make_disc_plan(**overrides)` (dois
  títulos 16:9, idiomas `pt`/`en`, `menu` com uma página principal de série).
- [ ] **Step 4:** os testes da Step 2 passam; `make test` e `make lint` verdes.
- [ ] **Step 5: commit** `feat: add the disc project table and the disc plan models`.

---

### Task 2: entrada do disco, nomes, ordem, tipo, faixas por idioma e reconciliação

**Files:**
- Create: `src/projeto_dvd/planner/disc.py`
- Test: `tests/unit/test_disc.py`

**Interfaces:**
- Consumes: `DiscChoices`, `Theme`, `UND` (Task 1); `Summary`, `AudioTrack` (`library/probe.py`); `SubtitleOption`, `subtitle_options`, `audio_output` (`dvd_plan.py`); `Guess`, `guess` (`metadata/filename.py`); `TitleInfo` (`metadata/details.py`); `natural_key` (`library/files.py`); `dvd_language` (`planner/languages.py`); `suggest_profile`, `PROFILES` (Task 3 depois troca a calculadora; aqui a sugestão de perfil usa `estimate_disc` da Task 3, então a função `suggest` recebe `estimate` injetado: ver abaixo).
- Produces:

```python
MAX_TITLES = 60
MAX_LANGUAGES = 4

@dataclass(frozen=True)
class DiscTitle:
    path: str                       # relativo a MEDIA_DIR
    video: VideoFile
    summary: Summary
    options: tuple[SubtitleOption, ...]
    info: TitleInfo | None          # match confirmado
    guess: Guess

def disc_titles(view: FolderView, infos: Mapping[str, TitleInfo], max_year: int) -> tuple[DiscTitle, ...]
    # só arquivos com summary; o motivo de bloqueio fica em folder_reasons (Task 9)
def menu_name(title: DiscTitle, kind: Literal["movies", "series"]) -> str
def disc_name(titles: Sequence[DiscTitle], folder: str) -> tuple[str, str | None]  # nome e linha secundária
def strip_prefix(name: str, disc: str) -> str
def suggest_order(titles: Sequence[DiscTitle]) -> tuple[str, ...]
def suggest_kind(titles: Sequence[DiscTitle]) -> Literal["movies", "series"]
def audio_languages(titles: Sequence[DiscTitle]) -> tuple[str, ...]      # união, ordem de 1ª aparição
def subtitle_languages(titles: Sequence[DiscTitle]) -> tuple[str, ...]
def best_audio(title: DiscTitle, language: str) -> AudioTrack | None
def best_subtitle(title: DiscTitle, language: str) -> SubtitleOption | None
def track_warnings(titles: Sequence[DiscTitle], choices: DiscChoices) -> tuple[str, ...]
def suggest_choices(titles: Sequence[DiscTitle], folder: str, profile_for: Callable[[DiscChoices], str]) -> DiscChoices
def reconcile(saved: str | None, titles: Sequence[DiscTitle], suggestion: DiscChoices, backdrops: Sequence[str]) -> DiscChoices
def choice_errors(choices: DiscChoices, titles: Sequence[DiscTitle]) -> list[str]   # regras (limites, nenhum áudio)
```

Regras (da spec):
- `menu_name`: filme confirmado → `info.title`; episódio confirmado → `f"{info.episode}. {info.title}"` ou só `info.title` quando `generic_episode_name(info.title)`; sem match → `guess.title` (episódio: `f"{guess.episode}. {guess.title}"` não; sem match de episódio o nome é `f"Episódio {guess.episode}"` quando há número, senão `guess.title`); vazio → `PurePosixPath(path).stem`.
- `disc_name`: todos episódios confirmados da mesma série → (`show`, `"Temporada N"` se uma temporada só); um filme confirmado → título; todos filmes confirmados com o mesmo `collection` → collection; senão (`folder`, None).
- `strip_prefix("O Senhor dos Anéis: A Sociedade do Anel", "O Senhor dos Anéis")` → `"A Sociedade do Anel"` (remove o prefixo seguido de `:`, ` - ` ou espaço, só se sobrar texto).
- `suggest_order`: série (todos com temporada e episódio pela `info` ou pelo `guess`) → por `(season, episode)`; filmes → por `(info.year or 9999, natural_key(path))`.
- `best_audio`: faixas com `dvd_language(t.language) or UND == language`; prefere sem "coment"/"comment" no título, depois mais canais, depois menor índice.
- `best_subtitle`: opções suportadas do idioma, não forçadas; se só houver forçada, `None`.
- `track_warnings`: "As Duas Torres não tem áudio em Inglês: toca em Português." e "As Duas Torres não tem legenda em Inglês." e "As Duas Torres só tem a legenda forçada em Português." Nome do idioma pelo filtro `language` existente (`api/formatting.py`); `und` → "Idioma não informado".
- `suggest_choices`: audio = `pt` se existir na união, mais o original (TMDB do primeiro confirmado, senão o idioma da primeira faixa do primeiro título na ordem), sem repetir, máximo 4; subtitles = (`pt`,) se existir; subtitle_on = `pt` se o primeiro áudio não for `pt` e houver legenda `pt`; chapters `file` se todos os títulos têm ≥ 2 capítulos, senão `every` com 5 min; theme `Theme()`; profile = `profile_for(draft)`.
- `reconcile`: `saved` inválido (`ValidationError`) ou `None` → `suggestion`; ordem reconciliada (mantém os que existem, adiciona os novos na ordem de `suggestion.order`); `profile` fora de `PROFILES` → da sugestão; idiomas fora da união saem (áudio vazio → da sugestão); `subtitle_on` fora de `subtitles` → None; `theme.backdrop` fora de `backdrops` → None.
- `choice_errors`: mais de 60 títulos; mais de 4 idiomas de áudio ou de legenda; nenhum áudio.

- [ ] **Step 1: testes que falham** (um por regra; exemplos):

```python
def test_und_tracks_become_a_choosable_language() -> None:
    titles = [title("a.mp4", audio=[audio(1, None)])]
    assert audio_languages(titles) == ("und",)
    assert suggest_choices(titles, "Pasta", lambda c: "dvd5").audio == ("und",)

def test_a_forced_only_subtitle_counts_as_missing() -> None:
    t = title("a.mkv", subtitles=[sub(3, "por", forced=True)])
    assert best_subtitle(t, "pt") is None

def test_reconcile_survives_a_schema_change() -> None:
    titles = [title("Pasta/a.mkv")]
    suggestion = suggest_choices(titles, "Pasta", lambda c: "dvd5")
    assert reconcile('{"kind": "x"}', titles, suggestion, []) == suggestion

def test_reconcile_drops_removed_videos_and_appends_new_ones() -> None:
    ...  # saved order (b, gone) + pasta (a, b) → (b, a)

def test_reconcile_drops_a_backdrop_that_is_no_longer_available() -> None: ...

def test_series_order_by_season_and_episode() -> None: ...
def test_missing_audio_language_warns_with_the_fallback() -> None:
    # disco pt+en; título 2 só pt → "B não tem áudio em Inglês: toca em Português."
```

  Helpers de teste (`title`, `audio`, `sub`) montam `DiscTitle` com `Summary` a partir de dicts
  de ffprobe pelo `summarize` existente.
- [ ] **Step 2:** `uv run pytest tests/unit/test_disc.py -q` → FAIL.
- [ ] **Step 3:** implementar `planner/disc.py` com as regras acima.
- [ ] **Step 4:** PASS; `make test`, `make lint`.
- [ ] **Step 5: commit** `feat: suggest and reconcile the disc of a folder`.

---

### Task 3: `estimate_disc`

**Files:** Modify `src/projeto_dvd/planner/calculator.py`; Test `tests/unit/test_calculator.py`.

**Interfaces:**
- Produces:

```python
MENU_PAGE_BYTES = 2 * 1024 * 1024

@dataclass(frozen=True)
class TitleLoad:
    duration: float
    audio_kbps: tuple[int, ...]
    subtitles: int

def estimate_disc(profile: DiscProfile, titles: Sequence[TitleLoad], menu_pages: int) -> Estimate
def estimate(profile, duration, audio_kbps, subtitles) -> Estimate:  # passa a chamar estimate_disc(..., 0)
```

Fórmula: `room = (usable_bytes − menu_pages × MENU_PAGE_BYTES) × 8 / (1 + overhead)`;
`other = Σ dur_i × (Σaudio_i + 10 × subs_i) × 1000`; `video = (room − other) / Σdur / 1000`;
`maxrate = min_i maxrate_kbps(profile, audio_i, subs_i)`; `video = int(min(video, 0.95 × maxrate))`;
`size = Σ dur_i × (video + Σaudio_i + 10 × subs_i) × 1000 × (1 + overhead) / 8 + reserve + menu_pages × MENU_PAGE_BYTES`.

- [ ] **Step 1:** testes: (a) um título e 0 páginas dá o mesmo `Estimate` de antes para 3
  durações conhecidas (valores atuais dos testes de `estimate`); (b) dois títulos com áudios
  diferentes usam o menor maxrate; (c) 10 páginas de menu reduzem o vídeo e somam 20 MiB ao
  tamanho; (d) duração total 0 levanta `ValueError` explícito ("disc without duration").
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte.
- [ ] **Step 5: commit** `feat: estimate a disc with several titles and menus`.

---

### Task 4: páginas lógicas do menu

**Files:** Create `src/projeto_dvd/menus/__init__.py`, `src/projeto_dvd/menus/pages.py`; Test `tests/unit/test_menu_pages.py`.

**Interfaces:**
- Consumes: `MenuItem`, `MenuPage` (Task 1).
- Produces:

```python
PAGE_SIZE = 6
LARGE_MAX = 4

def build_pages(
    kind: Literal["movies", "series"],
    names: Sequence[str],          # nomes no menu, na ordem do disco (títulos 1..N)
    disc_name: str,
    secondary: str | None,
    audio_labels: Sequence[str],   # "Português", "Inglês (original)"
    subtitle_labels: Sequence[str],
) -> tuple[MenuPage, ...]
def page_of_title(pages: Sequence[MenuPage], title: int) -> tuple[int, int]  # (índice da página, botão 1-based)
def audio_variant(pages: Sequence[MenuPage], option: int) -> int             # índice da página
def subtitle_variant(pages: Sequence[MenuPage], option: int) -> int          # option 0 = sem legenda
```

Ordem fixa das páginas: `[principal(is), episódios ou filmes 2..k, variantes de Áudio (uma por
opção), variantes de Legendas (sem legenda + uma por idioma)]`. Regras:
- Um título só: principal "Assistir" (`play` 1), "Áudio", "Legendas" (grande).
- Filmes (Ruling do plano sobre a spec: a lista grande comporta 4 itens, então "até 4 filmes
  mais Áudio e Legendas na lista grande" não cabe; e um rodapé de 4 posições não cabe em 448 px):
  - filmes + itens de idioma ≤ 4: principal grande com os filmes, "Áudio", "Legendas";
  - ≤ 6: principal normal com os filmes, "Áudio", "Legendas";
  - mais: principal grande ("Filmes" `page` 1, "Áudio", "Legendas") e páginas de filmes como as
    de episódios (até 6, rodapé ◀ Anterior / Voltar / Próxima ▶). O filme volta à página dele.
- Série: principal grande ("Tocar todos" `play_all`, "Episódios" `page` 1, "Áudio", "Legendas");
  páginas de episódios com até 6 itens e rodapé (◀ Anterior/None, "Voltar", Próxima ▶/None).
  `secondary` das páginas de episódios: "Episódios 7 a 12 de 24".
- Áudio: cabeçalho "Áudio", itens = opções (`audio` i) + "Voltar" (`back`), `checked = i`,
  `focus = i + 1`, grande. Legendas: "Sem legenda" (`subtitle` 0), idiomas (`subtitle` i+1),
  "Voltar". "Áudio" some com 1 idioma; "Legendas" some com 0.
- `focus` da principal: 1.

- [ ] **Step 1:** testes: um título; 3 filmes; 7 filmes (2 páginas, filme 7 na página 1 índice
  da lista 1 → `page_of_title(pages, 7) == (1, 1)`); série de 13 (3 páginas de episódios,
  "Episódios 13 a 13 de 13"); 1 idioma de áudio some; 0 legendas some; variantes com `checked`;
  nenhuma página com mais de 6 itens normais ou 5 grandes.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte.
- [ ] **Step 5: commit** `feat: build the DVD menu pages`.

---

### Task 5: tema e layout

**Files:** Create `src/projeto_dvd/menus/theme.py`, `src/projeto_dvd/menus/layout.py`; Test `tests/unit/test_menu_theme.py`, `tests/unit/test_menu_layout.py`.

**Interfaces:**
- Produces (`theme.py`):

```python
PALETTE: dict[str, tuple[str, str]] = {"ambar": ("Âmbar", "#E0A526"), "vermelho": ("Vermelho", "#D9483B"),
    "azul": ("Azul", "#4C9BE0"), "verde": ("Verde", "#3DB894"), "lilas": ("Lilás", "#A685E0"),
    "gelo": ("Gelo", "#E6E6E6")}
TEXT, SECONDARY, OUTLINE = "#EBEBEB", "#B4B4B4", "#101010"

def available_backdrops(output_dir: Path, folder: str) -> tuple[str, ...]
    # sorted(p.parent.name for p in (output_dir/"covers"/safe_name(folder)).glob("*/backdrop.jpg"))
def backdrop_path(output_dir: Path, folder: str, name: str) -> Path   # via art_dir; ValueError fora
def auto_accent(image: Image.Image | None) -> str                     # chave da paleta
def resolve_accent(accent: str, image: Image.Image | None) -> str     # hex
```

  `auto_accent`: `image.convert("RGB").resize((64, 36)).quantize(8, method=Image.Quantize.MEDIANCUT)`,
  peso `count × saturação` (HSV de `colorsys`), ignora V < 0,25 ou S < 0,20; escolhe a chave da
  paleta (exceto gelo) com menor distância circular de matiz; sem candidata → `"ambar"`.

- Produces (`layout.py`):

```python
@dataclass(frozen=True)
class Box:  # coordenadas em 720x480, pares
    x0: int; y0: int; x1: int; y1: int

@dataclass(frozen=True)
class ButtonGeometry:
    number: int                 # 1-based, na ordem: itens da lista, depois rodapé da esquerda para a direita
    box: Box                    # a faixa (720)
    marker: Box                 # o marcador de 8 px quadrados convertido
    text_x: int                 # no espaço quadrado
    text_y: int
    font_size: int
    up: int; down: int; left: int; right: int

@dataclass(frozen=True)
class PageLayout:
    width: int                  # 854 ou 640 (espaço quadrado)
    heading_lines: tuple[str, ...]  # já quebrado (até 2 linhas)
    heading_size: int
    buttons: tuple[ButtonGeometry, ...]

def square_width(aspect: str) -> int
def to_720(x: int, width: int) -> int        # round(x * 720 / width / 2) * 2
def letterbox_y(y: int) -> int               # 60 + y*3/4, par
def layout_page(page: MenuPage, aspect: str, side: str, measure: Callable[[str, int], int]) -> PageLayout
def fit_label(text: str, width: int, measure: Callable[[str, int], int]) -> tuple[str, int]  # (texto, tamanho 28 → 24 → reticências)
```

  `measure(text, size)` devolve a largura em px no espaço quadrado (injetado: o render usa o
  DejaVu; os testes, uma função fixa como `len(text) * size * 0.6`). Grade da spec: área segura
  y 48 a 432; coluna 16:9 85 a 565 (esquerda) ou 289 a 769 (direita); 4:3 64 a 512 ou 128 a 576;
  texto 32 px depois da borda; lista normal passo 40 faixa 36 Bold 28; grande passo 56 faixa 48
  Bold 34; lista ancorada embaixo (termina em 396 com rodapé, 432 sem); rodapé y 400 a 432,
  faixa 32, Bold 24, três posições fixas dividindo a coluna em três; setas: lista sem volta,
  baixo do último vai ao rodapé (posição do meio, ou a existente mais próxima), cima do rodapé
  volta ao último item, esquerda/direita só no rodapé (entre as posições existentes); botão sem
  vizinho aponta para ele mesmo. Cabeçalho y 48 a 120: Bold 34 numa linha se couber, senão até
  2 linhas Bold 28 (reticências na 2ª).

- [ ] **Step 1:** testes de tema: `available_backdrops` com duas pastas (uma sem `backdrop.jpg`);
  `backdrop_path` com `../x` levanta `ValueError`; `auto_accent` de uma imagem azul sólida → `azul`,
  de uma cinza → `ambar`, `None` → `ambar`; `resolve_accent("verde", None) == "#3DB894"`.
  Testes de layout, para os planos de exemplo (filmes 1, 4, 6, 7; série 13; 16:9 e 4:3; lado
  esquerdo e direito): todas as caixas dentro de x 72..648 e y 48..432 em 720; todas as
  coordenadas pares; duas caixas nunca a menos de 4 px; números de botão contíguos; setas
  apontam para botões existentes; `letterbox_y(114) == 146`; `fit_label` corta com "…" um nome
  enorme e cai para 24 antes.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte.
- [ ] **Step 5: commit** `feat: lay out the DVD menu pages`.

---

### Task 6: render dos menus (Pillow)

**Files:** Create `src/projeto_dvd/menus/render.py`; Test `tests/unit/test_menu_render.py`.

**Interfaces:**
- Consumes: Tasks 4 e 5; `FONT` (`authoring/dvd/subtitles.py`) e o caminho do Bold
  (`FONT_BOLD = FONT.with_name("DejaVuSans-Bold.ttf")`, constante nova ao lado de `FONT`).
- Produces:

```python
Fonts = Callable[[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont]  # (tamanho, bold)

def dejavu(size: int, bold: bool) -> ImageFont.FreeTypeFont
def text_dark_enough(image: Image.Image, box: tuple[int, int, int, int]) -> bool  # p95 da luma 601 ≤ 64
def background(page: MenuPage, layout: PageLayout, backdrop: Image.Image | None, accent: str,
               side: str, disc_name: str, fonts: Fonts) -> Image.Image   # 720x480 RGB
def highlight(layout: PageLayout, accent: str, select: bool) -> Image.Image  # 720x480 "P" ou "RGBA" com ≤ 4 cores, alfa 0/255
def render_page(plan: MenuPlan, index: int, fonts: Fonts = dejavu) -> RenderedPage
def preview(plan: MenuPlan, index: int, fonts: Fonts = dejavu) -> bytes  # PNG: fundo + highlight do foco

@dataclass(frozen=True)
class RenderedPage:
    background: Image.Image
    highlight: Image.Image
    select: Image.Image
    layout: PageLayout
```

Fundo com arte (spec): cover-crop no espaço quadrado; brilho e saturação × 0,85; gradiente preto
do lado dos botões (alfa 0,85 até o fim da coluna + 40 px, linear até 0 nos 35% seguintes);
desfoque gaussiano raio 4 só sob o gradiente (`Image.composite`); checagem `text_dark_enough` em
cada caixa de texto, subindo o alfa para 0,92 e 0,97; texto com `stroke_width=2,
stroke_fill=OUTLINE`; ✓ antes do item `checked`; filtro vertical `[0,1,0, 0,2,0, 0,1,0]/4`;
redução para 720x480 com `Image.Resampling.LANCZOS`. Fundo neutro: gradiente diagonal `#262B3A`
→ `#121216`, brilho radial do destaque a 12%, filete 120x4 sob o nome do disco, ruído ±2
(`numpy` não: `Image.effect_noise` misturado com 2% ou `random.Random(0)` por linha). Highlight:
paleta com 4 entradas (transparente, destaque, destaque da faixa, `#101010`); a faixa e o marcador
desenhados com `ImageDraw.rectangle` direto em 720x480; no `select` o marcador é `#EBEBEB`. O
contraste parcial (faixa a 5/15 e 9/15) vai no XML do spumux (Task 7), não no PNG.

- [ ] **Step 1:** testes (fonte de teste `lambda size, bold: ImageFont.load_default(size=size)`):
  `highlight` tem no máximo 4 valores RGBA distintos e alfa só em {0, 85, 255} (`select`: {0,
  153, 255}), sem nenhum valor intermediário de antialias (`getcolors()`); nenhum pixel
  não transparente fora das caixas; `background` é 720x480 RGB; com um backdrop branco sólido,
  `text_dark_enough` passa em todas as caixas de texto depois do tratamento; o ✓ muda os pixels
  da linha `checked`; o fundo neutro funciona sem backdrop; `preview` devolve PNG 720x480.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte.
- [ ] **Step 5: commit** `feat: render the DVD menu pages with Pillow`.

---

### Task 7: autoria dos menus (ffmpeg, spumux, dvdauthor)

**Files:** Create `src/projeto_dvd/authoring/dvd/menus.py`; Modify `src/projeto_dvd/authoring/dvd/dvdauthor.py`; Test `tests/unit/test_authoring.py`, `tests/unit/test_menu_authoring.py`.

**Interfaces:**
- Consumes: `DiscPlan`, `TitlePlan`, `MenuPlan` (Task 1); `PageLayout`, `letterbox_y` (Task 5);
  `page_of_title`, `audio_variant`, `subtitle_variant` (Task 4); `CODEC_OPTIONS`, `COLOR_TAGS`
  (`encode/video.py`).
- Produces (`menus.py`):

```python
def menu_video_command(background: Path, aspect: str, output: Path) -> list[str]
def spumux_buttons_xml(layout: PageLayout, highlight: Path, select: Path, letterbox: bool) -> str
def spumux_menu_command(xml: Path, stream: int) -> list[str]   # ["spumux", "-m", "dvd", "-s", str(stream), str(xml)]
def page_file(job_dir: Path, index: int) -> Path               # job_dir / f"menu{index}.mpg"
```

  Comando do fundo (spec): `ffmpeg -y -nostdin -loop 1 -framerate 30000/1001 -i background.png
  -f lavfi -i anullsrc=r=48000:cl=stereo -t 1 -vf format=yuv420p,setsar=<32/27 ou 8/9>
  *CODEC_OPTIONS -q:v 2 -flags +cgop+ilme+ildct -top 1 -aspect <a> -bsf:v COLOR_TAGS -c:a ac3
  -b:a 192k -f dvd -muxrate 10080k -packetsize 2048 <out>` (sem `-b:v`, sem `-maxrate`).
  XML do spumux: `<subpictures format="NTSC"><stream><spu start="00:00:00.00" force="yes"
  highlight=… select=… autooutline="none" autoorder="rows"…>` com
  `<button name="N" x0 y0 x1 y1 up down left right/>` explícitos; no letterbox o y é
  `letterbox_y`. As cores e o contraste: `highlight` e `select` como PNG indexado e o
  contraste parcial pelo alfa da entrada 2 da paleta do PNG (o spumux converte o alfa de cada
  cor em contraste: 85 ≈ 5/15 no highlight, 153 ≈ 9/15 no select). O teste `slow` (Task 10)
  confirma; se não passar, plano B da spec (tudo opaco, marcador e contorno).

- Produces (`dvdauthor.py`):

```python
MAX_COMMANDS = 128
def dvdauthor_xml(plan: DiscPlan, job_dir: Path, layouts: Sequence[PageLayout]) -> str
def command_count(pgc_commands: str) -> int   # conta comandos (separados por ';', 'if' conta 2)
```

  Estrutura (spec, números de menu do VMGM: 1 despachante de títulos, 2 despachante de páginas,
  página `p` = menu `p + 3`):
  - `<fpc>g0 = 0; g1 = <subtitle_on>; g2 = 0; g3 = 1024; g5 = 0; jump menu 1;</fpc>`
  - menu 1 (`entry="title"`): `<pre>g4 = g2; g2 = 0; if (g4 == 1) jump title 1; …; jump menu 2;</pre>` (sem `vob`).
  - menu 2: `<pre>if (g5 == 1) jump menu 4; …; if (g5 == AUDIO) {if (g0 == 0) jump menu A0; …} if (g5 == SUBS) {…} jump menu 3;</pre>`, com `AUDIO = 100` e `SUBS = 101`.
  - menu `p + 3`: `<pre>g5 = p; button = g3;</pre>` (variantes: `g5 = 100|101; button = <focus>*1024;`), `<vob file=menuP.mpg pause="inf"/>` e um `<button name="N">` por botão do layout:
    - `play` t (filme ou episódio escolhido): `g2 = 0; g3 = <N*1024>; g5 = p; jump title t;`
    - `play_all`: `g2 = 0; g3 = <N*1024>; g5 = 0; jump title 1;`
    - `page` q: `g3 = 1024; jump menu q+3;` (Anterior, Próxima, Episódios)
    - `audio` i: `g0 = i; jump menu <audio_variant(i)+3>;`; `subtitle` i: `g1 = i; jump menu …;`
    - `back`: `g3 = <botão de origem na principal>; jump menu 3;`; "Áudio"/"Legendas" da principal: `g3 = <N*1024>; jump menu <variante atual>` via `g5 = 100; jump menu 2;`.
  - `<menus lang="pt">` no VMGM com `<video format="ntsc" aspect=… [widescreen="nopanscan"]/>` e, no 16:9, `<subpicture><stream id="0" mode="widescreen"/><stream id="1" mode="letterbox"/></subpicture>`.
  - Um `<titleset>` por título: `<menus lang="pt"><video …/><pgc entry="root"><pre>g2 = 0; jump vmgm menu 1;</pre></pgc></menus>`; `<titles>` com `video`, um `<audio lang>` por faixa (sem `lang` para `und`), `<subpicture lang>` por legenda; `<pgc>` com `<pre>` do mapa (`if (g0 == k) audio = audio_map[k]; …; if (g1 == 0) subtitle = 0; if (g1 == k+1) subtitle = 64 + subtitle_map[k];` e, para `None`, `subtitle = 0`), `<vob file=titleN.mpg chapters=…/>` e `<post>`:
    - filme: `g2 = 0; g3 = <botão dele>*1024; g5 = <página dele>; call vmgm menu 1;`
    - episódio não último: `g2 = <t+1>; call vmgm menu 1;`; último: `g2 = 0; g3 = 2048; g5 = 0; call vmgm menu 1;` ("Episódios" é o botão 2 da principal da série).
  - `ValueError` se algum PGC passar de `MAX_COMMANDS`.

- [ ] **Step 1: testes que falham** (sobre `make_disc_plan` e planos de exemplo):

```python
def test_the_title_dispatcher_clears_g2_before_jumping() -> None:
    root = ET.fromstring(dvdauthor_xml(series_plan(3), Path("/j"), layouts))
    pre = root.find("vmgm/menus/pgc[@entry='title']/pre").text
    assert pre.startswith("g4 = g2; g2 = 0;") and "jump title 3;" in pre and root.find("vmgm/menus/pgc[@entry='title']/vob") is None

def test_every_button_targets_an_existing_title_or_menu() -> None: ...   # parse 'jump title N' e 'jump menu K'
def test_a_movie_returns_to_its_page_and_button() -> None:              # 7 filmes: o 7º volta g5=1, g3=1024
def test_the_last_episode_returns_with_episodes_highlighted() -> None: ...
def test_one_titleset_per_title_declares_only_its_tracks() -> None: ...
def test_a_title_without_the_second_language_maps_it_to_its_first_track() -> None:
    # audio_map (0, 0) → "if (g0 == 1) audio = 0;"
def test_sixty_titles_fit_in_128_commands() -> None: ...
def test_sixty_one_titles_raise() -> None: ...
def test_letterbox_buttons_are_the_widescreen_ones_moved() -> None: ...
def test_menu_video_is_interlaced_and_quantizer_based() -> None:
    cmd = menu_video_command(Path("bg.png"), "16:9", Path("m.mpg"))
    assert "+cgop+ilme+ildct" in cmd and "-q:v" in cmd and "-b:v" not in cmd
```

- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte. Conferir na imagem
  (`docker build --target test`), com o XML gerado para 3 títulos, que o `dvdauthor` aceita
  (pode ficar para a Task 10, que roda tudo).
- [ ] **Step 5: commit** `feat: author DVD menus with a VMGM dispatcher`.

---

### Task 8: do `DiscChoices` ao `DiscPlan`

**Files:** Modify `src/projeto_dvd/planner/disc_plan.py`; Test `tests/unit/test_disc_plan.py`.

**Interfaces:**
- Consumes: Tasks 1 a 5; `geometry` (`planner/source.py`), `plan_chapters`, `audio_output`,
  `volume_name` (`dvd_plan.py`).
- Produces:

```python
@dataclass(frozen=True)
class TitleSource:            # um título pronto para o encode (prepare/frame scan feitos)
    title: DiscTitle
    mode: VideoMode
    top_field_first: bool

def title_plan(source: TitleSource, choices: DiscChoices, menu_name: str) -> TitlePlan
def menu_plan(choices: DiscChoices, titles: Sequence[DiscTitle], folder: str, backdrop: Path | None,
              accent_image: Image.Image | None) -> MenuPlan
def disc_estimate(profile: DiscProfile, plans: Sequence[TitlePlan], menu_pages: int) -> Estimate
def build_disc_plan(folder: str, sources: Sequence[TitleSource], choices: DiscChoices,
                    menu: MenuPlan, confirm_low: bool, replace_iso: bool) -> DiscPlan
def disc_errors(choices: DiscChoices, titles: Sequence[DiscTitle], estimate: Estimate,
                confirm_low: bool) -> list[str]   # choice_errors + "não cabe" + "confirme a qualidade baixa"
```

- `title_plan`: faixas na ordem dos idiomas do disco, sem repetir stream (dois idiomas que caem
  na mesma faixa por fallback não duplicam: o mapa aponta para o mesmo índice); `audio_map[k]` =
  posição no `audio` do título da faixa do idioma k, ou 0 (a primeira faixa do disco que ele
  tem) quando falta; `subtitle_map[k]` = posição ou None; capítulos por `plan_chapters`.
- `menu_plan`: aspecto 16:9 salvo se todos os títulos forem 4:3; rótulos de áudio com
  "(original)" quando o idioma é o `original_language` do primeiro título confirmado; o nome do
  disco por `disc_name`; nomes por `menu_name` + `strip_prefix`.
- `build_disc_plan`: bitrate pelo `estimate_disc` com `len(menu.pages)` páginas; `subtitle_on`
  = posição + 1 de `choices.subtitle_on` ou 0; `volume_name(folder)`, `iso_name=f"{folder}.iso"`.

- [ ] **Step 1:** testes: faixa `und`; fallback de idioma (mapa 0); dois idiomas no mesmo stream
  não duplicam; menu 4:3 só com todos 4:3; "(original)"; bitrate igual para todos; o plano de
  um título com menu tem `estimated_bytes` maior que sem menu em 2 MiB por página; `disc_errors`
  de 61 títulos e de "não cabe".
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte.
- [ ] **Step 5: commit** `feat: turn the disc choices into a disc plan`.

---

### Task 9: pipeline, QA, worker e telas do job com vários títulos e menus

**Files:** Modify `encode/video.py`, `encode/audio.py` (tipo), `authoring/dvd/mux.py`,
`authoring/dvd/qa.py`, `jobs/pipeline.py`, `jobs/worker.py`, `jobs/store.py`, `api/jobs.py`,
templates do job; Delete do `dvd_plan.py`: `Choices`, `suggest_choices`, `validate_choices`,
`build_plan`, `DvdPlan`, `audio_kbps`; `planner/disc_source.py` passa a preparar vários títulos;
Test: `test_pipeline.py`, `test_qa.py`, `test_worker.py`, `test_store.py`, `test_job_routes.py`,
`test_encode.py`, `test_authoring.py`, `test_disc_source.py`, `tests/plans.py`.

**Interfaces:**
- `video_pass_command(title: TitlePlan, video_kbps, maxrate_kbps, source, job_dir, pass_number, number)`;
  arquivos por título: `title{n}.m2v`, `title{n}.audio{k}.ac3`, `title{n}.mpg`.
- `mux_command(title: TitlePlan, job_dir, number, first_pts)`; `iso_command(plan: DiscPlan, job_dir)`.
- QA: `size_checks(iso_bytes, plan: DiscPlan)`; `tree_check(listing, titles: int)` (exige
  `VIDEO_TS.VOB` e `VTS_NN_0.IFO/BUP`, `VTS_NN_1.VOB` para NN de 1 a N);
  `dvd_probe_command(iso, title)`, `extract_video_command(iso, output, title)`,
  `decode_command(iso, title)`, `stream_checks(probe, title: TitlePlan, seconds)`,
  `bitstream_checks(report, aspect)`, `sync_check(probe, title)`; menus:
  `menu_probe_command(iso, pgc)`, `extract_menu_command(iso, output, pgc)`,
  `menu_checks(probe, aspect)` (mpeg2video 720x480, aspecto, um ac3). Os `Check.label` dos
  checks por título levam o prefixo "Título N: ", e os de menu "Menu K: ".
- `Step` ganha `MENUS = "menus"` (entre `SUBTITLES` e `AUTHOR`); `report(step, fraction, title)`
  com `title` 0 para etapas do disco; `store.save_progress(engine, job_id, step_text, progress)`
  com `step_text = f"{title}:{step}"` ou `step`; `overall_progress(plan, step, fraction, title)`
  com peso de cada título proporcional à duração.
- `store.enqueue(session, plan: DiscPlan)`; worker lê `DiscPlan`; `run_pipeline(plan: DiscPlan, …)`
  recusa `plan.menu is None` (`PipelineError("Job criado numa versão anterior; gere de novo.")`).
- Pipeline: para cada título (com `_check_source`), as etapas da Fase 3 com os nomes por título
  (o `movie.mpg` vira `title{n}.mpg`); depois `MENUS`: `render_page` de cada página → PNGs →
  `menu_video_command` → `spumux_menu_command` (stream 0 e, no 16:9, stream 1 com o XML
  letterbox) → `menu{p}.mpg`; `AUTHOR` com `dvdauthor_xml(plan, job_dir, layouts)`; apaga os
  `title*.mpg` e `menu*.mpg`; ISO; QA por título e por página (`pgc = página + 3`); cópia.
- `api/jobs.py`: `JobView.plan: DiscPlan`; `_steps` mostra as etapas por título com o prefixo
  "Título k de N · " quando há mais de um título, e lê o formato antigo (`job.step` sem `:`).
  `jobs.html` mostra o perfil e o número de títulos.
- `disc_source.py`: `folder_reasons(view)` sem `ONE_VIDEO` (qualquer arquivo com erro ou
  `check_video` com motivos bloqueia, com o nome do arquivo: "a.mkv: <motivo>");
  `prepare_title(title: DiscTitle, capture) -> TitleSource | tuple[str, ...]`;
  `suggested_disc_plan(session, media_dir, output_dir, folder) -> DiscPlan | tuple[str, ...]` para o comando de
  desenvolvimento (`python -m projeto_dvd.jobs.pipeline <pasta>`).

- [ ] **Step 1:** atualizar os testes existentes para os tipos novos e acrescentar: pipeline com 2
  títulos (ferramentas falsas do `test_pipeline.py`) chama o encode de cada um, a etapa `MENUS`
  gera um `menu{p}.mpg` por página e dois spumux no 16:9; recusa plano sem menu; QA reprova se
  faltar `VTS_02_1.VOB`; `_steps` com "Título 2 de 3"; job antigo convertido abre na tela.
- [ ] **Step 2:** FAIL. **Step 3:** implementar e apagar o código antigo. **Step 4:** `make test`
  (100%) e `make lint`.
- [ ] **Step 5: commit** `feat: generate discs with several titles and menus`.

---

### Task 10: teste `slow` do disco com menus e da navegação

**Files:** Create `tests/integration/navigation.py`; Modify `tests/integration/clips.py`, `tests/integration/test_dvd.py`.

**Interfaces:**
- `navigation.py` (base: o driver do `tech-lead-midia`, com tipos e sem prints):

```python
class Nav:
    def __init__(self, iso_or_dir: Path) -> None
    def menu_still(self) -> tuple[str, int, int]     # (domínio, título, parte) ao parar num menu
    def highlighted(self) -> int
    def press(self, button: int) -> None
    def title_key(self) -> None                      # dvdnav_menu_call(…, DVD_MENU_Title=2)
    def menu_key(self) -> None                       # DVD_MENU_Root=3
    def play_until_title(self, title: int) -> None
    def streams(self) -> tuple[int, int]             # áudio e legenda ativos
```

- `clips.py`: `series_folder(media)` com 3 clipes de 4 s (dois 16:9 com `por`+`eng` e legenda
  `por` no 1º, `eng` só no 2º; um 4:3 com `por`), `S01E01..03` no nome; `disc_plan_for(media,
  folder, output, **choice_overrides)`.

- [ ] **Step 1:** testes (`pytestmark = pytest.mark.slow`):
  1. a série vira ISO, a QA passa, os menus ficam abaixo de 2 MiB por página, o `VIDEO_TS.VOB`
     tem dois grupos de botões (ler o PCI com o `pci.py` do tech-lead, portado), e o grupo 2 tem
     o y transformado;
  2. navegação: inserir → menu principal com o botão 1; "Tocar todos" → título 1 → no fim vai
     sozinho ao título 2; `title_key()` no meio do título 2 → menu (não volta ao título 2);
     `menu_key()` no meio do título 1 → menu; escolher Inglês na página Áudio e tocar o título 1
     → áudio ativo 1; o título 3 (sem Inglês) toca no áudio 0;
  3. 7 filmes minúsculos: o 7º volta para a página 2 com o botão 1 destacado;
  4. 60 títulos minúsculos: o dvdauthor aceita (só autoria, sem encode: `.mpg` gerados uma vez e
     repetidos).
- [ ] **Step 2:** rodar `make test-slow` (ou `docker run … pytest -m slow -k menus`) e corrigir o
  que falhar com debugging sistemático (cada correção com teste unitário que reproduz).
- [ ] **Step 3:** decidir o contraste parcial do destaque pelo resultado (Ruling da Task 7).
- [ ] **Step 4: commit** `test: author and navigate a DVD with menus`.

---

### Task 11: tela "Montar DVD", rotas e preview

**Files:** Modify `src/projeto_dvd/api/dvd.py`, `web/templates/dvd_form.html`, `_dvd_block.html`,
`_profile_cards.html`, `web/static/app.css`; Create `web/templates/_disc_results.html`;
Test `tests/unit/test_dvd_routes.py`.

**Interfaces:**
- Rotas da spec: `GET /folders/{name}/dvd` (`dvd_form`), `POST /folders/{name}/dvd/choices`
  (`dvd_choices`), `GET /folders/{name}/dvd/menu.png` (`dvd_menu_preview`, `page: int`, `v: str`),
  `POST /folders/{name}/dvd` (`create_dvd`). Some `/dvd/estimate`.
- `parse_disc_form(form, titles) -> DiscChoices | None` (ordem por inputs `order`; `move=i:up|down`
  aplicado; idiomas `audio`, `subtitle`, `subtitle_on`; `kind`; `profile`; `chapters`; `minutes`;
  `backdrop`, `accent`, `side`); valores fora das listas do servidor → `None` (formulário
  inválido) ou caem na reconciliação.
- Contexto da tela: títulos com `menu_name` exibido ("No menu: …"), avisos, estimativas por
  perfil (`disc_estimate` com o `TitlePlan` aproximado: sem frame scan, `mode` do `check_video`),
  páginas do menu (`menu_plan`) com rótulos para o seletor, fundos disponíveis, paleta com o
  `auto` resolvido, `v = sha1(choices_json)[:12]`.
- Preview: `Response(content=preview(plan, page), media_type="image/png", headers={"Cache-Control": "no-cache"})`; página fora → 404.
- `create_dvd`: frame scan só aqui (`prepare_title` com o cache `_frames`), `disc_errors`,
  `preflight`, `store.enqueue`. `confirm_low` e `replace_iso` lidos do formulário e nunca salvos.
- Template: blocos na ordem da spec (Títulos, Idiomas, Menu, Capítulos, Disco); barra fixa;
  `hx-post` do formulário para `/choices` com `hx-trigger="change"`, `hx-sync="this:queue all"`;
  resposta `_disc_results.html` com `hx-swap-oob` para `#disc-titles` (quando a ordem mudou),
  `#disc-warnings`, `#profiles`, `#disc-bar`, `#menu-preview`. Botões Subir/Descer 44x44 com
  `aria-label` e foco devolvido pelo id (`hx-on::after-swap`).
- `_dvd_block.html`: "Montar DVD".

- [ ] **Step 1:** testes de rota: o GET mostra todos os títulos com o nome no menu e não grava;
  `/choices` grava o `disc_project` e devolve os blocos `oob`; `move=1:up` troca a ordem;
  `order` que não é permutação → erro de formulário sem gravar; `backdrop=../../etc` vira `None`;
  `confirm_low` não aparece no `choices_json`; preview 200 PNG, página 99 → 404; `create_dvd`
  enfileira um `DiscPlan` com 2 títulos e menu; pasta com arquivo ilegível bloqueia com o nome;
  JSON salvo inválido abre com a sugestão; job ativo redireciona.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS, `make test` 100%, `make lint`;
  conferir a tela com Chrome headless em 375 px e 1100 px (docker compose com uma pasta de 3
  clipes) e o preview.
- [ ] **Step 5: commit** `feat: build the DVD of a folder on the Montar DVD page`.

---

### Task 12: documentação, smoke e fechamento

**Files:** `README.md`, `README.pt-BR.md`, `CLAUDE.md` (3.3, 3.4, 5.1, 7, 7.1, 7.2, 9, 12, 13,
Estado atual, Log de decisões), `.github/workflows/ci.yml` (smoke: a tela "Montar DVD" responde
200 numa pasta escaneada, se o smoke atual já cria pasta; senão, só o que ele já faz).

- [ ] **Step 1:** atualizar a documentação (sem travessão; README com a seção do disco com menu e
  a navegação; CLAUDE.md com as decisões da fase).
- [ ] **Step 2:** `make lint`, `make test`, `make test-slow` verdes; `docker compose up -d --build`
  e smoke manual da tela.
- [ ] **Step 3: commit** `docs: document the disc builder and DVD menus`.
- [ ] **Step 4:** revisão final do branch (revisor fresco), correções com TDD, PR.

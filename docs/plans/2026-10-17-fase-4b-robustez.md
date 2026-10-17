# Fase 4b: Robustez (plano de implementação)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** retomar jobs, reaproveitar o vídeo já codificado (cache por limite de espaço) e copiar
o vídeo de rips de DVD compatíveis sem recodificar.

**Architecture:** `jobs/cache.py` guarda o `.m2v` de cada título recodificado por hard link,
chaveado pelo próprio comando da 2ª passada; o pipeline consulta o cache antes das passadas e o
worker despeja por `mtime`. Retomar é uma rota que roda o preflight, limpa a pasta do job e
devolve o mesmo job à fila num `UPDATE` atômico. A cópia do rip é decidida em `title_plan`
(puro), confirmada pela amostra de quadros ao gerar, e executada como a etapa `VIDEO_COPY`, com
conferência imediata do bitstream, capítulos levados para GOP fechado e QA de vídeo idêntico.

**Tech Stack:** Python 3.12, FastAPI + HTMX, SQLModel, ffmpeg/ffprobe, dvdauthor, libdvdnav nos
testes `slow`.

**Spec:** `docs/plans/2026-10-17-fase-4b-robustez-design.md` (aprovada pelo Vini).

## Global Constraints

- Conversa em português; código, commits e README em inglês; **sem travessão (—)**.
- Conventional Commits terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `make lint` e `make test` (100%) verdes a cada task, conferindo o código de saída do lint (não
  o do `tail`); `make test-slow` nas tasks com ferramentas reais (`--memory 3g`).
- `CACHE_LIMIT_GB` padrão 50 (`float`, ≥ 0; 0 desliga); cache em `WORK_DIR/cache`, nomes
  `^[0-9a-f]{64}\.(m2v|json)$`; hard link sempre; só o worker despeja.
- Menus na calculadora: `max(páginas, 20) × 2 MiB`; `maxrate` só dos recodificados.
- Rip copiável: MPEG-2 720x480, sem escala, aspecto 4:3/16:9, "CPB properties" `max_bitrate ≤
  9.800.000` e `buffer_size ≤ 1.835.008`, orçamento herdado do áudio, tamanho conhecido,
  `reencode_rips` desmarcado; GOP ≤ 36 campos exibidos; capítulos do arquivo levados ao GOP
  fechado a até 1 s.
- Nunca chamar o TMDB real; nunca commitar mídia, ISO, `.env`, banco.

## Review Focus

1. Job cancelado depois de um cache hit e retomado: o `.m2v` ligado ao cache nunca é truncado
   nem editado (Task 2: teste com `st_nlink` e o arquivo do cache intacto).
2. Retomar um job cujo ISO já existe na saída sem `replace_existing`: recusa na hora, com a
   mensagem do preflight, não depois de horas (Task 3).
3. Disco só com rips copiados: a calculadora não divide por zero, o cartão diz "vídeo copiado do
   DVD" (Task 4).
4. Rip com capítulo no meio de GOP aberto: o capítulo vai para o GOP fechado mais próximo, ou sai
   (Task 5).
5. "Limpar cache" com um link simbólico ou um arquivo de nome estranho na pasta do cache: nada
   fora dos nomes válidos é apagado (Task 3).

---

### Task 1: calculadora estável e o módulo do cache

**Files:** Modify `src/projeto_dvd/planner/calculator.py`, `src/projeto_dvd/planner/disc_build.py`,
`src/projeto_dvd/config.py`, `src/projeto_dvd/encode/mpeg2.py` (`PULLDOWN_VERSION = 1`),
`docker-compose.yml`, `.env.example`; Create `src/projeto_dvd/jobs/cache.py`; Test
`tests/unit/test_calculator.py`, `tests/unit/test_cache.py`, `tests/unit/test_disc_build.py`.

**Interfaces (produces):**

```python
# calculator.py
MENU_RESERVE_PAGES = 20
def menu_bytes(pages: int) -> int  # max(pages, MENU_RESERVE_PAGES) * MENU_PAGE_BYTES
# estimate_disc usa menu_bytes(menu_pages)

# config.py
cache_limit_gb: float = Field(default=50, ge=0)

# jobs/cache.py
NAME = re.compile(r"^[0-9a-f]{64}\.(m2v|json)$")
def cache_dir(work_dir: Path) -> Path                    # work_dir / "cache"
def cache_key(disc: DiscPlan, number: int, ffmpeg_version: str | None) -> str
def lookup(work_dir: Path, key: str, target: Path) -> RunResult | None
def store(work_dir: Path, key: str, m2v: Path, pass2: RunResult) -> None   # OSError propaga
def cache_bytes(work_dir: Path) -> int
def evict(work_dir: Path, limit_bytes: int, keep: Collection[str]) -> int  # apaga; devolve bytes apagados
def clean(work_dir: Path) -> int                          # só nomes válidos, sem seguir links
def plan_keys(disc: DiscPlan, ffmpeg_version: str | None) -> list[str]   # títulos recodificados
```

`cache_key`: sha256 de `json.dumps({"source": [path, size, mtime_ns], "command":
video_pass_command(disc, n, Path("/media") / path, Path("/job"), 2), "pulldown":
PULLDOWN_VERSION, "ffmpeg": ffmpeg_version}, sort_keys=True)`. `lookup`: exige `.m2v` e `.json`,
tamanho igual ao do JSON; `target.unlink(missing_ok=True)`; `os.link`; `os.utime`; devolve
`RunResult(progress_do_json, "")`; qualquer `OSError` ou JSON inválido devolve `None`.
`store`: `os.link(m2v, <key>.m2v)` (ignora se já existe) e grava o JSON `{"size": ..., "progress":
{frame, dup_frames, drop_frames, out_time_us}}`. `evict`: soma `.m2v`, apaga pelos `mtime` mais
antigos (o par `.m2v`/`.json`) até ficar ≤ limite, pulando `keep`; `limit_bytes == 0` apaga tudo
fora de `keep`.

- [ ] **Step 1:** testes: `menu_bytes(3) == 20 * MiB*2`, `menu_bytes(25) == 25*2 MiB`; estimate de
  um disco com 3 e com 10 páginas dá o mesmo `video_kbps`; `maxrate` ignora títulos copiados (fica
  para a Task 4: aqui só a reserva); chave muda com bitrate, `mtime_ns`, versão do ffmpeg,
  `PULLDOWN_VERSION` e filtro (aspecto), e não muda com o menu, a ordem de outros títulos, os
  capítulos e o `job_dir`; `store` + `lookup` devolvem o progress e um hard link (`st_nlink == 2`);
  `lookup` com tamanho errado, sem JSON, JSON inválido → `None`; `evict` apaga o mais antigo
  (`os.utime`), respeita `keep`, `limit 0`; `clean` apaga só nomes válidos (link simbólico e
  `notas.txt` ficam); `cache_bytes`; `Settings(cache_limit_gb=-1)` recusa.
- [ ] **Step 2:** FAIL. **Step 3:** implementar. **Step 4:** PASS + suíte + lint.
- [ ] **Step 5:** commit `feat: add the encoded video cache`.

### Task 2: pipeline com o cache

**Files:** Modify `src/projeto_dvd/jobs/pipeline.py`, `src/projeto_dvd/jobs/worker.py`,
`src/projeto_dvd/encode/mpeg2.py`; Test `tests/unit/test_pipeline.py`, `tests/unit/test_worker.py`.

**Interfaces:**
- `run_pipeline(..., cache: CacheUse | None = None)` com
  `@dataclass(frozen=True) class CacheUse: work_dir: Path; limit_bytes: int; ffmpeg: str | None`
  (`None` ou `limit_bytes == 0`: sem cache).
- `_encode_title`: `m2v.unlink(missing_ok=True)`; se `cache` e `lookup(...)` devolve `RunResult`,
  usa como `pass2`, escreve "vídeo reaproveitado do cache" no log (via `tools.log`? não existe:
  usa `report(Step.VIDEO_PASS2, 1.0, n)` e o runner já registra comandos; o texto vai num
  `job_dir/job.log` com `_note(job_dir, texto)` que faz append), pula passadas e pulldown;
  senão passadas + pulldown + `store` (OSError → `_note`) + `evict(work_dir, limit, keep=plan_keys)`.
- `apply_soft_pulldown` levanta `PulldownError` se `path.stat().st_nlink > 1`.
- Worker: `Worker.cache_use()` monta `CacheUse` com `settings.work_dir`,
  `int(settings.cache_limit_gb * GIB)` e `detect_versions().get("ffmpeg")`; no início de cada job
  `evict(... keep=plan_keys(plan))`; em `QaFailed` apaga as entradas de `plan_keys(plan)`
  (`purge(work_dir, keys)` em `cache.py`); escreve "Início em <iso>" no `job.log` ao pegar o job.
  Mensagens `RESTARTED`/`STOPPED` com "Use Retomar.".
- `preflight`: com cache ligado, `3 × estimated + GiB` na pasta de trabalho (parâmetro
  `cache_on: bool`).

- [ ] **Step 1:** testes: dois `run_pipeline` seguidos com o mesmo `work_dir` de cache: o segundo não
  roda nenhum comando com `-pass`, não chama o pulldown e a QA passa (o `progress` do JSON);
  um `title1.m2v` que é hard link do cache e sobrou na pasta do job é desligado antes (o arquivo do
  cache fica com o conteúdo original); `apply_soft_pulldown` recusa `st_nlink > 1`; `store` com
  `OSError` não derruba o job; o worker apaga o cache do plano em `QaFailed`, despeja no início e
  anota "Início em"; preflight pede 3× com cache.
- [ ] **Step 2–4** como de costume. **Step 5:** commit `feat: reuse encoded video from the cache`.

### Task 3: Retomar e a tela do cache

**Files:** Modify `src/projeto_dvd/jobs/store.py`, `src/projeto_dvd/api/jobs.py`,
`web/templates/_job_status.html`, `jobs.html`; Test `tests/unit/test_store.py`,
`tests/unit/test_job_routes.py`.

**Interfaces:**
- `store.resume(engine, job_id) -> bool` (o `UPDATE` atômico da spec; `IntegrityError` → levanta
  `ActiveJobError(id_ativo)`); `False` se o estado não permitia.
- `POST /jobs/{job_id}/resume` (`resume_job`): só se é o `latest_job` da pasta, `failed|canceled`
  e `plan.menu` não nulo (senão 409); roda `preflight(...)` (com `cache_on`), em erro devolve o
  `_job_status.html` com os erros num banner; senão `clean_job_dir`, `store.resume`, e devolve o
  status (que passa a fazer polling). `ActiveJobError` → banner com link para o job ativo.
- `JobView.can_resume: bool`; botão "Retomar" no `_job_status.html` ao lado de "Gerar de novo".
- `GET /jobs` mostra `cache_bytes(work_dir)` e o limite; `POST /cache/clean` (`clean_cache`):
  409 com job ativo; senão `cache.clean` e redireciona para `/jobs`.

- [ ] **Step 1:** testes: resume de `failed`, `canceled` (campos limpos, `created_at` novo, status
  `queued`), recusa de `done`/`running`, de job que não é o último, de plano sem menu; preflight
  com ISO existente recusa com a mensagem; colisão com job ativo; a pasta do job fica só com o log;
  a tela mostra "Retomar" só quando pode; cache na lista de jobs; limpar com job ativo dá 409,
  sem job apaga só nomes válidos; cross-site 403.
- [ ] **Step 2–4.** **Step 5:** commit `feat: resume a job and clean the cache`.

### Task 4: rip copiável no plano e na calculadora

**Files:** Modify `src/projeto_dvd/library/probe.py` (`Video.stream_bytes: int | None`,
`Video.dvd_header: tuple[int, int] | None` = (max_bitrate, buffer_size) do "CPB properties"),
`planner/source.py` (frame scan com `key_frame`; `max_gop_fields(frames) -> int`),
`planner/disc_plan.py` (`TitlePlan.copy_video: bool = False`, `video_bytes: int | None = None`;
`DiscChoices.reencode_rips: bool = False`), `planner/calculator.py` (`TitleLoad.video_bytes`),
`planner/disc_build.py`, `planner/disc.py` (`copy_reason(title, choices) -> str | None`),
`api/dvd.py` + templates (badge, caixa, cartão, nota de capítulos), `planner/disc_source.py`;
Test respectivos.

**Interfaces:**
- `copy_reason(title, choices) -> str | None` (None = copiável); motivos em português:
  "não é vídeo de DVD", "as faixas escolhidas pedem mais espaço que o disco original",
  "tamanho do vídeo desconhecido", "Recodificar os rips está marcado".
- `video_size(title) -> int | None`: `stream_bytes` válido, senão arquivo − Σ(`bit_rate` × duração)
  do áudio (None se algum áudio não tiver `bit_rate` e não houver tag).
- `title_plan` define `copy_video`/`video_bytes`; para título copiado os capítulos são os do
  arquivo (`plan_chapters(..., "file", ...)` com fallback só no início).
- `estimate_disc`: copiados reservados, bitrate sobre os recodificados, `maxrate` só deles; sem
  recodificado → `video_kbps = maxrate = 0`, "Ótima" ou "Não cabe".
- `prepare_title` (frame scan) devolve também `max_gop_fields`; `build_disc_plan` recebe
  `long_gop: set[str]` (caminhos acima de 36 campos) e recodifica esses.

- [ ] **Step 1:** testes de cada regra de `copy_reason`, do probe (tags `NUMBER_OF_BYTES-eng`,
  side data), de `video_size`, de `max_gop_fields` (15 quadros com pulldown = 37/38), de
  `estimate_disc` (só cópias, misto, não cabe), de `title_plan` (capítulos do arquivo), da tela
  (badge, caixa, "Não cabe com o vídeo copiado"), e do `create_dvd` recodificando um rip com GOP
  longo na amostra.
- [ ] **Step 2–4.** **Step 5:** commit `feat: plan DVD rips as copied video`.

### Task 5: pipeline e QA do título copiado

**Files:** Modify `src/projeto_dvd/encode/mpeg2.py` (`StreamReport`: `max_gop_fields`, `gops:
list[tuple[float, bool]]` (início em segundos, fechado), `headers_per_gop_ok: bool`,
`first_gop_closed: bool`), `jobs/pipeline.py` (`Step.VIDEO_COPY`, `copy_command`, conferência
imediata, `chapters_on_closed_gops`, underflow no mux, `sha256`), `authoring/dvd/dvdauthor.py`
(capítulos ajustados por título), `authoring/dvd/qa.py` (`copied_checks`), `api/jobs.py`
(`_title_steps` com `VIDEO_COPY`); Test `test_mpeg2.py`, `test_pipeline.py`, `test_qa.py`,
`test_menu_authoring.py`, `test_job_routes.py`.

**Interfaces:**
- `copy_command(source: Path, video_index: int, output: Path) -> list[str]`
- `chapters_on_closed_gops(chapters: tuple[float, ...], gops: list[tuple[float, bool]], limit=1.0)
  -> tuple[tuple[float, ...], list[float]]` (capítulos, descartados)
- `disc_xml(plan, job_dir, chapters: Mapping[int, tuple[float, ...]] | None = None)`
- `copied_checks(report_iso: StreamReport, report_source: StreamReport, same: bool, cells_ok: bool)
  -> list[Check]`

- [ ] **Step 1:** testes do leitor (GOP aberto/fechado, tempos com RFF, headers por GOP), de
  `chapters_on_closed_gops`, do pipeline com um título copiado (sem passadas nem pulldown, etapa
  `VIDEO_COPY`, conferência imediata recusando aspecto misto, primeiro GOP aberto, GOP > 36 campos,
  arquivo maior que `video_bytes` + 1%; underflow no mux falha com a mensagem), da QA copiada
  (`same_video`, `fields` com aviso, `gop`), do XML com os capítulos ajustados, da tela do job com a
  etapa.
- [ ] **Step 2–4.** **Step 5:** commit `feat: copy the video of DVD rips`.

### Task 6: testes `slow`, documentação e smoke

**Files:** `tests/integration/test_dvd.py`, `tests/integration/clips.py`, README (EN/pt-BR),
CLAUDE.md, `.github/workflows/ci.yml` (se precisar).

- [ ] **Step 1:** `slow`: mesmo disco duas vezes (a segunda sem `-pass` no log, QA ok); cancelar no
  `VIDEO_PASS1` do título 2 e rodar de novo com o mesmo cache (título 1 do cache, QA ok); rip
  estilo DVD (GOP aberto de 12, pulldown, capítulos no meio de GOP) copiado, com e sem
  `NUMBER_OF_BYTES-eng`, ISO com vídeo idêntico (`framemd5`) e capítulos em GOP fechado; leitura do
  "CPB properties" de um `.m2v` de referência.
- [ ] **Step 2:** `make test-slow` (todos) verde; docs; smoke compose (gerar duas vezes e ver o
  reaproveitamento no log).
- [ ] **Step 3:** commit `test: cover the cache, resume and DVD rip copy` e `docs: document resume,
  the cache and DVD rip copy`; revisão final; PR.

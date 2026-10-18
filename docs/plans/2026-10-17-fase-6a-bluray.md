# Fase 6a: Blu-ray de um título, sem menu (plano de implementação)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uma pasta com um vídeo HD vira um ISO de Blu-ray (BD-25 ou BD-50) sem menu, com o
vídeo do remux copiado ou recodificado pelo x264 em modo Blu-ray, conferido por uma QA que lê o
ISO pela libbluray.

**Architecture:** o meio sai do perfil (`PROFILES[key].medium`), sem campo novo em plano ou
escolha. O planejamento reaproveita `DiscChoices`, `DiscPlan` e `TitlePlan`; o job do Blu-ray é
um módulo próprio (`jobs/bluray.py`) que importa as peças comuns do `pipeline.py`. Comandos,
`.meta` e checagens são funções puras; só o wrapper ctypes da libbluray/libudfread depende das
bibliotecas da imagem.

**Tech Stack:** Python 3.12, FastAPI + HTMX, SQLModel, ffmpeg 7.1 + libx264, tsMuxeR 2.7.0,
libbluray 1.3 e libudfread (ctypes), pytest.

**Spec:** `docs/plans/2026-10-17-fase-6a-bluray-design.md` (aprovada).

## Global Constraints

- Conversa em português; código, commits e docstrings em inglês; **sem travessão** em nada.
- Conventional Commits terminando com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `make lint` (ruff, format, mypy strict) e `make test` (100% de cobertura) verdes em cada task;
  conferir o código de saída (`make lint >/dev/null 2>&1; echo $?`), nunca por `| tail`.
- Nunca chamar o TMDB real; nunca commitar mídia, ISO, artes ou `.env`; o HD é só leitura.
- Meio: `PROFILES[profile].medium`; **nenhum campo novo** em `DiscPlan`/`DiscChoices`; o único
  campo novo de plano é `SubtitleChoice.codec`; jobs e projetos antigos continuam válidos.
- Um título por disco Blu-ray; perfis BD só para pasta com um vídeo aceito pelo Blu-ray.
- x264 exatamente com os parâmetros da spec (seção Vídeo); tsMuxeR recebe `.h264` Annex B, sem
  `insertSEI` e sem `contSPS`; `--label` ASCII até 30 caracteres; SRT sem BOM e com linha em
  branco no fim.
- O job reprova se a saída do tsMuxeR tiver `Warning`, `bad frame`, `Invalid` ou `Can't`.
- Perfis BD: setores 12.219.392 e 24.438.784, margem 0,97, reserva 64 MiB, sobrecarga 6%,
  vídeo máximo 35.000, mux 48.000, pico PGS 500 kbps, verde 15.000, amarelo 8.000, não cabe
  abaixo de 3.000.

## Review Focus

1. Pasta com um vídeo HD e escolha salva em BD que ganha um segundo vídeo: a tela abre na
   sugestão, sem erro (Task 4).
2. Áudio com atraso na origem (MKV com `start_time` do áudio 0,5 s): o disco sai alinhado
   (Task 5, e o `slow` da Task 10).
3. Nome de pasta só com acentos ou símbolos: o rótulo do volume vira "DISC", o ISO sai (Task 6).
4. tsMuxeR que sai com 0 mas escreve "Warning": o job falha com a mensagem na tela, sem publicar
   o ISO (Task 8).
5. Job de Blu-ray cancelado no meio: "Retomar" aparece e o job volta à fila (Task 8).

---

### Task 1: perfis BD, calculadora e sugestão

**Files:** Modify `planner/profiles.py`, `planner/calculator.py`; Test
`tests/unit/test_profiles.py`, `tests/unit/test_calculator.py`.

**Interfaces:**

```python
Medium = Literal["dvd", "bluray"]

@dataclass(frozen=True)
class DiscProfile:          # campos novos, com os valores do DVD por padrão
    medium: Medium = "dvd"
    pack_overhead_kbps: int = 300      # BD: 2717 = 48000 × 0,06 / 1,06
    subtitle_peak_kbps: int = 40       # BD: 500
    # good_kbps, acceptable_kbps, min_kbps, max_video_kbps, mux_rate_kbps já existem

BD25 = DiscProfile(key="bd25", name="BD-25", description="camada única, 25 GB",
                   sectors=12_219_392, medium="bluray", reserve_bytes=64 * MIB,
                   mux_overhead=0.06, good_kbps=15_000, acceptable_kbps=8_000,
                   min_kbps=3_000, max_video_kbps=35_000, mux_rate_kbps=48_000,
                   pack_overhead_kbps=2_717, subtitle_peak_kbps=500)
BD50 = ...  # o mesmo com sectors=24_438_784, "dupla camada, 50 GB"
PROFILES = {p.key: p for p in (DVD5, DVD9, BD25, BD50)}

def suggest_profile(estimates: Sequence[Estimate], hd: bool = False) -> DiscProfile
```

- `maxrate_kbps` usa os campos do perfil (`pack_overhead_kbps`, `subtitle_peak_kbps`): a fórmula
  do DVD não muda de valor.
- `suggest_profile(..., hd=True)`: o primeiro perfil **Blu-ray** com qualidade ótima; se nenhum
  BD for ótimo, o maior BD que cabe; sem BD na lista, a regra de hoje.

- [ ] **Step 1:** testes: valores dos perfis BD (`capacity_bytes` 25.025.314.816 e
  50.050.629.632); `maxrate` do BD com 640k de AC-3 e 2 PGS = `min(35000, 48000 − 640 − 1000 −
  2717)`; maxrate do DVD igual ao de antes (teste existente continua verde); faixas de
  qualidade do BD (15.000 ótima, 10.000 aceitável, 5.000 baixa, 2.000 não cabe); sugestão HD
  (BD-25 ótimo sugerido mesmo com DVD-9 ótimo; nenhum BD ótimo: o BD-50); sem `hd`, igual a hoje.
- [ ] **Step 2:** rodar e ver falhar. **Step 3:** implementar. **Step 4:** suíte inteira e lint.
- [ ] **Step 5:** commit `feat: add the BD-25 and BD-50 profiles to the calculator`.

### Task 2: probe e origem do Blu-ray

**Files:** Modify `library/probe.py`, `planner/source.py`; Create `planner/bd_source.py`; Test
`tests/unit/test_probe.py`, `tests/unit/test_source.py`, `tests/unit/test_bd_source.py`.

**Interfaces:**

```python
# library/probe.py: campos novos com padrão (JSONs antigos continuam lendo)
class Video:      profile: str | None = None; level: int | None = None
                  pix_fmt: str | None = None; sar: Fraction | None = None
class AudioTrack: profile: str | None = None   # "DTS-HD MA", "DTS"...
                  bits: int | None = None      # bits_per_raw_sample ou do sample_fmt

# planner/source.py
def check_video(summary: Summary, medium: Medium = "dvd") -> SourceCheck
BD_SD = "O vídeo é SD (até 576 linhas): use DVD."   # e os outros motivos em português

# planner/bd_source.py
@dataclass(frozen=True)
class HeaderReport:
    hrd: bool
    slices: int              # slices por quadro (first_mb_in_slice == 0 conta um quadro)
    max_dec_frame_buffering: int | None

def trace_headers_command(path: Path, video_index: int, seconds: int = 3) -> list[str]
def parse_trace_headers(stderr: str) -> HeaderReport
def bd_frame(video: Video) -> tuple[int, int, bool] | None   # (largura, altura, escala) ou None
def bd_copy_reason(title: DiscTitle, choices: DiscChoices,
                   headers: HeaderReport | None, gop_frames: int | None) -> str | None
```

- `check_video(summary, "bluray")`: aceita 1920x1080, 1920x(< 1080), 1440x1080 SAR 4:3,
  1280x720 (e menores que caibam em 1280x720 com pad); 23,976 progressivo; SDR; recusa acima de
  1080p, HDR, 24 exato, 25/50, 29,97, 59,94, entrelaçado, VFR, altura ≤ 576 (`BD_SD`). O DVD
  continua idêntico (testes existentes verdes).
- `bd_frame`: 1920x1080 SAR 1:1 → (1920, 1080, False); 1920x800 → (1920, 1080, False) com pad;
  1440x1080 SAR 4:3 → (1920, 1080, True); 1280x720 → (1280, 720, False).
- `bd_copy_reason` (None = copia): H.264, perfil High ou Main, level ≤ 41, `yuv420p`, 23,976,
  1920x1080 SAR 1:1 ou 1440x1080 SAR 4:3, `headers.hrd`, `headers.slices >= 4`,
  `max_dec_frame_buffering ≤ 4`, `gop_frames ≤ 24`, `video.stream_bytes` ou tamanho estimável,
  `choices.reencode_rips` falso. Cada falha com o motivo curto ("recodificado: sem HRD").
  `headers`/`gop_frames` `None` (a tela não roda a amostra): as condições deles contam como
  "a conferir ao gerar" e a tela mostra "vídeo copiado do Blu-ray (conferido ao gerar)".

- [ ] **Step 1:** testes: probe lê `profile`, `level`, `pix_fmt`, `sample_aspect_ratio` e o
  `profile`/bits do áudio, e um JSON antigo sem eles; cada recusa e cada aceite do
  `check_video` Blu-ray; `bd_frame` nos 4 casos; `parse_trace_headers` com um trecho de stderr
  inventado no formato do `trace_headers` (HRD 1/0, 4 slices/1 slice, dpb); `bd_copy_reason` com
  cada condição falhando sozinha e com tudo certo.
- [ ] **Step 2–4.** **Step 5:** commit `feat: check sources and copy rules for Blu-ray`.

### Task 3: faixas por meio

**Files:** Modify `planner/dvd_plan.py`, `planner/disc.py`; Test `tests/unit/test_dvd_plan.py`,
`tests/unit/test_disc.py`.

**Interfaces:**

```python
def bd_audio_output(track: AudioTrack) -> AudioOutput   # action "copy" ou "ac3"
def subtitle_options(summary, external, medium: Medium = "dvd") -> list[SubtitleOption]
class SubtitleChoice(BaseModel): codec: Literal["text", "pgs"] = "text"
def best_audio(title: DiscTitle, language: str, medium: Medium = "dvd") -> AudioTrack | None
def audio_languages(titles, medium="dvd"); subtitle_languages(titles, medium="dvd")
def reconcile(saved, titles, suggestion, backdrops) -> DiscChoices  # usa o meio do perfil salvo
```

- `bd_audio_output`: copia AC-3 ≤ 640k a 48 kHz (kbps = bit_rate, ou 640), DTS core (kbps =
  bit_rate, ou 1536), DTS-HD MA/HRA (kbps = canais × bits × 48), LPCM 16/24 bits (canais × bits
  × 48); converte o resto para AC-3 (640k de 3 a 6 canais com `downmix=6` acima de 6; 256k
  estéreo; 128k mono). TrueHD sempre converte.
- `best_audio(..., "bluray")`: entre as faixas do idioma, prefere as que o `bd_audio_output`
  copia (TrueHD com irmã AC-3 escolhe a AC-3), depois mais canais, sem comentário.
- `subtitle_options(..., "bluray")`: `hdmv_pgs_subtitle` é suportado; o resto igual ao DVD.
- `reconcile`: o meio vem de `PROFILES[saved.profile].medium` e as listas de idiomas usam esse
  meio; perfil salvo que não existe mais, ou BD quando a pasta não é elegível (Task 4 dá
  `bd_eligible`), volta à sugestão.

- [ ] **Step 1:** testes de cada linha da regra de áudio (inclusive DTS-HD 7.1 24 bits = 9216
  kbps e TrueHD → AC-3 640k); `best_audio` BD com TrueHD + AC-3 irmã; PGS suportado só no BD;
  `subtitle_languages` por meio; `SubtitleChoice` antiga sem `codec` continua lendo.
- [ ] **Step 2–4.** **Step 5:** commit `feat: choose Blu-ray audio and subtitle tracks`.

### Task 4: plano do disco por meio

**Files:** Modify `planner/disc_build.py`, `planner/disc.py`, `planner/disc_source.py`,
`planner/dvd_plan.py` (`volume_name`, `plan_chapters`); Test `tests/unit/test_disc_build.py`,
`tests/unit/test_disc.py`.

**Interfaces:**

```python
def medium_of(profile_key: str) -> Medium                  # planner/profiles.py
def bd_eligible(titles: Sequence[DiscTitle]) -> str | None # motivo, ou None quando o BD vale
BD_ONE_TITLE = "Blu-ray: um título por disco nesta fase."
def plan_chapters(source, duration, mode, minutes, max_chapters: int = MAX_CHAPTERS)
def bd_volume_label(folder: str) -> str                    # ASCII, até 30, "DISC" se vazio
def iso_name(folder: str, medium: Medium) -> str           # "<pasta>.iso" ou "<pasta> (BD).iso"
```

- `title_plan` com perfil BD: `mode=FILM`, `top_field_first=True`, `aspect="16:9"`;
  `width/height/scale` de `bd_frame`; `copy_video` pela `bd_copy_reason` (com `headers` e
  `gop_frames` vindos do `TitleSource`, que ganha `headers: HeaderReport | None = None`);
  áudio por `bd_audio_output` e `best_audio(..., "bluray")`, e a regra do atraso: faixa
  copiada de AC-3, DTS ou DTS-HD com `|offset| > 0,032` vira `ac3` 640k (LPCM continua cópia,
  com o silêncio no início na extração); legendas com `codec` ("pgs" para
  `hdmv_pgs_subtitle`, "text" para o resto); capítulos com `max_chapters=999`.
- `build_disc_plan` com BD: `menu=None`, `volume=bd_volume_label(folder)`,
  `iso_name=iso_name(folder, "bluray")`, `maxrate` e bitrate da calculadora com o perfil BD.
- `disc_estimates`: perfis BD só quando `bd_eligible(titles) is None`; `menu_plan` não é
  chamado para BD (0 páginas). `profile_for` passa `hd = altura > 576 and bd_eligible is None`.
- `bd_eligible`: `BD_ONE_TITLE` com mais de um vídeo; senão o primeiro motivo do
  `check_video(..., "bluray")` com o prefixo "Blu-ray: ".
- `prepare_titles` (api/dvd.py) para BD roda a amostra de quadros (GOP) e o `trace_headers`
  só quando a cópia é possível pelo resto das regras.

- [ ] **Step 1:** testes: plano BD de um remux copiado (copy_video, video_bytes, sem menu,
  rótulo, nome do ISO), de um WEB-DL recodificado (pad 1920x800, alvo e maxrate), de 1440x1080
  copiado e recodificado (escala), de 720p; `bd_eligible` com 2 vídeos e com SD; estimativas sem
  BD para pasta não elegível; sugestão HD; `bd_volume_label("O Senhor dos Anéis: A Sociedade do
  Anel")` = `"O Senhor dos Aneis A Sociedade"` (sem pontuação, até 30), `"ÉÇ!"` → `"EC"`, `"!!"`
  → `"DISC"`; capítulos acima de 99 no BD; reconcile de BD salvo numa pasta que ganhou um vídeo
  volta à sugestão.
- [ ] **Step 2–4.** **Step 5:** commit `feat: plan a Blu-ray disc from the saved choices`.

### Task 5: comandos do encode e das extrações

**Files:** Create `encode/x264.py`, `encode/bd_extract.py`; Modify `jobs/cache.py`; Test
`tests/unit/test_x264.py`, `tests/unit/test_bd_extract.py`, `tests/unit/test_cache.py`.

**Interfaces:**

```python
# encode/x264.py
X264_PARAMS = ("bluray-compat=1:keyint=24:min-keyint=1:slices=4:b-pyramid=strict:open-gop=0:"
               "nal-hrd=vbr:aud=1:colorprim=bt709:transfer=bt709:colormatrix=bt709")
def x264_pass_command(source: Path, title: TitlePlan, target_kbps: int, maxrate_kbps: int,
                      pass_number: int, passlog: Path, out: Path) -> list[str]

# encode/bd_extract.py
def h264_copy_command(source: Path, video_index: int, out: Path) -> list[str]
def audio_es_command(source: Path, choice: AudioChoice, out: Path) -> list[str]
def audio_suffix(choice: AudioChoice, codec: str) -> str   # ".ac3", ".dts", ".wav"
def sup_command(source: Path, stream_index: int, out: Path) -> list[str]
def srt_command(source: Path, stream_index: int, out: Path) -> list[str]
def normalize_srt(data: bytes) -> bytes                     # sem BOM, CRLF → LF, termina "\n\n"

# jobs/cache.py
VIDEO_SUFFIX = {"dvd": ".m2v", "bluray": ".h264"}
```

- `x264_pass_command`: `ffmpeg -nostdin -y -i <src> -map 0:<v> -an -sn` + o filtro de geometria
  (pad `pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black` quando a altura é menor; `scale=1920:1080:
  flags=lanczos,setsar=1` quando `scale`; nada no 720p) + os argumentos da spec, `-pass N
  -passlogfile <passlog>`, `-progress pipe:1`; o pass 1 sai em `-f null -`.
- `audio_es_command`: copy → `-c:a copy` para o ES (`-f ac3`, `-f dts`, `-f wav` com
  `pcm_s24le`/`s16le` conforme os bits); LPCM com atraso: `-af adelay=<ms>:all=1`; ac3 →
  `-c:a ac3 -b:a <kbps>k` (+ `-ac <downmix>`) e `adelay` quando há atraso; sempre `-t` igual à
  duração do vídeo (o áudio não passa do filme).
- A regra do atraso é decidida no `title_plan` (Task 4); esta task só monta o comando conforme a
  `action` e o `offset` da faixa.
- `cache_key`/`plan_keys` escolhem o construtor de comando pelo meio (`x264_pass_command` com
  pass 2 no BD); `NAME` aceita `m2v|h264|json`; `_entries`, `cache_bytes` e `evict` contam os
  dois vídeos.

- [ ] **Step 1:** testes comparando listas de argumentos (pass 1 e 2, pad, escala, 720p,
  `-pix_fmt yuv420p` sempre, `vbv` fora do `-x264-params`); comandos de extração (cada formato,
  atraso, downmix, `-t`); `normalize_srt` (BOM, CRLF, sem linha final, já certo); cache com
  `.h264` (lookup, store, contagem, despejo misto).
- [ ] **Step 2–4.** **Step 5:** commit `feat: build the x264 and extraction commands for Blu-ray`.

### Task 6: tsMuxeR

**Files:** Create `authoring/bluray/__init__.py`, `authoring/bluray/meta.py`; Test
`tests/unit/test_bd_meta.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class BdInputs:
    video: Path
    audio: tuple[Path, ...]        # na ordem do plano
    subtitles: tuple[Path, ...]

def iso_639_2(code: str | None) -> str                  # "pt" → "por", None/und → "und"
def chapters_text(starts: Sequence[float]) -> str       # "00:00:00.000;00:05:00.000"
def bd_meta(plan: DiscPlan, inputs: BdInputs) -> str
def tsmuxer_command(meta: Path, iso: Path) -> list[str] # ["tsMuxeR", meta, iso]
def tsmuxer_progress(line: str) -> float | None         # "45.3% complete" → 0.453
def tsmuxer_problem(output: str) -> str | None          # a 1ª linha com Warning/bad frame/...
```

- `bd_meta`: `MUXOPT --blu-ray --vbr --label="<volume>" --custom-chapters=<capítulos>`; a linha
  `V_MPEG4/ISO/AVC, "<video>", fps=23.976`; uma linha por áudio (`A_AC3`, `A_DTS`, `A_LPCM`
  pelo sufixo) com `lang=` e `default` na primeira faixa (a que toca primeiro); PGS
  `S_HDMV/PGS`; texto `S_TEXT/UTF8` com `font-name="DejaVu Sans", font-size=58, font-border=4,
  bottom-offset=108, video-width=1920, video-height=1080, fps=23.976` (720p: 1280, 720, 39, 72)
  e `default=all` na legenda ligada (`plan.subtitle_on`). Linhas separadas por `\n`, terminando
  em `\n`.
- `tsmuxer_problem`: casa `Warning`, `bad frame`, `Invalid`, `Can't` (sem diferenciar maiúscula),
  ignorando as linhas normais de progresso.

- [ ] **Step 1:** testes: o `.meta` inteiro comparado como texto para (a) remux com AC-3, DTS-HD
  e PGS, legenda ligada; (b) 720p com SRT e LPCM, sem legenda ligada; `chapters_text`;
  `iso_639_2`; progresso; problema (Warning, bad frame, saída limpa → None).
- [ ] **Step 2–4.** **Step 5:** commit `feat: write the tsMuxeR meta for a Blu-ray disc`.

### Task 7: QA do Blu-ray

**Files:** Create `authoring/bluray/libs.py` (ctypes), `authoring/bluray/qa.py` (puro); Modify
`pyproject.toml` (`[tool.coverage.run] omit` só para `authoring/bluray/libs.py`); Test
`tests/unit/test_bd_qa.py`, `tests/integration/test_bluray_libs.py` (`slow`).

**Interfaces:**

```python
# libs.py (ctypes; argtypes e restype em todas as funções; testado nos slow)
@dataclass(frozen=True)
class BdStream: coding_type: int; format: int; rate: int; language: str
@dataclass(frozen=True)
class BdInfo:
    detected: bool; first_play: bool
    duration: float                       # da playlist 0, em segundos (ticks de 90 kHz)
    chapters: tuple[float, ...]
    video: tuple[BdStream, ...]; audio: tuple[BdStream, ...]; pg: tuple[BdStream, ...]
def bd_info(iso: Path) -> BdInfo                     # libbluray.so.2
def udf_tree(iso: Path) -> tuple[str, ...]           # libudfread.so.0, caminhos completos
def udf_copy(iso: Path, inner: str, out: IO[bytes]) -> None   # lê o m2ts em blocos

# qa.py (puro)
REQUIRED = ("/BDMV/index.bdmv", "/BDMV/MovieObject.bdmv", "/BDMV/PLAYLIST/00000.mpls",
            "/BDMV/CLIPINF/00000.clpi", "/BDMV/STREAM/00000.m2ts",
            "/BDMV/BACKUP/index.bdmv", "/CERTIFICATE/id.bdmv")
def tree_checks(paths: Sequence[str]) -> list[Check]
def info_checks(info: BdInfo, plan: DiscPlan) -> list[Check]
def coverage_checks(probe_json: str, plan: DiscPlan) -> list[Check]   # pts de cada faixa
def es_check(disc_sha256: str, delivered_sha256: str) -> Check
```

- `info_checks`: detectado e `first_play`; duração = vídeo (±1 quadro, 1001/24000); capítulos =
  plano (±1 quadro); vídeo `0x1b`; cada áudio na ordem com o tipo (`0x81` AC-3, `0x82` DTS,
  `0x86` DTS-HD MA, `0x80` LPCM) e o idioma ISO 639-2; cada PG `0x90` com o idioma.
- `coverage_checks`: com o JSON do `ffprobe -show_entries stream=index,codec_type,start_time,
  duration` (ou os pacotes primeiro/último) do m2ts lido por pipe, cada faixa começa até 0,1 s e
  termina até 0,5 s da duração do vídeo; PGS só confere o início ≥ 0.
- `size_checks` da QA do DVD é reaproveitado (tornado público se ainda não for).
- Cobertura: `libs.py` fora do `--cov` (as bibliotecas só existem na imagem); o resto 100%.

- [ ] **Step 1:** testes unitários de `qa.py` com `BdInfo` inventado (cada checagem passa e
  falha); `slow` do `libs.py` num ISO feito na hora pelo tsMuxeR (clipe lavfi + AC-3): árvore,
  duração, capítulos, faixas, `udf_copy` com o tamanho certo.
- [ ] **Step 2–4.** **Step 5:** commit `feat: check a Blu-ray ISO through libbluray`.

### Task 8: job do Blu-ray

**Files:** Create `jobs/bluray.py`; Modify `jobs/pipeline.py` (nomes públicos, `steps_for`,
`OLD_PLAN` só no DVD), `jobs/worker.py`, `api/jobs.py` (`_can_resume`, etapas),
`api/formatting.py` (`ENCODE_SECONDS_PER_SECOND` por meio); Test `tests/unit/test_bluray_job.py`,
`tests/unit/test_pipeline.py`, `tests/unit/test_worker.py`, `tests/unit/test_job_routes.py`.

**Interfaces:**

```python
# pipeline.py
def steps_for(plan: DiscPlan) -> tuple[tuple[Step, ...], tuple[Step, ...]]  # (título, disco)
def overall_progress(plan, step, fraction, title) -> float    # usa steps_for
check_source, tool_step, publish, note, preflight              # antes com "_"

# bluray.py
BD_TITLE_STEPS = (Step.VIDEO_COPY, Step.VIDEO_PASS1, Step.VIDEO_PASS2, Step.AUDIO,
                  Step.SUBTITLES)
BD_DISC_STEPS = (Step.ISO, Step.QA, Step.COPY)
TSMUXER_FAILED = "O tsMuxeR avisou um problema no disco: {line}"
def run_bluray(plan: DiscPlan, *, media_dir, job_dir, output_dir, tools, report,
               should_cancel, cache: CacheUse | None = None) -> PipelineResult
```

- Fluxo: checa a origem; vídeo (cópia: `h264_copy_command`, sha256 do `.h264`; encode: 2
  passes com cache); áudio (`audio_es_command` por faixa); legendas (`.sup` ou `.srt`
  normalizado); `.meta` e tsMuxeR com progresso; `tsmuxer_problem` na saída → `PipelineError`
  na etapa ISO; QA (`size_checks`, `tree_checks`, `info_checks`, `coverage_checks`, `es_check`
  com o sha256 do ES extraído do m2ts por `udf_copy` + `ffmpeg -i pipe: -map 0:v -c copy -f
  h264`); publica com `publish`. Apaga cada intermediário quando a etapa seguinte não precisa
  mais.
- Rótulo de `Step.VIDEO_COPY` vira "Vídeo copiado da origem"; `Step.ISO` no BD mostra
  "Montando o Blu-ray (tsMuxeR)".
- Worker: `run = run_bluray if medium_of(plan.profile) == "bluray" else run_pipeline`.
- `OLD_PLAN`, `_can_resume` e a etapa MENUS: "DVD e `menu is None`".
- Tempo: BD ×1,0 (encode) e ×0,02 (cópia) da duração.

- [ ] **Step 1:** testes com `Tools` falso (como os do `pipeline.py`): remux copiado (comandos
  na ordem, sem x264, QA chamada, ISO publicado); recodificado com cache (2ª vez sem passadas);
  tsMuxeR com "Warning" falha e não publica; cancelamento; `steps_for` e `overall_progress` do
  BD; worker escolhe pelo meio; job BD com `menu=None` não é `OLD_PLAN`, aparece com Retomar e
  as etapas certas na tela; job da Fase 3 continua `OLD_PLAN`.
- [ ] **Step 2–4.** **Step 5:** commit `feat: run Blu-ray jobs in the worker`.

### Task 9: tela "Montar disco"

**Files:** Modify `api/dvd.py`, `web/templates/dvd_form.html`, `_profile_cards.html`,
`_dvd_block.html`, `_disc_titles.html`, `job.html`/`_job_status.html` (textos), `app.css`; Test
`tests/unit/test_dvd_routes.py`.

- Textos: "Montar disco" (botão da pasta e título da tela), "Gerando disco", "Não dá para
  montar o disco desta pasta", "Gerar disco"; a tela do job diz o meio ("Blu-ray BD-25").
- Cartões: os quatro perfis quando `bd_eligible` é `None`; senão os dois de DVD e uma linha com
  o motivo do Blu-ray.
- Perfil BD escolhido: a seção Menu vira o aviso "Sem menu por enquanto: o disco começa sozinho
  e os capítulos pulam pelo filme."; a caixa "Recodificar o vídeo (em vez de copiar o
  original)" quando há cópia; a nota do título ("vídeo copiado do Blu-ray (conferido ao gerar)"
  ou "recodificado: motivo"); idiomas de legenda com PGS.
- O formulário continua um só; trocar o perfil atualiza as seções pelo HTMX como hoje (o
  `_disc_results.html` passa a trocar também a seção Menu/aviso e os idiomas de legenda).
- Conferir no Chrome headless a 375 e 1100 px.

- [ ] **Step 1:** testes de rota: pasta HD de um vídeo mostra BD-25 e BD-50 e sugere BD; pasta
  com dois vídeos mostra a linha "um título por disco"; escolher BD esconde o menu e mostra o
  aviso; gerar com BD enfileira um plano com `menu=None` e nome "(BD).iso"; DVD continua igual.
- [ ] **Step 2–4.** **Step 5:** commit `feat: offer Blu-ray on the Montar disco page`.

### Task 10: slow, documentação e fechamento

- [ ] **Step 1:** testes `slow` (na imagem, sem rede) em `tests/integration/test_bluray.py`:
  - clipe 1080p 23,976 (lavfi, H.264 qualquer) + AC-3 + SRT → BD-25 recodificado, QA aprovada,
    legenda presente;
  - clipe H.264 feito com o x264 em modo Blu-ray num MKV (com HRD, 4 slices) → vídeo copiado,
    sha256 igual;
  - clipe com LPCM e áudio com `start_time` 0,5 → coberto e alinhado;
  - um ISO com uma faixa a menos que o plano → QA reprova.
- [ ] **Step 2:** README (EN e pt-BR) com o Blu-ray; CLAUDE.md (3.3, 4, 5.2 com os parâmetros
  finais, 6.1, 7, 9, 12, 13, Estado atual e Log de decisões).
- [ ] **Step 3:** `make lint`, `make test`, `make test-slow`; commits `test: ...` e `docs: ...`;
  revisão final; PR.

"use strict";

const SAMPLE_ROOT = "./sample-data/";
const LANGUAGES = {
  hi: { name: "Hindi", native: "हिन्दी", locale: "hi" },
  ta: { name: "Tamil", native: "தமிழ்", locale: "ta" },
  bn: { name: "Bengali", native: "বাংলা", locale: "bn" },
  en: { name: "English", native: "English", locale: "en" },
};
const PIPELINE_STEPS = [
  ["01", "Scan & assess", "Pages are rendered and checked for blur, skew and contrast before text is read.", "Deterministic"],
  ["02", "Read the page", "Bodhan Indic-OCR finds text blocks. Doubtful regions can be retried at a higher scale.", "Bodhan · OCR"],
  ["03", "Repair the structure", "Repeated page furniture is removed; XY-cut builds reading order. An optional LLM can suggest block IDs only.", "Guarded decision"],
  ["04", "Translate with checks", "Protected terms, numbers, equations and document structure are checked after translation.", "Bodhan · Translate"],
  ["05", "Plan the narration", "Prose, equations, tables and figures are prepared as short, type-aware narration chunks.", "Deterministic"],
  ["06", "Speak & verify", "Bodhan speech is transcribed back; repeats, omissions and degraded chunks are recorded.", "Bodhan · Speak + ASR"],
];
const state = {
  report: null,
  files: null,
  imported: false,
  sample: true,
  language: "",
  mode: "translation",
  section: 0,
  fullLesson: false,
  content: [],
  sourceContent: [],
  sections: [],
  sourceSections: [],
  chapters: [],
  completed: new Set(),
  objectUrls: new Map(),
  toastTimer: 0,
  sourceLabel: "Source lesson",
};

const el = (id) => document.getElementById(id);
const audio = el("audio-element");

function safePath(value) {
  const path = String(value || "").replaceAll("\\", "/").replace(/^\.\/+/, "");
  if (!path || path.startsWith("/") || path.split("/").some((part) => part === "..")) {
    throw new Error("The run report contains an unsafe file path.");
  }
  return path;
}

function languageInfo(code) {
  return LANGUAGES[code] || { name: String(code).toUpperCase(), native: String(code), locale: "und" };
}

function hasPlaceholderAudio() {
  const warnings = Array.isArray(state.report?.warnings) ? state.report.warnings : [];
  return state.sample || warnings.some((warning) => {
    const message = typeof warning === "string" ? warning : warning?.msg;
    return typeof message === "string" && message.toLowerCase().includes("offline demo: models are simulated");
  });
}

function setAudioControlsEnabled(enabled) {
  ["play-audio", "rewind-audio", "forward-audio", "playback-speed", "audio-seek"]
    .forEach((id) => { el(id).disabled = !enabled; });
}

function notice(message) {
  const target = el("toast");
  target.textContent = message;
  target.classList.add("is-visible");
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => target.classList.remove("is-visible"), 3300);
}

async function readFile(relativePath, optional = false) {
  const path = safePath(relativePath);
  if (state.files) {
    const file = state.files.get(path);
    if (!file) {
      if (optional) return null;
      throw new Error(`This run is missing “${path}”.`);
    }
    return file.text();
  }
  const response = await fetch(`${SAMPLE_ROOT}${path}`);
  if (!response.ok) {
    if (optional && response.status === 404) return null;
    throw new Error(`Could not load sample asset “${path}” (${response.status}).`);
  }
  return response.text();
}

function fileUrl(relativePath) {
  const path = safePath(relativePath);
  if (state.files) {
    const file = state.files.get(path);
    if (!file) return "";
    if (!state.objectUrls.has(path)) state.objectUrls.set(path, URL.createObjectURL(file));
    return state.objectUrls.get(path);
  }
  return `${SAMPLE_ROOT}${path}`;
}

function releaseObjectUrls() {
  for (const url of state.objectUrls.values()) URL.revokeObjectURL(url);
  state.objectUrls.clear();
}

function getLanguageData(code) {
  const languages = state.report?.languages;
  const data = languages && languages[code];
  if (!data || typeof data !== "object") throw new Error(`The run report has no language entry for “${code}”.`);
  return data;
}

function getSectionRecords(code) {
  const records = getLanguageData(code).sections;
  return Array.isArray(records) ? records : [];
}

function splitLesson(markdown, records) {
  const lines = String(markdown).replace(/\r\n/g, "\n").replace(/^<!--.*?-->\s*$/gm, "").split("\n");
  const parts = [];
  let current = null;
  for (const line of lines) {
    const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      current = { title: heading[2], body: [] };
      parts.push(current);
    } else {
      if (!current) {
        current = { title: "", body: [] };
        parts.push(current);
      }
      current.body.push(line);
    }
  }
  const cleaned = parts.map((part) => ({
    title: part.title,
    body: part.body.join("\n").trim(),
  })).filter((part) => part.title || part.body);
  const expected = Array.isArray(records) ? records : [];
  if (expected.length <= 1) return [{ ...(cleaned[0] || { body: "" }), title: expected[0]?.title || cleaned[0]?.title || "Lesson" }];
  return expected.map((record, index) => {
    const part = cleaned[index];
    return { title: record.title || part?.title || `Section ${index + 1}`, body: part?.body || "" };
  });
}

async function loadLesson() {
  const language = state.language;
  const records = getSectionRecords(language);
  const lessonCandidates = [`${language}/lesson.${language}.md`, `${language}/lesson.md`];
  const lessonPath = state.files
    ? lessonCandidates.find((candidate) => state.files.has(candidate))
    : lessonCandidates[0];
  const file = lessonPath ? await readFile(lessonPath, true) : null;
  if (file === null) throw new Error(`No translated Markdown lesson was found for ${languageInfo(language).name}.`);
  state.content = splitLesson(file, records);

  const defaultSourcePath = `source/lesson.${state.report?.source?.language || "en"}.md`;
  const sourceCandidates = state.files
    ? ["source/lesson.src.md", "source/lesson.en.md", "source/lesson.md"].filter((candidate) => state.files.has(candidate))
    : [defaultSourcePath];
  let source = null;
  let sourcePath = "";
  for (const candidate of sourceCandidates) {
    source = await readFile(candidate);
    sourcePath = candidate;
    break;
  }
  if (source !== null) {
    const sourceLang = state.report?.source?.language || "en";
    state.sourceLabel = `${languageInfo(sourceLang).name} source`;
    state.sourceSections = splitLesson(source, records);
  } else {
    state.sourceLabel = "Source text unavailable";
    state.sourceSections = [];
  }

  const chapters = await readFile(`${language}/chapters.${language}.json`, true);
  state.chapters = chapters ? parseJson(chapters, `${language} chapter markers`) : [];
  state.sections = records;
  state.section = Math.min(state.section, Math.max(state.sections.length - 1, 0));
  el("lesson-content").setAttribute("lang", languageInfo(state.mode === "source" ? state.report?.source?.language : language).locale);
  if (!sourcePath) state.sourceSections = [];
  renderAll();
}

function parseJson(text, label) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Could not read ${label}: ${error.message}`);
  }
}

function setupLanguageSelect() {
  const select = el("language-select");
  select.replaceChildren();
  for (const code of Object.keys(state.report.languages || {})) {
    const option = document.createElement("option");
    const info = languageInfo(code);
    option.value = code;
    option.textContent = `${info.name} · ${info.native}`;
    select.append(option);
  }
  const available = Object.keys(state.report.languages || {});
  if (!available.length) throw new Error("This report does not contain any language results.");
  if (!available.includes(state.language)) state.language = available[0];
  select.value = state.language;
}

function setSourceMode(mode) {
  if (mode === "source" && !state.sourceSections.length) {
    notice("No source lesson file was found in this run.");
    return;
  }
  state.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mode === mode);
  });
  el("reading-language").textContent = mode === "source" ? state.sourceLabel : languageInfo(state.language).native;
  el("lesson-content").setAttribute("lang", languageInfo(mode === "source" ? state.report?.source?.language || "en" : state.language).locale);
  renderCurrentSection();
}

function createInline(parent, text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g);
  for (const part of parts) {
    if (!part) continue;
    let node;
    if (part.startsWith("**") && part.endsWith("**")) {
      node = document.createElement("strong");
      node.textContent = part.slice(2, -2);
    } else if (part.startsWith("`") && part.endsWith("`")) {
      node = document.createElement("code");
      node.textContent = part.slice(1, -1);
    } else if (part.startsWith("*") && part.endsWith("*")) {
      node = document.createElement("em");
      node.textContent = part.slice(1, -1);
    } else {
      node = document.createTextNode(part);
    }
    parent.append(node);
  }
}

function renderMarkdown(target, markdown) {
  target.replaceChildren();
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const headingNode = document.createElement(`h${Math.min(heading[1].length + 1, 6)}`);
      createInline(headingNode, heading[2]);
      target.append(headingNode);
      index += 1;
      continue;
    }
    if (line.startsWith("$$")) {
      const equation = [];
      const firstLine = line.replace(/^\$\$|\$\$$/g, "").trim();
      if (firstLine) equation.push(firstLine);
      index += 1;
      while (index < lines.length && !lines[index].includes("$$")) {
        equation.push(lines[index].trim());
        index += 1;
      }
      if (index < lines.length) {
        const last = lines[index].replace(/^\$\$|\$\$$/g, "").trim();
        if (last) equation.push(last);
        index += 1;
      }
      const pre = document.createElement("pre");
      pre.textContent = equation.join("\n");
      target.append(pre);
      continue;
    }
    if (line.startsWith("|") && index + 1 < lines.length && /^\|?[\s:|-]+\|?$/.test(lines[index + 1].trim())) {
      const table = document.createElement("table");
      const rows = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        const cells = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!/^[\s:|-]+$/.test(lines[index].trim().replace(/\|/g, ""))) rows.push(cells);
        index += 1;
      }
      rows.forEach((row, rowIndex) => {
        const tr = document.createElement("tr");
        row.forEach((cell) => {
          const cellNode = document.createElement(rowIndex === 0 ? "th" : "td");
          createInline(cellNode, cell);
          tr.append(cellNode);
        });
        (rowIndex === 0 ? table.createTHead() : table.createTBody()).append(tr);
      });
      target.append(table);
      continue;
    }
    const listMatch = line.match(/^\s*[-*]\s+(.+)$/);
    if (listMatch) {
      const list = document.createElement("ul");
      while (index < lines.length) {
        const item = lines[index].trim().match(/^[-*]\s+(.+)$/);
        if (!item) break;
        const li = document.createElement("li");
        createInline(li, item[1]);
        list.append(li);
        index += 1;
      }
      target.append(list);
      continue;
    }
    if (/^---+$/.test(line)) {
      target.append(document.createElement("hr"));
      index += 1;
      continue;
    }
    const paragraph = document.createElement("p");
    const text = [];
    while (index < lines.length && lines[index].trim() && !/^(#{1,6})\s/.test(lines[index].trim()) && !/^\s*[-*]\s+/.test(lines[index]) && !lines[index].trim().startsWith("|")) {
      text.push(lines[index].trim());
      index += 1;
    }
    createInline(paragraph, text.join(" "));
    target.append(paragraph);
  }
}

function renderSectionList() {
  const list = el("section-list");
  const query = el("section-search").value.trim().toLocaleLowerCase();
  list.replaceChildren();
  const visible = state.sections
    .map((section, index) => ({ section, index }))
    .filter(({ section, index }) => !query || `${section.title} ${state.content[index]?.body || ""}`.toLocaleLowerCase().includes(query));
  if (!visible.length) {
    const empty = document.createElement("p");
    empty.className = "empty-search";
    empty.textContent = "No matching sections.";
    list.append(empty);
    return;
  }
  for (const { section, index } of visible) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `section-link${index === state.section ? " is-active" : ""}`;
    button.setAttribute("aria-current", index === state.section ? "step" : "false");
    button.addEventListener("click", () => selectSection(index));
    const number = document.createElement("span");
    number.className = "section-number";
    number.textContent = String(index + 1).padStart(2, "0");
    const title = document.createElement("span");
    title.textContent = section.title || `Section ${index + 1}`;
    const done = document.createElement("span");
    done.className = "section-done";
    done.textContent = state.completed.has(`${state.language}:${index}`) ? "✓" : "";
    button.append(number, title, done);
    list.append(button);
  }
}

async function selectSection(index) {
  state.section = index;
  audio.pause();
  renderCurrentSection();
  await loadNarration();
  await loadAudio();
}

function renderCurrentSection() {
  const record = state.sections[state.section] || {};
  const translated = state.content[state.section] || { body: "" };
  const source = state.sourceSections[state.section];
  const selected = state.mode === "source" ? source : translated;
  const title = record.title || selected?.title || `Section ${state.section + 1}`;
  el("lesson-title").textContent = title;
  el("audio-title").textContent = state.fullLesson ? `${languageInfo(state.language).native} · Full lesson` : title;
  el("breadcrumb-title").textContent = title;
  el("section-kicker").textContent = `SECTION ${String(state.section + 1).padStart(2, "0")} · LESSON`;
  el("section-description").textContent = selected?.body ? "Read along with the section narration, or switch to the source text." : "No text is available for this section in the selected version.";
  el("reading-language").textContent = state.mode === "source" ? state.sourceLabel : languageInfo(state.language).native;
  el("block-count").textContent = `${record.chunks ?? "—"} narration chunks · ${record.skipped_blocks?.length ?? 0} blocks withheld`;
  const chapter = state.chapters[state.section];
  el("page-count").textContent = chapter?.start_s != null ? `FROM ${formatTime(chapter.start_s)}` : `SECTION ${String(state.section + 1).padStart(2, "0")}`;
  el("aside-title").textContent = title.replace(/\s+and\s+/i, " & ");
  el("aside-copy").textContent = state.sample
    ? "This synthetic chapter lets you try the reader, audio controls, language switcher and report without using model credits."
    : "A chapter from the imported pipeline run. Review its source, language output and checks side by side.";
  el("mark-complete").classList.toggle("is-complete", state.completed.has(`${state.language}:${state.section}`));
  el("mark-complete").setAttribute("aria-pressed", String(state.completed.has(`${state.language}:${state.section}`)));
  renderMarkdown(el("lesson-content"), selected?.body || "");
  renderSectionList();
}

function formatTime(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "0:00";
  const minutes = Math.floor(value / 60);
  const remaining = Math.floor(value % 60).toString().padStart(2, "0");
  return `${minutes}:${remaining}`;
}

function currentAudioPath() {
  const section = state.sections[state.section] || {};
  if (typeof section.file === "string" && section.file) return section.file;
  return "";
}

function fullLessonAudioPath() {
  const candidates = [`${state.language}/lesson.${state.language}.mp3`, `${state.language}/lesson.${state.language}.wav`];
  return state.files ? candidates.find((candidate) => state.files.has(candidate)) || "" : candidates[0];
}

async function loadAudio() {
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  audio.onloadedmetadata = null;
  const placeholderAudio = hasPlaceholderAudio();
  const completeLessonPath = fullLessonAudioPath();
  if (!completeLessonPath) state.fullLesson = false;
  el("toggle-full-lesson").hidden = !completeLessonPath;
  el("toggle-full-lesson").setAttribute("aria-pressed", String(state.fullLesson));
  el("toggle-full-lesson").innerHTML = state.fullLesson
    ? 'Play this section only <span aria-hidden="true">↗</span>'
    : 'Play the full lesson <span aria-hidden="true">↗</span>';
  el("audio-title").textContent = state.fullLesson
    ? `${languageInfo(state.language).native} · Full lesson`
    : state.sections[state.section]?.title || "Narrated section";
  if (placeholderAudio) {
    state.fullLesson = false;
    el("toggle-full-lesson").hidden = true;
    el("toggle-full-lesson").setAttribute("aria-pressed", "false");
    setAudioControlsEnabled(false);
    el("play-audio").setAttribute("aria-label", "Audio unavailable: simulated test tone");
    el("audio-title").textContent = "No voice in simulated audio";
    el("audio-message").textContent = "Playback disabled · test tones are not speech";
    el("audio-disclaimer").textContent = "The offline demo generated a 300 Hz test tone instead of a voice. Playback is disabled; open a completed Bodhan run with real narration to listen.";
    el("audio-duration").textContent = "—:—";
    el("audio-total").textContent = "0:00";
    el("audio-current").textContent = "0:00";
    el("audio-seek").value = "0";
    return;
  }
  const path = state.fullLesson ? completeLessonPath : currentAudioPath();
  const url = path ? fileUrl(path) : "";
  setAudioControlsEnabled(Boolean(url));
  if (!url) {
    el("audio-message").textContent = "No audio asset is included for this section.";
    el("audio-duration").textContent = "—:—";
    el("audio-total").textContent = "0:00";
    el("audio-current").textContent = "0:00";
    el("audio-seek").value = "0";
    return;
  }
  const expectedDuration = state.fullLesson
    ? state.chapters.at(-1)?.end_s
    : state.sections[state.section]?.seconds;
  if (expectedDuration != null && Number.isFinite(Number(expectedDuration))) {
    const formattedDuration = formatTime(Number(expectedDuration));
    el("audio-duration").textContent = formattedDuration;
    el("audio-total").textContent = formattedDuration;
  }
  const sourceUrl = new URL(url, window.location.href).href;
  const fullLessonPlayback = state.fullLesson;
  const chapter = state.chapters[state.section];
  audio.onloadedmetadata = () => {
    if (fullLessonPlayback && Number.isFinite(Number(chapter?.start_s)) && chapter.start_s < audio.duration) {
      audio.currentTime = chapter.start_s;
    }
    updateAudioUi();
  };
  audio.src = sourceUrl;
  el("audio-message").textContent = "Imported audio · stored in this folder";
  el("audio-disclaimer").textContent = "Audio is loaded from the selected local run folder. Its provenance is determined by the run, not this reader.";
}

async function loadNarration() {
  const record = state.sections[state.section] || {};
  const slug = record.slug || String(record.title || `section-${state.section + 1}`).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const fileName = `${String(record.index || state.section + 1).padStart(2, "0")}-${slug}.${state.language}.json`;
  const script = await readFile(`${state.language}/narration/${fileName}`, true);
  const body = el("transcript-body");
  body.replaceChildren();
  if (!script) {
    const message = document.createElement("p");
    message.className = "transcript-empty";
    message.textContent = "This run does not include a narration script for the selected section.";
    body.append(message);
    return;
  }
  const parsed = parseJson(script, `${languageInfo(state.language).name} narration script`);
  const items = Array.isArray(parsed.items) ? parsed.items : [];
  if (!items.length) {
    const message = document.createElement("p");
    message.className = "transcript-empty";
    message.textContent = "The narration script has no items.";
    body.append(message);
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "transcript-item";
    const text = document.createElement("p");
    text.textContent = item.text || "";
    const meta = document.createElement("small");
    meta.textContent = [item.kind, ...(Array.isArray(item.notes) ? item.notes : [])].filter(Boolean).join(" · ");
    row.append(text, meta);
    body.append(row);
  }
}

function updateAudioUi() {
  const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
  const current = Number.isFinite(audio.currentTime) ? audio.currentTime : 0;
  el("audio-current").textContent = formatTime(current);
  el("audio-total").textContent = formatTime(duration);
  el("audio-duration").textContent = duration
    ? formatTime(duration)
    : state.sections[state.section]?.seconds != null
      ? formatTime(Number(state.sections[state.section].seconds))
      : "—:—";
  el("audio-seek").value = duration ? String(Math.round((current / duration) * 1000)) : "0";
  el("audio-seek").disabled = duration <= 0;
  const playing = !audio.paused && !audio.ended;
  el("play-audio").setAttribute("aria-label", playing ? "Pause audio" : "Play audio");
  el("play-audio").innerHTML = playing
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zM14 5h4v14h-4z"/></svg>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7V5Z"/></svg>';
}

function renderReport() {
  const report = state.report;
  const source = report.source || {};
  const languages = Object.entries(report.languages || {});
  el("stat-pages").textContent = source.pages ?? "—";
  el("stat-sections").textContent = source.sections ?? "—";
  el("stat-languages").textContent = languages.length;
  el("stat-source-language").textContent = languageInfo(source.language || "—").name;
  el("section-count").textContent = String(source.sections ?? "—").padStart(2, "0");
  el("report-status").textContent = state.sample ? "SIMULATED SAMPLE" : "IMPORTED RUN";
  const summary = el("report-summary");
  summary.replaceChildren();
  const summaries = [
    ["Pages processed", source.pages ?? "—"],
    ["Sections assembled", source.sections ?? "—"],
    ["Flagged OCR blocks", source.flagged_blocks ?? "—"],
    ["Runtime", report.total_runtime_s != null ? `${Number(report.total_runtime_s).toFixed(1)} s` : "Not reported"],
    ["Estimated cost", report.usage?.total_cost_inr != null ? `₹${Number(report.usage.total_cost_inr).toFixed(2)}` : "Not reported"],
  ];
  for (const [label, value] of summaries) {
    const card = document.createElement("div");
    card.className = "report-stat";
    const name = document.createElement("span");
    name.textContent = label;
    const metric = document.createElement("strong");
    metric.textContent = String(value);
    card.append(name, metric);
    summary.append(card);
  }
  const table = el("report-languages");
  table.replaceChildren();
  for (const [code, data] of languages) {
    const targets = data.targets || {};
    const row = document.createElement("tr");
    const meanCer = Number(targets.section_mean_cer);
    const worstCer = Number(targets.worst_section_cer);
    const loudness = Array.isArray(targets.loudness_lufs_range)
      ? `${targets.loudness_lufs_range.map((value) => Number(value).toFixed(1)).join(" to ")} LUFS`
      : Number.isFinite(Number(data.full_lufs)) ? `${Number(data.full_lufs).toFixed(1)} LUFS` : "Not reported";
    const values = [
      languageInfo(code).name,
      data.status || "unknown",
      data.structure_ok === true || targets.structure_survival === true ? "Preserved" : data.structure_ok === false ? "Needs review" : "Not reported",
      targets.section_mean_cer != null && Number.isFinite(meanCer) ? meanCer.toFixed(3) : "Not reported",
      targets.worst_section_cer != null && Number.isFinite(worstCer) ? worstCer.toFixed(3) : "Not reported",
      Array.isArray(data.sections) ? String(data.sections.length) : "—",
      String((data.skipped_blocks?.length || 0) + (data.sections || []).reduce((total, section) => total + (section.skipped_blocks?.length || 0), 0)),
      targets.loudness_lufs_range || data.full_lufs != null ? loudness : "Not reported",
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 1) {
        const status = document.createElement("span");
        status.className = "table-status";
        status.textContent = String(value);
        cell.append(status);
      } else {
        cell.textContent = String(value);
      }
      row.append(cell);
    });
    table.append(row);
  }
  const usageRows = el("report-usage");
  usageRows.replaceChildren();
  const usage = report.usage && typeof report.usage === "object" ? report.usage : {};
  const usageEntries = Object.entries(usage).filter(([name, value]) => name !== "total_cost_inr" && value && typeof value === "object");
  for (const [name, metrics] of usageEntries) {
    const row = document.createElement("tr");
    const values = [
      name,
      metrics.calls ?? "—",
      metrics.retries ?? "—",
      metrics.failures ?? "—",
      metrics.latency_s != null ? `${Number(metrics.latency_s).toFixed(2)} s` : "—",
      metrics.cost_inr != null ? Number(metrics.cost_inr).toFixed(2) : "—",
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = String(value);
      row.append(cell);
    });
    usageRows.append(row);
  }
  const timingRows = el("report-timings");
  timingRows.replaceChildren();
  const timings = report.timings_s && typeof report.timings_s === "object" ? report.timings_s : {};
  for (const [name, seconds] of Object.entries(timings)) {
    const row = document.createElement("tr");
    const stage = document.createElement("td");
    stage.textContent = name;
    const elapsed = document.createElement("td");
    elapsed.textContent = `${Number(seconds).toFixed(3)} s`;
    row.append(stage, elapsed);
    timingRows.append(row);
  }
  const warningMessages = (Array.isArray(report.warnings) ? report.warnings : [])
    .map((warning) => typeof warning === "string" ? warning : warning?.msg)
    .filter(Boolean);
  const note = el("report-note");
  if (state.sample) {
    note.textContent = `SIMULATED OUTPUT — ${warningMessages.join(" · ") || "This run uses simulated models. Values here are illustrative only and are not live Bodhan performance or billing data."}`;
  } else if (warningMessages.length) {
    note.textContent = `Run warnings: ${warningMessages.join(" · ")}`;
  } else {
    note.textContent = "This reader does not independently verify model provenance or accuracy. Use the source artifacts and run evidence for review.";
  }
  el("section-progress").textContent = `${state.completed.size} / ${state.sections.length}`;
  el("run-label").textContent = state.sample ? "Simulated sample" : "Imported run";
  el("provenance-chip").textContent = state.sample ? "SIMULATED SAMPLE" : "IMPORTED RUN";
  el("provenance-notice").hidden = !state.sample || sessionStorage.getItem("bodhan-notice-dismissed") === "1";
}

function renderWorkflow() {
  const grid = el("workflow-grid");
  grid.replaceChildren();
  for (const [number, title, description, tag] of PIPELINE_STEPS) {
    const card = document.createElement("article");
    card.className = "workflow-card";
    const top = document.createElement("div");
    top.className = "workflow-step";
    const stepNumber = document.createElement("strong");
    stepNumber.textContent = number;
    const badge = document.createElement("span");
    badge.className = "workflow-tag";
    badge.textContent = tag;
    top.append(stepNumber, badge);
    const heading = document.createElement("h3");
    heading.textContent = title;
    const paragraph = document.createElement("p");
    paragraph.textContent = description;
    card.append(top, heading, paragraph);
    grid.append(card);
  }
}

function renderAll() {
  renderReport();
  renderSectionList();
  renderCurrentSection();
  renderWorkflow();
  loadNarration().catch((error) => notice(error.message));
  loadAudio().catch((error) => notice(error.message));
}

function activateView(name) {
  document.querySelectorAll("[data-view-tab]").forEach((button) => button.classList.toggle("is-active", button.dataset.viewTab === name));
  document.querySelectorAll("[data-view-panel]").forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== name; });
  document.querySelector(".secondary-view:not([hidden])")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function collectImportedFiles(fileList) {
  const entries = Array.from(fileList).map((file) => ({
    file,
    path: String(file.webkitRelativePath || file.name).replaceAll("\\", "/"),
  }));
  const reports = entries.filter((entry) => entry.path.split("/").at(-1).toLowerCase() === "report.json");
  if (!reports.length) throw new Error("No report.json was found. Choose a completed pipeline output folder.");
  reports.sort((a, b) => a.path.split("/").length - b.path.split("/").length);
  const shallowest = reports.filter((entry) => entry.path.split("/").length === reports[0].path.split("/").length);
  if (shallowest.length > 1) throw new Error("More than one run report was found. Choose a single run output folder, not its parent.");
  const reportEntry = reports[0];
  const reportParts = reportEntry.path.split("/");
  const base = reportParts.slice(0, -1).join("/");
  const files = new Map();
  for (const entry of entries) {
    if (base && !entry.path.startsWith(`${base}/`)) continue;
    const relative = base ? entry.path.slice(base.length + 1) : entry.path;
    if (relative) files.set(relative, entry.file);
  }
  return { files, reportEntry: files.get("report.json") };
}

async function importRun(fileList) {
  try {
    if (!fileList?.length) return;
    const imported = collectImportedFiles(fileList);
    const reportText = await imported.reportEntry.text();
    const report = parseJson(reportText, "report.json");
    if (!report || typeof report.languages !== "object" || !report.languages || typeof report.source !== "object") {
      throw new Error("report.json does not match the Bodhan lesson run format.");
    }
    audio.pause();
    releaseObjectUrls();
    state.files = imported.files;
    state.imported = true;
    state.sample = false;
    state.report = report;
    state.language = "";
    state.mode = "translation";
    state.section = 0;
    state.completed.clear();
    setupLanguageSelect();
    await loadLesson();
    el("app-error").hidden = true;
    activateView("read");
    notice("Run opened locally. No files were uploaded.");
  } catch (error) {
    showError(error);
  } finally {
    el("run-folder").value = "";
  }
}

function showError(error) {
  const target = el("app-error");
  target.textContent = `Unable to open the lesson: ${error.message}`;
  target.hidden = false;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function downloadReport() {
  try {
    const text = state.files
      ? await state.files.get("report.json")?.text()
      : await readFile("report.json");
    if (!text) throw new Error("report.json is unavailable.");
    const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "report.json";
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    notice(error.message);
  }
}

function loadTheme() {
  const theme = localStorage.getItem("bodhan-theme") === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = theme;
  el("theme-toggle").setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
}

function bindEvents() {
  document.querySelectorAll("[data-view-tab]").forEach((button) => button.addEventListener("click", () => activateView(button.dataset.viewTab)));
  document.querySelectorAll("[data-view-link]").forEach((button) => button.addEventListener("click", () => activateView(button.dataset.viewLink)));
  document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => setSourceMode(button.dataset.mode)));
  el("language-select").addEventListener("change", async (event) => {
    try {
      state.language = event.target.value;
      state.section = 0;
      await loadLesson();
      if (state.mode === "source") setSourceMode("source");
    } catch (error) { showError(error); }
  });
  el("section-search").addEventListener("input", renderSectionList);
  el("import-run").addEventListener("click", () => el("run-folder").click());
  el("import-run-rail").addEventListener("click", () => el("run-folder").click());
  el("run-folder").addEventListener("change", (event) => importRun(event.target.files));
  el("open-sample").addEventListener("click", () => {
    activateView("read");
    el("lesson-title").scrollIntoView({ behavior: "smooth", block: "center" });
  });
  el("dismiss-notice").addEventListener("click", () => {
    sessionStorage.setItem("bodhan-notice-dismissed", "1");
    el("provenance-notice").hidden = true;
  });
  el("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("bodhan-theme", next);
    el("theme-toggle").setAttribute("aria-label", next === "dark" ? "Switch to light theme" : "Switch to dark theme");
  });
  el("mark-complete").addEventListener("click", () => {
    const key = `${state.language}:${state.section}`;
    if (state.completed.has(key)) state.completed.delete(key);
    else state.completed.add(key);
    renderSectionList();
    renderCurrentSection();
    el("section-progress").textContent = `${state.completed.size} / ${state.sections.length}`;
  });
  el("transcript-toggle").addEventListener("click", () => {
    const expanded = el("transcript-toggle").getAttribute("aria-expanded") === "true";
    el("transcript-toggle").setAttribute("aria-expanded", String(!expanded));
    el("transcript-body").hidden = expanded;
  });
  el("play-audio").addEventListener("click", async () => {
    if (!audio.src) {
      notice("No audio file is available for this section.");
      return;
    }
    try {
      if (audio.paused) await audio.play();
      else audio.pause();
    } catch (error) {
      notice(`Audio could not be played: ${error.message}`);
    }
  });
  el("rewind-audio").addEventListener("click", () => { if (audio.src) audio.currentTime = Math.max(0, audio.currentTime - 10); });
  el("forward-audio").addEventListener("click", () => { if (audio.src) audio.currentTime = Math.min(audio.duration || Infinity, audio.currentTime + 10); });
  el("playback-speed").addEventListener("change", (event) => { audio.playbackRate = Number(event.target.value); });
  el("audio-seek").addEventListener("input", (event) => {
    if (Number.isFinite(audio.duration) && audio.duration > 0) audio.currentTime = (Number(event.target.value) / 1000) * audio.duration;
  });
  el("toggle-full-lesson").addEventListener("click", () => {
    state.fullLesson = !state.fullLesson;
    loadAudio();
  });
  ["loadedmetadata", "timeupdate", "play", "pause", "ended"].forEach((event) => audio.addEventListener(event, updateAudioUi));
  audio.addEventListener("error", () => {
    if (audio.src) el("audio-message").textContent = "This audio file could not be decoded by the browser.";
  });
  el("download-report").addEventListener("click", downloadReport);
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      el("section-search").focus();
    }
  });
}

async function initialize() {
  bindEvents();
  loadTheme();
  renderWorkflow();
  try {
    state.report = parseJson(await readFile("report.json"), "sample report");
    if (!state.report || typeof state.report.languages !== "object") throw new Error("The sample report has an invalid shape.");
    state.sample = true;
    setupLanguageSelect();
    await loadLesson();
  } catch (error) {
    showError(error);
    el("run-label").textContent = "No run loaded";
    el("provenance-chip").textContent = "NO RUN LOADED";
  }
}

initialize();

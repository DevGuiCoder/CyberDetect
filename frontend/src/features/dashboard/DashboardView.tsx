import { useCallback, useEffect, useMemo, useRef, useState, memo } from "react";
import type { ReactNode } from "react";

import { AppIcon } from "../../shared/components/AppIcon";
import logo from "../../assets/terminal-logo.png";

type RiskClass = "SEGURO" | "SUSPEITO" | "GOLPE" | "ERRO" | string;

type AnalysisItem = {
  id: number;
  created_at: string;
  source: string;
  app_name?: string;
  model?: string;
  classification?: RiskClass;
  scam_type?: string;
  score?: number;
  input_text?: string;
  summary?: string;
  recommendation?: string;
  predicted_class?: RiskClass;
  ground_truth?: string;
  validated?: number | boolean;
  validated_at?: string;
  validation_note?: string;
  validation_source?: string;
  validation_correct?: number | boolean | null;
  result?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

type MonitoredApp = {
  id: number;
  name: string;
  enabled: number | boolean;
  is_custom: number | boolean;
  app_key?: string | null;
  canonical_name?: string;
  installed?: boolean;
  active?: boolean;
  web_only?: boolean;
  can_monitor?: boolean;
  download_url?: string;
  icon_path?: string;
  status?: string;
  status_label?: string;
  lock_reason?: string;
  install_hint?: string;
};

type MonitoringTestResult = {
  app_detectado?: string;
  app_monitorado?: string;
  janela?: string;
  processo?: string;
  captura?: string;
  ocr?: string;
  trigger?: string;
  status?: string;
  ocr_preview?: string;
};

type EventItem = {
  id: number;
  created_at: string;
  level: string;
  category: string;
  message: string;
};

type DashboardData = {
  stats: {
    total: number;
    detected: number;
    avg_score: number;
    top_model: string;
    top_app: string;
    risk_distribution: Record<string, number>;
    type_distribution: Array<{ label: string; value: number }>;
    trend: Array<{ day: string; total: number; avg_score: number }>;
  };
  analyses: AnalysisItem[];
  events: EventItem[];
  apps: MonitoredApp[];
  models: {
    installed: string[];
    supported: string[];
    ollamaRunning: boolean;
  };
  settings: Record<string, string | boolean | number>;
  logs: {
    files: Array<{ name: string; size: number }>;
    tail: Array<{ name: string; lines: string[] }>;
  };
  system: {
    model?: string;
    auto_interval?: number;
    protection_active?: boolean;
    auto_region_selected?: boolean;
  };
  experimental: ExperimentalData;
};

type ExperimentalDataset = {
  id: number;
  name: string;
  version: string;
  sample_count?: number;
  total_samples?: number;
  imported_at?: string;
  label_distribution?: Record<string, number>;
};

type ExperimentItem = {
  id: string;
  status: string;
  dataset_name?: string;
  sample_count?: number;
  completed_results?: number;
  expected_results?: number;
  error_results?: number;
  progress_percent?: number;
  models?: string[];
  approaches?: string[];
  created_at?: string;
  duration_ms?: number;
};

type ExperimentMetric = {
  id?: number;
  experiment_id?: string;
  model: string;
  approach: string;
  metrics: {
    sample_count?: number;
    accuracy?: number | null;
    false_positive_rate?: number | null;
    false_negative_rate?: number | null;
    macro?: Record<string, number>;
    weighted?: Record<string, number>;
    per_class?: Record<string, Record<string, number>>;
    confusion_matrix?: { labels: string[]; matrix: number[][] };
    latency?: Record<string, number | null>;
    errors?: {
      false_positives?: Array<Record<string, unknown>>;
      false_negatives?: Array<Record<string, unknown>>;
    };
    robustness?: {
      sample_count?: number;
      average_stability_rate?: number | null;
      details?: Array<Record<string, unknown>>;
    };
  };
};

type ThresholdRow = {
  model: string;
  approach: string;
  threshold: number;
  sample_count: number;
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  false_positive_rate: number;
  false_negative_rate: number;
};

type DiagnosticCheck = {
  id: string;
  label: string;
  category: string;
  status: "OK" | "WARN" | "ERRO" | string;
  detail: string;
  metadata?: Record<string, unknown>;
  duration_ms?: number;
};

type DiagnosticReport = {
  generated_at: string;
  summary: {
    status: "OK" | "WARN" | "ERRO" | string;
    total: number;
    ok: number;
    warn: number;
    error: number;
  };
  checks: DiagnosticCheck[];
  notes?: string[];
};

type OcrPipelineRow = {
  name: string;
  description?: string;
  size?: number[];
  latency_ms?: number;
  extracted_length?: number;
  ocr_text_preview?: string;
  wer?: number | null;
  cer?: number | null;
};

type OcrBenchmarkResult = Record<string, unknown> & {
  sample_count?: number;
  average_wer?: number | null;
  average_cer?: number | null;
  best_pipeline?: string | null;
  pipelines?: OcrPipelineRow[];
  path?: string;
};

type ExperimentalData = {
  datasets: ExperimentalDataset[];
  experiments: ExperimentItem[];
  latest_metrics: ExperimentMetric[];
  rankings?: Record<string, { model?: string; approach?: string; [key: string]: unknown } | null>;
  totals: {
    datasets: number;
    samples: number;
    experiments: number;
  };
};

type ApiResult<T = unknown> = { ok: boolean; error?: string } & T;
type ViewKey = "analise" | "ocr" | "monitoramento" | "ameacas" | "laboratorio" | "logs" | "historico" | "configuracoes";
type Tone = "safe" | "warn" | "danger" | "muted";

const MENU: Array<{ id: string; label: string; key: ViewKey; hint: string }> = [
  { id: "01", label: "ANALISE", key: "analise", hint: "texto / imagem / captura" },
  { id: "02", label: "OCR", key: "ocr", hint: "extracao / preview / logs" },
  { id: "03", label: "MONITORAMENTO", key: "monitoramento", hint: "auto / apps / trigger / cooldown" },
  { id: "04", label: "AMEACAS", key: "ameacas", hint: "score / golpe / evidencias" },
  { id: "05", label: "LABORATORIO", key: "laboratorio", hint: "benchmark / consenso / divergencias" },
  { id: "06", label: "LOGS", key: "logs", hint: "ocr / ia / benchmark / erros" },
  { id: "07", label: "HISTORICO", key: "historico", hint: "sqlite / relatorios salvos" },
  { id: "08", label: "CONFIGURACOES", key: "configuracoes", hint: "modelos / api / ocr / trigger" },
];

const emptyData: DashboardData = {
  stats: {
    total: 0,
    detected: 0,
    avg_score: 0,
    top_model: "-",
    top_app: "-",
    risk_distribution: {},
    type_distribution: [],
    trend: [],
  },
  analyses: [],
  events: [],
  apps: [],
  models: { installed: [], supported: ["gemma3:4b", "llama3.2:3b", "qwen2.5:3b", "phi4-mini:latest"], ollamaRunning: false },
  settings: {},
  logs: { files: [], tail: [] },
  system: {},
  experimental: {
    datasets: [],
    experiments: [],
    latest_metrics: [],
    rankings: {},
    totals: { datasets: 0, samples: 0, experiments: 0 },
  },
};

function api() {
  return window.pywebview?.api;
}

function useClock() {
  const [date, setDate] = useState(new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setDate(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return date;
}

function fmtDate(value?: string) {
  if (!value) return "--/-- --:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function short(value?: string, limit = 96) {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  return clean.length <= limit ? clean : `${clean.slice(0, limit - 1)}...`;
}

function compactUnknown(value: unknown, limit = 160) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return short(String(value), limit);
  if (typeof value !== "object") return short(String(value), limit);

  const record = value as Record<string, unknown>;
  const readable = record.description || record.descricao || record.message || record.mensagem || record.text || record.tipo || record.type;
  if (readable) return short(String(readable), limit);

  try {
    return short(JSON.stringify(value), limit);
  } catch {
    return short(String(value), limit);
  }
}

function analysisPayload(item?: AnalysisItem | null) {
  return item?.result && typeof item.result === "object" ? item.result : {};
}

function resultText(result: Record<string, unknown> | null | undefined, key: string, fallback = "") {
  if (!result) return fallback;
  const value = result[key];
  return value === null || value === undefined ? fallback : String(value);
}

function resultNumber(result: Record<string, unknown> | null | undefined, key: string, fallback = 0) {
  const value = Number(result?.[key] ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function textList(value: unknown): string[] {
  if (value === null || value === undefined || value === "") return [];
  if (Array.isArray(value)) return value.flatMap((item) => textList(item));
  if (typeof value === "object") return [compactUnknown(value)];
  return [String(value)];
}

function resultLines(result: Record<string, unknown>, keys: string[], limit = 6) {
  const seen = new Set<string>();
  const lines = keys.flatMap((key) => textList(result[key]))
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => {
      const marker = item.toLowerCase();
      if (seen.has(marker)) return false;
      seen.add(marker);
      return true;
    });
  return lines.slice(0, limit);
}

function resultClassification(result: Record<string, unknown> | null | undefined, fallback = "SEM CLASSE") {
  return String(
    result?.classificacao ||
    result?.classification ||
    result?.classe ||
    fallback
  ).toUpperCase();
}

function resultScore(result: Record<string, unknown> | null | undefined, fallback = 0) {
  return resultNumber(result, "score_risco", resultNumber(result, "score", fallback));
}

function intervalLabel(seconds?: number | string) {
  const value = Number(seconds || 0);
  if (value <= 0) return "OFF";
  if (value % 60 === 0) return `${value / 60}MIN`;
  return `${value}S`;
}

function riskTone(classification?: RiskClass, score?: number) {
  const value = String(classification || "").toUpperCase();
  const risk = Number(score || 0);
  if (value === "GOLPE" || risk >= 70) return "danger";
  if (value === "SUSPEITO" || risk >= 31) return "warn";
  if (value === "SEGURO") return "safe";
  return "muted";
}

function sourceLabel(source?: string) {
  const value = String(source || "manual").toUpperCase();
  if (value === "AUTO") return "CAPTURA AUTO";
  if (value === "CAPTURE") return "CAPTURA";
  if (value === "BENCHMARK") return "COMPARACAO";
  return value;
}

function approachLabel(value?: string) {
  const key = String(value || "").toLowerCase();
  if (key === "ai_only") return "IA";
  if (key === "heuristic_only") return "REGRAS";
  if (key === "hybrid") return "IA + REGRAS";
  return value || "N/A";
}

function statusTone(status?: string): Tone {
  const value = String(status || "").toUpperCase();
  if (["ERRO", "ERROR", "FAILED", "FALHA", "OFFLINE"].includes(value)) return "danger";
  if (["WARN", "WARNING", "SUSPEITO", "PAUSADA", "CANCELLED"].includes(value)) return "warn";
  if (["OK", "ONLINE", "ATIVO", "ATIVA", "COMPLETED", "SEGURO"].includes(value)) return "safe";
  return "muted";
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return target.isContentEditable || tag === "input" || tag === "textarea" || tag === "select";
}

export function DashboardView() {
  const [data, setData] = useState<DashboardData>(emptyData);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const menuRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const clock = useClock();
  const selectedItem = selected === null ? null : MENU[selected] || MENU[0];

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    async function refresh(quiet = false) {
      if (inFlight) return;
      inFlight = true;
      if (!quiet) setLoading(true);
      try {
        const next = (await api()?.getDashboardData?.()) as DashboardData | undefined;
        if (!cancelled && next) setData(next);
      } catch (error) {
        if (!cancelled) setToast(`ERRO :: ${String(error)}`);
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    }

    refresh();
    const onPyWebViewReady = () => refresh();
    window.addEventListener("pywebviewready", onPyWebViewReady);
    const timer = window.setInterval(() => refresh(true), 6000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("pywebviewready", onPyWebViewReady);
    };
  }, [refreshKey]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;

      if (event.key === "ArrowDown" || event.key === "Tab") {
        event.preventDefault();
        setSelected((current) => {
          const next = current === null ? 0 : (current + 1) % MENU.length;
          window.requestAnimationFrame(() => menuRefs.current[next]?.focus());
          return next;
        });
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelected((current) => {
          const next = current === null ? MENU.length - 1 : (current - 1 + MENU.length) % MENU.length;
          window.requestAnimationFrame(() => menuRefs.current[next]?.focus());
          return next;
        });
      }

      if (event.key === "Escape") setSelected(null);
      if (event.key === "Enter" && selected !== null) {
        event.preventDefault();
        menuRefs.current[selected]?.click();
        menuRefs.current[selected]?.focus();
      }

      const index = MENU.findIndex((item) => item.id === event.key.padStart(2, "0"));
      if (index >= 0) {
        setSelected(index);
        window.requestAnimationFrame(() => menuRefs.current[index]?.focus());
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);
  const updateData = useCallback((patch: Partial<DashboardData>) => setData((current) => ({ ...current, ...patch })), []);
  const onlineLabel = data.models.ollamaRunning ? "ONLINE" : "LOCAL";

  return (
    <div className="terminal-app crt-scanlines crt-flicker">
      <div className="terminal-frame">
        <header className="terminal-topline">
          <span>C:\&gt;</span>
          <strong>=== CYBERDETECT TERMINAL 1.0 ===</strong>
          <span>[ {onlineLabel} ]</span>
          <span>{clock.toLocaleTimeString("pt-BR", { hour12: false })}</span>
        </header>

        <main className="terminal-shell">
          <aside className="terminal-menu" aria-label="Menu principal">
            <div className="section-title">&gt; SELECIONE UMA OPCAO:</div>
            <nav className="terminal-menu-list">
              {MENU.map((item, index) => (
                <button
                  key={item.id}
                  ref={(node) => { menuRefs.current[index] = node; }}
                  type="button"
                  className={index === selected ? "is-active" : ""}
                  onClick={() => setSelected(index)}
                  aria-current={index === selected ? "page" : undefined}
                >
                  <span>{index === selected ? ">" : " "}</span>
                  <em>{item.id}.</em>
                  <strong>{item.label}</strong>
                </button>
              ))}
            </nav>
          </aside>

          <section className="terminal-workspace">
            <div className="workspace-title">
              <span>{selectedItem ? `${selectedItem.id} :: ${selectedItem.label}` : "C:\\CYBERDETECT\\MENU"}</span>
              <em>{selectedItem?.hint || "aguardando comando do operador"}</em>
            </div>
            {loading ? (
              <TerminalPanel title="BOOT">
                <p className="empty-terminal">&gt; carregando estado operacional_</p>
              </TerminalPanel>
            ) : selectedItem === null ? (
              <HomeConsole data={data} />
            ) : (
              <ConsoleScreen
                data={data}
                view={selectedItem.key}
                onRefresh={refresh}
                updateData={updateData}
                setToast={setToast}
              />
            )}
          </section>
        </main>

        <section className="terminal-prompt-panel">
          <b>C:\&gt;</b>
          <span>Pronto para comandos. Digite 01-08 ou use TAB para navegar.</span>
          <i aria-hidden="true" />
        </section>

        <footer className="terminal-shortcuts">
          <span>[ENTER] executar</span>
          <span>[TAB] proximo</span>
          <span>[ESC] voltar</span>
          <span>DB:{data.stats.total}</span>
        </footer>
      </div>

      {toast && (
        <button className="terminal-toast" type="button" onClick={() => setToast("")}>
          {toast}
        </button>
      )}
    </div>
  );
}

function ConsoleScreen({
  data,
  view,
  onRefresh,
  updateData,
  setToast,
}: {
  data: DashboardData;
  view: ViewKey;
  onRefresh: () => void;
  updateData: (patch: Partial<DashboardData>) => void;
  setToast: (value: string) => void;
}) {
  if (view === "ocr") return <OcrConsole data={data} onRefresh={onRefresh} setToast={setToast} />;
  if (view === "monitoramento") return <MonitorConsole data={data} onRefresh={onRefresh} updateData={updateData} setToast={setToast} />;
  if (view === "ameacas") return <ThreatConsole data={data} setToast={setToast} updateData={updateData} />;
  if (view === "laboratorio") return <LaboratoryConsole data={data} onRefresh={onRefresh} setToast={setToast} />;
  if (view === "logs") return <LogsConsole data={data} onRefresh={onRefresh} />;
  if (view === "historico") return <HistoryConsole data={data} onRefresh={onRefresh} updateData={updateData} setToast={setToast} />;
  if (view === "configuracoes") return <SettingsConsole data={data} onRefresh={onRefresh} updateData={updateData} setToast={setToast} />;
  return <AnalysisConsole onRefresh={onRefresh} setToast={setToast} />;
}

function TerminalPanel({ title, children, compact = false }: { title: string; children: ReactNode; compact?: boolean }) {
  return (
    <section className={`term-panel ${compact ? "compact" : ""}`}>
      <span className="term-panel-header">{title}</span>
      {children}
    </section>
  );
}

function SectionHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="section-header">
      <div>
        <strong>{title}</strong>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="section-action">{action}</div>}
    </div>
  );
}

function EmptyState({ children }: { children: ReactNode }) {
  return <p className="empty-terminal">&gt; {children}_</p>;
}

function StatusLabel({ label, tone = "muted" }: { label: string; tone?: Tone }) {
  return <span className={`status-label ${tone}`}>{label}</span>;
}

function TerminalTabs<T extends string>({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: Array<{ key: T; label: string; hint?: string }>;
  active: T;
  onChange: (key: T) => void;
  label: string;
}) {
  return (
    <div className="terminal-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={active === tab.key ? "is-active" : ""}
          onClick={() => onChange(tab.key)}
          role="tab"
          aria-selected={active === tab.key}
        >
          <strong>{tab.label}</strong>
          {tab.hint && <span>{tab.hint}</span>}
        </button>
      ))}
    </div>
  );
}

function RiskBadge({ classification, score }: { classification?: RiskClass; score?: number }) {
  const risk = Number(score || 0);
  const tone = riskTone(classification, risk);
  return (
    <div className={`risk-badge ${tone}`}>
      <strong>{String(classification || "SEM CLASSE").toUpperCase()}</strong>
      <span>{String(Math.round(risk)).padStart(3, "0")}/100</span>
    </div>
  );
}

function AnalysisDetailPanel({
  item,
  result,
  onValidate,
}: {
  item?: AnalysisItem | null;
  result?: Record<string, unknown> | null;
  onValidate?: (groundTruth: string) => void;
}) {
  const payload = result || analysisPayload(item);
  const classification = (item?.classification || resultClassification(payload)) as RiskClass;
  const score = item?.score ?? resultScore(payload);
  const summary = item?.summary || resultText(payload, "resumo", resultText(payload, "summary", "Sem resumo retornado."));
  const recommendation = item?.recommendation || resultText(payload, "recomendacao", resultText(payload, "recommendation", "Verifique por canais oficiais antes de agir."));
  const evidence = resultLines(payload, ["fatores_risco_identificados", "evidencias", "evidences", "indicadores", "red_flags", "sinais"]);
  const links = resultLines(payload, ["links", "urls", "dominios", "domains"], 5);
  const model = item?.model || resultText(payload, "modelo", resultText(payload, "model", "-"));

  if (!item && !result) return <EmptyState>aguardando analise</EmptyState>;

  return (
    <div className="analysis-detail">
      <div className="detail-topline">
        <RiskBadge classification={classification} score={score} />
        <div>
          <span>{sourceLabel(item?.source || resultText(payload, "source", "manual"))}</span>
          <strong>{item?.app_name || resultText(payload, "app", "ENTRADA MANUAL")}</strong>
        </div>
        <div>
          <span>modelo</span>
          <strong>{model}</strong>
        </div>
        <div>
          <span>data</span>
          <strong>{item?.created_at ? fmtDate(item.created_at) : "agora"}</strong>
        </div>
      </div>

      <div className="detail-block">
        <span>Resumo</span>
        <p>{summary}</p>
      </div>
      <div className="detail-block">
        <span>Recomendacao</span>
        <p>{recommendation}</p>
      </div>

      <div className="detail-grid">
        <div className="detail-block">
          <span>Evidencias</span>
          {evidence.length ? (
            <ul>
              {evidence.map((line) => <li key={line}>{line}</li>)}
            </ul>
          ) : (
            <p>Nenhuma evidencia estruturada foi retornada.</p>
          )}
        </div>
        <div className="detail-block">
          <span>Trecho analisado</span>
          <p>{short(item?.input_text || resultText(payload, "texto_analisado", resultText(payload, "input_text", "")), 360) || "Sem texto salvo."}</p>
          {links.length > 0 && <p>Links/dominos: {links.join(" | ")}</p>}
        </div>
      </div>

      {item && (
        <div className="detail-validation">
          <StatusLabel
            label={item.validated ? `validado ${item.ground_truth || "-"}` : "nao validado"}
            tone={item.validated ? (item.validation_correct ? "safe" : "warn") : "muted"}
          />
          {onValidate && ["SEGURO", "SUSPEITO", "GOLPE"].map((label) => (
            <button key={label} type="button" onClick={() => onValidate(label)}>{label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function HomeConsole({ data }: { data: DashboardData }) {
  return (
    <TerminalPanel title="SISTEMA PRONTO">
      <div className="home-console">
        <img src={logo} alt="CyberDetect" />
        <div>
          <strong>CYBERDETECT OS</strong>
          <p>&gt; selecione uma funcao no menu lateral para iniciar uma verificacao.</p>
          <p>&gt; use Analise para textos e prints, OCR para revisar capturas e Historico para auditar resultados.</p>
          <p>&gt; monitoramento automatico so roda quando ativado pelo operador.</p>
          <dl className="mini-status">
            <div><dt>analises</dt><dd>{data.stats.total}</dd></div>
            <div><dt>alertas</dt><dd>{data.stats.detected}</dd></div>
            <div><dt>modelos</dt><dd>{data.models.ollamaRunning ? "ONLINE" : "LOCAL"}</dd></div>
          </dl>
          <div className="quick-guide">
            <span>01 texto / imagem</span>
            <span>03 protecao automatica</span>
            <span>05 testes comparativos</span>
            <span>07 registros salvos</span>
          </div>
        </div>
      </div>
    </TerminalPanel>
  );
}

function AnalysisConsole({ onRefresh, setToast }: { onRefresh: () => void; setToast: (value: string) => void }) {
  const [text, setText] = useState("");
  const [imageName, setImageName] = useState("");
  const [busy, setBusy] = useState(false);
  const [imageBusy, setImageBusy] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [mode, setMode] = useState<"texto" | "imagem" | "captura">("texto");

  const analyze = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const response = (await api()?.analyzeText?.(text)) as ApiResult<{ result: Record<string, unknown> }> | undefined;
      if (response?.ok) {
        setResult(response.result);
        setToast("ANALISE :: concluida");
        onRefresh();
      } else {
        setToast(response?.error || "ANALISE :: falha no processamento");
      }
    } finally {
      setBusy(false);
    }
  };

  const capture = async () => {
    const response = (await api()?.requestScreenAnalysis?.()) as ApiResult | undefined;
    setToast(response?.ok ? "CAPTURA :: solicitada" : "CAPTURA :: indisponivel");
    window.setTimeout(onRefresh, 900);
  };

  const analyzeImage = async (file?: File) => {
    if (!file) return;
    setImageName(file.name);
    setImageBusy(true);

    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      const response = (await api()?.analyzeImageData?.(dataUrl, file.name)) as ApiResult<{ result: Record<string, unknown>; extracted_text?: string; analysis_text?: string }> | undefined;
      if (response?.ok) {
        setResult(response.result);
        if (response.analysis_text || response.extracted_text) setText(response.analysis_text || response.extracted_text || "");
        setToast("IMAGEM :: OCR e analise concluidos");
        onRefresh();
      } else {
        setToast(response?.error || "IMAGEM :: falha no OCR");
      }
    } finally {
      setImageBusy(false);
    }
  };

  return (
    <>
      <TerminalPanel title="ANALISE MANUAL">
        <SectionHeader
          title="Enviar conteudo suspeito"
          description="Cole uma mensagem, envie um print ou solicite uma captura da tela atual."
          action={<StatusLabel label={busy || imageBusy ? "processando" : "pronto"} tone={busy || imageBusy ? "warn" : "safe"} />}
        />
        <TerminalTabs
          label="Tipo de analise"
          active={mode}
          onChange={setMode}
          tabs={[
            { key: "texto", label: "Texto", hint: "conversa, link, cobranca" },
            { key: "imagem", label: "Imagem", hint: "print com OCR" },
            { key: "captura", label: "Captura", hint: "janela atual" },
          ]}
        />

        {mode !== "captura" && (
          <textarea
            className="terminal-input"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="C:\ANALISE> cole texto, conversa, cobranca, link ou mensagem suspeita..."
          />
        )}

        {mode === "imagem" && (
          <div className="upload-drop">
            <label className="file-command">
              <input type="file" accept="image/*" onChange={(event) => analyzeImage(event.target.files?.[0])} />
              {imageBusy ? "LENDO IMAGEM" : "ESCOLHER PRINT"}
            </label>
            <span>{imageName || "OCR extrai o texto e envia para classificacao."}</span>
          </div>
        )}

        {mode === "captura" && (
          <div className="capture-panel">
            <strong>Captura manual</strong>
            <p>Solicita uma leitura da tela ativa e retorna a classificacao quando o backend concluir.</p>
          </div>
        )}

        <div className="command-row">
          {mode === "texto" && <button type="button" onClick={analyze} disabled={busy || !text.trim()}>{busy ? "PROCESSANDO" : "ANALISAR TEXTO"}</button>}
          {mode === "imagem" && <button type="button" onClick={analyze} disabled={busy || !text.trim()}>{busy ? "PROCESSANDO" : "ANALISAR TEXTO OCR"}</button>}
          {mode === "captura" && <button type="button" onClick={capture}>CAPTURAR AGORA</button>}
          <button type="button" onClick={() => { setText(""); setResult(null); setImageName(""); }}>LIMPAR</button>
        </div>
      </TerminalPanel>

      <TerminalPanel title="DOSSIER DA ANALISE">
        <AnalysisDetailPanel result={result} />
      </TerminalPanel>
    </>
  );
}

function OcrConsole({ data, onRefresh, setToast }: { data: DashboardData; onRefresh: () => void; setToast: (value: string) => void }) {
  const latest = data.analyses.find((item) => item.input_text || item.source === "auto" || item.source === "capture") || data.analyses[0];
  const ocrEvents = data.events.filter((event) => event.category.toLowerCase().includes("ocr") || event.message.toLowerCase().includes("ocr"));
  const [imageName, setImageName] = useState("");
  const [busy, setBusy] = useState(false);
  const [extracted, setExtracted] = useState("");

  const analyzeImage = async (file?: File) => {
    if (!file) return;
    setImageName(file.name);
    setBusy(true);
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      const response = (await api()?.analyzeImageData?.(dataUrl, file.name)) as ApiResult<{ extracted_text?: string; analysis_text?: string }> | undefined;
      if (response?.ok) {
        setExtracted(response.analysis_text || response.extracted_text || "");
        setToast("OCR :: imagem processada");
        onRefresh();
      } else {
        setToast(response?.error || "OCR :: falha ao processar imagem");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TerminalPanel title="OCR GUIADO">
        <SectionHeader
          title="Transformar print em texto"
          description="Envie uma imagem para OCR ou revise o ultimo texto extraido por captura."
          action={<StatusLabel label={busy ? "lendo" : "pronto"} tone={busy ? "warn" : "safe"} />}
        />
        <div className="upload-drop">
          <label className="file-command">
            <input type="file" accept="image/*" onChange={(event) => analyzeImage(event.target.files?.[0])} />
            {busy ? "PROCESSANDO" : "ESCOLHER IMAGEM"}
          </label>
          <span>{imageName || "PNG, JPG ou screenshot da conversa suspeita."}</span>
        </div>
      </TerminalPanel>

      <TerminalPanel title="TEXTO EXTRAIDO">
        {extracted || latest?.input_text ? (
          <pre className="text-preview">{short(extracted || latest?.input_text, 1600)}</pre>
        ) : (
          <EmptyState>nenhum texto OCR no buffer local</EmptyState>
        )}
      </TerminalPanel>

      <TerminalPanel title="EVENTOS OCR">
        <EventList events={ocrEvents.length ? ocrEvents : data.events.slice(0, 6)} />
      </TerminalPanel>
    </>
  );
}

function MonitorConsole({
  data,
  onRefresh,
  updateData,
  setToast,
}: {
  data: DashboardData;
  onRefresh: () => void;
  updateData: (patch: Partial<DashboardData>) => void;
  setToast: (value: string) => void;
}) {
  const [testBusy, setTestBusy] = useState(false);
  const [testResult, setTestResult] = useState<MonitoringTestResult | null>(null);

  const setInterval = async (seconds: number) => {
    const response = (await api()?.setProtection?.(seconds)) as ApiResult | undefined;
    setToast(response?.ok ? `MONITORAMENTO :: intervalo ${intervalLabel(seconds)}` : "MONITORAMENTO :: falha ao alterar intervalo");
    window.setTimeout(onRefresh, 900);
  };

  const toggleApp = async (appId: number, enabled: boolean) => {
    const response = (await api()?.setAppEnabled?.(appId, enabled)) as ApiResult<{ apps: MonitoredApp[] }> | undefined;
    if (response?.apps) updateData({ apps: response.apps });
    setToast(response?.ok ? "APP :: monitoramento atualizado" : response?.error || "APP :: indisponivel");
  };

  const downloadApp = async (appId: number) => {
    const response = (await api()?.openAppDownload?.(appId)) as ApiResult<{ url?: string; apps?: MonitoredApp[] }> | undefined;
    if (response?.apps) updateData({ apps: response.apps });
    setToast(response?.ok ? `DOWNLOAD :: ${response.url}` : response?.error || "DOWNLOAD :: indisponivel");
  };

  const captureManual = async () => {
    const response = (await api()?.requestScreenAnalysis?.()) as ApiResult | undefined;
    setToast(response?.ok ? "CAPTURA :: solicitada" : "CAPTURA :: indisponivel");
    window.setTimeout(onRefresh, 900);
  };

  const testMonitoring = async () => {
    setTestBusy(true);
    setToast("TESTE :: minimizando painel e capturando janela ativa");
    try {
      const response = (await api()?.testMonitoring?.()) as ApiResult<{ result: MonitoringTestResult; apps?: MonitoredApp[] }> | undefined;
      if (response?.apps) updateData({ apps: response.apps });
      if (response?.ok) {
        setTestResult(response.result);
        setToast(`TESTE :: ${response.result?.status || "concluido"}`);
      } else {
        setToast(response?.error || "TESTE :: falha no monitoramento");
      }
    } finally {
      setTestBusy(false);
    }
  };

  return (
    <>
      <TerminalPanel title="MONITORAMENTO AUTOMATICO">
        <SectionHeader
          title="Protecao de tela"
          description="Ative ciclos automaticos para verificar a janela em uso, ou execute uma captura manual quando precisar."
          action={<StatusLabel label={data.system.protection_active ? "ativo" : "manual"} tone={data.system.protection_active ? "safe" : "muted"} />}
        />
        <dl className="status-list">
          <div><dt>modo</dt><dd>{data.system.protection_active ? "ATIVO" : "MANUAL"}</dd></div>
          <div><dt>cooldown</dt><dd>{intervalLabel(data.system.auto_interval || Number(data.settings.cooldownSeconds || 0))}</dd></div>
          <div><dt>trigger inteligente</dt><dd>{data.settings.smartTrigger ? "ON" : "OFF"}</dd></div>
          <div><dt>regiao selecionada</dt><dd>{data.system.auto_region_selected ? "SIM" : "NAO"}</dd></div>
        </dl>
        <div className="command-row action-grid">
          <button type="button" onClick={captureManual}>CAPTURAR AGORA</button>
          <button type="button" onClick={() => setInterval(30)}>INICIAR 30S</button>
          <button type="button" onClick={() => setInterval(180)}>INICIAR 3MIN</button>
          <button type="button" onClick={() => setInterval(0)}>PAUSAR</button>
          <button type="button" onClick={testMonitoring} disabled={testBusy}>{testBusy ? "TESTANDO" : "TESTAR MONITORAMENTO"}</button>
        </div>
        {testResult && <MonitoringTestPanel result={testResult} />}
      </TerminalPanel>
      <TerminalPanel title="APPS MONITORADOS">
        <AppList apps={data.apps} onToggle={toggleApp} onDownload={downloadApp} />
      </TerminalPanel>
    </>
  );
}

function MonitoringTestPanel({ result }: { result: MonitoringTestResult }) {
  const rows = [
    ["APP DETECTADO", result.app_detectado || "-"],
    ["APP MONITORADO", result.app_monitorado || "-"],
    ["JANELA", result.janela || "-"],
    ["CAPTURA", result.captura || "-"],
    ["OCR", result.ocr || "-"],
    ["TRIGGER", result.trigger || "-"],
    ["STATUS", result.status || "-"],
  ];

  return (
    <div className="monitor-test-result">
      {rows.map(([label, value]) => (
        <div key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
      {result.ocr_preview && <pre>{short(result.ocr_preview, 520)}</pre>}
    </div>
  );
}

function ThreatConsole({
  data,
  setToast,
  updateData,
}: {
  data: DashboardData;
  setToast: (value: string) => void;
  updateData: (patch: Partial<DashboardData>) => void;
}) {
  const threats = useMemo(() => data.analyses.filter((item) => riskTone(item.classification, item.score) !== "safe"), [data.analyses]);
  const [selectedId, setSelectedId] = useState<number | null>(threats[0]?.id || null);
  const selectedThreat = threats.find((item) => item.id === selectedId) || threats[0];

  useEffect(() => {
    if (!selectedId && threats[0]?.id) setSelectedId(threats[0].id);
  }, [selectedId, threats]);

  const validate = async (id: number, groundTruth: string) => {
    const response = (await api()?.validateAnalysis?.(id, groundTruth, "Validado na tela de ameacas", "manual")) as ApiResult<{ analyses?: AnalysisItem[] }> | undefined;
    if (response?.ok) {
      if (response.analyses) updateData({ analyses: response.analyses });
      setToast(`AMEACA :: validada como ${groundTruth}`);
    } else {
      setToast(response?.error || "AMEACA :: falha ao validar");
    }
  };

  return (
    <>
      <TerminalPanel title="AMEACAS DETECTADAS">
        <SectionHeader
          title="Fila de alertas"
          description="Revise os itens suspeitos, confira as evidencias e valide quando houver confirmacao."
          action={<StatusLabel label={`${threats.length} alertas`} tone={threats.length ? "warn" : "safe"} />}
        />
        <dl className="status-list">
          <div><dt>detectadas</dt><dd>{data.stats.detected}</dd></div>
          <div><dt>score medio</dt><dd>{data.stats.avg_score}</dd></div>
          <div><dt>tipo principal</dt><dd>{data.stats.type_distribution[0]?.label || "-"}</dd></div>
          <div><dt>fonte principal</dt><dd>{data.stats.top_app || "-"}</dd></div>
        </dl>
      </TerminalPanel>
      <div className="split-workspace">
        <TerminalPanel title="ALERTAS">
          <AnalysisList items={threats.slice(0, 12)} selectedId={selectedThreat?.id} onSelect={setSelectedId} />
        </TerminalPanel>
        <TerminalPanel title="DETALHE">
          <AnalysisDetailPanel item={selectedThreat} onValidate={(label) => selectedThreat && validate(selectedThreat.id, label)} />
        </TerminalPanel>
      </div>
    </>
  );
}

type LabSection = "benchmark" | "datasets" | "experimentos" | "metricas" | "robustez" | "ocr" | "thresholds";

const LAB_SECTIONS: Array<{ key: LabSection; label: string; hint: string }> = [
  { key: "benchmark", label: "Benchmark", hint: "comparar modelos" },
  { key: "datasets", label: "Datasets", hint: "base validada" },
  { key: "experimentos", label: "Experimentos", hint: "rodar em lote" },
  { key: "metricas", label: "Metricas", hint: "resultado final" },
  { key: "robustez", label: "Robustez", hint: "variacoes" },
  { key: "ocr", label: "OCR Benchmark", hint: "qualidade do OCR" },
  { key: "thresholds", label: "Thresholds", hint: "sensibilidade" },
];

function LaboratoryConsole({ data, onRefresh, setToast }: { data: DashboardData; onRefresh: () => void; setToast: (value: string) => void }) {
  const available = data.models.supported.length ? data.models.supported : emptyData.models.supported;
  const datasets = data.experimental?.datasets || [];
  const latestExperiment = data.experimental?.experiments?.[0];
  const latestMetrics = data.experimental?.latest_metrics || [];
  const [section, setSection] = useState<LabSection>("benchmark");
  const [text, setText] = useState("");
  const [models, setModels] = useState(available.slice(0, 3));
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [datasetVersion, setDatasetVersion] = useState("1.0");
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<number>(datasets[0]?.id || 0);
  const [sampleLimit, setSampleLimit] = useState("25");
  const [seed, setSeed] = useState("42");
  const [approaches, setApproaches] = useState(["hybrid"]);
  const [runningId, setRunningId] = useState("");
  const [experimentStatus, setExperimentStatus] = useState<{ experiment?: ExperimentItem; metrics?: ExperimentMetric[]; results?: Array<Record<string, unknown>> } | null>(null);
  const [ocrBenchmark, setOcrBenchmark] = useState<OcrBenchmarkResult | null>(null);
  const [ocrImageBenchmark, setOcrImageBenchmark] = useState<OcrBenchmarkResult | null>(null);
  const [ocrExpectedText, setOcrExpectedText] = useState("");
  const [thresholdInput, setThresholdInput] = useState("60,65,70,75,80");
  const [thresholdRows, setThresholdRows] = useState<ThresholdRow[]>([]);

  useEffect(() => {
    if (!selectedDatasetId && datasets[0]?.id) setSelectedDatasetId(datasets[0].id);
  }, [datasets, selectedDatasetId]);

  useEffect(() => {
    if (!runningId) return;
    let cancelled = false;
    let inFlight = false;

    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const response = (await api()?.getExperimentalStatus?.(runningId)) as ApiResult<{
          experiment: ExperimentItem;
          metrics: ExperimentMetric[];
          results: Array<Record<string, unknown>>;
        }> | undefined;
        if (!cancelled && response?.ok) {
          setExperimentStatus({ experiment: response.experiment, metrics: response.metrics, results: response.results });
          if (["completed", "cancelled", "failed"].includes(String(response.experiment.status))) {
            setToast(`EXPERIMENTO :: ${String(response.experiment.status).toUpperCase()}`);
            setRunningId("");
            onRefresh();
          }
        }
      } finally {
        inFlight = false;
      }
    };

    poll();
    const timer = window.setInterval(poll, 2200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [runningId, onRefresh, setToast]);

  const run = async () => {
    if (!text.trim() || models.length === 0) return;
    setBusy(true);
    try {
      const response = (await api()?.runBenchmark?.(text, models)) as ApiResult<{ results: Array<Record<string, unknown>>; comparison: Record<string, unknown> }> | undefined;
      if (response?.ok) {
        setResults(response.results || []);
        setComparison(response.comparison || null);
        setToast("BENCHMARK :: concluido");
        onRefresh();
      } else {
        setToast(response?.error || "BENCHMARK :: falha");
      }
    } finally {
      setBusy(false);
    }
  };

  const importDataset = async (file?: File) => {
    if (!file) return;
    const content = await file.text();
    const response = (await api()?.importExperimentalDataset?.(
      file.name,
      content,
      datasetName || file.name.replace(/\.[^.]+$/, ""),
      datasetVersion || "1.0",
      false
    )) as ApiResult<{ dataset?: ExperimentalDataset; errors?: string[] }> | undefined;
    setImportErrors(response?.errors || []);
    if (response?.ok) {
      setToast(`DATASET :: ${response.dataset?.sample_count || response.dataset?.total_samples || 0} amostras importadas`);
      onRefresh();
    } else {
      setToast(response?.error || "DATASET :: importacao falhou");
    }
  };

  const toggleApproach = (approach: string) => {
    setApproaches((current) => current.includes(approach) ? current.filter((item) => item !== approach) : [...current, approach]);
  };

  const startBatch = async () => {
    if (!selectedDatasetId) {
      setToast("EXPERIMENTO :: selecione um dataset");
      return;
    }
    if (!approaches.length) {
      setToast("EXPERIMENTO :: selecione uma abordagem");
      return;
    }

    const response = (await api()?.startExperimentalBatch?.({
      datasetId: selectedDatasetId,
      models,
      approaches,
      sampleLimit: Number(sampleLimit || 0),
      seed: seed.trim() ? Number(seed) : "",
    })) as ApiResult<{ experimentId?: string }> | undefined;
    if (response?.ok && response.experimentId) {
      setRunningId(response.experimentId);
      setExperimentStatus(null);
      setToast(`EXPERIMENTO :: ${response.experimentId}`);
      onRefresh();
    } else {
      setToast(response?.error || "EXPERIMENTO :: falha ao iniciar");
    }
  };

  const cancelBatch = async () => {
    if (!runningId) return;
    const response = (await api()?.cancelExperimentalBatch?.(runningId)) as ApiResult | undefined;
    setToast(response?.ok ? "EXPERIMENTO :: cancelamento solicitado" : response?.error || "EXPERIMENTO :: nao esta rodando");
  };

  const resumeBatch = async () => {
    const experimentId = activeExperiment?.id || latestExperiment?.id || "";
    if (!experimentId) {
      setToast("EXPERIMENTO :: sem experimento para continuar");
      return;
    }
    const response = (await api()?.resumeExperimentalBatch?.(experimentId)) as ApiResult<{ experimentId?: string }> | undefined;
    if (response?.ok) {
      setRunningId(response.experimentId || experimentId);
      setToast(`EXPERIMENTO :: retomando ${response.experimentId || experimentId}`);
    } else {
      setToast(response?.error || "EXPERIMENTO :: falha ao continuar");
    }
  };

  const startRobustness = async () => {
    if (!selectedDatasetId) {
      setToast("ROBUSTEZ :: selecione um dataset");
      return;
    }
    const response = (await api()?.startRobustnessExperiment?.({
      datasetId: selectedDatasetId,
      models,
      approaches,
      sampleLimit: Number(sampleLimit || 0),
      seed: seed.trim() ? Number(seed) : "",
      variantLimit: 10,
    })) as ApiResult<{ experimentId?: string }> | undefined;
    if (response?.ok && response.experimentId) {
      setRunningId(response.experimentId);
      setSection("robustez");
      setToast(`ROBUSTEZ :: ${response.experimentId}`);
    } else {
      setToast(response?.error || "ROBUSTEZ :: falha");
    }
  };

  const exportExperimentFile = async (type: "csv" | "json") => {
    const experimentId = experimentStatus?.experiment?.id || latestExperiment?.id || "";
    if (!experimentId) {
      setToast("EXPORT :: sem experimento");
      return;
    }
    const response = (await api()?.exportExperiment?.(experimentId, type)) as ApiResult<{ path?: string }> | undefined;
    setToast(response?.ok ? `EXPORT :: ${response.path}` : response?.error || "EXPORT :: falha");
  };

  const generateReport = async () => {
    const experimentId = experimentStatus?.experiment?.id || latestExperiment?.id || "";
    if (!experimentId) {
      setToast("RELATORIO :: sem experimento");
      return;
    }
    const response = (await api()?.generateExperimentReport?.(experimentId)) as ApiResult<{ path?: string }> | undefined;
    setToast(response?.ok ? `RELATORIO :: ${response.path}` : response?.error || "RELATORIO :: falha");
  };

  const runOcrBenchmark = async (file?: File) => {
    if (!file) return;
    const content = await file.text();
    const response = (await api()?.runOcrBenchmark?.(file.name, content)) as ApiResult<{ result?: OcrBenchmarkResult }> | undefined;
    if (response?.ok && response.result) {
      setOcrBenchmark(response.result);
      setToast(`OCR BENCH :: ${response.result.sample_count || 0} amostras`);
    } else {
      setToast(response?.error || "OCR BENCH :: falha");
    }
  };

  const runOcrImageBenchmark = async (file?: File) => {
    if (!file) return;
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    const response = (await api()?.runOcrImageBenchmark?.(dataUrl, file.name, ocrExpectedText)) as ApiResult<{ result?: OcrBenchmarkResult }> | undefined;
    if (response?.ok && response.result) {
      setOcrImageBenchmark(response.result);
      setToast(`OCR IMG :: ${response.result.best_pipeline || response.result.sample_count || 0}`);
    } else {
      setToast(response?.error || "OCR IMG :: falha");
    }
  };

  const runThresholdCalibration = async () => {
    const experimentId = experimentStatus?.experiment?.id || latestExperiment?.id || "";
    if (!experimentId) {
      setToast("THRESHOLD :: sem experimento");
      return;
    }
    const thresholds = thresholdInput
      .split(/[,\s;]+/)
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item));
    const response = (await api()?.runThresholdCalibration?.(experimentId, thresholds)) as ApiResult<{ rows?: ThresholdRow[] }> | undefined;
    if (response?.ok) {
      setThresholdRows(response.rows || []);
      setToast(`THRESHOLD :: ${response.rows?.length || 0} linhas`);
    } else {
      setToast(response?.error || "THRESHOLD :: falha");
    }
  };

  const activeExperiment = experimentStatus?.experiment || latestExperiment;
  const activeMetrics = experimentStatus?.metrics || latestMetrics;

  return (
    <>
      <TerminalPanel title="LABORATORIO EXPERIMENTAL">
        <SectionHeader
          title="Testes controlados"
          description="Use o laboratorio para comparar modelos, validar datasets e medir qualidade com passos simples."
          action={<StatusLabel label={runningId ? "rodando" : "pronto"} tone={runningId ? "warn" : "safe"} />}
        />
        <dl className="status-list">
          <div><dt>ollama</dt><dd>{data.models.ollamaRunning ? "ONLINE" : "OFFLINE"}</dd></div>
          <div><dt>datasets</dt><dd>{data.experimental?.totals.datasets || 0}</dd></div>
          <div><dt>amostras</dt><dd>{data.experimental?.totals.samples || 0}</dd></div>
          <div><dt>experimentos</dt><dd>{data.experimental?.totals.experiments || 0}</dd></div>
        </dl>
        <TerminalTabs tabs={LAB_SECTIONS} active={section} onChange={setSection} label="Laboratorio experimental" />
      </TerminalPanel>

      {section === "benchmark" && (
        <TerminalPanel title="BENCHMARK SIMPLES">
          <SectionHeader
            title="Comparar modelos em uma amostra"
            description="Cole um texto suspeito, escolha ate 3 modelos e veja consenso, divergencias e tempo de resposta."
          />
          <dl className="status-list">
            <div><dt>comparacao</dt><dd>{models.length} MODELOS</dd></div>
            <div><dt>instalados</dt><dd>{data.models.installed.length}</dd></div>
            <div><dt>foco</dt><dd>GEMMA / LLAMA / QWEN</dd></div>
            <div><dt>modo</dt><dd>AMOSTRA UNICA</dd></div>
          </dl>
          <div className="model-select">
            {available.map((model) => (
              <label key={model}>
                <input
                  type="checkbox"
                  checked={models.includes(model)}
                  onChange={() => setModels((current) => current.includes(model) ? current.filter((item) => item !== model) : [...current, model].slice(0, 3))}
                />
                <span>{model}</span>
              </label>
            ))}
          </div>
          <textarea
            className="terminal-input short"
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="C:\LABORATORIO> cole uma amostra para comparar Gemma, Llama e Qwen..."
          />
          <div className="command-row">
            <button type="button" onClick={run} disabled={busy || !text.trim()}>{busy ? "EXECUTANDO" : "COMPARAR MODELOS"}</button>
          </div>
          <BenchmarkResults results={results} comparison={comparison} />
        </TerminalPanel>
      )}

      {section === "datasets" && (
        <TerminalPanel title="DATASETS COM GROUND TRUTH">
          <SectionHeader
            title="Importar base validada"
            description="Envie CSV, JSON ou JSONL com texto e classe correta para medir o desempenho real."
          />
          <div className="settings-grid">
            <label>Nome do dataset<input value={datasetName} onChange={(event) => setDatasetName(event.target.value)} placeholder="cyberdetect_eval_v1" /></label>
            <label>Versao<input value={datasetVersion} onChange={(event) => setDatasetVersion(event.target.value)} /></label>
          </div>
          <div className="command-row">
            <label className="file-command">
              <input type="file" accept=".csv,.json,.jsonl" onChange={(event) => importDataset(event.target.files?.[0])} />
              IMPORT CSV/JSON/JSONL
            </label>
          </div>
          <DatasetList datasets={datasets} />
          {importErrors.length > 0 && <pre className="text-preview">{importErrors.slice(0, 10).join("\n")}</pre>}
        </TerminalPanel>
      )}

      {section === "experimentos" && (
        <TerminalPanel title="EXPERIMENTO EM LOTE">
          <SectionHeader
            title="Rodar dataset contra modelos"
            description="Escolha a base, modelos e abordagem. O progresso aparece abaixo e pode ser retomado se houver interrupcao."
            action={<StatusLabel label={activeExperiment?.status ? String(activeExperiment.status) : "sem execucao"} tone={statusTone(activeExperiment?.status)} />}
          />
          <div className="settings-grid">
            <label>Dataset
              <select value={selectedDatasetId} onChange={(event) => setSelectedDatasetId(Number(event.target.value))}>
                <option value={0}>SEM DATASET</option>
                {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.name} :: {dataset.total_samples || dataset.sample_count || 0}</option>)}
              </select>
            </label>
            <label>Amostras<input type="number" min="0" value={sampleLimit} onChange={(event) => setSampleLimit(event.target.value)} /></label>
            <label>Seed<input type="number" value={seed} onChange={(event) => setSeed(event.target.value)} /></label>
          </div>
          <div className="model-select">
            {available.map((model) => (
              <label key={model}>
                <input
                  type="checkbox"
                  checked={models.includes(model)}
                  onChange={() => setModels((current) => current.includes(model) ? current.filter((item) => item !== model) : [...current, model].slice(0, 3))}
                />
                <span>{model}</span>
              </label>
            ))}
          </div>
          <div className="model-select">
            {[
              ["ai_only", "SOMENTE IA"],
              ["heuristic_only", "SOMENTE HEURISTICAS"],
              ["hybrid", "HIBRIDO"],
            ].map(([key, label]) => (
              <label key={key}>
                <input type="checkbox" checked={approaches.includes(key)} onChange={() => toggleApproach(key)} />
                <span>{label}</span>
              </label>
            ))}
          </div>
          <div className="command-row">
            <button type="button" onClick={startBatch}>INICIAR EXPERIMENTO</button>
            <button type="button" onClick={resumeBatch} disabled={!activeExperiment}>CONTINUAR</button>
            <button type="button" onClick={cancelBatch} disabled={!runningId}>CANCELAR</button>
            <button type="button" onClick={() => exportExperimentFile("csv")} disabled={!activeExperiment}>EXPORTAR CSV</button>
            <button type="button" onClick={() => exportExperimentFile("json")} disabled={!activeExperiment}>EXPORTAR JSON</button>
            <button type="button" onClick={generateReport} disabled={!activeExperiment}>RELATORIO</button>
          </div>
          <ExperimentProgress experiment={activeExperiment} />
        </TerminalPanel>
      )}

      {section === "metricas" && (
        <TerminalPanel title="METRICAS DO EXPERIMENTO">
          <SectionHeader
            title="Ler resultado final"
            description="Veja rankings, metricas por modelo, matriz de confusao e comparacao entre IA, regras e hibrido."
          />
          <RankingSummary rankings={data.experimental?.rankings || {}} />
          <MetricsTable metrics={activeMetrics} />
          <ConfusionMatrices metrics={activeMetrics} />
          <SectionHeader title="Comparacao de abordagens" description="Quando disponivel, mostra somente IA, somente regras e hibrido lado a lado." />
          <MetricsTable metrics={activeMetrics.filter((item) => ["ai_only", "heuristic_only", "hybrid"].includes(item.approach))} />
        </TerminalPanel>
      )}

      {section === "thresholds" && (
        <TerminalPanel title="THRESHOLD CALIBRATION">
          <SectionHeader
            title="Ajustar sensibilidade"
            description="Teste diferentes limites de score para escolher o equilibrio entre falsos positivos e falsos negativos."
          />
          <div className="settings-grid">
            <label>Thresholds<input value={thresholdInput} onChange={(event) => setThresholdInput(event.target.value)} /></label>
          </div>
          <div className="command-row">
            <button type="button" onClick={runThresholdCalibration}>CALIBRAR</button>
          </div>
          <ThresholdCalibrationTable rows={thresholdRows} />
        </TerminalPanel>
      )}

      {section === "robustez" && (
        <TerminalPanel title="ROBUSTEZ">
          <SectionHeader
            title="Testar variacoes da mesma amostra"
            description="Mede se o classificador permanece estavel com acentos, espacos, caixa, pontuacao e outros ruidos."
          />
          <dl className="status-list">
            <div><dt>variantes</dt><dd>base / acentos / espacos / caixa / pontuacao / linhas / leet / unicode / erros / parafrase</dd></div>
            <div><dt>limite</dt><dd>10 por amostra</dd></div>
          </dl>
          <div className="command-row">
            <button type="button" onClick={startRobustness}>EXECUTAR ROBUSTEZ</button>
            <button type="button" onClick={cancelBatch} disabled={!runningId}>CANCELAR</button>
          </div>
          <RobustnessSummary metrics={activeMetrics} />
        </TerminalPanel>
      )}

      {section === "ocr" && (
        <TerminalPanel title="OCR BENCHMARK">
          <SectionHeader
            title="Medir qualidade do OCR"
            description="Compare texto esperado com texto extraido ou teste pipelines usando uma imagem real."
          />
          <div className="settings-grid">
            <label>Texto esperado para imagem
              <input value={ocrExpectedText} onChange={(event) => setOcrExpectedText(event.target.value)} placeholder="Opcional: ground truth textual" />
            </label>
          </div>
          <div className="command-row">
            <label className="file-command">
              <input type="file" accept=".csv,.json,.jsonl" onChange={(event) => runOcrBenchmark(event.target.files?.[0])} />
              IMPORT OCR CSV/JSON/JSONL
            </label>
            <label className="file-command">
              <input type="file" accept="image/*" onChange={(event) => runOcrImageBenchmark(event.target.files?.[0])} />
              TESTAR IMAGEM OCR
            </label>
          </div>
          <OcrBenchmarkSummary result={ocrBenchmark} />
          <OcrPipelineSummary result={ocrImageBenchmark} />
        </TerminalPanel>
      )}
    </>
  );
}

function DatasetList({ datasets }: { datasets: ExperimentalDataset[] }) {
  if (!datasets.length) return <p className="empty-terminal">&gt; nenhum dataset importado_</p>;
  return (
    <div className="dataset-list">
      {datasets.map((dataset) => (
        <article key={dataset.id}>
          <strong>{dataset.name}</strong>
          <span>v{dataset.version}</span>
          <em>{dataset.total_samples || dataset.sample_count || 0} amostras</em>
          <p>
            SEGURO {dataset.label_distribution?.SEGURO || 0} | SUSPEITO {dataset.label_distribution?.SUSPEITO || 0} | GOLPE {dataset.label_distribution?.GOLPE || 0}
          </p>
        </article>
      ))}
    </div>
  );
}

function ExperimentProgress({ experiment }: { experiment?: ExperimentItem }) {
  if (!experiment) return <p className="empty-terminal">&gt; nenhum experimento executado_</p>;
  const progress = Number(experiment.progress_percent || 0);
  return (
    <div className="experiment-progress">
      <div>
        <strong>{experiment.id}</strong>
        <span>{String(experiment.status || "N/A").toUpperCase()}</span>
      </div>
      <i style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
      <p>
        {experiment.completed_results || 0} / {experiment.expected_results || 0} :: erros {experiment.error_results || 0} :: {progress.toFixed(1)}%
      </p>
    </div>
  );
}

function percent(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "N/A";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function RankingSummary({ rankings }: { rankings: ExperimentalData["rankings"] }) {
  const rows = [
    ["maior accuracy", rankings?.best_accuracy],
    ["maior precision", rankings?.best_precision],
    ["maior recall", rankings?.best_recall],
    ["maior f1", rankings?.best_f1],
    ["menor fnr", rankings?.lowest_false_negative_rate],
    ["mais rapido", rankings?.fastest],
  ];

  return (
    <div className="ranking-summary">
      {rows.map(([label, item]) => (
        <article key={String(label)}>
          <span>{String(label)}</span>
          <strong>{item && typeof item === "object" ? `${item.model || "-"} :: ${approachLabel(item.approach)}` : "N/A"}</strong>
        </article>
      ))}
    </div>
  );
}

function MetricsTable({ metrics }: { metrics: ExperimentMetric[] }) {
  if (!metrics.length) return <p className="empty-terminal">&gt; SEM DADOS / NAO EXECUTADO_</p>;
  return (
    <div className="metrics-table">
      <div className="metrics-row header">
        <span>MODELO</span>
        <span>ABORDAGEM</span>
        <span>ACC</span>
        <span>PREC</span>
        <span>RECALL</span>
        <span>F1</span>
        <span>FPR</span>
        <span>FNR</span>
        <span>LAT</span>
      </div>
      {metrics.map((item) => (
        <div className="metrics-row" key={`${item.model}-${item.approach}`}>
          <strong>{item.model}</strong>
          <span>{approachLabel(item.approach)}</span>
          <span>{percent(item.metrics.accuracy)}</span>
          <span>{percent(item.metrics.macro?.precision)}</span>
          <span>{percent(item.metrics.macro?.recall)}</span>
          <span>{percent(item.metrics.macro?.f1)}</span>
          <span>{percent(item.metrics.false_positive_rate)}</span>
          <span>{percent(item.metrics.false_negative_rate)}</span>
          <span>{item.metrics.latency?.average_ms ?? "N/A"}ms</span>
        </div>
      ))}
    </div>
  );
}

function ThresholdCalibrationTable({ rows }: { rows: ThresholdRow[] }) {
  if (!rows.length) return <p className="empty-terminal">&gt; execute a calibracao sobre um experimento com scores_</p>;
  return (
    <div className="metrics-table">
      <div className="metrics-row header">
        <span>MODELO</span>
        <span>ABORDAGEM</span>
        <span>THR</span>
        <span>ACC</span>
        <span>PREC</span>
        <span>RECALL</span>
        <span>F1</span>
        <span>FPR</span>
        <span>FNR</span>
      </div>
      {rows.map((row) => (
        <div className="metrics-row" key={`${row.model}-${row.approach}-${row.threshold}`}>
          <strong>{row.model}</strong>
          <span>{approachLabel(row.approach)}</span>
          <span>{row.threshold}</span>
          <span>{percent(row.accuracy)}</span>
          <span>{percent(row.precision)}</span>
          <span>{percent(row.recall)}</span>
          <span>{percent(row.f1)}</span>
          <span>{percent(row.false_positive_rate)}</span>
          <span>{percent(row.false_negative_rate)}</span>
        </div>
      ))}
    </div>
  );
}

function ConfusionMatrices({ metrics }: { metrics: ExperimentMetric[] }) {
  if (!metrics.length) return <p className="empty-terminal">&gt; SEM DADOS / MATRIZ NAO GERADA_</p>;
  return (
    <div className="confusion-grid">
      {metrics.map((item) => {
        const labels = item.metrics.confusion_matrix?.labels || [];
        const matrix = item.metrics.confusion_matrix?.matrix || [];
        return (
          <article key={`${item.model}-${item.approach}`}>
            <strong>{item.model} :: {approachLabel(item.approach)}</strong>
            <table>
              <thead>
                <tr>
                  <th>REAL\PRED</th>
                  {labels.map((label) => <th key={label}>{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {matrix.map((row, index) => (
                  <tr key={labels[index] || index}>
                    <th>{labels[index]}</th>
                    {row.map((value, col) => <td key={`${index}-${col}`}>{value}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            <p>FP {item.metrics.errors?.false_positives?.length || 0} :: FN {item.metrics.errors?.false_negatives?.length || 0}</p>
          </article>
        );
      })}
    </div>
  );
}

function RobustnessSummary({ metrics }: { metrics: ExperimentMetric[] }) {
  const rows = metrics
    .map((item) => ({
      model: item.model,
      approach: item.approach,
      stability: item.metrics.robustness?.average_stability_rate as number | null | undefined,
      samples: item.metrics.robustness?.sample_count as number | undefined,
    }))
    .filter((item) => item.stability !== undefined && item.stability !== null);

  if (!rows.length) return <p className="empty-terminal">&gt; SEM DADOS / ROBUSTEZ NAO EXECUTADA_</p>;
  return (
    <div className="metrics-table">
      <div className="metrics-row compact">
        <span>MODELO</span>
        <span>ABORDAGEM</span>
        <span>ESTABILIDADE</span>
        <span>AMOSTRAS</span>
      </div>
      {rows.map((item) => (
        <div className="metrics-row compact" key={`${item.model}-${item.approach}`}>
          <strong>{item.model}</strong>
          <span>{approachLabel(item.approach)}</span>
          <span>{percent(item.stability)}</span>
          <span>{item.samples || 0}</span>
        </div>
      ))}
    </div>
  );
}

function OcrBenchmarkSummary({ result }: { result: OcrBenchmarkResult | null }) {
  if (!result) return <p className="empty-terminal">&gt; informe CSV/JSON/JSONL com expected_text e ocr_text_</p>;
  return (
    <dl className="status-list">
      <div><dt>amostras</dt><dd>{String(result.sample_count ?? 0)}</dd></div>
      <div><dt>wer medio</dt><dd>{percent(result.average_wer as number | null)}</dd></div>
      <div><dt>cer medio</dt><dd>{percent(result.average_cer as number | null)}</dd></div>
      <div><dt>arquivo</dt><dd>{String(result.path || "N/A")}</dd></div>
    </dl>
  );
}

function OcrPipelineSummary({ result }: { result: OcrBenchmarkResult | null }) {
  if (!result) return <p className="empty-terminal">&gt; envie imagem para comparar pipelines OCR_</p>;
  return (
    <>
      <dl className="status-list">
        <div><dt>pipelines</dt><dd>{String(result.sample_count ?? 0)}</dd></div>
        <div><dt>melhor</dt><dd>{String(result.best_pipeline || "N/A")}</dd></div>
        <div><dt>wer medio</dt><dd>{percent(result.average_wer as number | null)}</dd></div>
        <div><dt>cer medio</dt><dd>{percent(result.average_cer as number | null)}</dd></div>
      </dl>
      <div className="metrics-table">
        <div className="metrics-row ocr-pipeline header">
          <span>PIPELINE</span>
          <span>WER</span>
          <span>CER</span>
          <span>MS</span>
          <span>CHARS</span>
          <span>PREVIEW</span>
        </div>
        {(result.pipelines || []).map((row) => (
          <div className="metrics-row ocr-pipeline" key={row.name}>
            <strong>{row.name}</strong>
            <span>{percent(row.wer as number | null)}</span>
            <span>{percent(row.cer as number | null)}</span>
            <span>{row.latency_ms ?? 0}</span>
            <span>{row.extracted_length ?? 0}</span>
            <span>{short(row.ocr_text_preview, 96)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function LogsConsole({ data, onRefresh }: { data: DashboardData; onRefresh: () => void }) {
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState("todos");
  const [hideTail, setHideTail] = useState(false);
  const visibleEvents = useMemo(() => {
    const needle = query.toLowerCase().trim();
    return data.events
      .filter((event) => level === "todos" || event.level.toLowerCase() === level)
      .filter((event) => !needle || `${event.category} ${event.level} ${event.message}`.toLowerCase().includes(needle))
      .slice(0, 18);
  }, [data.events, level, query]);
  const logTail = useMemo(() => {
    if (hideTail) return "";
    const needle = query.toLowerCase().trim();
    return data.logs.tail
      .map((file) => {
        const lines = needle ? file.lines.filter((line) => line.toLowerCase().includes(needle)) : file.lines;
        return lines.length ? `--- ${file.name} ---\n${lines.join("")}` : "";
      })
      .filter(Boolean)
      .join("\n");
  }, [data.logs.tail, hideTail, query]);

  return (
    <>
      <TerminalPanel title="EVENTOS REAIS">
        <SectionHeader
          title="Auditoria operacional"
          description="Filtre eventos do sistema, OCR, IA, benchmark e erros sem abrir arquivos manualmente."
          action={<button type="button" onClick={onRefresh}>ATUALIZAR</button>}
        />
        <div className="history-filter">
          <input value={query} onChange={(event) => { setQuery(event.target.value); setHideTail(false); }} placeholder="C:\LOGS> buscar..." />
          <select value={level} onChange={(event) => setLevel(event.target.value)}>
            <option value="todos">TODOS</option>
            <option value="info">INFO</option>
            <option value="warn">WARN</option>
            <option value="error">ERROR</option>
          </select>
          <button type="button" onClick={() => { setQuery(""); setLevel("todos"); setHideTail(false); }}>LIMPAR FILTRO</button>
        </div>
        <EventList events={visibleEvents} />
      </TerminalPanel>
      <TerminalPanel title="ARQUIVOS DE LOG">
        <div className="log-files">
          {data.logs.files.length ? data.logs.files.map((file) => <span key={file.name}>{file.name} :: {file.size}b</span>) : <span>sem arquivos .log</span>}
        </div>
        <div className="command-row">
          <button type="button" onClick={() => setHideTail((value) => !value)}>{hideTail ? "MOSTRAR TERMINAL" : "LIMPAR TERMINAL"}</button>
        </div>
        <pre className="log-tail">{logTail || "C:\\LOGS> sem linhas para exibir."}</pre>
      </TerminalPanel>
    </>
  );
}

function HistoryConsole({
  data,
  onRefresh,
  updateData,
  setToast,
}: {
  data: DashboardData;
  onRefresh: () => void;
  updateData: (patch: Partial<DashboardData>) => void;
  setToast: (value: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(
    () => data.analyses.filter((item) => `${item.classification} ${item.scam_type} ${item.summary} ${item.model} ${item.source} ${item.input_text}`.toLowerCase().includes(query.toLowerCase())),
    [data.analyses, query]
  );
  const [selectedId, setSelectedId] = useState<number | null>(filtered[0]?.id || null);
  const selectedItem = filtered.find((item) => item.id === selectedId) || filtered[0];

  useEffect(() => {
    if (!selectedId && filtered[0]?.id) setSelectedId(filtered[0].id);
  }, [filtered, selectedId]);

  const remove = async (id: number) => {
    const response = (await api()?.deleteHistory?.(id)) as { ok: boolean; analyses: AnalysisItem[] } | undefined;
    if (response?.ok) {
      updateData({ analyses: response.analyses });
      setToast("HISTORICO :: registro removido");
      if (selectedId === id) setSelectedId(null);
    }
  };

  const clearAll = async () => {
    if (!window.confirm("Limpar todo o historico local de analises?")) return;
    const response = (await api()?.clearHistory?.()) as { ok: boolean; analyses?: AnalysisItem[] } | undefined;
    if (response?.ok) {
      updateData({ analyses: response.analyses || [] });
      setSelectedId(null);
      setToast("HISTORICO :: limpo");
      onRefresh();
    } else {
      setToast("HISTORICO :: falha ao limpar");
    }
  };

  const validate = async (id: number, groundTruth: string) => {
    const response = (await api()?.validateAnalysis?.(id, groundTruth, "Validado no historico", "manual")) as ApiResult<{ analyses?: AnalysisItem[] }> | undefined;
    if (response?.ok) {
      if (response.analyses) updateData({ analyses: response.analyses });
      setToast(`VALIDACAO :: ${groundTruth}`);
      onRefresh();
    } else {
      setToast(response?.error || "VALIDACAO :: falha");
    }
  };

  const markFeedback = async (id: number, isCorrect: boolean, correctClass = "") => {
    const response = (await api()?.markAnalysisFeedback?.(id, isCorrect, correctClass)) as { ok: boolean; analyses: AnalysisItem[] } | undefined;
    if (response?.ok) {
      updateData({ analyses: response.analyses });
      setToast(isCorrect ? "FEEDBACK :: correta" : `GROUND TRUTH :: ${correctClass}`);
    } else {
      setToast("FEEDBACK :: falha");
    }
  };

  const exportFile = async (type: "csv" | "json") => {
    const response = (await api()?.exportHistory?.(type)) as { ok: boolean; path?: string } | undefined;
    setToast(response?.ok ? `EXPORT :: ${response.path}` : "EXPORT :: falha");
  };

  return (
    <div className="split-workspace">
      <TerminalPanel title="HISTORICO LOCAL SQLITE">
        <SectionHeader
          title="Registros salvos"
          description="Pesquise, abra um dossie, valide ground truth ou exporte o historico local."
          action={<StatusLabel label={`${filtered.length} registros`} tone={filtered.length ? "safe" : "muted"} />}
        />
        <div className="history-filter">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="C:\HISTORICO> pesquisar..." />
          <button type="button" onClick={() => exportFile("csv")}>CSV</button>
          <button type="button" onClick={() => exportFile("json")}>JSON</button>
          <button type="button" onClick={clearAll}>LIMPAR</button>
        </div>
        <AnalysisList
          items={filtered.slice(0, 16)}
          selectedId={selectedItem?.id}
          onSelect={setSelectedId}
          onDelete={remove}
          onFeedback={markFeedback}
        />
      </TerminalPanel>
      <TerminalPanel title="DOSSIER SALVO">
        <AnalysisDetailPanel item={selectedItem} onValidate={(label) => selectedItem && validate(selectedItem.id, label)} />
      </TerminalPanel>
    </div>
  );
}

type SettingsSection = "ia" | "ocr" | "monitoramento" | "sistema" | "apps";

const SETTINGS_SECTIONS: Array<{ key: SettingsSection; label: string; hint: string }> = [
  { key: "ia", label: "IA", hint: "modelos e API" },
  { key: "ocr", label: "OCR", hint: "idioma" },
  { key: "monitoramento", label: "Monitoramento", hint: "captura" },
  { key: "sistema", label: "Sistema", hint: "diagnostico" },
  { key: "apps", label: "Apps", hint: "alvos" },
];

function SettingsConsole({
  data,
  onRefresh,
  updateData,
  setToast,
}: {
  data: DashboardData;
  onRefresh: () => void;
  updateData: (patch: Partial<DashboardData>) => void;
  setToast: (value: string) => void;
}) {
  const [settings, setSettings] = useState<Record<string, string | boolean | number>>(data.settings);
  const [appName, setAppName] = useState("");
  const [diagnostics, setDiagnostics] = useState<DiagnosticReport | null>(null);
  const [diagnosticsBusy, setDiagnosticsBusy] = useState(false);
  const [section, setSection] = useState<SettingsSection>("ia");

  useEffect(() => {
    setSettings(data.settings);
  }, [data.settings]);

  const setField = (key: string, value: string | boolean | number) => setSettings((current) => ({ ...current, [key]: value }));

  const save = async () => {
    const response = (await api()?.saveSettings?.(settings)) as ApiResult<{ settings: Record<string, string | boolean | number> }> | undefined;
    setToast(response?.ok ? "CONFIG :: salva" : "CONFIG :: falha ao salvar");
    onRefresh();
  };

  const addApp = async () => {
    if (!appName.trim()) return;
    const response = (await api()?.addApp?.(appName)) as ApiResult<{ apps?: MonitoredApp[] }> | undefined;
    setToast(response?.ok ? "APP :: adicionado" : "APP :: nao adicionado");
    if (response?.apps) updateData({ apps: response.apps });
    setAppName("");
  };

  const removeApp = async (id: number) => {
    const response = (await api()?.removeApp?.(id)) as ApiResult<{ apps?: MonitoredApp[] }> | undefined;
    if (response?.apps) updateData({ apps: response.apps });
    if (response?.ok) setToast("APP :: removido");
  };

  const toggleApp = async (id: number, enabled: boolean) => {
    const response = (await api()?.setAppEnabled?.(id, enabled)) as ApiResult<{ apps?: MonitoredApp[] }> | undefined;
    if (response?.apps) updateData({ apps: response.apps });
    setToast(response?.ok ? "APP :: monitoramento atualizado" : response?.error || "APP :: indisponivel");
  };

  const downloadApp = async (id: number) => {
    const response = (await api()?.openAppDownload?.(id)) as ApiResult<{ url?: string; apps?: MonitoredApp[] }> | undefined;
    if (response?.apps) updateData({ apps: response.apps });
    setToast(response?.ok ? `DOWNLOAD :: ${response.url}` : response?.error || "DOWNLOAD :: indisponivel");
  };

  const runDiagnostics = async () => {
    setDiagnosticsBusy(true);
    try {
      const response = (await api()?.runSystemDiagnostics?.({
        includeCapture: true,
        includeExternalApi: true,
        includeOllama: true,
      })) as ApiResult<{ diagnostics?: DiagnosticReport }> | undefined;
      if (response?.ok && response.diagnostics) {
        setDiagnostics(response.diagnostics);
        setToast(`DIAGNOSTICO :: ${response.diagnostics.summary.status}`);
      } else {
        setToast(response?.error || "DIAGNOSTICO :: falha");
      }
    } finally {
      setDiagnosticsBusy(false);
    }
  };

  return (
    <>
      <TerminalPanel title="MODELOS E IAs">
        <SectionHeader
          title="Central de configuracao"
          description="Ajuste modelos, OCR, captura automatica, diagnostico e apps monitorados."
          action={<StatusLabel label={data.models.ollamaRunning ? "online" : "local"} tone={data.models.ollamaRunning ? "safe" : "warn"} />}
        />
        <dl className="status-list">
          <div><dt>ollama</dt><dd>{data.models.ollamaRunning ? "ONLINE" : "OFFLINE"}</dd></div>
          <div><dt>modelo padrao</dt><dd>{data.system.model || data.settings.defaultModel || "-"}</dd></div>
          <div><dt>instalados</dt><dd>{data.models.installed.length ? data.models.installed.join(" / ") : "nenhum"}</dd></div>
          <div><dt>suportados</dt><dd>{data.models.supported.length ? data.models.supported.join(" / ") : "gemma / llama / qwen"}</dd></div>
        </dl>
        <TerminalTabs tabs={SETTINGS_SECTIONS} active={section} onChange={setSection} label="Configuracoes" />
      </TerminalPanel>

      {section === "ia" && (
        <TerminalPanel title="IA E MODELOS">
          <SectionHeader title="Modelos de classificacao" description="Defina provider externo e modelo local usado como padrao." />
          <div className="settings-grid">
            <label>API externa<input value={String(settings.provider || "")} onChange={(event) => setField("provider", event.target.value)} /></label>
            <label>Modelo externo<input value={String(settings.externalModel || "")} onChange={(event) => setField("externalModel", event.target.value)} /></label>
            <label>Modelo local<input value={String(settings.defaultModel || "")} onChange={(event) => setField("defaultModel", event.target.value)} /></label>
          </div>
          <div className="command-row">
            <button type="button" onClick={save}>SALVAR CONFIG</button>
          </div>
        </TerminalPanel>
      )}

      {section === "ocr" && (
        <TerminalPanel title="OCR">
          <SectionHeader title="Leitura de imagens" description="Configure o idioma usado para extrair texto de prints e capturas." />
          <div className="settings-grid">
            <label>Idioma OCR<input value={String(settings.ocrLanguage || "")} onChange={(event) => setField("ocrLanguage", event.target.value)} /></label>
          </div>
          <div className="command-row">
            <button type="button" onClick={save}>SALVAR CONFIG</button>
          </div>
        </TerminalPanel>
      )}

      {section === "monitoramento" && (
        <TerminalPanel title="MONITORAMENTO">
          <SectionHeader title="Captura automatica" description="Controle intervalo, sensibilidade e gatilho inteligente da protecao." />
          <div className="settings-grid">
            <label>Cooldown<input type="number" value={String(settings.cooldownSeconds || 30)} onChange={(event) => setField("cooldownSeconds", event.target.value)} /></label>
            <label>Sensibilidade<input type="number" value={String(settings.sensitivity || 70)} onChange={(event) => setField("sensitivity", event.target.value)} /></label>
            <label className="check-row"><input type="checkbox" checked={Boolean(settings.smartTrigger)} onChange={(event) => setField("smartTrigger", event.target.checked)} /> Trigger inteligente</label>
            <label className="check-row"><input type="checkbox" checked={Boolean(settings.autoProtection)} onChange={(event) => setField("autoProtection", event.target.checked)} /> Captura automatica</label>
          </div>
          <div className="command-row">
            <button type="button" onClick={save}>SALVAR CONFIG</button>
          </div>
        </TerminalPanel>
      )}

      {section === "sistema" && (
        <TerminalPanel title="DIAGNOSTICO DO SISTEMA">
          <SectionHeader title="Autodiagnostico" description="Verifica captura, OCR, modelos locais e integracao externa." />
          <div className="command-row">
            <button type="button" onClick={runDiagnostics} disabled={diagnosticsBusy}>
              {diagnosticsBusy ? "EXECUTANDO..." : "EXECUTAR AUTODIAGNOSTICO"}
            </button>
          </div>
          <DiagnosticResults report={diagnostics} />
        </TerminalPanel>
      )}

      {section === "apps" && (
        <TerminalPanel title="APPS MONITORADOS">
          <SectionHeader title="Aplicativos observados" description="Ative, remova ou adicione apps que devem ser reconhecidos pelo monitoramento." />
          <div className="history-filter">
            <input value={appName} onChange={(event) => setAppName(event.target.value)} placeholder="C:\CONFIG> novo app..." />
            <button type="button" onClick={addApp}>ADD</button>
          </div>
          <AppList apps={data.apps} onToggle={toggleApp} onRemove={removeApp} onDownload={downloadApp} />
        </TerminalPanel>
      )}
    </>
  );
}

function DiagnosticResults({ report }: { report: DiagnosticReport | null }) {
  if (!report) return <p className="empty-terminal">&gt; diagnostico ainda nao executado_</p>;
  const summary = report.summary;
  return (
    <div className="diagnostic-results">
      <dl className="status-list">
        <div><dt>status</dt><dd>{summary.status}</dd></div>
        <div><dt>checks</dt><dd>{summary.total} total / {summary.ok} ok / {summary.warn} warn / {summary.error} erro</dd></div>
        <div><dt>gerado</dt><dd>{fmtDate(report.generated_at)}</dd></div>
      </dl>
      <div className="event-list diagnostic-list">
        {report.checks.map((check) => (
          <article key={check.id}>
            <span>{check.category}</span>
            <strong>{short(check.label, 32)}</strong>
            <em>{check.status}</em>
            <p>{short(check.detail, 150)}</p>
          </article>
        ))}
      </div>
      {report.notes?.length ? <p className="empty-terminal">&gt; {short(report.notes.join(" "), 180)}</p> : null}
    </div>
  );
}

const AppList = memo(function AppList({
  apps,
  onToggle,
  onRemove,
  onDownload,
}: {
  apps: MonitoredApp[];
  onToggle?: (id: number, enabled: boolean) => void;
  onRemove?: (id: number) => void;
  onDownload?: (id: number) => void;
}) {
  if (!apps.length) return <p className="empty-terminal">&gt; nenhum app monitorado_</p>;
  return (
    <div className="app-list">
      {apps.map((app) => {
        const canMonitor = app.can_monitor !== false;
        const checked = canMonitor && Boolean(app.enabled);
        const status = app.status_label || (checked ? "MONITORANDO" : "INSTALADO");
        const appLabel = app.canonical_name || app.name;
        const stateClass = !canMonitor
          ? "is-missing"
          : app.web_only
            ? "is-web"
            : app.active
              ? "is-active-app"
              : checked
                ? "is-monitoring"
                : "is-installed";
        const hint = app.lock_reason || app.install_hint || (app.is_custom ? "App customizado" : "Verificacao local");

        return (
          <article key={app.id} className={`app-card ${stateClass}`}>
            <label className="app-toggle" title={canMonitor ? "Alternar monitoramento" : app.lock_reason || "Nao instalado"}>
              <input
                type="checkbox"
                disabled={!canMonitor}
                checked={checked}
                onChange={(event) => onToggle?.(app.id, event.target.checked)}
              />
              <span className={`app-check ${checked ? "is-checked" : ""}`} aria-hidden="true" />
            </label>
            <AppIcon
              appId={app.app_key}
              name={appLabel}
              iconPath={app.icon_path}
              installed={canMonitor}
              status={app.status_label || app.status}
            />
            <div className="app-main">
              <strong>{appLabel}</strong>
              <small>{hint}</small>
            </div>
            <div className="app-status">
              <em>{status}</em>
              {checked && status !== "MONITORANDO" && <span>MONITORANDO</span>}
            </div>
            <div className="app-actions">
              {!canMonitor && app.download_url && onDownload && (
                <button type="button" onClick={() => onDownload(app.id)}>BAIXAR</button>
              )}
              {app.web_only && <span>VIA NAVEGADOR</span>}
              {onRemove && Boolean(app.is_custom) && <button type="button" onClick={() => onRemove(app.id)}>DEL</button>}
            </div>
          </article>
        );
      })}
    </div>
  );
});

function EventList({ events }: { events: EventItem[] }) {
  if (!events.length) return <p className="empty-terminal">&gt; sem eventos no buffer_</p>;
  return (
    <div className="event-list">
      {events.map((event) => (
        <article key={event.id}>
          <span>{fmtDate(event.created_at)}</span>
          <strong>{event.category}</strong>
          <em>{event.level}</em>
          <p>{short(event.message, 110)}</p>
        </article>
      ))}
    </div>
  );
}

const AnalysisList = memo(function AnalysisList({
  items,
  selectedId,
  onSelect,
  onDelete,
  onFeedback,
}: {
  items: AnalysisItem[];
  selectedId?: number;
  onSelect?: (id: number) => void;
  onDelete?: (id: number) => void;
  onFeedback?: (id: number, isCorrect: boolean, correctClass?: string) => void;
}) {
  if (!items.length) return <p className="empty-terminal">&gt; nenhum registro encontrado_</p>;
  return (
    <div className="analysis-list">
      {items.map((item) => {
        const predicted = item.predicted_class || item.classification || "ERRO";
        const validated = Boolean(item.validated);
        const correct = item.validation_correct === true || item.validation_correct === 1;
        const validationStatus = validated
          ? `GT ${item.ground_truth || "-"} ${correct ? "OK" : "DIVERGE"}`
          : item.scam_type || sourceLabel(item.source);

        return (
          <article key={item.id} className={`${riskTone(item.classification, item.score)} ${selectedId === item.id ? "is-selected" : ""}`}>
            <strong>{String(item.score ?? 0).padStart(3, "0")}</strong>
            <div>
              <span>{predicted} :: {validationStatus}</span>
              <p>{short(item.summary || item.recommendation || item.input_text, 120)}</p>
            </div>
            <em>{fmtDate(item.created_at)}</em>
            {onSelect && <button className="open-record" type="button" onClick={() => onSelect(item.id)}>ABRIR</button>}
            {onFeedback && (
              <div className="validation-actions">
                <button type="button" onClick={() => onFeedback(item.id, true)}>OK</button>
                {["SEGURO", "SUSPEITO", "GOLPE"].map((label) => (
                  <button key={label} type="button" onClick={() => onFeedback(item.id, false, label)}>{label.slice(0, 3)}</button>
                ))}
              </div>
            )}
            {onDelete && <button type="button" onClick={() => onDelete(item.id)}>DEL</button>}
          </article>
        );
      })}
    </div>
  );
});

function BenchmarkResults({ results, comparison }: { results: Array<Record<string, unknown>>; comparison: Record<string, unknown> | null }) {
  if (!results.length) return <p className="empty-terminal">&gt; benchmark aguardando amostra_</p>;
  const divergences = Array.isArray(comparison?.divergencias) ? comparison.divergencias : [];
  return (
    <div className="benchmark-results">
      {results.map((item) => (
        <article key={String(item.modelo)}>
          <strong>{String(item.modelo || "-")}</strong>
          <span>{String(item.classificacao || "ERRO")} :: {String(item.score_risco ?? "--")}/100</span>
          <p>{String(item.tempo_resposta_ms ?? "--")}ms</p>
        </article>
      ))}
      <div className="comparison-summary">
        <p>&gt; consenso :: {String(comparison?.consenso || "sem consenso")}</p>
        <p>&gt; tempo medio :: {String(comparison?.media_tempo_ms ?? "--")}ms</p>
        <p>&gt; score medio :: {String(comparison?.media_score ?? "--")}</p>
        <p>&gt; melhor resposta :: {String(comparison?.melhor_resposta_geral || "-")}</p>
        {divergences.length ? (
          <p>&gt; divergencias :: {divergences.map((item) => String(item)).join(" | ")}</p>
        ) : (
          <p>&gt; divergencias :: aguardando comparacao</p>
        )}
      </div>
    </div>
  );
}

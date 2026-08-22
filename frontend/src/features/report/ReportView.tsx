import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

type RiskPoint = {
  trecho?: string;
  motivo?: string;
  gravidade?: string;
};

type SuspiciousLink = {
  conteudo?: string;
  motivo?: string;
};

type QrAnalysis = {
  id?: string;
  kind?: string;
  content_preview?: string;
  content?: string;
  score_estrutural?: number;
  structural_score?: number;
  is_url?: boolean;
  is_pix?: boolean;
};

type RiskFactor = {
  fator?: string;
  factor?: string;
  peso?: number;
  weight?: number;
  categoria?: string;
  category?: string;
  evidencia?: string;
  evidence?: string;
};

type ReportData = {
  classificacao?: string;
  score_risco?: number;
  confianca_analise?: string;
  tipo_golpe?: string | null;
  resumo?: string;
  recomendacao?: string;
  pontos_suspeitos?: RiskPoint[];
  links_ou_arquivos_suspeitos?: SuspiciousLink[];
  qr_analysis?: QrAnalysis[];
  analise_qr?: QrAnalysis[];
  tecnicas_engenharia_social?: string[];
  fatores_risco?: RiskFactor[];
  acao_recomendada?: string;
  [key: string]: unknown;
};

function clampScore(value: unknown) {
  const score = Number(value || 0);
  if (!Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function cleanText(value: unknown, fallback = "") {
  const text = String(value ?? "").trim();
  if (!text) return fallback;

  const replacements: Array<[string, string]> = [
    ["ÃƒÂ¡", "á"],
    ["Ãƒ ", "à"],
    ["ÃƒÂ¢", "â"],
    ["ÃƒÂ£", "ã"],
    ["ÃƒÂ©", "é"],
    ["ÃƒÂª", "ê"],
    ["ÃƒÂ­", "í"],
    ["ÃƒÂ³", "ó"],
    ["ÃƒÂ´", "ô"],
    ["ÃƒÂµ", "õ"],
    ["ÃƒÂº", "ú"],
    ["ÃƒÂ§", "ç"],
    ["Ã¢â‚¬Â¢", "-"],
    ["Ã¢â‚¬â€œ", "-"],
    ["Ã¢â‚¬â€", "-"],
    ["Ã¢â‚¬Å“", "\""],
    ["Ã¢â‚¬Â", "\""],
    ["Ã¢â‚¬Ëœ", "'"],
    ["Ã¢â‚¬â„¢", "'"],
    ["Ã‚", ""],
    ["ï¿½", ""],
  ];

  return replacements.reduce((current, [broken, fixed]) => current.split(broken).join(fixed), text);
}

function nowStamp() {
  return new Date().toISOString().slice(0, 19).replace("T", " ");
}

function severityFor(classification: string) {
  if (classification.includes("GOLPE")) return "danger";
  if (classification.includes("SUSPEITO")) return "warn";
  if (classification.includes("SEGURO")) return "safe";
  return "neutral";
}

export function ReportView() {
  const [report, setReport] = useState<ReportData | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timeout = 0;

    function showLoadError(message: string) {
      setReport({
        classificacao: "ERRO",
        score_risco: 0,
        resumo: message,
        recomendacao: "Reabra o relatorio pelo painel principal ou tente gerar a analise novamente.",
      });
    }

    async function loadReport() {
      try {
        const data = await window.pywebview?.api?.getReportData?.();
        if (!cancelled) setReport((data as ReportData) || {});
      } catch {
        if (!cancelled) showLoadError("Nao foi possivel carregar os dados do relatorio.");
      } finally {
        window.clearTimeout(timeout);
      }
    }

    if (window.pywebview?.api?.getReportData) {
      loadReport();
    } else {
      window.addEventListener("pywebviewready", loadReport, { once: true });
      timeout = window.setTimeout(() => {
        if (!cancelled) showLoadError("API PyWebView indisponivel para carregar o relatorio.");
      }, 3500);
    }

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      window.removeEventListener("pywebviewready", loadReport);
    };
  }, []);

  const score = clampScore(report?.score_risco);
  const classification = cleanText(report?.classificacao, "ERRO").toUpperCase();
  const points = Array.isArray(report?.pontos_suspeitos) ? report.pontos_suspeitos : [];
  const links = Array.isArray(report?.links_ou_arquivos_suspeitos) ? report.links_ou_arquivos_suspeitos : [];
  const qrItems = Array.isArray(report?.qr_analysis) ? report.qr_analysis : Array.isArray(report?.analise_qr) ? report.analise_qr : [];
  const techniques = Array.isArray(report?.tecnicas_engenharia_social) ? report.tecnicas_engenharia_social : [];
  const riskFactors = Array.isArray(report?.fatores_risco) ? report.fatores_risco : [];
  const confidence = cleanText(report?.confianca_analise, "Nao informada");
  const action = cleanText(report?.acao_recomendada, report?.recomendacao || "Verifique por canais oficiais antes de agir.");
  const safeClassification = classification.replace(/[^A-Z0-9_-]/g, "") || "ERRO";
  const severity = severityFor(classification);
  const issueCode = useMemo(() => `CD-${String(score).padStart(3, "0")}-${safeClassification}`, [score, safeClassification]);

  if (!report) {
    return <AnalysisLoadingScreenShim />;
  }

  return (
    <main className={`report-screen report-${severity}`}>
      <section className="dossier">
        <header className="dossier-topline">
          <span>{classification} / CYBERDETECT</span>
          <span>{issueCode}</span>
          <span>CONFIDENTIAL ANALYSIS</span>
        </header>

        <div className="dossier-head">
          <div>
            <p className="micro-label">CYBERDETECT</p>
            <strong>crime digital // br</strong>
          </div>
          <div>
            <p className="micro-label">dossie de inteligencia</p>
            <strong>{issueCode}</strong>
          </div>
          <div>
            <p className="micro-label">nivel de ameaca</p>
            <strong>{classification}</strong>
          </div>
        </div>

        <section className="risk-terminal">
          <div className="risk-score-block">
            <p className="section-index">// 00</p>
            <div className="risk-score">
              <span>{score}</span>
              <em>/100</em>
            </div>
            <div className="risk-bars" aria-hidden="true">
              {Array.from({ length: 20 }).map((_, index) => (
                <span key={index} className={index < Math.ceil(score / 5) ? "active" : ""} />
              ))}
            </div>
          </div>

          <div className={`stamp stamp-${severity}`}>
            <small>// veredicto</small>
            <strong>{classification}</strong>
            <span>{cleanText(report.tipo_golpe, "analise comportamental")}</span>
          </div>
        </section>

        <section className="report-metrics" aria-label="Resumo tecnico">
          <Metric label="confianca" value={confidence} />
          <Metric label="tipo" value={cleanText(report.tipo_golpe, "Nao classificado")} />
          <Metric label="evidencias" value={String(points.length)} />
          <Metric label="fatores" value={String(riskFactors.length)} />
          <Metric label="qr" value={String(qrItems.length)} />
        </section>

        <ReportSection index="01" title="Resumo da analise">
          <p className="lead-text">{cleanText(report.resumo, "Nenhum resumo foi retornado pelo motor de analise.")}</p>
        </ReportSection>

        <ReportSection index="02" title="Recomendacao operacional">
          <p className="recommendation">{cleanText(report.recomendacao, "Verifique por canais oficiais antes de agir.")}</p>
        </ReportSection>

        <ReportSection index="03" title="Acao recomendada">
          <p className="recommendation strong-recommendation">{action}</p>
        </ReportSection>

        <ReportSection index="04" title="Composicao do risco">
          <div className="evidence-list">
            {riskFactors.length ? (
              riskFactors.map((factor, index) => {
                const weight = clampScore(factor.peso ?? factor.weight);
                const label = cleanText(factor.fator || factor.factor, "Fator de risco");
                const category = cleanText(factor.categoria || factor.category, "geral");
                const evidence = cleanText(factor.evidencia || factor.evidence, "Evidencia normalizada pelo backend.");

                return (
                  <article className="evidence-item" key={`${label}-${index}`}>
                    <span>+{String(weight).padStart(2, "0")}%</span>
                    <div>
                      <strong>{label}</strong>
                      <p>
                        <em>[{category.toUpperCase()}]</em>
                        {evidence}
                      </p>
                    </div>
                  </article>
                );
              })
            ) : (
              <p className="muted-text">Nenhum fator de risco foi aplicado ao calculo.</p>
            )}
          </div>
        </ReportSection>

        <ReportSection index="05" title="Evidencias interceptadas">
          <div className="evidence-list">
            {points.length ? (
              points.map((point, index) => (
                <article className="evidence-item" key={`${point.trecho}-${index}`}>
                  <span>{String(index + 1).padStart(3, "0")}</span>
                  <div>
                    <strong>{cleanText(point.trecho, "Trecho nao especificado")}</strong>
                    <p>
                      <em>[{cleanText(point.gravidade, "BAIXA").toUpperCase()}]</em>
                      {cleanText(point.motivo, "Sinal de risco identificado.")}
                    </p>
                  </div>
                </article>
              ))
            ) : (
              <p className="muted-text">Nenhuma evidencia suspeita foi identificada.</p>
            )}
          </div>
        </ReportSection>

        <ReportSection index="06" title="Vetores de engenharia social">
          <div className="tag-row">
            {techniques.length ? (
              techniques.map((technique) => (
                <span key={technique}>{cleanText(technique)}</span>
              ))
            ) : (
              <p className="muted-text">Nenhuma tecnica especifica foi retornada.</p>
            )}
          </div>
        </ReportSection>

        <ReportSection index="07" title="Links e arquivos">
          <div className="link-list">
            {links.length ? (
              links.map((link, index) => (
                <article key={`${link.conteudo}-${index}`}>
                  <strong>{cleanText(link.conteudo, "Item suspeito")}</strong>
                  <p>{cleanText(link.motivo, "Sem motivo detalhado.")}</p>
                </article>
              ))
            ) : (
              <p className="muted-text">Nenhum link ou arquivo suspeito foi retornado.</p>
            )}
          </div>
        </ReportSection>

        {qrItems.length > 0 && (
          <ReportSection index="08" title="QR Code">
            <div className="link-list">
              {qrItems.map((item, index) => {
                const kind = cleanText(item.kind, "text").toUpperCase();
                const score = clampScore(item.score_estrutural ?? item.structural_score);
                const markers = [item.is_url ? "URL" : "", item.is_pix ? "PIX" : ""].filter(Boolean).join(" / ");
                return (
                  <article key={`${item.id || item.content_preview || index}`}>
                    <strong>{kind} :: {String(score).padStart(3, "0")}/100 {markers ? `:: ${markers}` : ""}</strong>
                    <p>{cleanText(item.content_preview || item.content, "Conteudo do QR preservado como dado local.")}</p>
                  </article>
                );
              })}
            </div>
          </ReportSection>
        )}

        <footer className="dossier-footer">
          <div>
            <p className="micro-label">analista responsavel</p>
            <strong>CyberDetect AI / modulo de deteccao</strong>
          </div>
          <button type="button" onClick={() => window.pywebview?.api?.closeWindow?.()}>
            fechar relatorio
          </button>
          <div>
            <p className="micro-label">emitido em</p>
            <strong>{nowStamp()}</strong>
          </div>
        </footer>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ReportSection({ index, title, children }: { index: string; title: string; children: ReactNode }) {
  return (
    <section className="report-section">
      <aside>
        <strong>{index}</strong>
        <span>{title}</span>
      </aside>
      <div className="report-section-body">{children}</div>
    </section>
  );
}

function AnalysisLoadingScreenShim() {
  return (
    <main className="analysis-loading-screen">
      <section className="analysis-loader-panel">
        <div className="analysis-loader-copy">
          <p>CYBERDETECT / REPORT</p>
          <h1>Carregando relatorio</h1>
        </div>
      </section>
    </main>
  );
}

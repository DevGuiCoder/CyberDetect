import { useState } from "react";

import { AnalysisLoadingScreen } from "../features/analysis/AnalysisLoadingScreen";
import { LoadingScreen } from "../features/boot/LoadingScreen";
import { DashboardView } from "../features/dashboard/DashboardView";
import { ReportView } from "../features/report/ReportView";

declare global {
  interface Window {
    pywebview?: {
      api?: {
        completeLoading?: () => void;
        getReportData?: () => Promise<unknown>;
        closeWindow?: () => void;
        getDashboardData?: () => Promise<unknown>;
        analyzeText?: (text: string) => Promise<unknown>;
        analyzeImageData?: (dataUrl: string, filename: string) => Promise<unknown>;
        runBenchmark?: (text: string, models: string[]) => Promise<unknown>;
        importExperimentalDataset?: (
          filename: string,
          content: string,
          datasetName?: string,
          version?: string,
          binary?: boolean
        ) => Promise<unknown>;
        startExperimentalBatch?: (config: Record<string, unknown>) => Promise<unknown>;
        resumeExperimentalBatch?: (experimentId: string) => Promise<unknown>;
        startRobustnessExperiment?: (config: Record<string, unknown>) => Promise<unknown>;
        getExperimentalStatus?: (experimentId: string) => Promise<unknown>;
        cancelExperimentalBatch?: (experimentId: string) => Promise<unknown>;
        exportExperiment?: (experimentId: string, filetype: "csv" | "json") => Promise<unknown>;
        generateExperimentReport?: (experimentId: string) => Promise<unknown>;
        runOcrBenchmark?: (filename: string, content: string) => Promise<unknown>;
        runOcrImageBenchmark?: (dataUrl: string, filename: string, expectedText?: string) => Promise<unknown>;
        runThresholdCalibration?: (experimentId?: string, thresholds?: number[]) => Promise<unknown>;
        runSystemDiagnostics?: (options?: Record<string, unknown>) => Promise<unknown>;
        validateAnalysis?: (analysisId: number, groundTruth: string, note?: string, source?: string) => Promise<unknown>;
        markAnalysisFeedback?: (
          analysisId: number,
          isCorrect: boolean,
          correctClass?: string,
          note?: string
        ) => Promise<unknown>;
        requestScreenAnalysis?: () => Promise<unknown>;
        setProtection?: (interval: number) => Promise<unknown>;
        setAppEnabled?: (appId: number, enabled: boolean) => Promise<unknown>;
        openAppDownload?: (appId: number) => Promise<unknown>;
        testMonitoring?: () => Promise<unknown>;
        addApp?: (name: string) => Promise<unknown>;
        removeApp?: (appId: number) => Promise<unknown>;
        deleteHistory?: (analysisId: number) => Promise<unknown>;
        clearHistory?: () => Promise<unknown>;
        exportHistory?: (filetype: "csv" | "json") => Promise<unknown>;
        saveSettings?: (settings: Record<string, unknown>) => Promise<unknown>;
      };
    };
  }
}

export default function App() {
  const queryParams = new URLSearchParams(window.location.search);
  const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const legacyHashMode = window.location.hash.replace(/^#/, "").replace(/^mode=/, "");
  const mode = queryParams.get("mode") || hashParams.get("mode") || legacyHashMode || "boot";
  const duration = Number(queryParams.get("duration") || hashParams.get("duration")) || 10000;
  const [loading, setLoading] = useState(true);

  const finishLoading = () => {
    if (window.pywebview?.api?.completeLoading) {
      window.pywebview.api.completeLoading();
      return;
    }

    setLoading(false);
  };

  if (mode === "analysis") {
    return <AnalysisLoadingScreen />;
  }

  if (mode === "report") {
    return <ReportView />;
  }

  if (mode === "dashboard") {
    return <DashboardView />;
  }

  if (loading) {
    return <LoadingScreen duration={duration} onComplete={finishLoading} />;
  }

  return (
    <main className="ready-screen">
      <h1>PRONTO</h1>
    </main>
  );
}

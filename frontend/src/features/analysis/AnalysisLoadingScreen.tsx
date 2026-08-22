import logo from "../../assets/terminal-logo.png";

export function AnalysisLoadingScreen() {
  return (
    <main className="analysis-loading-screen">
      <div className="analysis-grid" />
      <div className="analysis-orbit" />
      <section className="analysis-loader-panel">
        <div className="analysis-loader-mark">
          <img src={logo} alt="CyberDetect" />
          <span className="scan-line" />
        </div>
        <div className="analysis-loader-copy">
          <p>CYBERDETECT / OCR</p>
          <h1>Analisando dados</h1>
          <div className="analysis-steps" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
          <small>extraindo texto - avaliando risco - montando relatorio</small>
        </div>
      </section>
    </main>
  );
}

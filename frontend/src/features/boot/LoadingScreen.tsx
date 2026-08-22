import { useEffect, useRef, useState } from "react";

import logo from "../../assets/terminal-logo.png";

interface LoadingScreenProps {
  duration?: number;
  onComplete?: () => void;
}

export function LoadingScreen({ duration = 10000, onComplete }: LoadingScreenProps) {
  const [progress, setProgress] = useState(0);
  const completedRef = useRef(false);
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    const start = performance.now();
    let raf = 0;
    const safeDuration = Math.max(250, duration);

    const tick = (now: number) => {
      const nextProgress = Math.min(1, (now - start) / safeDuration);
      setProgress(nextProgress);

      if (nextProgress < 1) {
        raf = requestAnimationFrame(tick);
      } else if (!completedRef.current) {
        completedRef.current = true;
        onCompleteRef.current?.();
      }
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [duration]);

  return (
    <div className="loading-screen" role="status" aria-label="Carregando CyberDetect">
      <div className="loader-ambient-wrap">
        <div className="loader-ambient" />
      </div>

      <div className="loader-hud" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>

      <div className="loader-logo-wrap">
        <img src={logo} alt="CyberDetect" className="loader-logo-base" />
        <div className="loader-sweep" aria-hidden="true" />
      </div>

      <div className="loader-boot-lines" aria-hidden="true">
        <span>C:\BOOT&gt; inicializando modulos</span>
        <span>C:\BOOT&gt; validando OCR pipeline</span>
        <span>C:\BOOT&gt; montando interface CRT</span>
      </div>

      <div className="loader-progress-track">
        <div
          className="loader-progress-fill"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      <p className="loader-progress-text">
        Carregando {Math.floor(progress * 100)}%
      </p>
    </div>
  );
}

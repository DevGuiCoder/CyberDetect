import { memo, useEffect, useMemo, useState } from "react";

type AppIconProps = {
  appId?: string | null;
  name: string;
  iconPath?: string;
  installed?: boolean;
  status?: string;
};

const APP_ICON_SOURCES: Record<string, string> = {
  chrome: "chrome.svg",
  edge: "edge.svg",
  firefox: "firefox.svg",
  discord: "discord.svg",
  telegram: "telegram.svg",
  whatsapp_desktop: "whatsapp-desktop.svg",
  whatsapp_web: "whatsapp-web.svg",
  gmail: "https://www.gstatic.com/images/branding/product/1x/gmail_2020q4_48dp.png",
  outlook: "outlook.svg",
};

const FALLBACK_LABELS: Record<string, string> = {
  chrome: "CH",
  edge: "ED",
  firefox: "FF",
  discord: "DC",
  telegram: "TG",
  whatsapp_desktop: "WA",
  whatsapp_web: "WA",
  gmail: "GM",
  outlook: "OL",
};

function iconAssetPath(appId?: string | null) {
  if (!appId || !APP_ICON_SOURCES[appId]) return "";
  const source = APP_ICON_SOURCES[appId];
  if (/^(https?:)?\/\//.test(source) || source.startsWith("data:") || source.startsWith("file:")) return source;
  const base = import.meta.env.BASE_URL || "/";
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  return `${normalizedBase}apps/${source}`;
}

function fallbackIcon(appId?: string | null, name?: string) {
  if (appId && FALLBACK_LABELS[appId]) return FALLBACK_LABELS[appId];
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "?";
}

function isWebService(appId?: string | null, status?: string) {
  const normalizedStatus = String(status || "").toLowerCase();
  return appId === "whatsapp_web" || appId === "gmail" || normalizedStatus.includes("web");
}

export const AppIcon = memo(function AppIcon({
  appId,
  name,
  iconPath,
  installed = true,
  status = "",
}: AppIconProps) {
  const src = iconPath || iconAssetPath(appId);
  const fallback = useMemo(() => fallbackIcon(appId, name), [appId, name]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  const locked = !installed;
  const showImage = Boolean(src && !failed);
  const showWebBadge = appId !== "gmail" && isWebService(appId, status);

  return (
    <span
      className={`app-icon ${locked ? "is-locked" : ""} ${showWebBadge ? "is-web-service" : ""}`}
      title={name}
      aria-label={`${name} icon`}
      data-app-icon={appId || "custom"}
    >
      {showImage ? (
        <img
          src={src}
          alt=""
          draggable={false}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="app-icon-fallback">{fallback}</span>
      )}
      {showWebBadge && <span className="app-icon-web-badge">WEB</span>}
      {locked && <span className="app-icon-lock" aria-hidden="true" />}
    </span>
  );
});

# CyberDetect React Frontend

Interface principal do CyberDetect em React + Vite, carregada pelo app desktop Python via `pywebview`.

## Desenvolvimento

```powershell
cd frontend
npm install
npm run dev
```

## Build usado pelo app desktop

```powershell
cd frontend
npm install
npm run build
```

O Python abre `frontend/dist/index.html` quando o build existe e `pywebview` esta instalado. A splash Tkinter continua como fallback de inicializacao.

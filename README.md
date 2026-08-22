# CyberDetect - Plataforma de Deteccao de Golpes e Benchmarking

O CyberDetect e um aplicativo desktop Windows para deteccao inteligente de golpes digitais em conversas, prints e textos copiados. Ele combina OCR, IA local via Ollama, API externa opcional, benchmark de modelos, historico local e monitoramento em segundo plano pelo tray.

## Modelos

Modelos locais principais:

- Google Gemma 3 4B (`gemma3:4b`)
- Meta Llama 3.2 3B (`llama3.2:3b`)
- Qwen 2.5 3B (`qwen2.5:3b`)
- Microsoft Phi-4-mini (`phi4-mini:latest`)

API externa opcional:

- OpenAI GPT-4o Mini (`gpt-4o-mini`)

## Pre-requisitos

1. Python 3.11+
2. Node.js 20+ para desenvolver ou rebuildar o frontend React
3. Tesseract OCR 5.x
   - Baixe em https://github.com/UB-Mannheim/tesseract/wiki
   - Instale os idiomas Portuguese e English.
   - Caminho padrao esperado: `C:\Program Files\Tesseract-OCR\tesseract.exe`
4. Ollama para Windows, caso use IA local
   - Baixe em https://ollama.com/download/windows
   - Instale os modelos com:

```powershell
.\scripts\download_models.ps1
```

## Instalacao local

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Compile o painel React:

```powershell
cd frontend
npm install
npm run build
cd ..
```

Rode a aplicacao:

```powershell
.\venv\Scripts\python.exe main.py
```

## Funcionalidades

- Painel principal em React com dashboard, analise manual, protecao ativa, laboratorio de modelos, historico, relatorios, apps monitorados, configuracoes, logs e sobre.
- Tray do Windows para protecao continua em segundo plano.
- Atalho global `Ctrl+Shift+G` para capturar e analisar uma regiao da tela.
- OCR com Tesseract usando `por+eng`.
- Analise local com Ollama ou externa com OpenAI quando configurada.
- Historico local em SQLite e exportacao CSV/JSON.
- Benchmark comparando modelos locais com resumo de consenso, divergencias, tempo e score.

## Arquitetura

- `main.py`: entrada da aplicacao, instancia unica, tray, hotkey, captura, automacao e ponte com o painel.
- `app/`: codigo Python da aplicacao.
- `app/core/`: OCR, analise, prompt, clientes de IA, benchmark, historico SQLite, diagnosticos e laboratorio experimental.
- `app/desktop/`: tray, host `pywebview`, splash/fallbacks e janelas tecnicas ainda necessarias.
- `app/shared/`: logging e utilitarios compartilhados.
- `app/paths.py`: caminhos centralizados para config, dados, logs, recursos, OCR e frontend.
- `frontend/`: interface React/Vite. O build em `frontend/dist` e carregado pelo desktop.
- `core/`, `ui/` e `utils/`: pacotes de compatibilidade para imports existentes.
- `resources/assets/`: icones, logos e imagens do app.
- `resources/ocr/tessdata/`: arquivos locais de idioma para OCR.
- `config/config.ini`: configuracao padrao local.
- `data/`: banco local, exportacoes e conversas de teste.
- `scripts/`: scripts auxiliares de instalacao e manutencao.
- `tests/unit/`: testes automatizados.

## Privacidade

O historico fica localmente em SQLite. Chaves de API externa sao armazenadas pelo Windows Credential Manager via `keyring`, sem ficar em texto puro no repositorio.

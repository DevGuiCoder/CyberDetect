Write-Host "Aguardando instalação do Ollama..."
while (!(Get-Command ollama -ErrorAction SilentlyContinue)) {
    Start-Sleep -Seconds 10
}
Write-Host "Ollama encontrado. Aguardando servidor iniciar..."
Start-Sleep -Seconds 15

Write-Host "Iniciando download dos modelos locais..."
ollama pull llama3.2:3b
ollama pull gemma3:4b
ollama pull qwen2.5:3b
ollama pull phi4-mini
Write-Host "Downloads concluídos!"

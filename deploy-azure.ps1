# 🚀 Script de Deploy Automatizado - Ceci na Azure
# Execute este script após Docker Desktop estar rodando

# Configurações
$DOCKER_USERNAME = Read-Host "Digite seu username do Docker Hub (ou pressione Enter para criar conta)"
$DOCKER_IMAGE = "ceci-api"
$AZURE_RG = "ceci-rg"
$AZURE_APP = "ceci-transport-api-rm560593"

Write-Host "🐳 === DEPLOY CECI NA AZURE VIA DOCKER ===" -ForegroundColor Cyan
Write-Host ""

# Passo 1: Verificar Docker
Write-Host "1️⃣ Verificando Docker..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "✅ Docker está rodando!" -ForegroundColor Green
}
catch {
    Write-Host "❌ Docker não está rodando. Por favor, inicie o Docker Desktop." -ForegroundColor Red
    exit 1
}

# Passo 2: Build da imagem
Write-Host ""
Write-Host "2️⃣ Building imagem Docker (pode demorar 10-15 minutos)..." -ForegroundColor Yellow
docker build -t ${DOCKER_IMAGE}:latest .
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro no build!" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Build concluído!" -ForegroundColor Green

# Passo 3: Decidir método de deploy
Write-Host ""
Write-Host "3️⃣ Escolha o método de deploy:" -ForegroundColor Yellow
Write-Host "   [1] Docker Hub (recomendado - grátis, público)"
Write-Host "   [2] Azure Container Registry (privado, requer registro)"
Write-Host "   [3] Pular push (apenas build local)"
$choice = Read-Host "Digite 1, 2 ou 3"

if ($choice -eq "1") {
    # Docker Hub
    Write-Host ""
    Write-Host "📦 Login no Docker Hub..." -ForegroundColor Yellow
    docker login
    
    if ($LASTEXITCODE -eq 0) {
        $actualUsername = docker info 2>$null | Select-String "Username:" | ForEach-Object { $_.ToString().Split(":")[1].Trim() }
        Write-Host "✅ Logado como: $actualUsername" -ForegroundColor Green
        
        Write-Host ""
        Write-Host "🚀 Fazendo push para Docker Hub..." -ForegroundColor Yellow
        docker tag ${DOCKER_IMAGE}:latest ${actualUsername}/${DOCKER_IMAGE}:latest
        docker push ${actualUsername}/${DOCKER_IMAGE}:latest
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Push concluído!" -ForegroundColor Green
            $finalImage = "${actualUsername}/${DOCKER_IMAGE}:latest"
        }
        else {
            Write-Host "❌ Erro no push!" -ForegroundColor Red
            exit 1
        }
    }
    
}
elseif ($choice -eq "2") {
    Write-Host "⚠️ Azure Container Registry requer registro do provider." -ForegroundColor Yellow
    Write-Host "Use a opção 1 (Docker Hub) que é mais simples!" -ForegroundColor Yellow
    exit 1
    
}
else {
    Write-Host "⏭️ Pulando push. Imagem disponível apenas localmente." -ForegroundColor Yellow
    $finalImage = "${DOCKER_IMAGE}:latest"
}

# Passo 4: Deploy no Azure
Write-Host ""
Write-Host "4️⃣ Fazendo deploy no Azure..." -ForegroundColor Yellow

# Atualizar PATH para Azure CLI
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine")

# Configurar Web App para usar container
Write-Host "   Configurando Web App para Container..." -ForegroundColor Cyan
az webapp config container set `
    --resource-group $AZURE_RG `
    --name $AZURE_APP `
    --docker-custom-image-name $finalImage `
    --docker-registry-server-url https://index.docker.io

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro ao configurar container!" -ForegroundColor Red
    exit 1
}

# Passo 5: Configurar variáveis de ambiente
Write-Host ""
Write-Host "5️⃣ Configurando variáveis de ambiente..." -ForegroundColor Yellow
$SECRET = Read-Host "Digite o SECRET (ou pressione Enter para usar padrão)"
if ([string]::IsNullOrWhiteSpace($SECRET)) {
    $SECRET = "minhaChaveSuperSecretaParaJwtComTamanhoAdequado!"
}

$OPENAI_KEY = Read-Host "Digite sua OPENAI_API_KEY"

az webapp config appsettings set `
    --resource-group $AZURE_RG `
    --name $AZURE_APP `
    --settings `
    SECRET="$SECRET" `
    OPENAI_API_KEY="$OPENAI_KEY" `
    WEBSITES_PORT=8000 `
    WEBSITES_CONTAINER_START_TIME_LIMIT=1800

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Erro ao configurar variáveis!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Variáveis configuradas!" -ForegroundColor Green

# Passo 6: Restart da aplicação
Write-Host ""
Write-Host "6️⃣ Reiniciando aplicação..." -ForegroundColor Yellow
az webapp restart --resource-group $AZURE_RG --name $AZURE_APP

# Finalização
Write-Host ""
Write-Host "🎉 === DEPLOY CONCLUÍDO! ===" -ForegroundColor Green
Write-Host ""
Write-Host "🌐 URL da API: https://${AZURE_APP}.azurewebsites.net" -ForegroundColor Cyan
Write-Host "📊 Health Check: https://${AZURE_APP}.azurewebsites.net/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "⏳ Aguarde 2-3 minutos para a aplicação iniciar completamente." -ForegroundColor Yellow
Write-Host "📝 Ver logs: az webapp log tail --resource-group $AZURE_RG --name $AZURE_APP" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ Pronto! A Ceci está no ar!" -ForegroundColor Green

# Script PowerShell - Conectar VM Ubuntu via SSH e rodar CFTV
# Uso: .\deploy_cftv_ssh.ps1 -VMIp "10.0.2.15" -User "vboxuser"

param(
    [string]$VMIp = "",
    [string]$User = "vboxuser",
    [int]$Port = 22,
    [switch]$Interactive = $false
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "CFTV Painel - Deploy via SSH" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Se não passou IP, pedir
if ([string]::IsNullOrWhiteSpace($VMIp)) {
    $VMIp = Read-Host "Digite o IP da VM Ubuntu"
}

Write-Host "Conectando a $User@$VMIp`:$Port..." -ForegroundColor Yellow

# Criar script em base64 para executar na VM
$setupScript = @'
#!/bin/bash
set -e
echo "=========================================="
echo "[CFTV] Iniciando setup na VM..."
echo "=========================================="
cd ~
if [ ! -d "SIMULA-O-CFTV" ]; then
  echo "[CFTV] Clonando repositório..."
  git clone https://github.com/oliveiravianaraf-eng/SIMULA-O-CFTV.git
else
  echo "[CFTV] Atualizando repositório..."
  cd SIMULA-O-CFTV && git pull origin main && cd ..
fi
cd SIMULA-O-CFTV
echo "[CFTV] Criando ambiente virtual..."
python3 -m venv .venv
source .venv/bin/activate
echo "[CFTV] Instalando dependencias..."
pip install -q -r requirements.txt
echo "[CFTV] Executando testes..."
python3 -m unittest discover -s tests -q
VM_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=========================================="
echo "✓ Setup concluído!"
echo "=========================================="
echo "Painel: http://${VM_IP}:8080"
echo "API: http://${VM_IP}:8080/api/status"
echo ""
echo "Iniciando painel..."
python3 servidor_web_cftv.py --host 0.0.0.0 --port 8080
'@

# Executar via SSH
try {
    $setupScript | ssh -o ConnectTimeout=5 -p $Port "${User}@${VMIp}" "bash -s"
} catch {
    Write-Host "Erro ao conectar: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Sugestões:" -ForegroundColor Yellow
    Write-Host "1. Testar conectividade: ping -n 1 $VMIp"
    Write-Host "2. Testar SSH diretamente: ssh ${User}@${VMIp}"
    Write-Host "3. Verificar Port Forwarding no VirtualBox se usar NAT"
    Write-Host "4. Executar setup manual na VM:"
    Write-Host "   bash <(curl -s https://raw.githubusercontent.com/oliveiravianaraf-eng/SIMULA-O-CFTV/main/setup_cftv_vm.sh)"
    exit 1
}

Write-Host ""
Write-Host "✓ Deploy concluído via SSH!" -ForegroundColor Green

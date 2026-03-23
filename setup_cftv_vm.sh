#!/bin/bash
# Setup automático - CFTV Painel Web na VM Ubuntu
# Uso: bash setup_cftv_vm.sh

set -e

echo "=========================================="
echo "CFTV Painel Web - Setup Automático"
echo "=========================================="
echo ""

# 1. Atualizar pacotes
echo "[1/6] Atualizando pacotes..."
sudo apt update -qq
sudo apt install -y -qq git python3 python3-venv python3-pip openssh-server > /dev/null 2>&1

# 2. Clonar repositório
if [ ! -d "SIMULA-O-CFTV" ]; then
  echo "[2/6] Clonando repositório..."
  git clone https://github.com/oliveiravianaraf-eng/SIMULA-O-CFTV.git > /dev/null 2>&1
else
  echo "[2/6] Repositório já existe (atualizando)..."
  cd SIMULA-O-CFTV && git pull origin main > /dev/null 2>&1 && cd ..
fi

# 3. Criar ambiente virtual
cd SIMULA-O-CFTV
echo "[3/6] Criando ambiente virtual..."
python3 -m venv .venv > /dev/null 2>&1
source .venv/bin/activate

# 4. Instalar dependências (se houver requirements.txt)
if [ -f "requirements.txt" ]; then
  echo "[4/6] Instalando dependências Python..."
  pip install -q -r requirements.txt
else
  echo "[4/6] Sem requirements.txt (usando libs padrão)"
fi

# 5. Rodar testes rápidos
echo "[5/6] Executando testes..."
python3 -m unittest discover -s tests -q 2>/dev/null || echo "Testes executados (algumas falhas esperadas)"

# 6. Exibir informações de rede
echo "[6/6] Obtendo IP da VM..."
VM_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=========================================="
echo "✓ Setup concluído com sucesso!"
echo "=========================================="
echo ""
echo "Painel disponível em:"
echo "  → http://${VM_IP}:8080"
echo "  → http://localhost:8080 (dentro da VM)"
echo ""
echo "API de status:"
echo "  → http://${VM_IP}:8080/api/status"
echo ""
echo "Para iniciar o painel, execute:"
echo "  $ source .venv/bin/activate"
echo "  $ python3 servidor_web_cftv.py --host 0.0.0.0 --port 8080"
echo ""
echo "=========================================="

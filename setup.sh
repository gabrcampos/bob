#!/bin/bash
# Setup do servidor BOB — Google Cloud e2-micro (Ubuntu 24.04)
# Uso: bash setup.sh
# Tempo estimado: ~10 minutos

set -e  # para se qualquer comando falhar

echo "======================================"
echo " BOB — Setup do Servidor"
echo "======================================"

# ── 1. Sistema ─────────────────────────────
echo ""
echo "[1/7] Atualizando o sistema..."
sudo apt update -y && sudo apt upgrade -y
sudo apt install -y git curl wget unzip ffmpeg build-essential

# ── 2. Python 3.12 ─────────────────────────
echo ""
echo "[2/7] Instalando Python 3.12..."
sudo apt install -y python3.12 python3.12-venv python3-pip
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
sudo update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# ── 3. Node.js 20 ──────────────────────────
echo ""
echo "[3/7] Instalando Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# ── 4. Claude Code ─────────────────────────
echo ""
echo "[4/7] Instalando Claude Code..."
sudo npm install -g @anthropic-ai/claude-code

# ── 5. Projeto ─────────────────────────────
echo ""
echo "[5/7] Clonando o repositório..."
cd ~
git clone https://github.com/gabrcampos/bob.git
cd bob

echo "Instalando dependências Python..."
pip install --break-system-packages -r requirements.txt

echo "Criando diretórios necessários..."
mkdir -p config outputs

# ── 6. Arquivo .env ─────────────────────────
echo ""
echo "[6/7] Criando .env..."
cat > ~/bob/.env << 'EOF'
GEMINI_API_KEY=PREENCHER
MONGODB_URI=PREENCHER
GOOGLE_DRIVE_FOLDER_ID=PREENCHER
EOF

echo ""
echo "ATENÇÃO: edite o .env com suas chaves:"
echo "  nano ~/bob/.env"

# ── 7. Google Cloud CLI ─────────────────────
echo ""
echo "[7/7] Instalando Google Cloud CLI..."
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
sudo apt update -y && sudo apt install -y google-cloud-cli

# ── Resumo final ────────────────────────────
echo ""
echo "======================================"
echo " Setup concluído!"
echo "======================================"
echo ""
echo "Próximos passos manuais:"
echo ""
echo "  1. Preencher as chaves no .env:"
echo "       nano ~/bob/.env"
echo ""
echo "  2. Copiar credenciais do Google Drive do seu PC:"
echo "       scp config/oauth_client.json SEU_USUARIO@IP_DA_VM:~/bob/config/"
echo "       scp config/drive_token.json  SEU_USUARIO@IP_DA_VM:~/bob/config/"
echo ""
echo "  3. Autenticar o Claude Code:"
echo "       cd ~/bob && claude"
echo ""
echo "  4. Autenticar o Google Cloud CLI:"
echo "       gcloud auth login"
echo "       gcloud config set project bob-server"
echo ""

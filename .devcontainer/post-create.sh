#!/bin/bash
# =============================================================================
# Dev Container 初始化腳本
# 在容器建立後自動執行
# =============================================================================

set -e

echo "🚀 初始化開發環境..."

# -----------------------------------------------------------------------------
# Pyenv 設定（確保使用 Python 3.11.14）
# -----------------------------------------------------------------------------
if [ ! -d "$HOME/.pyenv" ]; then
    echo "📦 安裝 pyenv..."
    curl https://pyenv.run | bash

    # 設定 pyenv 環境變數
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - bash)"

    # 將 pyenv 配置添加到 bashrc（如果尚未添加）
    if ! grep -q "PYENV_ROOT" ~/.bashrc; then
        cat >> ~/.bashrc << 'EOF'

# Pyenv configuration
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
EOF
    fi

    # 安裝 Python 3.11.14
    echo "📦 安裝 Python 3.11.14..."
    pyenv install 3.11.14
    pyenv global 3.11.14
else
    # pyenv 已安裝，確保環境變數設定
    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - bash)"

    # 確認 3.11.14 已安裝
    if ! pyenv versions | grep -q "3.11.14"; then
        echo "📦 安裝 Python 3.11.14..."
        pyenv install 3.11.14
    fi
    pyenv global 3.11.14
fi

# -----------------------------------------------------------------------------
# Python 環境設定
# -----------------------------------------------------------------------------
echo "📦 設定 Python 虛擬環境..."

if [ ! -d "/workspace/.venv" ]; then
    ~/.pyenv/versions/3.11.14/bin/python -m venv /workspace/.venv
fi

source /workspace/.venv/bin/activate

echo "📦 安裝 Python 依賴..."
pip install --upgrade pip
pip install -e ".[dev]"

# -----------------------------------------------------------------------------
# Node.js 環境設定
# -----------------------------------------------------------------------------
echo "📦 安裝 Frontend 依賴..."
cd /workspace/frontend
npm install
cd /workspace

# -----------------------------------------------------------------------------
# Git 設定
# -----------------------------------------------------------------------------
echo "🔧 設定 Git..."
git config --global core.autocrlf input
git config --global core.eol lf

# 設定 safe directory（避免權限問題）
git config --global --add safe.directory /workspace

# -----------------------------------------------------------------------------
# 資料庫初始化（等待 DB 就緒）
# -----------------------------------------------------------------------------
echo "⏳ 等待資料庫就緒..."
for i in {1..30}; do
    if mysql -h db -u admin -padmin -e "SELECT 1" &> /dev/null; then
        echo "✅ 資料庫連線成功！"
        break
    fi
    echo "等待中... ($i/30)"
    sleep 2
done

# 執行資料庫遷移
echo "🗄️ 執行資料庫遷移..."
cd /workspace
source .venv/bin/activate
alembic upgrade head || echo "⚠️ 遷移失敗或無需遷移"

# -----------------------------------------------------------------------------
# 完成
# -----------------------------------------------------------------------------
echo ""
echo "✅ 開發環境初始化完成！"
echo ""
echo "可用指令："
echo "  Backend:  cd /workspace && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0"
echo "  Frontend: cd /workspace/frontend && npm run dev -- --host"
echo ""

#!/bin/bash
# 双击此文件启动「茅台抢单软件」CLI（macOS）

cd "$(dirname "$0")"

# 终端窗口标题
printf '\033]0;茅台抢单软件\007'

echo "======================================"
echo "       茅台抢单软件 · i茅台预约"
echo "======================================"
echo ""

if ! command -v python3 &>/dev/null; then
    echo "未找到 python3，请先安装 Python 3"
    read -p "按回车退出..."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "首次运行，正在创建环境..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

python cli.py

echo ""
read -p "按回车关闭窗口..."

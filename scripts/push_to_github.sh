#!/usr/bin/env bash
# 一键推送到 GitHub（需先创建仓库，见《云部署说明.md》）
# 用法:
#   bash scripts/push_to_github.sh <你的GitHub用户名> <仓库名>
set -e

USER=${1:?用法: bash scripts/push_to_github.sh <GitHub用户名> <仓库名>}
REPO=${2:?用法: bash scripts/push_to_github.sh <GitHub用户名> <仓库名>}
DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$DIR"

if [ ! -d .git ]; then
  echo "==> 初始化 git 仓库"
  git init -b main
  git add -A
  git commit -m "feat: 每日金融复盘系统（云端自动运行 + GitHub Pages）" || true
fi

echo "==> 添加远程仓库"
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${USER}/${REPO}.git"

echo "==> 推送代码"
git push -u origin main || {
  echo ""
  echo "推送失败，常见原因："
  echo "  1. 仓库还未创建 → 去 https://github.com/new 创建名为 ${REPO} 的仓库（Public 免费无限流量）"
  echo "  2. 需要登录 → Windows 建议安装 Git Credential Manager（默认自带）"
  echo "  3. 分支名不同 → 若默认分支是 master： git branch -M main 后重试"
  exit 1
}

echo ""
echo "✅ 推送成功！接下来（只需做一次）："
echo "  1. 打开 https://github.com/${USER}/${REPO}/settings/pages"
echo "  2. Source 选择: GitHub Actions（不要选 Deploy from a branch）"
echo "  3. 打开 https://github.com/${USER}/${REPO}/actions 手动运行一次 '每日金融复盘'"
echo "  4. 几分钟后访问: https://${USER}.github.io/${REPO}/ 即可看到报告"
echo "  之后每天 17:00 自动更新，手机/平板浏览器打开同一网址即可查看"

#!/usr/bin/env bash
# Установка агента «Облигационер».
#   ./install.sh                 -> Hermes Agent: отдельный профиль "bonds" (команда `bonds chat`)
#   ./install.sh hermes-default  -> Hermes Agent: только навык в основной профиль (~/.hermes)
#   ./install.sh claude          -> Claude Code: навык ~/.claude/skills/ru-bonds + субагент ~/.claude/agents/bonds.md
#   ./install.sh codex           -> Codex CLI: навык ~/.codex/skills/ru-bonds
#   ./install.sh all             -> всё сразу (что установлено)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$HERE/skills/finance/ru-bonds"
TARGET="${1:-hermes}"

copy_skill() {  # $1 = каталог назначения навыка
  mkdir -p "$(dirname "$1")"
  rm -rf "$1"
  cp -r "$SKILL_SRC" "$1"
  chmod +x "$1/scripts/"*.py
  echo "Навык -> $1"
}

install_hermes() {
  local home="$HOME/.hermes/profiles/bonds"
  if [[ ! -d "$home" ]]; then
    echo "Создаю профиль Hermes 'bonds' (копия текущих ключей/модели)..."
    hermes profile create bonds --clone
  fi
  cp "$HERE/SOUL.md" "$home/SOUL.md"
  echo "SOUL.md -> $home/SOUL.md"
  copy_skill "$home/skills/finance/ru-bonds"
  echo "Hermes: запустите 'bonds chat'"
}

install_hermes_default() {
  copy_skill "$HOME/.hermes/skills/finance/ru-bonds"
  echo "Hermes: новая сессия или /reset"
}

install_claude() {
  copy_skill "$HOME/.claude/skills/ru-bonds"
  mkdir -p "$HOME/.claude/agents"
  cp "$HERE/agents/claude-code/bonds.md" "$HOME/.claude/agents/bonds.md"
  echo "Субагент -> $HOME/.claude/agents/bonds.md"
  echo "Claude Code: перезапустите сессию; попросите «используй агента bonds» или просто спросите про облигации"
}

install_codex() {
  copy_skill "$HOME/.codex/skills/ru-bonds"
  echo "Codex: перезапустите сессию. Альтернатива: работайте из этой папки — Codex прочитает AGENTS.md"
}

case "$TARGET" in
  hermes) install_hermes ;;
  hermes-default) install_hermes_default ;;
  claude) install_claude ;;
  codex) install_codex ;;
  all)
    command -v hermes >/dev/null && install_hermes || echo "Hermes не найден — пропускаю"
    [[ -d "$HOME/.claude" ]] && install_claude || echo "Claude Code не найден — пропускаю"
    [[ -d "$HOME/.codex" ]] && install_codex || echo "Codex не найден — пропускаю"
    ;;
  *) echo "Неизвестная цель: $TARGET (hermes | hermes-default | claude | codex | all)"; exit 1 ;;
esac

python3 -m pip install --user --quiet pypdf 2>/dev/null || echo "pypdf не установлен — для чтения PDF: pip install pypdf"
echo "Проверка доступа к MOEX..."
python3 "$SKILL_SRC/scripts/macro.py" | head -3 || echo "MOEX ISS недоступен — проверьте сеть"

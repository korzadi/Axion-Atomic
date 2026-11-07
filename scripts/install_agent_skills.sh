#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/addyosmani/agent-skills.git"
PINNED_COMMIT="301b02b12bff98e4688e6984af6556802322bbde"
DEST=".agents/skills/agent-skills-pack"

if [[ -e "$DEST" || -L "$DEST" ]]; then
  printf 'ERROR: el destino ya existe; no se sobrescribirá: %s\n' "$DEST" >&2
  exit 2
fi

mkdir -p "$(dirname "$DEST")"
tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

git -C "$tmp" init -q
git -C "$tmp" remote add origin "$REPO_URL"
git -C "$tmp" fetch --quiet --depth 1 origin "$PINNED_COMMIT"
git -C "$tmp" checkout --quiet --detach FETCH_HEAD

count="$(find "$tmp/skills" -mindepth 2 -maxdepth 2 -type f -name SKILL.md | wc -l | tr -d ' ')"
if [[ "$count" != "25" ]]; then
  printf 'ERROR: se esperaban 25 skills; se encontraron %s. No se instaló el pack.\n' "$count" >&2
  exit 3
fi

mkdir -p "$DEST"
cp -a "$tmp/skills" "$DEST/"
if [[ -d "$tmp/references" ]]; then cp -a "$tmp/references" "$DEST/"; fi
cp "$tmp/LICENSE" "$DEST/LICENSE"
printf 'Instalado pack Agent Skills (%s skills) en %s\n' "$count" "$DEST"
printf 'Commit upstream fijado: %s\n' "$PINNED_COMMIT"

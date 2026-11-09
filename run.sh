#!/usr/bin/env bash
# Changeling Tiresias Realtime runs in Changeling Tiresias's environment: it needs Changeling Tiresias and Changeling
# CopyCat Realtime next to this folder (as in Changeling Studio). Missing ones are fetched here.
set -e
cd "$(dirname "$0")"
STUDIO="$(cd .. && pwd)"
for a in Tiresias CopyCat-Realtime; do
    if [ ! -d "$STUDIO/Changeling-$a" ]; then
        echo "Getting Changeling $a ..."
        git clone "https://github.com/CursedPrograms/Changeling-$a" "$STUDIO/Changeling-$a"
    fi
done

# The environment: Changeling Tiresias's, or a sibling's (Tiresias, Chronos and Natio need the same things).
PY=""
for a in Tiresias Tiresias Chronos Natio; do
    for p in "$STUDIO/Changeling-$a/psdenv/bin/python" "$STUDIO/Changeling-$a/psdenv/Scripts/python.exe"; do
        env="$(dirname "$(dirname "$p")")"
        if [ -z "$PY" ] && [ -x "$p" ] && { [ -d "$env/Lib/site-packages/torch" ] || ls -d "$env"/lib/python3*/site-packages/torch >/dev/null 2>&1; }; then PY="$p"; fi
    done
done
if [ -z "$PY" ]; then
    echo "Setting up Changeling Tiresias first, once: its environment and its models."
    bash "$STUDIO/Changeling-Tiresias/run.sh" --download-models
    PY="$STUDIO/Changeling-Tiresias/psdenv/bin/python"
fi

exec "$PY" live.py "$@"

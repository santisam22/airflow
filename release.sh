#!/bin/zsh
# Publishes the build in dist/ as a GitHub release: tags v<version>, pushes, and uploads
# Airflow.dmg, Airflow-update.zip and update.json. Installed copies of Airflow pick it up
# through update.json, and the download page always serves the latest release.
#   Usage: ./build.sh && ./release.sh "Short title"
set -euo pipefail
cd "$(dirname "$0")"
REPO=santisam22/airflow
VERSION=$(.venv.nosync/bin/python -c "from airflow.config import VERSION; print(VERSION)")
TITLE=${1:-$(head -1 WHATS_NEW.txt)}
NOTES=$(cat WHATS_NEW.txt)

for f in dist/Airflow.dmg dist/Airflow-update.zip dist/update.json; do
  [[ -f $f ]] || { echo "Missing $f: run ./build.sh first"; exit 1; }
done
grep -q "\"version\": \"$VERSION\"" dist/update.json || { echo "dist/ is not a $VERSION build"; exit 1; }
[[ -z $(git status --porcelain) ]] || { echo "Commit your changes first"; exit 1; }
if gh release view "v$VERSION" -R $REPO >/dev/null 2>&1; then
  echo "v$VERSION is already released: bump VERSION in airflow/config.py"; exit 1
fi

git tag "v$VERSION"
git push origin main "v$VERSION"
gh release create "v$VERSION" -R $REPO --title "Airflow $VERSION: $TITLE" --notes "$NOTES" \
  dist/Airflow.dmg dist/Airflow-update.zip dist/update.json
echo "✓ Released Airflow $VERSION"

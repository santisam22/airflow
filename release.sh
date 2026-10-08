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

# The Windows build happens on GitHub (.github/workflows/windows.yml). Wait for it, then
# sign the .exe here (the key never leaves this Mac's Keychain) and add it to update.json
# so Windows copies of Airflow can update themselves.
echo "→ Waiting for the Windows build…"
RUN=""
for i in $(seq 1 60); do
  RUN=$(gh run list -R $REPO --workflow windows.yml --limit 10 --json databaseId,headBranch \
        --jq ".[] | select(.headBranch==\"v$VERSION\") | .databaseId" | head -1)
  [[ -n $RUN ]] && break
  sleep 5
done
if [[ -z $RUN ]] || ! gh run watch "$RUN" -R $REPO --exit-status >/dev/null; then
  echo "  Windows build failed or didn't start: Mac update is live, Windows players won't see this one."
  exit 0
fi
WIN="$HOME/Library/Caches/AirflowBuild/win"
rm -rf "$WIN" && mkdir -p "$WIN"
gh release download "v$VERSION" -R $REPO -p Airflow-Windows.exe -D "$WIN"
SHA=$(shasum -a 256 "$WIN/Airflow-Windows.exe" | cut -d' ' -f1)
printf "airflow-windows %s %s" "$VERSION" "$SHA" > "$WIN/message.txt"
WSIG=$(swift macos/sign_tool.swift sign "$WIN/message.txt")
.venv.nosync/bin/python - "$VERSION" "$SHA" "$WSIG" <<'PY'
import json, sys
version, sha, sig = sys.argv[1:]
d = json.load(open("dist/update.json"))
d.update({"win_url": f"https://github.com/santisam22/airflow/releases/download/v{version}/Airflow-Windows.exe",
          "win_sha256": sha, "win_signature": sig})
json.dump(d, open("dist/update.json", "w"), indent=2)
PY
gh release upload "v$VERSION" -R $REPO dist/update.json --clobber
echo "✓ Windows build signed and listed: Windows copies will now see Airflow $VERSION"

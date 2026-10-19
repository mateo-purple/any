#!/usr/bin/env bash
# Publish only built static files, preserving the source branch and rejecting races.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
npm run build
pages_tmp=$(mktemp -d /tmp/kotoba-pages.XXXXXX)
trap 'rm -rf "$pages_tmp"' EXIT
parent=()
remote=$(git ls-remote origin refs/heads/gh-pages)
if [[ -n "$remote" ]]; then
  git fetch origin refs/heads/gh-pages
  previous=$(git rev-parse FETCH_HEAD)
  git show "$previous:health.json" > "$pages_tmp/previous-health.json"
  node -e "const r=require(process.argv[1]);if(r.name!=='わたしは、なに？')process.exit(1)" "$pages_tmp/previous-health.json"
  parent=(-p "$previous")
fi
export GIT_INDEX_FILE="$pages_tmp/index"
git read-tree --empty
for file in index.html health.json credits.html dictionary.json .nojekyll; do
  object=$(git hash-object -w -- "$file")
  git update-index --add --cacheinfo "100644,$object,$file"
done
tree=$(git write-tree)
commit=$(git commit-tree "$tree" "${parent[@]}" -m 'Publish tested Kotoba Party static game')
git push origin "$commit:refs/heads/gh-pages"
printf 'Published static branch commit: %s\n' "$commit"

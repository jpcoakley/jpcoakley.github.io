#!/bin/sh
# Publish the site: rebuild galleries from Lightroom exports, commit, push.
cd "$(dirname "$0")" || exit 1
python3 build_galleries.py || exit 1
if git status --porcelain | grep -q .; then
  git add -A
  git commit -m "Update galleries"
  git pull --rebase && git push
  echo "Published — live in about a minute."
else
  echo "No changes to publish."
fi

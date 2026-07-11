#!/usr/bin/env bats
# hooks/test_post_commit.bats — Block 2: feedback index rebuild gate.
#
# Tests the grep -q '^ops/feedback/' filter in post-commit Block 2.
# Key assertions:
#   - sentinel file written when commit touches ops/feedback/
#   - sentinel file NOT written when commit does not touch ops/feedback/
#
# Strategy: install the hook via `cp` into .git/hooks/. The hook resolves
# BASH_SOURCE[0] to locate itself, so SCRIPTS_DIR resolves to .git/ when
# installed there. We therefore place stubs at:
#   .git/briefing/regen.py   — satisfies Block 1 existence check (no early exit)
#   .git/feedback/           — satisfies Block 2 directory check
# and stub `uv` on PATH to write a sentinel when called for feedback_index.

HOOK_REAL="$(cd "$(dirname "$BATS_TEST_FILENAME")/../.." && pwd)/hooks/post-commit"

# Per-PID sentinel so parallel bats runs don't collide.
SENTINEL_FEEDBACK="/tmp/post_commit_feedback_ran.$$"

setup() {
  REPO="$(mktemp -d)"
  cd "$REPO"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  # ops/feedback/ tree for test commits.
  mkdir -p ops/feedback/2026-05-22

  # The hook resolves paths relative to BASH_SOURCE[0]. When copied to
  # .git/hooks/post-commit, SCRIPT_DIR=.git/hooks and SCRIPTS_DIR=.git/.
  # Place the stubs the hook checks for at those resolved paths.
  mkdir -p .git/briefing
  printf '# stub regen\nimport sys; sys.exit(0)\n' > .git/briefing/regen.py
  mkdir -p .git/feedback

  # Install hook by copy (not symlink — symlink still resolves BASH_SOURCE to .git/hooks).
  cp "$HOOK_REAL" .git/hooks/post-commit
  chmod +x .git/hooks/post-commit

  # Stub `uv`: write sentinel when called for feedback_index, else exit 0.
  mkdir -p "$REPO/stub-bin"
  cat > "$REPO/stub-bin/uv" <<UVEOF
#!/bin/sh
for arg in "\$@"; do
  case "\$arg" in
    *feedback_index*) touch "${SENTINEL_FEEDBACK}" ;;
  esac
done
exit 0
UVEOF
  chmod +x "$REPO/stub-bin/uv"
  export PATH="$REPO/stub-bin:$PATH"

  # Initial commit so HEAD exists; does not touch ops/feedback/.
  git add .
  git commit -q -m "init"
  rm -f "${SENTINEL_FEEDBACK}"
}

teardown() {
  rm -rf "$REPO"
  rm -f "${SENTINEL_FEEDBACK}"
}

@test "feedback index rebuilt when commit touches ops/feedback/" {
  cd "$REPO"
  printf 'review data\n' > ops/feedback/2026-05-22/atlas-test.md
  git add ops/feedback/2026-05-22/atlas-test.md
  git commit -q -m "add feedback"
  [ -f "${SENTINEL_FEEDBACK}" ]
}

@test "feedback index NOT rebuilt when commit does not touch ops/feedback/" {
  cd "$REPO"
  printf 'unrelated\n' > README.md
  git add README.md
  git commit -q -m "unrelated change"
  [ ! -f "${SENTINEL_FEEDBACK}" ]
}

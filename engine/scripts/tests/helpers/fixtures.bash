fixture_setup() {
  FIXTURE_TMP="$(mktemp -d)"
  FIXTURE_AI_ROOT="$FIXTURE_TMP/.ai"
  # Fake engine root: mirrors real engine/skills/ so forge_templates_dir() resolves
  # via CONCLAVE_ENGINE_ROOT, and advisor stubs are seeded here so canonical_advisors()
  # finds them (aligned with lib/paths.sh engine_root() / CONCLAVE_ENGINE_ROOT anchor).
  FIXTURE_ENGINE_ROOT="$FIXTURE_TMP/engine"
  local _real_engine_root
  _real_engine_root="$(cd -- "$BATS_TEST_DIRNAME/../.." && pwd -P)"
  mkdir -p "$FIXTURE_ENGINE_ROOT"
  cp -r "$_real_engine_root/skills" "$FIXTURE_ENGINE_ROOT/"
  mkdir -p "$FIXTURE_AI_ROOT/agent-memory/advisors"/{briefings,sessions,decisions,mentions}
  mkdir -p "$FIXTURE_AI_ROOT/.claude/skills/team.forge/scripts"
  export FIXTURE_TMP FIXTURE_AI_ROOT FIXTURE_ENGINE_ROOT
  export CONCLAVE_AI_ROOT="$FIXTURE_AI_ROOT"
  export CONCLAVE_ENGINE_ROOT="$FIXTURE_ENGINE_ROOT"
  # Seed the canonical advisor inventory so writer scripts that validate
  # advisor names (mention.sh, file-handoff.sh, etc.) accept these in tests.
  _seed_advisors dev kai-cto nexus-ceo quorum shade-ciso spark-cmo
}

# Create stub team.<name>/SKILL.md entries so canonical_advisors() resolves.
# Args: bare advisor names (e.g., "kai-cto").
# Stubs land in FIXTURE_ENGINE_ROOT/skills/ (CODE anchor, resolved by
# CONCLAVE_ENGINE_ROOT in advisors.sh) and in FIXTURE_AI_ROOT/.claude/skills/
# for scripts that walk the AI root .claude/skills/ tree directly.
_seed_advisors() {
  local name skill_dir
  for name in "$@"; do
    # Engine skills dir — the CONCLAVE_ENGINE_ROOT/skills anchor.
    skill_dir="$FIXTURE_ENGINE_ROOT/skills/team.${name}"
    mkdir -p "$skill_dir"
    if [[ ! -f "$skill_dir/SKILL.md" ]]; then
      printf -- '---\nname: team.%s\n---\nstub for tests\n' "$name" \
        > "$skill_dir/SKILL.md"
    fi
    # AI root .claude/skills — kept for scripts that reference the DATA root.
    skill_dir="$FIXTURE_AI_ROOT/.claude/skills/team.${name}"
    mkdir -p "$skill_dir"
    if [[ ! -f "$skill_dir/SKILL.md" ]]; then
      printf -- '---\nname: team.%s\n---\nstub for tests\n' "$name" \
        > "$skill_dir/SKILL.md"
    fi
  done
}

fixture_teardown() {
  rm -rf "$FIXTURE_TMP"
}

# Copy lib/ + a script into fixture. Creates ops/handoffs + ops/meetings.
_install_script() {
  local name="$1"
  mkdir -p "$FIXTURE_AI_ROOT/.claude/skills/team.forge/scripts"
  cp -r "$BATS_TEST_DIRNAME/../lib" "$FIXTURE_AI_ROOT/.claude/skills/team.forge/scripts/"
  cp "$BATS_TEST_DIRNAME/../$name" "$FIXTURE_AI_ROOT/.claude/skills/team.forge/scripts/"
  chmod +x "$FIXTURE_AI_ROOT/.claude/skills/team.forge/scripts/$name"
  mkdir -p "$FIXTURE_AI_ROOT/ops/handoffs"
  mkdir -p "$FIXTURE_AI_ROOT/ops/meetings"
}

# Copy a single template into fixture.
# Sources lib/paths.sh (after fixture_setup has set VOIDPAY_AI_ROOT) so
# forge_templates_dir() resolves via engine_root() without a stale depth-relative path.
_install_template() {
  local name="$1"
  # shellcheck source=engine/scripts/lib/paths.sh
  source "$BATS_TEST_DIRNAME/../lib/paths.sh"
  mkdir -p "$FIXTURE_AI_ROOT/.claude/skills/team.forge/templates"
  cp "$(forge_templates_dir)/$name" \
     "$FIXTURE_AI_ROOT/.claude/skills/team.forge/templates/"
}

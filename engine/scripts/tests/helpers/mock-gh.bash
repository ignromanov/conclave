# mock-gh.bash — override gh command for tests.
# Usage: load helpers/mock-gh; mock_gh_set_fixture "issue-list-advisor-nexus.json"

mock_gh_set_fixture() {
  local fname="$1"
  export MOCK_GH_FIXTURE="$BATS_TEST_DIRNAME/fixtures/$fname"
}

gh() {
  # Trivial router: return whatever file MOCK_GH_FIXTURE points to.
  if [[ -n "${MOCK_GH_FIXTURE:-}" && -f "$MOCK_GH_FIXTURE" ]]; then
    cat "$MOCK_GH_FIXTURE"
    return 0
  fi
  printf 'mock gh: no fixture set for: %s\n' "$*" >&2
  return 127
}
export -f gh

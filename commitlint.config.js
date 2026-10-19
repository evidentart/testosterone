module.exports = {
  extends: ['@commitlint/config-conventional'],
  // Dependabot's commit bodies paste release notes with long lines; its
  // headers already follow the `chore(deps)` prefix set in .github/dependabot.yml.
  ignores: [(message) => message.includes('Signed-off-by: dependabot[bot]')],
};

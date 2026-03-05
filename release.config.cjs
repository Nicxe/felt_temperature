const config = require("@nicxe/semantic-release-config")({
  componentDir: "custom_components/felt_temperature",
  manifestPath: "custom_components/felt_temperature/manifest.json",
  projectName: "Felt Temperature",
  repoSlug: "Nicxe/felt_temperature"
}
);

const githubPlugin = config.plugins.find(
  (plugin) => Array.isArray(plugin) && plugin[0] === "@semantic-release/github"
);

if (githubPlugin?.[1]) {
  githubPlugin[1].successCommentCondition = false;
}

module.exports = config;

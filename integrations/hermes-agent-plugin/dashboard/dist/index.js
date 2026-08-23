(function () {
  "use strict";
  // reqogniloom dashboard plugin — POC. Ultra-basic stats tab: a handful of
  // counts from ReqogniLoom's REST API. No build step (plain ES, like
  // hermes-achievements' bundle) — this file is loaded as-is by the host.
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  var React = SDK.React;
  var hooks = SDK.hooks;
  var C = SDK.components;

  function api(path) {
    // SDK.fetchJSON handles host auth (loopback header / gated cookie) and
    // throws Error("<status>: <body>") on non-2xx — same contract as
    // hermes-achievements' api() helper.
    return SDK.fetchJSON("/api/plugins/reqogniloom" + path);
  }

  function StatCard(props) {
    return React.createElement(
      C.Card,
      { className: "reqlo-stat-card" },
      React.createElement(
        C.CardContent,
        null,
        React.createElement("div", { className: "reqlo-stat-value" }, props.value === null || props.value === undefined ? "—" : String(props.value)),
        React.createElement("div", { className: "reqlo-stat-label" }, props.label)
      )
    );
  }

  function ReqogniLoomPage() {
    var stateStats = hooks.useState(null);
    var stats = stateStats[0];
    var setStats = stateStats[1];

    var stateVersion = hooks.useState(null);
    var version = stateVersion[0];
    var setVersion = stateVersion[1];

    var stateError = hooks.useState(null);
    var error = stateError[0];
    var setError = stateError[1];

    var stateLoading = hooks.useState(true);
    var loading = stateLoading[0];
    var setLoading = stateLoading[1];

    function load() {
      setLoading(true);
      setError(null);
      Promise.all([api("/stats"), api("/version")])
        .then(function (results) {
          var statsResult = results[0];
          var versionResult = results[1];
          if (statsResult && statsResult.error) {
            setError(statsResult.error);
          }
          setStats(statsResult);
          setVersion(versionResult);
        })
        .catch(function (err) {
          setError(String(err));
        })
        .finally(function () {
          setLoading(false);
        });
    }

    hooks.useEffect(function () {
      load();
    }, []);

    return React.createElement(
      "div",
      { className: "reqlo-page" },
      React.createElement("div", { className: "reqlo-header" },
        React.createElement("h2", null, "ReqogniLoom"),
        React.createElement(C.Button, { onClick: load, disabled: loading }, loading ? "Loading…" : "Refresh")
      ),
      error
        ? React.createElement("div", { className: "reqlo-error" }, error)
        : null,
      React.createElement(
        "div",
        { className: "reqlo-grid" },
        React.createElement(StatCard, { value: stats ? stats.requirements : null, label: "Requirements" }),
        React.createElement(StatCard, { value: stats ? stats.testcases : null, label: "Test Cases" }),
        React.createElement(StatCard, { value: stats ? stats.open_interviews : null, label: "Open Interviews" })
      ),
      version && version.app_version
        ? React.createElement("div", { className: "reqlo-footer" }, "ReqogniLoom " + version.app_version + " (" + version.commit_short + ")")
        : null
    );
  }

  window.__HERMES_PLUGINS__.register("reqogniloom", ReqogniLoomPage);
})();

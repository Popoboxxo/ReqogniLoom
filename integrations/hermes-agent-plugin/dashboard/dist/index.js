(function () {
  "use strict";
  // reqogniloom dashboard plugin — the ReqogniLoom tab: per-workspace counts and
  // the interviews that are still open. No build step (plain ES, like
  // hermes-achievements' bundle) — this file is loaded as-is by the host.
  //
  // The tab loads straight into the data: the host dashboard's own auth is the
  // only gate, so there is no token form, no /version probe-first gate and no
  // request credential to carry. Two things shaped the rest:
  //
  //   * a count answers "how many", never "which" — a session left hanging was
  //     invisible, so the tab lists the open interviews as detail rows;
  //   * the operator picks the workspace instead of silently showing whichever
  //     one sorted first.
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  var React = SDK.React;
  var hooks = SDK.hooks;
  var C = SDK.components;

  var PAGE_ERROR_ID = "reqlo-page-error";

  function networkError() {
    var err = new Error(
      "The dashboard API could not be reached (network error) — the request got no answer at all."
    );
    err.status = 0;
    err.detail = "";
    return err;
  }

  function httpError(status, detail) {
    var err = new Error(
      "The dashboard API answered HTTP " + status + (detail ? ": " + detail : ".")
    );
    err.status = status;
    err.detail = detail || "";
    return err;
  }

  function queryString(params) {
    var parts = [];
    Object.keys(params).forEach(function (key) {
      if (params[key]) parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(params[key]));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  // The transport is window.fetch, not SDK.fetchJSON: that helper has no
  // definition, shim or vendored copy anywhere in this repo, so whether it even
  // accepts a headers option is unverifiable. The call carries no credential —
  // it relies on the host dashboard's own auth, same-origin.
  function api(path) {
    return window
      .fetch("/api/plugins/reqogniloom" + path, {
        method: "GET",
        credentials: "same-origin"
      })
      .then(function (response) {
        return response.text().then(function (raw) {
          var body = null;
          try {
            body = raw ? JSON.parse(raw) : null;
          } catch (err) {
            body = null; // Non-JSON body: the status still has to surface.
          }
          if (!response.ok) {
            throw httpError(response.status, (body && body.detail) || "");
          }
          return body;
        });
      })
      .catch(function (err) {
        if (err && typeof err.status === "number") throw err;
        throw networkError();
      });
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

  function InterviewList(props) {
    var interviews = props.interviews;
    if (!interviews || !interviews.length) {
      return React.createElement(
        "p",
        { className: "reqlo-empty", "data-testid": "reqlo-interviews-empty" },
        "No open interviews in this workspace."
      );
    }
    var rows = interviews.map(function (session) {
      var id = session.id || session.session_id || "";
      return React.createElement(
        "tr",
        { key: id },
        React.createElement("td", { className: "reqlo-mono" }, id ? id.slice(0, 8) : "—"),
        React.createElement("td", null, session.artifact_type || session.session_kind || "—"),
        React.createElement("td", null, session.phase || "—"),
        React.createElement("td", null, session.status || "—"),
        React.createElement("td", null, session.updated_at || session.created_at || "—")
      );
    });
    return React.createElement(
      "table",
      { className: "reqlo-table", "data-testid": "reqlo-interviews-table" },
      React.createElement(
        "thead",
        null,
        React.createElement(
          "tr",
          null,
          React.createElement("th", null, "Session"),
          React.createElement("th", null, "Type"),
          React.createElement("th", null, "Phase"),
          React.createElement("th", null, "Status"),
          React.createElement("th", null, "Updated")
        )
      ),
      React.createElement("tbody", null, rows)
    );
  }

  function ReqogniLoomPage() {
    var stateStats = hooks.useState(null);
    var stats = stateStats[0];
    var setStats = stateStats[1];

    var stateVersion = hooks.useState(null);
    var version = stateVersion[0];
    var setVersion = stateVersion[1];

    var stateWorkspaces = hooks.useState([]);
    var workspaces = stateWorkspaces[0];
    var setWorkspaces = stateWorkspaces[1];

    var stateWorkspaceId = hooks.useState("");
    var workspaceId = stateWorkspaceId[0];
    var setWorkspaceId = stateWorkspaceId[1];

    var stateInterviews = hooks.useState([]);
    var interviews = stateInterviews[0];
    var setInterviews = stateInterviews[1];

    var stateError = hooks.useState(null);
    var error = stateError[0];
    var setError = stateError[1];

    var stateLoading = hooks.useState(true);
    var loading = stateLoading[0];
    var setLoading = stateLoading[1];

    function loadWorkspace(selected) {
      return Promise.all([api("/stats" + queryString({ workspace_id: selected })), api("/interviews" + queryString({ workspace_id: selected }))])
        .then(function (results) {
          var statsResult = results[0];
          var interviewsResult = results[1];
          var firstError = (statsResult && statsResult.error) || (interviewsResult && interviewsResult.error);
          setError(firstError || null);
          setStats(statsResult);
          setInterviews((interviewsResult && interviewsResult.interviews) || []);
          setWorkspaceId((statsResult && statsResult.workspace_id) || selected || "");
        });
    }

    function load() {
      setLoading(true);
      setError(null);
      return api("/version")
        .then(function (versionResult) {
          setVersion(versionResult);
          return api("/workspaces");
        })
        .then(function (workspaceResult) {
          var list = (workspaceResult && workspaceResult.workspaces) || [];
          setWorkspaces(list);
          var preferred = "";
          for (var index = 0; index < list.length; index += 1) {
            if (list[index] && list[index].id === workspaceId) preferred = workspaceId;
          }
          if (!preferred && list.length) preferred = list[0].id || "";
          return list.length ? loadWorkspace(preferred) : null;
        })
        .catch(function (err) {
          setError(err && err.message ? err.message : String(err));
        })
        .finally(function () {
          setLoading(false);
        });
    }

    hooks.useEffect(function () {
      load();
    }, []);

    function onSelectWorkspace(event) {
      var selected = event.target.value;
      setLoading(true);
      setError(null);
      loadWorkspace(selected)
        .catch(function (err) {
          setError(err && err.message ? err.message : String(err));
        })
        .finally(function () {
          setLoading(false);
        });
    }

    var header = React.createElement(
      "div",
      { className: "reqlo-header" },
      React.createElement("h2", null, "ReqogniLoom"),
      React.createElement(
        "div",
        null,
        React.createElement("button", {
          type: "button",
          onClick: load,
          disabled: loading,
          "data-testid": "reqlo-refresh-button"
        }, loading ? "Loading…" : "Refresh")
      )
    );

    var picker = workspaces.length
      ? React.createElement(
          "label",
          { className: "reqlo-workspace" },
          "Workspace",
          React.createElement(
            "select",
            {
              value: workspaceId,
              onChange: onSelectWorkspace,
              disabled: loading,
              "data-testid": "reqlo-workspace-select"
            },
            workspaces.map(function (workspace) {
              return React.createElement(
                "option",
                { key: workspace.id, value: workspace.id },
                workspace.name || workspace.id
              );
            })
          )
        )
      : null;

    // Follow-up: a per-workspace artifact drill-in is intentionally NOT built
    // yet — the plugin exposes no /artifacts endpoint, so the counters below are
    // counts only. Wiring each card through to an artifact list/detail view is a
    // follow-up once such a read endpoint exists.
    return React.createElement(
      "div",
      { className: "reqlo-page" },
      header,
      error
        ? React.createElement("div", { className: "reqlo-error", id: PAGE_ERROR_ID, role: "alert" }, error)
        : null,
      picker,
      React.createElement(
        "div",
        { className: "reqlo-grid" },
        React.createElement(StatCard, { value: stats ? stats.requirements : null, label: "Requirements" }),
        React.createElement(StatCard, { value: stats ? stats.testcases : null, label: "Test Cases" }),
        React.createElement(StatCard, { value: stats ? stats.open_interviews : null, label: "Open Interviews" })
      ),
      React.createElement("h3", { className: "reqlo-section" }, "Open interviews"),
      React.createElement(InterviewList, { interviews: interviews }),
      version && version.app_version
        ? React.createElement("div", { className: "reqlo-footer" }, "ReqogniLoom " + version.app_version + (version.commit_short ? " (" + version.commit_short + ")" : ""))
        : null
    );
  }

  window.__HERMES_PLUGINS__.register("reqogniloom", ReqogniLoomPage);
})();

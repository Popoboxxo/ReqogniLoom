(function () {
  "use strict";
  // reqogniloom dashboard plugin — the ReqogniLoom tab: per-workspace counts and
  // the interviews that are still open. No build step (plain ES, like
  // hermes-achievements' bundle) — this file is loaded as-is by the host.
  //
  // Two upstream defects shaped this file:
  //
  //   * the API's token gate is OPT-IN on the server side (PLUG-12), so the tab
  //     now probes first and only asks for a credential when the server actually
  //     demands one (401). Demanding a token the server never wanted was the most
  //     visible defect of the first beta: "Connect" with nothing to connect to.
  //   * a count answers "how many", never "which" — a session left hanging was
  //     invisible. The tab lists the open interviews and lets the operator pick
  //     the workspace instead of silently showing whichever one sorted first.
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  var React = SDK.React;
  var hooks = SDK.hooks;
  var C = SDK.components;

  // The token stays optional: only a server with a configured gate needs it.
  var TOKEN_KEY = "reqogniloom.dashboard.token";
  var CREDENTIAL_HEADER = "X-ReqogniLoom-Dashboard-Token";
  var TOKEN_ENV_VAR = "REQOGNILOOM_DASHBOARD_TOKEN";

  var TOKEN_INPUT_ID = "reqlo-connect-token";
  var TOKEN_HINT_ID = "reqlo-connect-hint";
  var CONNECT_ERROR_ID = "reqlo-connect-error";
  var PAGE_ERROR_ID = "reqlo-page-error";

  // sessionStorage, deliberately not localStorage: the token is a live shared
  // secret and must not outlive the browser session. Access can throw (private
  // mode, storage disabled) — that degrades to "no token", never to a crash.
  function readToken() {
    try {
      return window.sessionStorage.getItem(TOKEN_KEY) || "";
    } catch (err) {
      return "";
    }
  }

  function hasToken() {
    return readToken() !== "";
  }

  function storeToken(value) {
    try {
      window.sessionStorage.setItem(TOKEN_KEY, value);
      return true;
    } catch (err) {
      return false;
    }
  }

  function forgetToken() {
    try {
      window.sessionStorage.removeItem(TOKEN_KEY);
    } catch (err) {
      // An unusable store already reads as "no token".
    }
  }

  // Turn the server's status + detail into an operator-actionable sentence.
  // Only the status codes and the server's own detail are used — never the
  // token, which therefore cannot leak through an error message.
  function describeFailure(status, detail) {
    var text = (detail || "").toLowerCase();
    if (status === 401) {
      if (text.indexOf("missing") !== -1) {
        return "The dashboard host did not forward the " + CREDENTIAL_HEADER +
          " request header, so no token reached the API. This is a host/proxy problem — the token was never checked.";
      }
      return "The dashboard API requires a token and rejected this one. Connect with the value of the " +
        TOKEN_ENV_VAR + " environment variable.";
    }
    if (status === 403) {
      if (text.indexOf(TOKEN_ENV_VAR.toLowerCase()) !== -1) {
        return "The dashboard process running this tab has " + TOKEN_ENV_VAR +
          " unset while the plugin build still expects it. Restart the dashboard on a build with the opt-in gate, or export the variable.";
      }
      if (text.indexOf("origin") !== -1) {
        return "This page's origin is not in the dashboard allowlist. Add it to REQOGNILOOM_DASHBOARD_ALLOWED_ORIGINS in the dashboard process environment.";
      }
      if (text.indexOf("host") !== -1) {
        return "This host is not in the dashboard allowlist. Add it to REQOGNILOOM_DASHBOARD_ALLOWED_HOSTS in the dashboard process environment.";
      }
      return "The dashboard refused the request (HTTP 403)" + (detail ? ": " + detail : ".");
    }
    return "The dashboard API answered HTTP " + status + (detail ? ": " + detail : ".");
  }

  function httpError(status, detail) {
    var err = new Error(describeFailure(status, detail));
    err.status = status;
    err.detail = detail || "";
    return err;
  }

  function networkError() {
    var err = new Error(
      "The dashboard API could not be reached (network error) — the request got no answer at all."
    );
    err.status = 0;
    err.detail = "";
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
  // accepts a headers option is unverifiable — and an option it ignored would
  // silently reproduce a 401. If a real SDK contract is ever proven, this
  // function is the single place to revisit.
  //
  // The URL stays relative and same-origin: a custom header only triggers a
  // CORS preflight for cross-origin requests, so this call is unaffected and
  // the preflight guard still keeps a foreign-origin page out.
  //
  // No stored token → no header at all. That is the opt-in case and it must
  // reach the server, which is why the old "reject before fetching" guard is
  // gone.
  function api(path) {
    var token = readToken();
    var headers = {};
    if (token) headers[CREDENTIAL_HEADER] = token;

    return window
      .fetch("/api/plugins/reqogniloom" + path, {
        method: "GET",
        headers: headers,
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
    // "probing" → ask the server whether it wants a credential at all;
    // "connect" → it does (401/403), show the form; "ready" → we have data.
    var statePhase = hooks.useState("probing");
    var phase = statePhase[0];
    var setPhase = statePhase[1];

    var stateDraft = hooks.useState("");
    var draft = stateDraft[0];
    var setDraft = stateDraft[1];

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
          setPhase("ready");
          return api("/workspaces").then(function (workspaceResult) {
            var list = (workspaceResult && workspaceResult.workspaces) || [];
            setWorkspaces(list);
            var preferred = "";
            for (var index = 0; index < list.length; index += 1) {
              if (list[index] && list[index].id === workspaceId) preferred = workspaceId;
            }
            if (!preferred && list.length) preferred = list[0].id || "";
            return list.length ? loadWorkspace(preferred) : null;
          });
        })
        .catch(function (err) {
          setPhase("connect");
          // A 401 means our stored token (if any) is not the answer: drop it so
          // the form starts clean. A 403 is a server-side guard where the token
          // may well be correct — keep it and show the reason.
          if (err && err.status === 401) forgetToken();
          setError(err && err.message ? err.message : String(err));
        })
        .finally(function () {
          setLoading(false);
        });
    }

    hooks.useEffect(function () {
      load();
    }, []);

    function connect(event) {
      event.preventDefault();
      var value = (draft || "").trim();
      if (!value) {
        setError("Enter the dashboard token to connect.");
        return;
      }
      setDraft(""); // Keep the secret out of the DOM once it is handed over.
      if (!storeToken(value)) {
        setError("This browser refused to store the token in sessionStorage (private mode?), so the tab cannot authenticate.");
        return;
      }
      setPhase("probing");
      load();
    }

    function disconnect() {
      forgetToken();
      setStats(null);
      setVersion(null);
      setInterviews([]);
      setError(null);
      setPhase("probing");
      load();
    }

    function onSelectWorkspace(event) {
      var selected = event.target.value;
      setLoading(true);
      setError(null);
      loadWorkspace(selected)
        .catch(function (err) {
          if (err && err.status === 401) {
            forgetToken();
            setPhase("connect");
          }
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
        phase === "ready"
          ? React.createElement("button", {
              type: "button",
              onClick: load,
              disabled: loading,
              "data-testid": "reqlo-refresh-button"
            }, loading ? "Loading…" : "Refresh")
          : null,
        hasToken()
          ? React.createElement("button", {
              type: "button",
              onClick: disconnect,
              "data-testid": "reqlo-disconnect-button"
            }, "Disconnect")
          : null
      )
    );

    if (phase !== "ready") {
      return React.createElement(
        "div",
        { className: "reqlo-page" },
        header,
        phase === "probing"
          ? React.createElement("p", { className: "reqlo-subtle", "data-testid": "reqlo-probing" }, "Loading…")
          : React.createElement(
              "form",
              { className: "reqlo-connect-form", onSubmit: connect },
              React.createElement("label", { htmlFor: TOKEN_INPUT_ID }, "Dashboard token"),
              React.createElement("input", {
                id: TOKEN_INPUT_ID,
                type: "password",
                className: "reqlo-connect-input",
                value: draft,
                autoComplete: "off",
                autoFocus: true,
                "aria-describedby": error ? TOKEN_HINT_ID + " " + CONNECT_ERROR_ID : TOKEN_HINT_ID,
                "data-testid": "reqlo-connect-token-input",
                onChange: function (event) {
                  setDraft(event.target.value);
                }
              }),
              React.createElement(
                "p",
                { className: "reqlo-connect-hint", id: TOKEN_HINT_ID },
                "Only needed when the dashboard process sets " + TOKEN_ENV_VAR + " — the token must match it."
              ),
              error
                ? React.createElement("div", { className: "reqlo-error", id: CONNECT_ERROR_ID, role: "alert" }, error)
                : null,
              React.createElement(
                "button",
                { type: "submit", "data-testid": "reqlo-connect-submit" },
                "Connect"
              )
            )
      );
    }

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

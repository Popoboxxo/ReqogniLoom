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

  // The dashboard API is fail-closed behind one custom request header, so the
  // operator pastes the shared secret once per browser session.
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
      return "The dashboard rejected the token as invalid. Disconnect and re-enter the value of the " +
        TOKEN_ENV_VAR + " environment variable.";
    }
    if (status === 403) {
      if (text.indexOf(TOKEN_ENV_VAR.toLowerCase()) !== -1) {
        return TOKEN_ENV_VAR + " is not set in the dashboard process, so the API refuses every request. Export it there and restart the dashboard.";
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
      "The dashboard API could not be reached (network error) — the request got no answer at all, so the token was not rejected."
    );
    err.status = 0;
    err.detail = "";
    return err;
  }

  // The transport is window.fetch, not SDK.fetchJSON: that helper has no
  // definition, shim or vendored copy anywhere in this repo, so whether it even
  // accepts a headers option is unverifiable — and an option it ignored would
  // silently reproduce today's 401. If a real SDK contract is ever proven, this
  // function is the single place to revisit.
  //
  // The URL stays relative and same-origin: a custom header only triggers a
  // CORS preflight for cross-origin requests, so this call is unaffected and
  // the preflight guard still keeps a foreign-origin page out.
  function api(path) {
    // Read at call time, so both members of the parallel pair carry the header.
    var token = readToken();
    if (!token) {
      return Promise.reject(
        new Error("The dashboard tab is not connected: no dashboard token in this browser session.")
      );
    }
    var headers = {};
    headers[CREDENTIAL_HEADER] = token;

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

  function ReqogniLoomPage() {
    var stateConnected = hooks.useState(hasToken());
    var connected = stateConnected[0];
    var setConnected = stateConnected[1];

    var stateDraft = hooks.useState("");
    var draft = stateDraft[0];
    var setDraft = stateDraft[1];

    var stateStats = hooks.useState(null);
    var stats = stateStats[0];
    var setStats = stateStats[1];

    var stateVersion = hooks.useState(null);
    var version = stateVersion[0];
    var setVersion = stateVersion[1];

    var stateError = hooks.useState(null);
    var error = stateError[0];
    var setError = stateError[1];

    var stateLoading = hooks.useState(hasToken());
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
          // A rejected credential means we are not connected: drop it and fall
          // back to the form. A 403 is a server-side guard (unset token env
          // var, allowlist) — there the token may well be correct.
          if (err && err.status === 401) {
            forgetToken();
            setConnected(false);
          }
          setError(err && err.message ? err.message : String(err));
        })
        .finally(function () {
          setLoading(false);
        });
    }

    // Keyed on `connected` so that connecting triggers the very first load
    // without a second call, and disconnecting triggers none at all.
    hooks.useEffect(function () {
      if (connected) load();
    }, [connected]);

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
      setConnected(true);
    }

    function disconnect() {
      forgetToken();
      setConnected(false);
      setDraft("");
      setStats(null);
      setVersion(null);
      setError(null);
    }

    if (!connected) {
      return React.createElement(
        "div",
        { className: "reqlo-page" },
        React.createElement("div", { className: "reqlo-header" },
          React.createElement("h2", null, "ReqogniLoom")
        ),
        React.createElement(
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
            "Must equal the " + TOKEN_ENV_VAR + " environment variable of the process that runs the dashboard."
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

    return React.createElement(
      "div",
      { className: "reqlo-page" },
      React.createElement("div", { className: "reqlo-header" },
        React.createElement("h2", null, "ReqogniLoom"),
        React.createElement("div", null,
          React.createElement("button", {
            type: "button",
            onClick: load,
            disabled: loading,
            "data-testid": "reqlo-refresh-button"
          }, loading ? "Loading…" : "Refresh"),
          React.createElement("button", {
            type: "button",
            onClick: disconnect,
            "data-testid": "reqlo-disconnect-button"
          }, "Disconnect")
        )
      ),
      error
        ? React.createElement("div", { className: "reqlo-error", id: PAGE_ERROR_ID, role: "alert" }, error)
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

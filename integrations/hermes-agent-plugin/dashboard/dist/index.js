(function () {
  "use strict";
  // reqogniloom dashboard plugin — the ReqogniLoom tab, full surface.
  //
  // Views: Overview · Write · Tools · Servers · Admin, driven by three backend
  // capabilities (see dashboard/plugin_api.py):
  //
  //   * /servers … — the multi-server registry the /reqogniloom command shares;
  //   * /tools …   — the live MCP catalogue of the selected server, classified
  //                  as read / compute / mutate (dashboard/reqogniloom_tools);
  //   * /write …   — the two-phase gate: /write/preview returns the risk class
  //                  and a token bound to server+tool+arguments, /write executes.
  //
  // Two rules shape this file:
  //
  //   1. Nothing is hardcoded per tool. The catalogue delivers every tool with
  //      its JSON schema, so a tool the server adds later is usable here without
  //      touching this plugin. The curated shortcuts only pick *which* tool to
  //      open, never which fields exist.
  //   2. The confirmation step cannot be skipped from here. Reads execute
  //      straight away, mutating calls go through the confirm panel, destructive
  //      ones additionally require the tool name typed — and the backend refuses
  //      a token that no longer matches the arguments.
  //
  // No build step (plain ES, loaded as-is by the host), no credential of its own:
  // the host dashboard's session cookie is the only inbound gate.
  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  var React = SDK.React;
  var hooks = SDK.hooks;
  var C = SDK.components;
  var h = React.createElement;

  var API = "/api/plugins/reqogniloom";

  // Tool names used by the curated shortcuts. Every one of them is asserted
  // against the repo's tool manifest in tests/test_tools_catalog.py — a rename
  // upstream cannot silently turn a button into a no-op.
  var TOOL = {
    requirementCreate: "requirement.create",
    needCreate: "needs.create",
    architectureCreate: "architecture.create",
    adrCreate: "adr.create",
    riskCreate: "risk.create",
    issueCreate: "issue.create",
    glossaryCreate: "glossary.create",
    changeRequestCreate: "change_request.create",
    icdCreate: "icd.create",
    testCreate: "test.create",
    diagramCreate: "diagram.create",
    goalCreate: "goal.create",
    linkCreate: "traceability.create_link",
    linkTypes: "link_type.list",
    reviewPending: "review.list_pending",
    reviewApprove: "review.approve",
    reviewReject: "review.reject",
    reviewRequestChanges: "review.request_changes",
    suggestionList: "suggestion.list",
    suggestionAccept: "suggestion.accept",
    suggestionReject: "suggestion.reject",
    memoryWrite: "memory.write",
    memoryOverview: "memory.overview",
    baselineCreate: "baseline.create",
    interviewAnswer: "interview.answer",
    interviewChat: "interview.chat",
    interviewFormalize: "interview.formalize",
    interviewAbandon: "interview.abandon"
  };

  var CREATE_FLOWS = [
    { label: "Requirement", tool: TOOL.requirementCreate },
    { label: "Stakeholder need", tool: TOOL.needCreate },
    { label: "Architecture element", tool: TOOL.architectureCreate },
    { label: "ADR", tool: TOOL.adrCreate },
    { label: "Risk", tool: TOOL.riskCreate },
    { label: "Issue", tool: TOOL.issueCreate },
    { label: "Glossary term", tool: TOOL.glossaryCreate },
    { label: "Change request", tool: TOOL.changeRequestCreate },
    { label: "ICD", tool: TOOL.icdCreate },
    { label: "Test case", tool: TOOL.testCreate },
    { label: "Diagram", tool: TOOL.diagramCreate },
    { label: "Goal", tool: TOOL.goalCreate }
  ];

  var VIEWS = [
    { id: "overview", label: "Overview" },
    { id: "write", label: "Write" },
    { id: "tools", label: "Tools" },
    { id: "servers", label: "Servers" },
    { id: "admin", label: "Admin" }
  ];

  // ------------------------------------------------------------------------
  // transport
  // ------------------------------------------------------------------------

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
    Object.keys(params || {}).forEach(function (key) {
      if (params[key]) parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(params[key]));
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  // The transport is window.fetch: SDK.fetchJSON has no definition anywhere in
  // the repo, so its contract (headers? POST?) is unverifiable. Same-origin, no
  // credential, exactly like the read-only revision of this tab did.
  function request(method, path, body) {
    var options = { method: method, credentials: "same-origin" };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }
    return window
      .fetch(API + path, options)
      .then(function (response) {
        return response.text().then(function (raw) {
          var parsed = null;
          try {
            parsed = raw ? JSON.parse(raw) : null;
          } catch (err) {
            parsed = null; // Non-JSON body: the status still has to surface.
          }
          if (!response.ok) {
            throw httpError(response.status, (parsed && parsed.detail) || "");
          }
          return parsed;
        });
      })
      .catch(function (err) {
        if (err && typeof err.status === "number") throw err;
        throw networkError();
      });
  }

  function apiGet(path) {
    return request("GET", path);
  }

  function apiPost(path, body) {
    return request("POST", path, body || {});
  }

  function apiPatch(path, body) {
    return request("PATCH", path, body || {});
  }

  function apiDelete(path) {
    return request("DELETE", path);
  }

  // ------------------------------------------------------------------------
  // small helpers
  // ------------------------------------------------------------------------

  function messageOf(err) {
    return err && err.message ? err.message : String(err);
  }

  function shortId(value) {
    var text = value === null || value === undefined ? "" : String(value);
    return text.length > 8 ? text.slice(0, 8) : text || "—";
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "object") {
      try {
        return JSON.stringify(value);
      } catch (err) {
        return String(value);
      }
    }
    return String(value);
  }

  function classBadge(toolClass) {
    var tone = toolClass === "mutate" ? "reqlo-badge-mutate" : toolClass === "compute" ? "reqlo-badge-compute" : "reqlo-badge-read";
    return h("span", { className: "reqlo-badge " + tone }, toolClass);
  }

  function gateIsOpen(registry) {
    return !registry || registry.write_gate !== false;
  }

  function StatCard(props) {
    return h(
      C.Card,
      { className: "reqlo-stat-card" },
      h(
        C.CardContent,
        null,
        h(
          "div",
          { className: "reqlo-stat-value" },
          props.value === null || props.value === undefined ? "—" : String(props.value)
        ),
        h("div", { className: "reqlo-stat-label" }, props.label)
      )
    );
  }

  function findTool(catalogue, name) {
    if (!catalogue || !catalogue.tools) return null;
    for (var index = 0; index < catalogue.tools.length; index += 1) {
      if (catalogue.tools[index].name === name) return catalogue.tools[index];
    }
    return null;
  }

  function problemsOf(result) {
    return (result && result.problems) || [];
  }

  // ------------------------------------------------------------------------
  // schema-driven form
  // ------------------------------------------------------------------------

  function initialValues(schema) {
    var values = {};
    var properties = (schema && schema.properties) || {};
    Object.keys(properties).forEach(function (name) {
      var spec = properties[name] || {};
      if (spec.default !== undefined) values[name] = spec.default;
      else if (spec.enum && spec.enum.length) values[name] = spec.enum[0];
      else if (spec.type === "boolean") values[name] = false;
      else values[name] = "";
    });
    return values;
  }

  function coerceField(spec, raw) {
    if (spec.type === "integer" || spec.type === "number") {
      if (raw === "" || raw === null || raw === undefined) return "";
      var num = Number(raw);
      return isNaN(num) ? raw : num;
    }
    if (spec.type === "array" || spec.type === "object") {
      var text = String(raw || "").trim();
      if (!text) return spec.type === "array" ? [] : {};
      try {
        return JSON.parse(text);
      } catch (err) {
        return text; // The backend validator reports the type mismatch.
      }
    }
    return raw;
  }

  // Renders exactly the properties the tool declares. Nothing else is offered:
  // the backend accepts some undeclared parameters (finding #1376) and this UI
  // must not be the place that starts sending them.
  function SchemaForm(props) {
    var schema = props.schema || {};
    var properties = schema.properties || {};
    var required = schema.required || [];
    var names = Object.keys(properties).sort();
    if (!names.length) {
      return h("p", { className: "reqlo-hint" }, "This tool takes no parameters.");
    }
    var fields = names.map(function (name) {
      var spec = properties[name] || {};
      var value = props.values[name];
      var isRequired = required.indexOf(name) !== -1;
      var onChange = function (raw) {
        var next = {};
        Object.keys(props.values).forEach(function (key) {
          next[key] = props.values[key];
        });
        next[name] = coerceField(spec, raw);
        props.onChange(next);
      };
      var common = {
        "data-testid": "reqlo-field-" + name,
        disabled: props.disabled,
        onChange: function (event) {
          onChange(event.target.value);
        },
        value: value === undefined || value === null ? "" : String(value)
      };
      var control;
      if (spec.enum && spec.enum.length) {
        control = h(
          "select",
          Object.assign({}, common, { className: "reqlo-input" }),
          spec.enum.map(function (option) {
            return h("option", { key: String(option), value: option }, String(option));
          })
        );
      } else if (spec.type === "boolean") {
        control = h("input", {
          type: "checkbox",
          "data-testid": "reqlo-field-" + name,
          disabled: props.disabled,
          checked: value === true,
          onChange: function (event) {
            onChange(event.target.checked);
          }
        });
      } else if (spec.type === "array" || spec.type === "object") {
        control = h("textarea", Object.assign({}, common, { rows: 3, className: "reqlo-input reqlo-mono" }));
      } else if (spec.format === "date-time" || spec.format === "date") {
        control = h("input", Object.assign({}, common, { type: "text", className: "reqlo-input", placeholder: "YYYY-MM-DD" }));
      } else {
        control = h("input", Object.assign({}, common, { type: "text", className: "reqlo-input" }));
      }
      return h(
        "label",
        { key: name, className: "reqlo-field" },
        h(
          "span",
          { className: "reqlo-field-label" },
          name,
          isRequired ? h("span", { className: "reqlo-required" }, " *") : null
        ),
        control,
        spec.description ? h("span", { className: "reqlo-hint" }, spec.description) : null
      );
    });
    return h("div", { className: "reqlo-form" }, fields);
  }

  // ------------------------------------------------------------------------
  // confirmation + result panels
  // ------------------------------------------------------------------------

  function ConfirmPanel(props) {
    var preview = props.preview;
    if (!preview) return null;
    var isDestructive = preview.risk === "destructive";
    var typedOk = !isDestructive || props.typed === preview.tool;
    return h(
      "div",
      { className: "reqlo-dialog", role: "dialog", "aria-modal": "true", "data-testid": "reqlo-confirm" },
      h("h4", null, isDestructive ? "Confirm destructive call" : "Confirm call"),
      h(
        "p",
        { className: "reqlo-hint" },
        preview.server + " · " + preview.tool + (preview.summary ? " · " + preview.summary : "")
      ),
      preview.requires_human
        ? h(
            "p",
            { className: preview.human_key_available ? "reqlo-hint" : "reqlo-error" },
            preview.human_key_available
              ? "Runs with the human principal (this decides a proposal)."
              : "Needs the human API key (user_api_key) of this server — set it in the server panel."
          )
        : null,
      preview.blocked
        ? h("p", { className: "reqlo-error" }, "The write gate is closed for this install.")
        : null,
      problemsOf(preview).length
        ? h(
            "ul",
            { className: "reqlo-problems", "data-testid": "reqlo-problems" },
            problemsOf(preview).map(function (problem) {
              return h("li", { key: problem }, problem);
            })
          )
        : null,
      isDestructive
        ? h(
            "label",
            { className: "reqlo-field" },
            h("span", { className: "reqlo-field-label" }, "Type " + preview.tool + " to confirm"),
            h("input", {
              type: "text",
              className: "reqlo-input",
              value: props.typed || "",
              "data-testid": "reqlo-typed-confirmation",
              disabled: props.disabled,
              onChange: function (event) {
                props.onTyped(event.target.value);
              }
            })
          )
        : null,
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            onClick: props.onConfirm,
            disabled: props.disabled || !typedOk || preview.blocked || problemsOf(preview).length > 0,
            "data-testid": "reqlo-confirm-button"
          },
          props.disabled ? "Running…" : isDestructive ? "Run destructive call" : "Run"
        ),
        h("button", {
          type: "button",
          onClick: props.onCancel,
          disabled: props.disabled,
          "data-testid": "reqlo-cancel-button"
        }, "Cancel")
      )
    );
  }

  function ResultPanel(props) {
    if (!props.result) return null;
    var result = props.result;
    var body = result.error
      ? h("div", { className: "reqlo-error", "data-testid": "reqlo-result-error" }, result.error)
      : h(
          "pre",
          { className: "reqlo-result reqlo-mono", "data-testid": "reqlo-result" },
          JSON.stringify(result.ok === undefined ? result : result.result, null, 2)
        );
    return h(
      "div",
      { className: "reqlo-result-panel" },
      h(
        "div",
        { className: "reqlo-result-head" },
        h("strong", null, result.tool || "result"),
        result.principal ? h("span", { className: "reqlo-hint" }, " principal: " + result.principal) : null,
        result.mutating ? h("span", { className: "reqlo-hint" }, " · mutating") : null
      ),
      body
    );
  }

  // ------------------------------------------------------------------------
  // tool console
  // ------------------------------------------------------------------------

  function ToolConsole(props) {
    var stateQuery = hooks.useState("");
    var query = stateQuery[0];
    var setQuery = stateQuery[1];
    var stateGroup = hooks.useState("");
    var group = stateGroup[0];
    var setGroup = stateGroup[1];
    var stateSelected = hooks.useState("");
    var selected = stateSelected[0];
    var setSelected = stateSelected[1];
    var stateValues = hooks.useState({});
    var values = stateValues[0];
    var setValues = stateValues[1];

    var catalogue = props.catalogue;
    var tools = (catalogue && catalogue.tools) || [];
    var filtered = tools.filter(function (tool) {
      if (group && tool.group !== group) return false;
      if (!query) return true;
      var needle = query.toLowerCase();
      return tool.name.toLowerCase().indexOf(needle) !== -1 || (tool.description || "").toLowerCase().indexOf(needle) !== -1;
    });
    var entry = selected ? findTool(catalogue, selected) : null;

    function pick(name) {
      var tool = findTool(catalogue, name);
      setSelected(name);
      setValues(initialValues(tool && tool.input_schema));
      props.onResetResult();
    }

    function run() {
      if (!entry) return;
      props.onRun(entry, values);
    }

    var groups = (catalogue && catalogue.groups) || [];
    var rows = filtered.slice(0, 300).map(function (tool) {
      return h(
        "tr",
        {
          key: tool.name,
          className: tool.name === selected ? "reqlo-row-selected" : "",
          onClick: function () {
            pick(tool.name);
          },
          "data-testid": "reqlo-tool-row"
        },
        h("td", { className: "reqlo-mono" }, tool.name),
        h("td", null, classBadge(tool.class)),
        h("td", null, tool.requires_human ? h("span", { className: "reqlo-badge reqlo-badge-human" }, "human key") : null),
        h("td", null, tool.destructive ? h("span", { className: "reqlo-badge reqlo-badge-destructive" }, "destructive") : null),
        h("td", { className: "reqlo-desc" }, tool.description)
      );
    });

    return h(
      "div",
      { className: "reqlo-split" },
      h(
        "div",
        { className: "reqlo-split-left" },
        h(
          "div",
          { className: "reqlo-filters" },
          h("input", {
            type: "text",
            className: "reqlo-input",
            placeholder: "Search " + tools.length + " tools…",
            value: query,
            "data-testid": "reqlo-tool-search",
            onChange: function (event) {
              setQuery(event.target.value);
            }
          }),
          h(
            "select",
            {
              className: "reqlo-input",
              value: group,
              "data-testid": "reqlo-tool-group",
              onChange: function (event) {
                setGroup(event.target.value);
              }
            },
            h("option", { value: "" }, "All groups"),
            groups.map(function (item) {
              return h("option", { key: item.name, value: item.name }, item.name + " (" + item.tool_count + ")");
            })
          ),
          h(
            "button",
            {
              type: "button",
              onClick: props.onRefresh,
              disabled: props.busy,
              "data-testid": "reqlo-tool-refresh"
            },
            "Refresh catalogue"
          )
        ),
        h(
          "table",
          { className: "reqlo-table reqlo-tool-table", "data-testid": "reqlo-tool-table" },
          h(
            "thead",
            null,
            h(
              "tr",
              null,
              h("th", null, "Tool"),
              h("th", null, "Class"),
              h("th", null, "Key"),
              h("th", null, "Risk"),
              h("th", null, "Description")
            )
          ),
          h("tbody", null, rows)
        ),
        filtered.length > 300
          ? h("p", { className: "reqlo-hint" }, "Showing the first 300 of " + filtered.length + " matches — narrow the search.")
          : null
      ),
      h(
        "div",
        { className: "reqlo-split-right" },
        entry
          ? h(
              "div",
              null,
              h("h4", { className: "reqlo-mono" }, entry.name),
              h("p", { className: "reqlo-hint" }, entry.description || ""),
              entry.destructive ? h("p", { className: "reqlo-error" }, "Destructive: requires typing the tool name.") : null,
              h(SchemaForm, {
                schema: entry.input_schema,
                values: values,
                onChange: setValues,
                disabled: props.busy
              }),
              h(
                "div",
                { className: "reqlo-dialog-actions" },
                h(
                  "button",
                  {
                    type: "button",
                    onClick: run,
                    disabled: props.busy,
                    "data-testid": "reqlo-tool-run"
                  },
                  props.busy ? "Running…" : entry.class === "mutate" ? "Preview & run…" : "Run"
                ),
                h("button", {
                  type: "button",
                  onClick: props.onResetResult,
                  disabled: props.busy,
                  "data-testid": "reqlo-tool-clear"
                }, "Clear result")
              )
            )
          : h("p", { className: "reqlo-hint", "data-testid": "reqlo-tool-none" }, "Pick a tool on the left.")
      )
    );
  }

  // ------------------------------------------------------------------------
  // curated write flows
  // ------------------------------------------------------------------------

  function CreateFlow(props) {
    var stateTool = hooks.useState(props.flows[0].tool);
    var tool = stateTool[0];
    var setTool = stateTool[1];
    var stateValues = hooks.useState(null);
    var values = stateValues[0];
    var setValues = stateValues[1];
    var entry = findTool(props.catalogue, tool);

    hooks.useEffect(
      function () {
        setValues(initialValues(entry && entry.input_schema));
      },
      [tool]
    );

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-create-flow" },
      h("h3", null, "Create an artifact"),
      h(
        "div",
        { className: "reqlo-filters" },
        h(
          "select",
          {
            className: "reqlo-input",
            value: tool,
            "data-testid": "reqlo-create-type",
            onChange: function (event) {
              setTool(event.target.value);
            }
          },
          props.flows.map(function (flow) {
            return h("option", { key: flow.tool, value: flow.tool }, flow.label);
          })
        )
      ),
      entry
        ? h(SchemaForm, { schema: entry.input_schema, values: values || {}, onChange: setValues, disabled: props.busy })
        : h("p", { className: "reqlo-hint" }, "This tool is not on the server (catalogue not loaded)."),
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !entry,
            "data-testid": "reqlo-create-run",
            onClick: function () {
              props.onRun(entry, props.withWorkspace(values || {}));
            }
          },
          "Preview & create…"
        )
      ),
      h(
        "p",
        { className: "reqlo-hint" },
        "Created objects are born as proposals (workflow state 'proposed') because the plugin writes with the agent key — confirm them in the review queue below or in ReqogniLoom."
      )
    );
  }

  function LinkFlow(props) {
    var entry = findTool(props.catalogue, TOOL.linkCreate);
    var stateValues = hooks.useState(null);
    var values = stateValues[0];
    var setValues = stateValues[1];
    var stateTypes = hooks.useState([]);
    var types = stateTypes[0];
    var setTypes = stateTypes[1];
    var stateError = hooks.useState(null);
    var error = stateError[0];
    var setError = stateError[1];

    hooks.useEffect(
      function () {
        setValues(initialValues(entry && entry.input_schema));
        props.runRead(TOOL.linkTypes, props.withWorkspace({})).then(function (result) {
          var payload = result && result.result;
          var list = (payload && (payload.link_types || payload.linkTypes || payload.items)) || [];
          if (payload && payload.error) setError(payload.error);
          setTypes(Array.isArray(list) ? list : []);
        });
      },
      []
    );

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-link-flow" },
      h("h3", null, "Link two artifacts"),
      error ? h("p", { className: "reqlo-error" }, error) : null,
      types.length
        ? h("p", { className: "reqlo-hint" }, "Known link types: " + types.map(function (item) { return item.key || item.name || item; }).join(", "))
        : h("p", { className: "reqlo-hint" }, "Link types load with the catalogue."),
      entry
        ? h(SchemaForm, { schema: entry.input_schema, values: values || {}, onChange: setValues, disabled: props.busy })
        : h("p", { className: "reqlo-hint" }, "traceability.create_link is not on this server."),
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !entry,
            "data-testid": "reqlo-link-run",
            onClick: function () {
              props.onRun(entry, props.withWorkspace(values || {}));
            }
          },
          "Preview & link…"
        )
      )
    );
  }

  function ReviewQueue(props) {
    var statePending = hooks.useState(null);
    var pending = statePending[0];
    var setPending = statePending[1];
    var stateBusy = hooks.useState(false);
    var busy = stateBusy[0];
    var setBusy = stateBusy[1];

    function load() {
      setBusy(true);
      props
        .runRead(TOOL.reviewPending, props.withWorkspace({}))
        .then(function (result) {
          setPending(result);
        })
        .finally(function () {
          setBusy(false);
        });
    }

    hooks.useEffect(function () {
      load();
    }, [props.workspaceId]);

    var payload = (pending && pending.result) || null;
    var items = payload ? payload.items || payload.pending || payload.proposals || [] : [];
    var list = Array.isArray(items)
      ? items
      : Object.keys(items || {}).map(function (key) {
          return Object.assign({ id: key }, items[key]);
        });

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-review-queue" },
      h(
        "div",
        { className: "reqlo-card-head" },
        h("h3", null, "Review queue"),
        h(
          "button",
          { type: "button", onClick: load, disabled: busy, "data-testid": "reqlo-review-reload" },
          busy ? "Loading…" : "Reload"
        )
      ),
      h(
        "p",
        { className: "reqlo-hint" },
        "Proposals waiting for a human decision. Approving needs the human key of this server — an agent may not decide its own proposal."
      ),
      list.length === 0
        ? h("p", { className: "reqlo-empty", "data-testid": "reqlo-review-empty" }, "Nothing waiting for review.")
        : h(
            "table",
            { className: "reqlo-table", "data-testid": "reqlo-review-table" },
            h("thead", null, h("tr", null, h("th", null, "Id"), h("th", null, "Artifact"), h("th", null, "State"), h("th", null, "Actions"))),
            h(
              "tbody",
              null,
              list.slice(0, 50).map(function (item, index) {
                var id = item.id || item.artifact_id || item.pk || String(index);
                return h(
                  "tr",
                  { key: String(id) },
                  h("td", { className: "reqlo-mono" }, shortId(id)),
                  h("td", null, displayValue(item.artifact_type || item.type || item.title)),
                  h("td", null, displayValue(item.status || item.state || item.workflow_state)),
                  h(
                    "td",
                    null,
                    h(
                      "button",
                      {
                        type: "button",
                        "data-testid": "reqlo-review-approve",
                        onClick: function () {
                          props.onRun(findTool(props.catalogue, TOOL.reviewApprove), { id: id }, true);
                        }
                      },
                      "Approve"
                    ),
                    h(
                      "button",
                      {
                        type: "button",
                        "data-testid": "reqlo-review-reject",
                        onClick: function () {
                          props.onRun(findTool(props.catalogue, TOOL.reviewReject), { id: id }, true);
                        }
                      },
                      "Reject"
                    ),
                    h(
                      "button",
                      {
                        type: "button",
                        "data-testid": "reqlo-review-changes",
                        onClick: function () {
                          props.onRun(findTool(props.catalogue, TOOL.reviewRequestChanges), { id: id }, true);
                        }
                      },
                      "Changes"
                    )
                  )
                );
              })
            )
          ),
      payload && payload.error ? h("p", { className: "reqlo-error" }, payload.error) : null
    );
  }

  function MemoryPanel(props) {
    var stateValues = hooks.useState({ content: "", scope: "workspace" });
    var values = stateValues[0];
    var setValues = stateValues[1];
    var entry = findTool(props.catalogue, TOOL.memoryWrite);

    // Two-step, like the shipped memory skill: a draft is staged here and only
    // an explicit confirm issues memory.write. Nothing auto-submits.
    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-memory" },
      h("h3", null, "Memory"),
      h("p", { className: "reqlo-hint" }, "Stage a fact, then confirm it — memory.write is the only memory tool that mutates state."),
      h(
        "label",
        { className: "reqlo-field" },
        h("span", { className: "reqlo-field-label" }, "Fact"),
        h("textarea", {
          rows: 3,
          className: "reqlo-input",
          value: values.content,
          "data-testid": "reqlo-memory-content",
          onChange: function (event) {
            setValues(Object.assign({}, values, { content: event.target.value }));
          }
        })
      ),
      h(
        "label",
        { className: "reqlo-field" },
        h("span", { className: "reqlo-field-label" }, "Scope"),
        h(
          "select",
          {
            className: "reqlo-input",
            value: values.scope,
            "data-testid": "reqlo-memory-scope",
            onChange: function (event) {
              setValues(Object.assign({}, values, { scope: event.target.value }));
            }
          },
          ["workspace", "user", "artifact"].map(function (scope) {
            return h("option", { key: scope, value: scope }, scope);
          })
        )
      ),
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !values.content,
            "data-testid": "reqlo-memory-stage",
            onClick: function () {
              props.onRun(entry, { scope: values.scope, content: values.content, workspace_id: props.workspaceId });
            }
          },
          "Stage & confirm…"
        ),
        h(
          "button",
          {
            type: "button",
            disabled: props.busy,
            "data-testid": "reqlo-memory-overview",
            onClick: function () {
              props.runRead(TOOL.memoryOverview, props.withWorkspace({}));
            }
          },
          "Show overview"
        )
      )
    );
  }

  function InterviewPanel(props) {
    var stateSession = hooks.useState("");
    var session = stateSession[0];
    var setSession = stateSession[1];
    var stateMessage = hooks.useState("");
    var message = stateMessage[0];
    var setMessage = stateMessage[1];

    var options = props.interviews || [];
    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-interview-panel" },
      h("h3", null, "Interviews"),
      options.length
        ? h(
            "select",
            {
              className: "reqlo-input",
              value: session,
              "data-testid": "reqlo-interview-session",
              onChange: function (event) {
                setSession(event.target.value);
              }
            },
            h("option", { value: "" }, "Pick an open interview"),
            options.map(function (item) {
              var id = item.id || item.session_id;
              return h("option", { key: id, value: id }, shortId(id) + " · " + (item.artifact_type || item.session_kind || "?") + " · " + (item.phase || "?"));
            })
          )
        : h("p", { className: "reqlo-empty" }, "No open interview in this workspace."),
      h("input", {
        type: "text",
        className: "reqlo-input",
        placeholder: "Chat message / answer value…",
        value: message,
        "data-testid": "reqlo-interview-message",
        onChange: function (event) {
          setMessage(event.target.value);
        }
      }),
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !session || !message,
            "data-testid": "reqlo-interview-chat",
            onClick: function () {
              props.onRun(findTool(props.catalogue, TOOL.interviewChat), { session_id: session, message: message });
            }
          },
          "Send chat turn…"
        ),
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !session,
            "data-testid": "reqlo-interview-formalize",
            onClick: function () {
              props.onRun(findTool(props.catalogue, TOOL.interviewFormalize), { session_id: session });
            }
          },
          "Formalize…"
        ),
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !session,
            "data-testid": "reqlo-interview-abandon",
            onClick: function () {
              props.onRun(findTool(props.catalogue, TOOL.interviewAbandon), { session_id: session });
            }
          },
          "Abandon…"
        )
      )
    );
  }

  function BaselinePanel(props) {
    var entry = findTool(props.catalogue, TOOL.baselineCreate);
    var stateValues = hooks.useState(null);
    var values = stateValues[0];
    var setValues = stateValues[1];
    hooks.useEffect(
      function () {
        setValues(initialValues(entry && entry.input_schema));
      },
      [props.catalogue]
    );
    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-baseline" },
      h("h3", null, "Baseline"),
      entry
        ? h(SchemaForm, { schema: entry.input_schema, values: values || {}, onChange: setValues, disabled: props.busy })
        : h("p", { className: "reqlo-hint" }, "baseline.create is not on this server."),
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !entry,
            "data-testid": "reqlo-baseline-create",
            onClick: function () {
              props.onRun(entry, props.withWorkspace(values || {}));
            }
          },
          "Preview & snapshot…"
        )
      )
    );
  }

  // ------------------------------------------------------------------------
  // servers
  // ------------------------------------------------------------------------

  function ServersPanel(props) {
    var registry = props.registry || { servers: [] };
    var stateForm = hooks.useState({ id: "", name: "", base_url: "", api_key: "" });
    var form = stateForm[0];
    var setForm = stateForm[1];

    function setField(key, value) {
      var next = Object.assign({}, form);
      next[key] = value;
      setForm(next);
    }

    var rows = (registry.servers || []).map(function (server) {
      var verify = server.verify || {};
      var state = !verify.checked_at
        ? "not checked"
        : verify.reachable
        ? verify.auth_ok
          ? "ok"
          : "key failed"
        : "unreachable";
      var tone = state === "ok" ? "reqlo-dot-ok" : state === "not checked" ? "reqlo-dot-unknown" : "reqlo-dot-bad";
      return h(
        "tr",
        { key: server.id, "data-testid": "reqlo-server-row" },
        h("td", null, h("span", { className: "reqlo-dot " + tone }), server.active ? " *" : ""),
        h("td", { className: "reqlo-mono" }, server.id),
        h("td", null, server.name),
        h("td", { className: "reqlo-mono" }, server.base_url),
        h("td", null, server.has_api_key ? server.api_key_source + (server.api_key_env ? " (" + server.api_key_env + ")" : "") : "missing"),
        h("td", null, server.has_user_api_key ? server.user_api_key_source : "—"),
        h("td", null, state + (verify.tool_count ? " · " + verify.tool_count + " tools" : "") + (verify.app_version ? " · " + verify.app_version : "")),
        h(
          "td",
          null,
          h("button", { type: "button", "data-testid": "reqlo-server-use", onClick: function () { props.onUse(server.id); } }, "Use"),
          h("button", { type: "button", "data-testid": "reqlo-server-test", onClick: function () { props.onTest(server.id); } }, "Test"),
          h("button", { type: "button", "data-testid": "reqlo-server-delete", onClick: function () { props.onDelete(server.id); } }, "Remove")
        )
      );
    });

    return h(
      "div",
      null,
      h(
        "section",
        { className: "reqlo-card", "data-testid": "reqlo-servers" },
        h("h3", null, "Servers"),
        h(
          "p",
          { className: "reqlo-hint" },
          "Registry: " + (registry.path || "") + ". Keys never leave the backend — this table shows where a key comes from, not its value."
        ),
        rows.length
          ? h(
              "table",
              { className: "reqlo-table", "data-testid": "reqlo-server-table" },
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  h("th", null, ""),
                  h("th", null, "Id"),
                  h("th", null, "Name"),
                  h("th", null, "URL"),
                  h("th", null, "Agent key"),
                  h("th", null, "Human key"),
                  h("th", null, "Health"),
                  h("th", null, "Actions")
                )
              ),
              h("tbody", null, rows)
            )
          : h("p", { className: "reqlo-empty", "data-testid": "reqlo-servers-empty" }, "No server configured yet."),
        h(
          "label",
          { className: "reqlo-field reqlo-gate" },
          h("input", {
            type: "checkbox",
            checked: gateIsOpen(registry),
            "data-testid": "reqlo-write-gate",
            onChange: function (event) {
              props.onGate(event.target.checked);
            }
          }),
          h("span", null, "Write gate open (mutating calls allowed; reads always work)")
        )
      ),
      h(
        "section",
        { className: "reqlo-card", "data-testid": "reqlo-server-add" },
        h("h3", null, "Add a server"),
        h("p", { className: "reqlo-hint" }, "Keys are stored in the registry file (0600) — or point at an environment variable instead."),
        h(
          "div",
          { className: "reqlo-form reqlo-form-inline" },
          h("input", { type: "text", className: "reqlo-input", placeholder: "id (a-z0-9-)", value: form.id, "data-testid": "reqlo-server-id", onChange: function (event) { setField("id", event.target.value); } }),
          h("input", { type: "text", className: "reqlo-input", placeholder: "name", value: form.name, "data-testid": "reqlo-server-name", onChange: function (event) { setField("name", event.target.value); } }),
          h("input", { type: "text", className: "reqlo-input", placeholder: "http://host:8001", value: form.base_url, "data-testid": "reqlo-server-url", onChange: function (event) { setField("base_url", event.target.value); } }),
          h("input", { type: "password", className: "reqlo-input", placeholder: "agent key (optional)", value: form.api_key, "data-testid": "reqlo-server-key", onChange: function (event) { setField("api_key", event.target.value); } })
        ),
        h(
          "div",
          { className: "reqlo-dialog-actions" },
          h(
            "button",
            {
              type: "button",
              disabled: props.busy || !form.id || !form.base_url,
              "data-testid": "reqlo-server-add-button",
              onClick: function () {
                props.onAdd(form);
              }
            },
            "Add & test"
          )
        )
      )
    );
  }

  // ------------------------------------------------------------------------
  // admin (destructive tools, typed confirmation)
  // ------------------------------------------------------------------------

  function AdminPanel(props) {
    var catalogue = props.catalogue;
    var destructive = ((catalogue && catalogue.tools) || []).filter(function (tool) {
      return tool.destructive;
    });
    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-admin" },
      h("h3", null, "Administration"),
      h(
        "p",
        { className: "reqlo-hint" },
        "Every destructive tool of this server, in one place. Each of them requires the tool name typed into the confirmation and a fresh preview."
      ),
      destructive.length === 0
        ? h("p", { className: "reqlo-hint" }, "No destructive tool on this server.")
        : destructive.map(function (tool) {
            return h(
              "div",
              { key: tool.name, className: "reqlo-admin-row" },
              h("span", { className: "reqlo-mono" }, tool.name),
              h("span", { className: "reqlo-hint" }, tool.description),
              h(
                "button",
                {
                  type: "button",
                  "data-testid": "reqlo-admin-open",
                  onClick: function () {
                    props.onOpen(tool.name);
                  }
                },
                "Open in console"
              )
            );
          })
    );
  }

  // ------------------------------------------------------------------------
  // page
  // ------------------------------------------------------------------------

  function ReqogniLoomPage() {
    var stateView = hooks.useState("overview");
    var view = stateView[0];
    var setView = stateView[1];

    var stateRegistry = hooks.useState(null);
    var registry = stateRegistry[0];
    var setRegistry = stateRegistry[1];

    var stateWorkspaces = hooks.useState([]);
    var workspaces = stateWorkspaces[0];
    var setWorkspaces = stateWorkspaces[1];

    var stateWorkspaceId = hooks.useState("");
    var workspaceId = stateWorkspaceId[0];
    var setWorkspaceId = stateWorkspaceId[1];

    var stateStats = hooks.useState(null);
    var stats = stateStats[0];
    var setStats = stateStats[1];

    var stateInterviews = hooks.useState([]);
    var interviews = stateInterviews[0];
    var setInterviews = stateInterviews[1];

    var stateVersion = hooks.useState(null);
    var version = stateVersion[0];
    var setVersion = stateVersion[1];

    var stateCatalogue = hooks.useState(null);
    var catalogue = stateCatalogue[0];
    var setCatalogue = stateCatalogue[1];

    var statePreview = hooks.useState(null);
    var preview = statePreview[0];
    var setPreview = statePreview[1];

    var stateTyped = hooks.useState("");
    var typed = stateTyped[0];
    var setTyped = stateTyped[1];

    var stateResult = hooks.useState(null);
    var result = stateResult[0];
    var setResult = stateResult[1];

    var stateMessage = hooks.useState(null);
    var message = stateMessage[0];
    var setMessage = stateMessage[1];

    var stateBusy = hooks.useState(false);
    var busy = stateBusy[0];
    var setBusy = stateBusy[1];

    var pendingRun = hooks.useState(null);
    var pending = pendingRun[0];
    var setPending = pendingRun[1];

    var activeServer = "";
    (registry && registry.servers ? registry.servers : []).forEach(function (server) {
      if (server.active) activeServer = server.id;
    });

    function withWorkspace(argumentsObject) {
      var next = Object.assign({}, argumentsObject || {});
      if (workspaceId && next.workspace_id === undefined) next.workspace_id = workspaceId;
      if (workspaceId && next.workspace === undefined && next.workspace_id === undefined) next.workspace_id = workspaceId;
      return next;
    }

    function loadServers() {
      return apiGet("/servers").then(function (payload) {
        if (payload && payload.error) setMessage(payload.error);
        setRegistry(payload);
        return payload;
      });
    }

    function loadCatalogue(force) {
      return apiGet("/tools" + queryString({ refresh: force ? 1 : 0 })).then(function (payload) {
        if (payload && payload.error) setMessage(payload.error);
        setCatalogue(payload);
        return payload;
      });
    }

    function loadWorkspaceScope(selected) {
      var scoped = queryString({ workspace_id: selected });
      return Promise.all([apiGet("/stats" + scoped), apiGet("/interviews" + scoped)]).then(function (results) {
        var statsResult = results[0];
        var interviewsResult = results[1];
        var firstError = (statsResult && statsResult.error) || (interviewsResult && interviewsResult.error);
        if (firstError) setMessage(firstError);
        setStats(statsResult);
        setInterviews((interviewsResult && interviewsResult.interviews) || []);
        setWorkspaceId((statsResult && statsResult.workspace_id) || selected || "");
      });
    }

    function loadAll() {
      setBusy(true);
      setMessage(null);
      return loadServers()
        .then(function () {
          return apiGet("/version");
        })
        .then(function (versionResult) {
          setVersion(versionResult);
          return apiGet("/workspaces");
        })
        .then(function (workspaceResult) {
          var list = (workspaceResult && workspaceResult.workspaces) || [];
          setWorkspaces(list);
          var preferred = "";
          for (var index = 0; index < list.length; index += 1) {
            if (list[index] && list[index].id === workspaceId) preferred = workspaceId;
          }
          if (!preferred && list.length) preferred = list[0].id || "";
          return list.length ? loadWorkspaceScope(preferred) : null;
        })
        .then(function () {
          return loadCatalogue(false);
        })
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    hooks.useEffect(function () {
      loadAll();
    }, []);

    // ---- the write gate: preview, then (maybe) confirm, then execute ----

    function execute(tool, argumentsObject, token, typedValue) {
      setBusy(true);
      return apiPost("/write", {
        tool: tool,
        arguments: argumentsObject,
        confirm_token: token,
        typed: typedValue
      })
        .then(function (payload) {
          setResult(Object.assign({ tool: tool }, payload));
          if (payload && payload.error) setMessage(payload.error);
          return payload;
        })
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
          setPreview(null);
          setTyped("");
        });
    }

    function runTool(entry, argumentsObject, forceConfirm) {
      if (!entry) {
        setMessage("That tool is not on this server.");
        return Promise.resolve(null);
      }
      var tool = entry.name;
      setBusy(true);
      setMessage(null);
      return apiPost("/write/preview", { tool: tool, arguments: argumentsObject })
        .then(function (payload) {
          setBusy(false);
          if (!payload || payload.error) {
            setResult({ tool: tool, error: (payload && payload.error) || "preview failed" });
            setMessage((payload && payload.error) || "preview failed");
            return null;
          }
          var needsDialog = entry.class === "mutate" || forceConfirm;
          if (needsDialog) {
            setPreview(payload);
            setPendingRun({ arguments: argumentsObject });
            setTyped("");
            return payload;
          }
          // A read or a computation runs straight away — with the token the
          // backend just issued, so the gate stays in charge.
          return execute(tool, argumentsObject, payload.confirm_token, "");
        })
        .catch(function (err) {
          setBusy(false);
          setMessage(messageOf(err));
        });
    }

    function runRead(tool, argumentsObject) {
      var entry = findTool(catalogue, tool);
      if (!entry) {
        setMessage("Tool " + tool + " is not on this server.");
        return Promise.resolve(null);
      }
      return apiPost("/write/preview", { tool: tool, arguments: argumentsObject }).then(function (payload) {
        if (!payload || payload.error) {
          setMessage((payload && payload.error) || "preview failed");
          return null;
        }
        return apiPost("/write", {
          tool: tool,
          arguments: argumentsObject,
          confirm_token: payload.confirm_token
        });
      });
    }

    function confirmRun() {
      if (!preview || !pending) return;
      execute(preview.tool, pending.arguments, preview.confirm_token, typed);
      loadServers();
    }

    function onServerAdd(form) {
      setBusy(true);
      apiPost("/servers", {
        id: form.id,
        name: form.name,
        base_url: form.base_url,
        api_key: form.api_key || undefined
      })
        .then(function (payload) {
          if (payload && payload.error) setMessage(payload.error);
          return loadServers();
        })
        .then(loadCatalogue)
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerUse(id) {
      setBusy(true);
      apiPost("/active", { server_id: id })
        .then(function (payload) {
          if (payload && payload.error) setMessage(payload.error);
          return Promise.all([loadServers(), loadCatalogue(true)]);
        })
        .then(function () {
          return apiGet("/workspaces");
        })
        .then(function (workspaceResult) {
          setWorkspaces((workspaceResult && workspaceResult.workspaces) || []);
          setWorkspaceId("");
        })
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerTest(id) {
      setBusy(true);
      apiPost("/servers/" + encodeURIComponent(id) + "/test")
        .then(function (payload) {
          if (payload && payload.error) setMessage(payload.error);
          else if (payload && payload.verify && !payload.verify.reachable) setMessage("Probe failed: " + (payload.verify.error || "unreachable"));
          return loadServers();
        })
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerDelete(id) {
      setBusy(true);
      apiDelete("/servers/" + encodeURIComponent(id))
        .then(function (payload) {
          if (payload && payload.error) setMessage(payload.error);
          return Promise.all([loadServers(), loadCatalogue(true)]);
        })
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onGate(enabled) {
      apiPost("/write-gate", { enabled: enabled }).then(function (payload) {
        if (payload && payload.error) setMessage(payload.error);
        return loadServers();
      });
    }

    function onSelectWorkspace(event) {
      var selected = event.target.value;
      setBusy(true);
      setMessage(null);
      loadWorkspaceScope(selected)
        .catch(function (err) {
          setMessage(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    var serverOptions = (registry && registry.servers) || [];
    var bar = h(
      "div",
      { className: "reqlo-bar" },
      h(
        "label",
        { className: "reqlo-inline" },
        "Server",
        h(
          "select",
          {
            className: "reqlo-input",
            value: activeServer,
            disabled: busy || !serverOptions.length,
            "data-testid": "reqlo-server-select",
            onChange: function (event) {
              onServerUse(event.target.value);
            }
          },
          serverOptions.length
            ? serverOptions.map(function (server) {
                return h("option", { key: server.id, value: server.id }, server.name + " (" + server.id + ")");
              })
            : h("option", { value: "" }, "none configured")
        )
      ),
      h(
        "label",
        { className: "reqlo-inline" },
        "Workspace",
        h(
          "select",
          {
            className: "reqlo-input",
            value: workspaceId,
            disabled: busy || !workspaces.length,
            "data-testid": "reqlo-workspace-select",
            onChange: onSelectWorkspace
          },
          workspaces.length
            ? workspaces.map(function (workspace) {
                return h("option", { key: workspace.id, value: workspace.id }, workspace.name || workspace.id);
              })
            : h("option", { value: "" }, "none visible")
        )
      ),
      h(
        "span",
        { className: "reqlo-inline" },
        h(
          "span",
          { className: "reqlo-dot " + (gateIsOpen(registry) ? "reqlo-dot-ok" : "reqlo-dot-bad") }
        ),
        gateIsOpen(registry) ? "writes open" : "writes locked"
      ),
      h(
        "button",
        { type: "button", onClick: loadAll, disabled: busy, "data-testid": "reqlo-refresh-button" },
        busy ? "Loading…" : "Refresh"
      )
    );

    var nav = h(
      "div",
      { className: "reqlo-nav", role: "tablist" },
      VIEWS.map(function (item) {
        return h(
          "button",
          {
            key: item.id,
            type: "button",
            role: "tab",
            "aria-selected": view === item.id,
            className: view === item.id ? "reqlo-nav-active" : "",
            "data-testid": "reqlo-nav-" + item.id,
            onClick: function () {
              setView(item.id);
            }
          },
          item.label
        );
      })
    );

    var interviewRows = interviews.length
      ? h(
          "table",
          { className: "reqlo-table", "data-testid": "reqlo-interviews-table" },
          h(
            "thead",
            null,
            h("tr", null, h("th", null, "Session"), h("th", null, "Type"), h("th", null, "Phase"), h("th", null, "Status"), h("th", null, "Updated"))
          ),
          h(
            "tbody",
            null,
            interviews.map(function (session) {
              var id = session.id || session.session_id || "";
              return h(
                "tr",
                { key: id },
                h("td", { className: "reqlo-mono" }, shortId(id)),
                h("td", null, displayValue(session.artifact_type || session.session_kind)),
                h("td", null, displayValue(session.phase)),
                h("td", null, displayValue(session.status)),
                h("td", null, displayValue(session.updated_at || session.created_at))
              );
            })
          )
        )
      : h("p", { className: "reqlo-empty", "data-testid": "reqlo-interviews-empty" }, "No open interviews in this workspace.");

    var overview = h(
      "div",
      null,
      h(
        "div",
        { className: "reqlo-grid" },
        h(StatCard, { value: stats ? stats.requirements : null, label: "Requirements" }),
        h(StatCard, { value: stats ? stats.testcases : null, label: "Test Cases" }),
        h(StatCard, { value: stats ? stats.open_interviews : null, label: "Open Interviews" }),
        h(StatCard, { value: catalogue ? catalogue.tool_count : null, label: "Tools on server" })
      ),
      h("h3", { className: "reqlo-section" }, "Open interviews"),
      interviewRows
    );

    var writeView = h(
      "div",
      { className: "reqlo-views" },
      h(CreateFlow, {
        catalogue: catalogue,
        flows: CREATE_FLOWS,
        busy: busy,
        onRun: runTool,
        withWorkspace: withWorkspace
      }),
      h(LinkFlow, { catalogue: catalogue, busy: busy, onRun: runTool, runRead: runRead, withWorkspace: withWorkspace }),
      h(ReviewQueue, {
        catalogue: catalogue,
        workspaceId: workspaceId,
        busy: busy,
        onRun: runTool,
        runRead: runRead,
        withWorkspace: withWorkspace
      }),
      h(MemoryPanel, {
        catalogue: catalogue,
        workspaceId: workspaceId,
        busy: busy,
        onRun: runTool,
        runRead: runRead,
        withWorkspace: withWorkspace
      }),
      h(InterviewPanel, { catalogue: catalogue, interviews: interviews, busy: busy, onRun: runTool }),
      h(BaselinePanel, { catalogue: catalogue, busy: busy, onRun: runTool, withWorkspace: withWorkspace })
    );

    var toolsView = h(ToolConsole, {
      catalogue: catalogue,
      busy: busy,
      onRun: runTool,
      onRefresh: function () {
        setBusy(true);
        loadCatalogue(true).finally(function () {
          setBusy(false);
        });
      },
      onResetResult: function () {
        setResult(null);
      }
    });

    var serversView = h(ServersPanel, {
      registry: registry,
      busy: busy,
      onAdd: onServerAdd,
      onUse: onServerUse,
      onTest: onServerTest,
      onDelete: onServerDelete,
      onGate: onGate
    });

    var adminView = h(AdminPanel, {
      catalogue: catalogue,
      onOpen: function (toolName) {
        setView("tools");
        setResult(null);
        setMessage("Search for " + toolName + " in the console to run it.");
      }
    });

    var body =
      view === "write" ? writeView : view === "tools" ? toolsView : view === "servers" ? serversView : view === "admin" ? adminView : overview;

    return h(
      "div",
      { className: "reqlo-page" },
      h(
        "div",
        { className: "reqlo-header" },
        h("h2", null, "ReqogniLoom"),
        version && version.app_version
          ? h("span", { className: "reqlo-hint" }, "server " + version.app_version + (version.commit_short ? " (" + version.commit_short + ")" : ""))
          : null
      ),
      bar,
      nav,
      message ? h("div", { className: "reqlo-error", role: "alert", "data-testid": "reqlo-message" }, message) : null,
      body,
      h(ConfirmPanel, {
        preview: preview,
        typed: typed,
        busy: busy,
        onTyped: setTyped,
        onConfirm: confirmRun,
        onCancel: function () {
          setPreview(null);
          setTyped("");
        }
      }),
      h(ResultPanel, { result: result })
    );
  }

  window.__HERMES_PLUGINS__.register("reqogniloom", ReqogniLoomPage);
})();

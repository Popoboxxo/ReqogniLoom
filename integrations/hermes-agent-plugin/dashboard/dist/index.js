(function () {
  "use strict";
  // reqogniloom dashboard plugin — the ReqogniLoom tab, full surface.
  //
  // Views: Overview · Write · Tools · Servers · Admin, over three backend
  // capabilities (see dashboard/plugin_api.py):
  //
  //   * /servers …          — the multi-server registry the /reqogniloom command shares;
  //   * /tools …            — the live MCP catalogue of the selected server,
  //                           classified read / compute / mutate;
  //   * /write/preview+/write — the two-phase gate: the preview classifies and
  //                           issues a single-use token bound to
  //                           server+tool+arguments, the write consumes it.
  //
  // Rules that shape this file:
  //
  //   1. Nothing is hardcoded per tool. Forms come from each tool's JSON schema,
  //      so a tool the server adds later is usable without touching this plugin.
  //   2. Only *declared* parameters are ever sent. The backend accepts a few
  //      undeclared ones (finding #1376) and this UI must not be the place that
  //      starts sending them — including the convenience workspace injection.
  //   3. The confirmation step cannot be skipped from here: reads run straight
  //      through (still with a token), mutating calls open the confirm panel,
  //      destructive ones additionally need the tool name typed — and the backend
  //      refuses a token that is stale, spent or bound to other arguments.
  //   4. Every control is reachable by keyboard and carries a data-testid.
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
  var PLUGIN_VERSION = "1.0.0";

  // Tool names used by the curated shortcuts. Every one of them is asserted
  // against the repo's tool manifest in tests/plugin_ui_smoke.mjs — a rename
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
    memoryWrite: "memory.write",
    memoryOverview: "memory.overview",
    baselineCreate: "baseline.create",
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

  // The selected workspace, for the convenience injection below. A module-level
  // cell rather than a prop on every call site: every component reads the same
  // value, and only the page writes it.
  var selectedWorkspaceId = "";

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
      var value = params[key];
      // Deliberately not a truthiness test: 0 and "" are legitimate values.
      if (value === undefined || value === null) return;
      parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
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
            var detail = parsed && (parsed.detail || parsed.error);
            throw httpError(response.status, typeof detail === "string" ? detail : "");
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
    var tone =
      toolClass === "mutate"
        ? "reqlo-badge-mutate"
        : toolClass === "compute"
        ? "reqlo-badge-compute"
        : "reqlo-badge-read";
    return h("span", { className: "reqlo-badge " + tone }, toolClass);
  }

  function gateIsOpen(registry) {
    return !registry || registry.write_gate !== false;
  }

  function findTool(catalogue, name) {
    if (!catalogue || !catalogue.tools) return null;
    for (var index = 0; index < catalogue.tools.length; index += 1) {
      if (catalogue.tools[index].name === name) return catalogue.tools[index];
    }
    return null;
  }

  function problemsOf(preview) {
    return (preview && preview.problems) || [];
  }

  function declaredProperties(entry) {
    var schema = (entry && entry.input_schema) || {};
    return schema.properties || {};
  }

  // Injects the selected workspace — but only when the tool declares that
  // parameter. Sending it to a tool whose schema has no such field is the
  // undeclared-parameter pattern (finding #1376) this plugin refuses, and the
  // backend rejects it anyway (which made the link flow unusable).
  function withWorkspace(entry, argumentsObject) {
    var next = Object.assign({}, argumentsObject || {});
    if (!selectedWorkspaceId) return next;
    if (Object.prototype.hasOwnProperty.call(declaredProperties(entry), "workspace_id")) {
      next.workspace_id = selectedWorkspaceId;
    }
    return next;
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

  // ------------------------------------------------------------------------
  // schema-driven form
  // ------------------------------------------------------------------------

  function initialValues(schema) {
    var values = {};
    var properties = (schema && schema.properties) || {};
    Object.keys(properties).forEach(function (name) {
      var spec = properties[name] || {};
      if (spec.default !== undefined) values[name] = spec.default;
      // An enum deliberately starts empty: pre-selecting enum[0] would record a
      // choice the author never made (requirement.create's verification_method
      // would silently become "Test").
      else if (spec.enum && spec.enum.length) values[name] = "";
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

  // Renders exactly the properties the tool declares (see rule 2 above).
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
      var fieldId = "reqlo-field-" + props.scope + "-" + name;
      var onChange = function (raw) {
        var next = {};
        Object.keys(props.values).forEach(function (key) {
          next[key] = props.values[key];
        });
        next[name] = coerceField(spec, raw);
        props.onChange(next);
      };
      var common = {
        id: fieldId,
        "data-testid": "reqlo-field-" + name,
        "aria-required": isRequired ? "true" : undefined,
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
          h("option", { key: "__empty", value: "" }, "— choose —"),
          spec.enum.map(function (option) {
            return h("option", { key: String(option), value: option }, String(option));
          })
        );
      } else if (spec.type === "boolean") {
        control = h("input", {
          id: fieldId,
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
      } else {
        control = h("input", Object.assign({}, common, { type: "text", className: "reqlo-input" }));
      }
      return h(
        "div",
        { key: name, className: "reqlo-field" },
        h(
          "label",
          { className: "reqlo-field-label", htmlFor: fieldId },
          name,
          isRequired ? h("span", { className: "reqlo-required" }, " (required)") : null
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
    var blocked = preview.blocked || problemsOf(preview).length > 0;
    var needsHuman = preview.requires_human && preview.human_key_available === false;
    var disabled = props.busy || !typedOk || blocked || needsHuman;
    return h(
      "div",
      {
        className: "reqlo-dialog",
        role: "dialog",
        "aria-labelledby": "reqlo-confirm-title",
        "aria-describedby": "reqlo-confirm-summary",
        "data-testid": "reqlo-confirm",
        onKeyDown: function (event) {
          if (event.key === "Escape") {
            event.stopPropagation();
            props.onCancel();
          }
        }
      },
      h(
        "h4",
        { id: "reqlo-confirm-title" },
        isDestructive ? "Confirm destructive call" : "Confirm call"
      ),
      h(
        "p",
        { className: "reqlo-hint", id: "reqlo-confirm-summary" },
        preview.server + " · " + preview.tool + (preview.summary ? " · " + preview.summary : "")
      ),
      preview.class === "mutate"
        ? h(
            "p",
            { className: "reqlo-hint" },
            "Result: a proposal (workflow state 'proposed') — a human still has to approve it."
          )
        : null,
      preview.requires_human
        ? h(
            "p",
            { className: preview.human_key_available ? "reqlo-hint" : "reqlo-error" },
            preview.human_key_available
              ? "Runs with the human principal (this decides a proposal)."
              : "Needs the human API key of this server — set it under Servers → Keys."
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
            "div",
            { className: "reqlo-field" },
            h(
              "label",
              { className: "reqlo-field-label", htmlFor: "reqlo-typed" },
              "Type " + preview.tool + " to confirm (required)"
            ),
            h("input", {
              id: "reqlo-typed",
              type: "text",
              className: "reqlo-input",
              value: props.typed || "",
              "data-testid": "reqlo-typed-confirmation",
              disabled: props.busy,
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
            ref: props.confirmRef,
            onClick: props.onConfirm,
            disabled: disabled,
            "aria-disabled": disabled ? "true" : undefined,
            "data-testid": "reqlo-confirm-button"
          },
          props.busy ? "Running…" : isDestructive ? "Run destructive call" : "Create proposal"
        ),
        h(
          "button",
          {
            type: "button",
            onClick: props.onCancel,
            disabled: props.busy,
            "data-testid": "reqlo-cancel-button"
          },
          "Cancel"
        )
      )
    );
  }

  function ResultPanel(props) {
    if (!props.result) return null;
    var result = props.result;
    var failed = Boolean(result.error);
    var body = failed
      ? h("div", { className: "reqlo-error", "data-testid": "reqlo-result-error" }, result.error)
      : h(
          "pre",
          { className: "reqlo-result reqlo-mono", "data-testid": "reqlo-result" },
          JSON.stringify(result.ok === undefined ? result : result.result, null, 2)
        );
    return h(
      "div",
      { className: "reqlo-result-panel" },
      // Announced on purpose: the JSON outcome is the proof a call landed, and a
      // screen reader must hear it without hunting for it.
      h(
        "div",
        { className: "reqlo-result-head", role: "status", "aria-live": "polite" },
        h("strong", null, result.tool || "result"),
        failed ? " — failed" : " — ok",
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
    var [query, setQuery] = hooks.useState("");
    var [group, setGroup] = hooks.useState("");
    var [selected, setSelected] = hooks.useState(props.initialTool || "");
    var [values, setValues] = hooks.useState({});

    hooks.useEffect(
      function () {
        if (!props.initialTool) return;
        var tool = findTool(props.catalogue, props.initialTool);
        setSelected(props.initialTool);
        setValues(initialValues(tool && tool.input_schema));
      },
      [props.initialTool, props.catalogue]
    );

    var catalogue = props.catalogue;
    var tools = (catalogue && catalogue.tools) || [];
    var filtered = tools.filter(function (tool) {
      if (group && tool.group !== group) return false;
      if (!query) return true;
      var needle = query.toLowerCase();
      return (
        tool.name.toLowerCase().indexOf(needle) !== -1 ||
        (tool.description || "").toLowerCase().indexOf(needle) !== -1
      );
    });
    var entry = selected ? findTool(catalogue, selected) : null;

    function pick(name) {
      var tool = findTool(catalogue, name);
      setSelected(name);
      setValues(initialValues(tool && tool.input_schema));
      props.onResetResult();
    }

    var groups = (catalogue && catalogue.groups) || [];
    var rows = filtered.slice(0, 300).map(function (tool) {
      var isSelected = tool.name === selected;
      return h(
        "tr",
        {
          key: tool.name,
          className: isSelected ? "reqlo-row-selected" : "",
          "data-testid": "reqlo-tool-row"
        },
        h(
          "td",
          { className: "reqlo-mono" },
          // A real button in the first cell: a clickable <tr> is mouse-only.
          h(
            "button",
            {
              type: "button",
              className: "reqlo-tool-pick",
              "aria-pressed": isSelected ? "true" : "false",
              "data-testid": "reqlo-tool-pick-" + tool.name,
              onClick: function () {
                pick(tool.name);
              }
            },
            tool.name
          )
        ),
        h("td", null, classBadge(tool.class)),
        h(
          "td",
          null,
          tool.requires_human ? h("span", { className: "reqlo-badge reqlo-badge-human" }, "human key") : null
        ),
        h(
          "td",
          null,
          tool.destructive ? h("span", { className: "reqlo-badge reqlo-badge-destructive" }, "destructive") : null
        ),
        h("td", { className: "reqlo-desc" }, tool.description)
      );
    });

    var emptyState = null;
    if (!catalogue) {
      emptyState = h(
        "p",
        { className: "reqlo-empty", "data-testid": "reqlo-tool-empty-catalogue" },
        "No catalogue loaded — use “Refresh catalogue” (the server may be unreachable)."
      );
    } else if (!filtered.length) {
      emptyState = h(
        "p",
        { className: "reqlo-empty", "data-testid": "reqlo-tool-empty-filter" },
        "No tool matches this filter."
      );
    }

    return h(
      "div",
      { className: "reqlo-split", role: "tabpanel", "aria-label": "Tools" },
      h(
        "div",
        { className: "reqlo-split-left" },
        h(
          "div",
          { className: "reqlo-filters" },
          h("input", {
            type: "text",
            className: "reqlo-input",
            placeholder: "Search tools…",
            "aria-label": "Search tools",
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
              "aria-label": "Filter by tool group",
              value: group,
              "data-testid": "reqlo-tool-group",
              onChange: function (event) {
                setGroup(event.target.value);
              }
            },
            h("option", { value: "" }, "All groups" + (tools.length ? " (" + tools.length + ")" : "")),
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
        emptyState,
        h(
          "div",
          { className: "reqlo-table-wrap", tabIndex: 0, role: "region", "aria-label": "Tool catalogue" },
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
                h("th", null, "Principal"),
                h("th", null, "Risk"),
                h("th", null, "Description")
              )
            ),
            h("tbody", null, rows)
          )
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
              entry.class === "mutate"
                ? h(
                    "p",
                    { className: "reqlo-hint" },
                    entry.destructive
                      ? "Destructive: requires a fresh preview and the tool name typed; the result is a proposal."
                      : "Creates a proposal — a human approves it in the review queue."
                  )
                : null,
              h(SchemaForm, {
                schema: entry.input_schema,
                values: values,
                scope: "console",
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
                    onClick: function () {
                      props.onRun(entry, values);
                    },
                    disabled: props.busy,
                    "data-testid": "reqlo-tool-run"
                  },
                  props.busy ? "Running…" : entry.class === "mutate" ? "Preview & run…" : "Run"
                ),
                h(
                  "button",
                  {
                    type: "button",
                    onClick: props.onResetResult,
                    disabled: props.busy,
                    "data-testid": "reqlo-tool-clear"
                  },
                  "Clear result"
                )
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
    var [tool, setTool] = hooks.useState(props.flows[0].tool);
    var entry = findTool(props.catalogue, tool);
    var [values, setValues] = hooks.useState(initialValues(entry && entry.input_schema));

    hooks.useEffect(
      function () {
        // Depends on the catalogue too: mounting before /tools resolves must not
        // leave the form permanently empty.
        setValues(initialValues(entry && entry.input_schema));
      },
      [tool, props.catalogue]
    );

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-create-flow" },
      h("h3", null, "Create an artifact"),
      h(
        "div",
        { className: "reqlo-filters" },
        h("label", { className: "reqlo-inline", htmlFor: "reqlo-create-type" }, "Type"),
        h(
          "select",
          {
            id: "reqlo-create-type",
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
        ? h(SchemaForm, {
            schema: entry.input_schema,
            values: values || {},
            scope: "create",
            onChange: setValues,
            disabled: props.busy
          })
        : h("p", { className: "reqlo-hint" }, "Catalogue not loaded — refresh it in the Tools view."),
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
              props.onRun(entry, withWorkspace(entry, values || {}));
            }
          },
          "Preview & create…"
        )
      ),
      h(
        "p",
        { className: "reqlo-hint" },
        "The plugin writes with the agent key, so a created object is born as a proposal (workflow state 'proposed'). Confirm it in the review queue below or in ReqogniLoom."
      )
    );
  }

  function LinkFlow(props) {
    var entry = findTool(props.catalogue, TOOL.linkCreate);
    var [values, setValues] = hooks.useState(initialValues(entry && entry.input_schema));
    var [types, setTypes] = hooks.useState([]);

    hooks.useEffect(
      function () {
        if (!entry) return;
        setValues(initialValues(entry.input_schema));
        // Link types load once the catalogue is there (not on mount: the
        // catalogue arrives after the first render).
        props
          .runRead(TOOL.linkTypes, {})
          .then(function (result) {
            var payload = result && result.result;
            var list = (payload && (payload.link_types || payload.linkTypes || payload.items)) || [];
            setTypes(Array.isArray(list) ? list : []);
          })
          .catch(function () {
            setTypes([]);
          });
      },
      [props.catalogue]
    );

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-link-flow" },
      h("h3", null, "Link two artifacts"),
      types.length
        ? h(
            "p",
            { className: "reqlo-hint" },
            "Known link types: " +
              types
                .map(function (item) {
                  return item.key || item.name || item;
                })
                .join(", ")
          )
        : h("p", { className: "reqlo-hint" }, "Link types load with the catalogue."),
      entry
        ? h(SchemaForm, {
            schema: entry.input_schema,
            values: values || {},
            scope: "link",
            onChange: setValues,
            disabled: props.busy
          })
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
              // No workspace injection: create_link declares none.
              props.onRun(entry, values || {});
            }
          },
          "Preview & link…"
        )
      )
    );
  }

  function ReviewQueue(props) {
    var [pending, setPending] = hooks.useState(null);
    var [busy, setBusy] = hooks.useState(false);
    var [note, setNote] = hooks.useState(null);

    hooks.useEffect(
      function () {
        var alive = true;
        setBusy(true);
        var entry = findTool(props.catalogue, TOOL.reviewPending);
        props
          .runRead(TOOL.reviewPending, withWorkspace(entry, {}))
          .then(function (result) {
            if (alive) setPending(result || null);
          })
          .catch(function (err) {
            if (alive) setNote("Could not load the queue: " + messageOf(err));
          })
          .finally(function () {
            if (alive) setBusy(false);
          });
        return function () {
          alive = false;
        };
      },
      [props.workspaceId, props.refresh, props.catalogue]
    );

    var payload = (pending && pending.result) || null;
    var items = [];
    if (payload) {
      var raw = payload.items || payload.pending || payload.proposals || [];
      items = Array.isArray(raw)
        ? raw
        : Object.keys(raw || {}).map(function (key) {
            return Object.assign({ item_id: key }, raw[key]);
          });
    }

    function decide(toolName, item) {
      var entry = findTool(props.catalogue, toolName);
      var id = item.item_id || item.id || item.artifact_id;
      var args = { item_id: id };
      // review.* declares item_type as well; send it only if it is declared, and
      // only if the row actually carries one.
      if (Object.prototype.hasOwnProperty.call(declaredProperties(entry), "item_type")) {
        var type = item.item_type || item.artifact_type || item.type;
        if (type) args.item_type = type;
      }
      setNote(null);
      props.onRun(entry, withWorkspace(entry, args), true);
    }

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-review-queue" },
      h(
        "div",
        { className: "reqlo-card-head" },
        h("h3", null, "Review queue"),
        h(
          "button",
          {
            type: "button",
            onClick: props.onReload,
            disabled: busy,
            "data-testid": "reqlo-review-reload"
          },
          busy ? "Loading…" : "Reload"
        )
      ),
      h(
        "p",
        { className: "reqlo-hint" },
        "Proposals waiting for a human decision. Approving needs the human key of this server — an agent may not decide its own proposal."
      ),
      note ? h("p", { className: "reqlo-error", role: "status" }, note) : null,
      items.length === 0
        ? h(
            "p",
            { className: "reqlo-empty", "data-testid": "reqlo-review-empty" },
            busy ? "Loading…" : "Nothing waiting for review."
          )
        : h(
            "div",
            { className: "reqlo-table-wrap", tabIndex: 0, role: "region", "aria-label": "Review queue" },
            h(
              "table",
              { className: "reqlo-table", "data-testid": "reqlo-review-table" },
              h(
                "thead",
                null,
                h("tr", null, h("th", null, "Item"), h("th", null, "Type"), h("th", null, "State"), h("th", null, "Actions"))
              ),
              h(
                "tbody",
                null,
                items.slice(0, 50).map(function (item, index) {
                  var id = item.item_id || item.id || item.artifact_id || String(index);
                  return h(
                    "tr",
                    { key: String(id) },
                    h("td", { className: "reqlo-mono" }, shortId(id)),
                    h("td", null, displayValue(item.item_type || item.artifact_type || item.type)),
                    h("td", null, displayValue(item.current_state || item.status || item.state)),
                    h(
                      "td",
                      null,
                      h(
                        "button",
                        {
                          type: "button",
                          disabled: props.busy,
                          "data-testid": "reqlo-review-approve",
                          onClick: function () {
                            decide(TOOL.reviewApprove, item);
                          }
                        },
                        "Approve"
                      ),
                      h(
                        "button",
                        {
                          type: "button",
                          disabled: props.busy,
                          "data-testid": "reqlo-review-reject",
                          onClick: function () {
                            decide(TOOL.reviewReject, item);
                          }
                        },
                        "Reject"
                      ),
                      h(
                        "button",
                        {
                          type: "button",
                          disabled: props.busy,
                          "data-testid": "reqlo-review-changes",
                          onClick: function () {
                            decide(TOOL.reviewRequestChanges, item);
                          }
                        },
                        "Request changes"
                      )
                    )
                  );
                })
              )
            )
          ),
      payload && payload.error ? h("p", { className: "reqlo-error" }, payload.error) : null
    );
  }

  function MemoryPanel(props) {
    var entry = findTool(props.catalogue, TOOL.memoryWrite);
    var properties = declaredProperties(entry);
    var hasContent = Object.prototype.hasOwnProperty.call(properties, "content");
    var hasScope = Object.prototype.hasOwnProperty.call(properties, "scope");
    var [values, setValues] = hooks.useState({});

    hooks.useEffect(
      function () {
        var next = {};
        Object.keys(properties).forEach(function (name) {
          next[name] = name === "scope" ? "workspace" : "";
        });
        setValues(next);
      },
      [props.catalogue]
    );

    function setField(name, value) {
      var next = Object.assign({}, values);
      next[name] = value;
      setValues(next);
    }

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-memory" },
      h("h3", null, "Memory"),
      h(
        "p",
        { className: "reqlo-hint" },
        "Stage a fact, then confirm it — memory.write is the only memory tool that mutates state."
      ),
      hasContent
        ? h(
            "div",
            { className: "reqlo-field" },
            h("label", { className: "reqlo-field-label", htmlFor: "reqlo-memory-content" }, "Fact"),
            h("textarea", {
              id: "reqlo-memory-content",
              rows: 3,
              className: "reqlo-input",
              value: values.content || "",
              "data-testid": "reqlo-memory-content",
              onChange: function (event) {
                setField("content", event.target.value);
              }
            })
          )
        : null,
      hasScope
        ? h(
            "div",
            { className: "reqlo-field" },
            h("label", { className: "reqlo-field-label", htmlFor: "reqlo-memory-scope" }, "Scope"),
            h(
              "select",
              {
                id: "reqlo-memory-scope",
                className: "reqlo-input",
                value: values.scope || "workspace",
                "data-testid": "reqlo-memory-scope",
                onChange: function (event) {
                  setField("scope", event.target.value);
                }
              },
              ["workspace", "user", "artifact"].map(function (scope) {
                return h("option", { key: scope, value: scope }, scope);
              })
            )
          )
        : null,
      h(
        "div",
        { className: "reqlo-dialog-actions" },
        h(
          "button",
          {
            type: "button",
            disabled: props.busy || !entry || !values.content,
            "data-testid": "reqlo-memory-stage",
            onClick: function () {
              props.onRun(entry, withWorkspace(entry, Object.assign({}, values)));
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
              // memory.overview declares no parameters at all — and its output
              // has to reach the result panel, or the button does nothing visible.
              props.onRun(findTool(props.catalogue, TOOL.memoryOverview), {});
            }
          },
          "Show overview"
        )
      )
    );
  }

  function InterviewPanel(props) {
    var [session, setSession] = hooks.useState("");
    var [message, setMessage] = hooks.useState("");
    var options = props.interviews || [];
    var chatEntry = findTool(props.catalogue, TOOL.interviewChat);

    function args(extra) {
      var base = {};
      if (Object.prototype.hasOwnProperty.call(declaredProperties(chatEntry), "session_id")) {
        base.session_id = session;
      }
      return Object.assign(base, extra || {});
    }

    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-interview-panel" },
      h("h3", null, "Interviews"),
      options.length
        ? h(
            "div",
            { className: "reqlo-field" },
            h("label", { className: "reqlo-field-label", htmlFor: "reqlo-interview-session" }, "Open interview"),
            h(
              "select",
              {
                id: "reqlo-interview-session",
                className: "reqlo-input",
                value: session,
                "data-testid": "reqlo-interview-session",
                onChange: function (event) {
                  setSession(event.target.value);
                }
              },
              h("option", { value: "" }, "— pick one —"),
              options.map(function (item, index) {
                var id = item.id || item.session_id || String(index);
                return h(
                  "option",
                  { key: String(id), value: id },
                  shortId(id) +
                    " · " +
                    (item.artifact_type || item.session_kind || "?") +
                    " · " +
                    (item.phase || "?")
                );
              })
            )
          )
        : h("p", { className: "reqlo-empty" }, "No open interview in this workspace."),
      h(
        "div",
        { className: "reqlo-field" },
        h("label", { className: "reqlo-field-label", htmlFor: "reqlo-interview-message" }, "Chat message"),
        h("input", {
          id: "reqlo-interview-message",
          type: "text",
          className: "reqlo-input",
          placeholder: "e.g. the payment path must be retryable",
          value: message,
          "data-testid": "reqlo-interview-message",
          onChange: function (event) {
            setMessage(event.target.value);
          }
        })
      ),
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
              props.onRun(chatEntry, args({ message: message }));
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
              // Formalize without a confirmed proposal: the server uses the draft
              // it built, which may differ from what the operator reviewed. Said
              // plainly here rather than implied.
              props.onRun(findTool(props.catalogue, TOOL.interviewFormalize), args({}));
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
              props.onRun(findTool(props.catalogue, TOOL.interviewAbandon), args({}));
            }
          },
          "Abandon…"
        )
      )
    );
  }

  function BaselinePanel(props) {
    var entry = findTool(props.catalogue, TOOL.baselineCreate);
    var [values, setValues] = hooks.useState(initialValues(entry && entry.input_schema));

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
        ? h(SchemaForm, {
            schema: entry.input_schema,
            values: values || {},
            scope: "baseline",
            onChange: setValues,
            disabled: props.busy
          })
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
              props.onRun(entry, withWorkspace(entry, values || {}));
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
    var [form, setForm] = hooks.useState({ id: "", name: "", base_url: "", api_key: "", user_api_key: "" });
    var [edit, setEdit] = hooks.useState({ id: "", api_key: "", user_api_key: "" });

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
        h(
          "td",
          null,
          h("span", { className: "reqlo-dot " + tone, role: "img", "aria-label": state }),
          server.active ? " active" : ""
        ),
        h("td", { className: "reqlo-mono" }, server.id),
        h("td", null, server.name),
        h("td", { className: "reqlo-mono" }, server.base_url),
        h(
          "td",
          null,
          server.has_api_key
            ? server.api_key_source + (server.api_key_env ? " (" + server.api_key_env + ")" : "")
            : "missing"
        ),
        h("td", null, server.has_user_api_key ? server.user_api_key_source : "—"),
        h(
          "td",
          null,
          state +
            (verify.tool_count ? " · " + verify.tool_count + " tools" : "") +
            (verify.app_version ? " · " + verify.app_version : "") +
            (verify.error && !verify.auth_ok ? " · " + verify.error : "")
        ),
        h(
          "td",
          null,
          h(
            "button",
            { type: "button", disabled: props.busy, "data-testid": "reqlo-server-use", onClick: function () { props.onUse(server.id); } },
            "Use"
          ),
          h(
            "button",
            { type: "button", disabled: props.busy, "data-testid": "reqlo-server-test", onClick: function () { props.onTest(server.id); } },
            "Test"
          ),
          h(
            "button",
            {
              type: "button",
              disabled: props.busy,
              "data-testid": "reqlo-server-keys",
              onClick: function () {
                setEdit({ id: server.id, api_key: "", user_api_key: "" });
              }
            },
            "Keys…"
          ),
          h(
            "button",
            { type: "button", disabled: props.busy, "data-testid": "reqlo-server-delete", onClick: function () { props.onDelete(server.id); } },
            "Remove"
          )
        )
      );
    });

    return h(
      "div",
      { role: "tabpanel", "aria-label": "Servers" },
      h(
        "section",
        { className: "reqlo-card", "data-testid": "reqlo-servers" },
        h("h3", null, "Servers"),
        h(
          "p",
          { className: "reqlo-hint" },
          "Registry file: " +
            (registry.path || "?") +
            " (mode 0600). Keys never leave the backend — this table shows where a key comes from, not its value."
        ),
        rows.length
          ? h(
              "div",
              { className: "reqlo-table-wrap", tabIndex: 0, role: "region", "aria-label": "Configured servers" },
              h(
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
            )
          : h("p", { className: "reqlo-empty", "data-testid": "reqlo-servers-empty" }, "No server configured yet."),
        h(
          "div",
          { className: "reqlo-field reqlo-gate" },
          h("input", {
            id: "reqlo-write-gate",
            type: "checkbox",
            checked: gateIsOpen(registry),
            disabled: props.busy,
            "data-testid": "reqlo-write-gate",
            onChange: function (event) {
              props.onGate(event.target.checked);
            }
          }),
          h("label", { htmlFor: "reqlo-write-gate" }, "Write gate open (mutating calls allowed; reads always work)")
        )
      ),
      h(
        "section",
        { className: "reqlo-card", "data-testid": "reqlo-server-add" },
        h("h3", null, "Add a server"),
        h(
          "p",
          { className: "reqlo-hint" },
          "Keys are stored in the registry file (0600) — or leave them empty and set REQOGNILOOM_API_KEY_<ID> / REQOGNILOOM_USER_API_KEY_<ID> in ~/.hermes/.env instead."
        ),
        h(
          "div",
          { className: "reqlo-form reqlo-form-inline" },
          h("input", { type: "text", className: "reqlo-input", placeholder: "id (a-z0-9-)", "aria-label": "Server id", value: form.id, "data-testid": "reqlo-server-id", onChange: function (event) { setField("id", event.target.value); } }),
          h("input", { type: "text", className: "reqlo-input", placeholder: "display name", "aria-label": "Display name", value: form.name, "data-testid": "reqlo-server-name", onChange: function (event) { setField("name", event.target.value); } }),
          h("input", { type: "text", className: "reqlo-input", placeholder: "http://host:8001", "aria-label": "Base URL", value: form.base_url, "data-testid": "reqlo-server-url", onChange: function (event) { setField("base_url", event.target.value); } }),
          h("input", { type: "password", className: "reqlo-input", placeholder: "agent key (optional)", "aria-label": "Agent API key", value: form.api_key, "data-testid": "reqlo-server-key", onChange: function (event) { setField("api_key", event.target.value); } }),
          h("input", { type: "password", className: "reqlo-input", placeholder: "human key (optional)", "aria-label": "Human API key", value: form.user_api_key, "data-testid": "reqlo-server-user-key", onChange: function (event) { setField("user_api_key", event.target.value); } })
        ),
        h(
          "div",
          { className: "reqlo-dialog-actions" },
          h(
            "button",
            {
              type: "button",
              disabled: props.busy || !form.id || !form.base_url,
              "aria-describedby": "reqlo-server-add-hint",
              "data-testid": "reqlo-server-add-button",
              onClick: function () {
                props.onAdd(form);
              }
            },
            "Add & test"
          ),
          h("span", { className: "reqlo-hint", id: "reqlo-server-add-hint" }, "Id and base URL are required.")
        )
      ),
      edit.id
        ? h(
            "section",
            { className: "reqlo-card", "data-testid": "reqlo-server-edit" },
            h("h3", null, "Keys for " + edit.id),
            h(
              "p",
              { className: "reqlo-hint" },
              "Leave a field empty to keep the current value; enter “-” to clear it."
            ),
            h(
              "div",
              { className: "reqlo-form reqlo-form-inline" },
              h("input", { type: "password", className: "reqlo-input", "aria-label": "New agent key", placeholder: "new agent key", value: edit.api_key, "data-testid": "reqlo-server-edit-agent", onChange: function (event) { setEdit(Object.assign({}, edit, { api_key: event.target.value })); } }),
              h("input", { type: "password", className: "reqlo-input", "aria-label": "New human key", placeholder: "new human key", value: edit.user_api_key, "data-testid": "reqlo-server-edit-user", onChange: function (event) { setEdit(Object.assign({}, edit, { user_api_key: event.target.value })); } })
            ),
            h(
              "div",
              { className: "reqlo-dialog-actions" },
              h(
                "button",
                {
                  type: "button",
                  disabled: props.busy,
                  "data-testid": "reqlo-server-edit-save",
                  onClick: function () {
                    var patch = {};
                    if (edit.api_key) patch.api_key = edit.api_key === "-" ? "" : edit.api_key;
                    if (edit.user_api_key) patch.user_api_key = edit.user_api_key === "-" ? "" : edit.user_api_key;
                    props.onPatch(edit.id, patch);
                    setEdit({ id: "", api_key: "", user_api_key: "" });
                  }
                },
                "Save keys"
              ),
              h(
                "button",
                {
                  type: "button",
                  disabled: props.busy,
                  onClick: function () {
                    setEdit({ id: "", api_key: "", user_api_key: "" });
                  }
                },
                "Close"
              )
            )
          )
        : null
    );
  }

  // ------------------------------------------------------------------------
  // admin (destructive tools)
  // ------------------------------------------------------------------------

  function AdminPanel(props) {
    var catalogue = props.catalogue;
    var destructive = ((catalogue && catalogue.tools) || []).filter(function (tool) {
      return tool.destructive;
    });
    return h(
      "section",
      { className: "reqlo-card", "data-testid": "reqlo-admin", role: "tabpanel", "aria-label": "Admin" },
      h("h3", null, "Administration"),
      h(
        "p",
        { className: "reqlo-hint" },
        "Every destructive tool of this server. Each one requires a fresh preview and the tool name typed into the confirmation."
      ),
      destructive.length === 0
        ? h("p", { className: "reqlo-hint" }, "No destructive tool on this server.")
        : destructive.map(function (tool) {
            return h(
              "div",
              { key: tool.name, className: "reqlo-admin-row" },
              h("span", { className: "reqlo-mono" }, tool.name),
              h("span", { className: "reqlo-hint reqlo-clamp" }, tool.description),
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
    var [view, setView] = hooks.useState("overview");
    var [registry, setRegistry] = hooks.useState(null);
    var [workspaces, setWorkspaces] = hooks.useState([]);
    var [workspaceId, setWorkspaceId] = hooks.useState("");
    var [stats, setStats] = hooks.useState(null);
    var [interviews, setInterviews] = hooks.useState([]);
    var [version, setVersion] = hooks.useState(null);
    var [catalogue, setCatalogue] = hooks.useState(null);
    var [preview, setPreview] = hooks.useState(null);
    var [typed, setTyped] = hooks.useState("");
    var [result, setResult] = hooks.useState(null);
    var [message, setMessage] = hooks.useState(null);
    var [busy, setBusy] = hooks.useState(false);
    var [pendingRun, setPendingRun] = hooks.useState(null);
    var [consoleTool, setConsoleTool] = hooks.useState("");
    var [queueRefresh, setQueueRefresh] = hooks.useState(0);

    var confirmRef = hooks.useRef ? hooks.useRef(null) : { current: null };

    selectedWorkspaceId = workspaceId;

    var activeServer = "";
    (registry && registry.servers ? registry.servers : []).forEach(function (server) {
      if (server.active) activeServer = server.id;
    });

    function info(text) {
      setMessage(text ? { kind: "info", text: text } : null);
    }

    function failure(text) {
      setMessage(text ? { kind: "error", text: text } : null);
    }

    function loadServers() {
      return apiGet("/servers").then(function (payload) {
        if (payload && payload.error) failure(payload.error);
        setRegistry(payload);
        return payload;
      });
    }

    function loadCatalogue(force) {
      return apiGet("/tools" + queryString({ refresh: force ? 1 : 0 })).then(function (payload) {
        if (payload && payload.error) failure(payload.error);
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
        if (firstError) failure(firstError);
        setStats(statsResult);
        setInterviews((interviewsResult && interviewsResult.interviews) || []);
        var resolved = (statsResult && statsResult.workspace_id) || selected || "";
        setWorkspaceId(resolved);
        selectedWorkspaceId = resolved;
        if (resolved) {
          // Its own POST, not a GET side effect — convenience only, so a failure
          // never becomes a user-visible error.
          apiPost("/workspace-selected", { workspace_id: resolved }).catch(function () {
            /* ignore */
          });
        }
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
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    hooks.useEffect(function () {
      loadAll();
    }, []);

    // Move focus into the confirmation when it opens, so a keyboard user does not
    // have to traverse the whole page to reach it.
    hooks.useEffect(
      function () {
        if (!preview) return;
        if (confirmRef.current && confirmRef.current.focus) {
          confirmRef.current.focus();
        }
      },
      [preview]
    );

    // ---- the write gate: preview, then (maybe) confirm, then execute ----

    function execute(entry, argumentsObject, token, typedValue) {
      setBusy(true);
      return apiPost("/write", {
        tool: entry.name,
        arguments: argumentsObject,
        confirm_token: token,
        typed: typedValue
      })
        .then(function (payload) {
          setResult(Object.assign({ tool: entry.name }, payload));
          if (payload && payload.error) failure(payload.error);
          else info(null);
          if (entry.class === "mutate") {
            setQueueRefresh(function (value) {
              return value + 1;
            });
          }
          return payload;
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
          setPreview(null);
          setTyped("");
        });
    }

    function runTool(entry, argumentsObject, forceConfirm) {
      if (!entry) {
        failure("That tool is not on this server.");
        return Promise.resolve(null);
      }
      setBusy(true);
      setMessage(null);
      return apiPost("/write/preview", { tool: entry.name, arguments: argumentsObject })
        .then(function (payload) {
          setBusy(false);
          if (!payload || payload.error) {
            setResult({ tool: entry.name, error: (payload && payload.error) || "preview failed" });
            failure((payload && payload.error) || "preview failed");
            return null;
          }
          if (problemsOf(payload).length) {
            failure("The server rejects these arguments: " + problemsOf(payload).join("; "));
            return null;
          }
          if (entry.class === "mutate" || forceConfirm) {
            setPreview(payload);
            setPendingRun({ entry: entry, arguments: argumentsObject });
            setTyped("");
            return payload;
          }
          // A read or a computation runs straight through — with the token the
          // backend just issued, so the gate stays in charge.
          return execute(entry, argumentsObject, payload.confirm_token, "");
        })
        .catch(function (err) {
          setBusy(false);
          failure(messageOf(err));
        });
    }

    function runRead(toolName, argumentsObject) {
      var entry = findTool(catalogue, toolName);
      if (!entry) {
        failure("Tool " + toolName + " is not on this server.");
        return Promise.resolve(null);
      }
      return apiPost("/write/preview", { tool: toolName, arguments: argumentsObject })
        .then(function (payload) {
          if (!payload || payload.error) {
            failure((payload && payload.error) || "preview failed");
            return null;
          }
          if (problemsOf(payload).length) {
            failure(problemsOf(payload).join("; "));
            return null;
          }
          return apiPost("/write", {
            tool: toolName,
            arguments: argumentsObject,
            confirm_token: payload.confirm_token
          });
        })
        .catch(function (err) {
          failure(messageOf(err));
          return null;
        });
    }

    function confirmRun() {
      if (!preview || !pendingRun) return;
      execute(pendingRun.entry, pendingRun.arguments, preview.confirm_token, typed);
    }

    function onServerAdd(form) {
      setBusy(true);
      setMessage(null);
      apiPost("/servers", {
        id: form.id,
        name: form.name,
        base_url: form.base_url,
        api_key: form.api_key || undefined,
        user_api_key: form.user_api_key || undefined
      })
        .then(function (payload) {
          if (payload && payload.error) failure(payload.error);
          else if (payload && payload.verify && !payload.verify.reachable) {
            failure("Server added, but the probe failed: " + (payload.verify.error || "unreachable"));
          } else {
            info("Server added and probed.");
          }
          return Promise.all([loadServers(), loadCatalogue(true)]);
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerPatch(serverId, patch) {
      if (!Object.keys(patch).length) {
        info("Nothing to change.");
        return;
      }
      setBusy(true);
      apiPatch("/servers/" + encodeURIComponent(serverId), patch)
        .then(function (payload) {
          if (payload && payload.error) failure(payload.error);
          else info("Keys updated for " + serverId + ".");
          return loadServers();
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerUse(id) {
      setBusy(true);
      setMessage(null);
      setStats(null);
      setInterviews([]);
      setVersion(null);
      setWorkspaceId("");
      selectedWorkspaceId = "";
      apiPost("/active", { server_id: id })
        .then(function (payload) {
          if (payload && payload.error) failure(payload.error);
          return Promise.all([loadServers(), loadCatalogue(true), apiGet("/workspaces"), apiGet("/version")]);
        })
        .then(function (results) {
          var workspaceResult = results[2];
          var versionResult = results[3];
          var list = (workspaceResult && workspaceResult.workspaces) || [];
          setWorkspaces(list);
          setVersion(versionResult);
          // Reload the scope for the *new* server: otherwise the Overview keeps
          // showing the previous server's counters, and the workspace bar looks
          // selected while the state is empty (so writes would drop workspace_id).
          return list.length ? loadWorkspaceScope(list[0].id || "") : null;
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerTest(id) {
      setBusy(true);
      apiPost("/servers/" + encodeURIComponent(id) + "/test")
        .then(function (payload) {
          if (payload && payload.error) failure(payload.error);
          else if (payload && payload.verify && !payload.verify.reachable) {
            failure("Probe failed: " + (payload.verify.error || "unreachable"));
          } else if (payload && payload.verify && !payload.verify.auth_ok) {
            failure("Reachable, but the key failed: " + (payload.verify.error || "unknown reason"));
          } else {
            info("Server " + id + " is healthy.");
          }
          return loadServers();
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onServerDelete(id) {
      setBusy(true);
      apiDelete("/servers/" + encodeURIComponent(id))
        .then(function (payload) {
          if (payload && payload.error) failure(payload.error);
          return Promise.all([loadServers(), loadCatalogue(true)]);
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onGate(enabled) {
      setBusy(true);
      apiPost("/write-gate", { enabled: enabled })
        .then(function (payload) {
          if (payload && payload.error) failure(payload.error);
          else info(enabled ? "Write gate open." : "Write gate closed — mutating calls are blocked.");
          return loadServers();
        })
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onSelectWorkspace(event) {
      var selected = event.target.value;
      setBusy(true);
      setMessage(null);
      loadWorkspaceScope(selected)
        .catch(function (err) {
          failure(messageOf(err));
        })
        .finally(function () {
          setBusy(false);
        });
    }

    function onOpenInConsole(toolName) {
      setConsoleTool(toolName);
      setResult(null);
      info("Opened " + toolName + " in the console.");
      setView("tools");
    }

    var serverOptions = (registry && registry.servers) || [];
    var bar = h(
      "div",
      { className: "reqlo-bar" },
      h(
        "span",
        { className: "reqlo-inline" },
        h("label", { htmlFor: "reqlo-server-select" }, "Server"),
        h(
          "select",
          {
            id: "reqlo-server-select",
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
        "span",
        { className: "reqlo-inline" },
        h("label", { htmlFor: "reqlo-workspace-select" }, "Workspace"),
        h(
          "select",
          {
            id: "reqlo-workspace-select",
            className: "reqlo-input",
            value: workspaceId,
            disabled: busy || !workspaces.length,
            "data-testid": "reqlo-workspace-select",
            onChange: onSelectWorkspace
          },
          workspaces.length
            ? [h("option", { key: "__none", value: "" }, "— none —")].concat(
                workspaces.map(function (workspace) {
                  return h("option", { key: workspace.id, value: workspace.id }, workspace.name || workspace.id);
                })
              )
            : h("option", { value: "" }, "none visible")
        )
      ),
      h(
        "span",
        { className: "reqlo-inline" },
        h("span", {
          className: "reqlo-dot " + (gateIsOpen(registry) ? "reqlo-dot-ok" : "reqlo-dot-bad"),
          role: "img",
          "aria-label": gateIsOpen(registry) ? "writes open" : "writes locked"
        }),
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
      { className: "reqlo-nav", role: "tablist", "aria-label": "ReqogniLoom views" },
      VIEWS.map(function (item) {
        var isActive = view === item.id;
        return h(
          "button",
          {
            key: item.id,
            type: "button",
            role: "tab",
            "aria-selected": isActive ? "true" : "false",
            tabIndex: isActive ? 0 : -1,
            className: isActive ? "reqlo-nav-active" : "",
            "data-testid": "reqlo-nav-" + item.id,
            onClick: function () {
              setView(item.id);
            },
            onKeyDown: function (event) {
              if (["ArrowRight", "ArrowLeft", "Home", "End"].indexOf(event.key) === -1) return;
              event.preventDefault();
              var index = 0;
              VIEWS.forEach(function (candidate, position) {
                if (candidate.id === view) index = position;
              });
              var next =
                event.key === "Home"
                  ? 0
                  : event.key === "End"
                  ? VIEWS.length - 1
                  : (index + (event.key === "ArrowRight" ? 1 : -1) + VIEWS.length) % VIEWS.length;
              setView(VIEWS[next].id);
            }
          },
          item.label
        );
      })
    );

    var interviewRows = interviews.length
      ? h(
          "div",
          { className: "reqlo-table-wrap", tabIndex: 0, role: "region", "aria-label": "Open interviews" },
          h(
            "table",
            { className: "reqlo-table", "data-testid": "reqlo-interviews-table" },
            h(
              "thead",
              null,
              h(
                "tr",
                null,
                h("th", null, "Session"),
                h("th", null, "Type"),
                h("th", null, "Phase"),
                h("th", null, "Status"),
                h("th", null, "Updated")
              )
            ),
            h(
              "tbody",
              null,
              interviews.map(function (session, index) {
                var id = session.id || session.session_id || String(index);
                return h(
                  "tr",
                  { key: String(id) },
                  h("td", { className: "reqlo-mono" }, shortId(id)),
                  h("td", null, displayValue(session.artifact_type || session.session_kind)),
                  h("td", null, displayValue(session.phase)),
                  h("td", null, displayValue(session.status)),
                  h("td", null, displayValue(session.updated_at || session.created_at))
                );
              })
            )
          )
        )
      : h(
          "p",
          { className: "reqlo-empty", "data-testid": "reqlo-interviews-empty" },
          "No open interviews in this workspace."
        );

    var overview = h(
      "div",
      { role: "tabpanel", "aria-label": "Overview" },
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
      { className: "reqlo-views", role: "tabpanel", "aria-label": "Write" },
      h(CreateFlow, { catalogue: catalogue, flows: CREATE_FLOWS, busy: busy, onRun: runTool }),
      h(LinkFlow, { catalogue: catalogue, busy: busy, onRun: runTool, runRead: runRead }),
      h(ReviewQueue, {
        catalogue: catalogue,
        workspaceId: workspaceId,
        busy: busy,
        refresh: queueRefresh,
        onRun: runTool,
        runRead: runRead,
        onReload: function () {
          setQueueRefresh(function (value) {
            return value + 1;
          });
        }
      }),
      h(MemoryPanel, { catalogue: catalogue, busy: busy, onRun: runTool }),
      h(InterviewPanel, { catalogue: catalogue, interviews: interviews, busy: busy, onRun: runTool }),
      h(BaselinePanel, { catalogue: catalogue, busy: busy, onRun: runTool })
    );

    var toolsView = h(ToolConsole, {
      catalogue: catalogue,
      busy: busy,
      initialTool: consoleTool,
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
      onPatch: onServerPatch,
      onUse: onServerUse,
      onTest: onServerTest,
      onDelete: onServerDelete,
      onGate: onGate
    });

    var adminView = h(AdminPanel, { catalogue: catalogue, onOpen: onOpenInConsole });

    var body =
      view === "write"
        ? writeView
        : view === "tools"
        ? toolsView
        : view === "servers"
        ? serversView
        : view === "admin"
        ? adminView
        : overview;

    return h(
      "div",
      { className: "reqlo-page" },
      h(
        "div",
        { className: "reqlo-header" },
        h("h2", null, "ReqogniLoom"),
        h(
          "span",
          { className: "reqlo-hint" },
          "plugin " +
            PLUGIN_VERSION +
            (version && version.app_version ? " · server " + version.app_version : "") +
            (version && version.commit_short ? " (" + version.commit_short + ")" : "")
        )
      ),
      bar,
      nav,
      message
        ? h(
            "div",
            {
              className: message.kind === "error" ? "reqlo-error" : "reqlo-note",
              role: "alert",
              "data-testid": "reqlo-message"
            },
            message.text
          )
        : null,
      body,
      h(ConfirmPanel, {
        preview: preview,
        typed: typed,
        busy: busy,
        confirmRef: confirmRef,
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

#!/usr/bin/env node
/**
 * Component hotspot analysis by responsibility (#598 S2).
 *
 * Hotspot = change frequency × complexity (Tornhill, *Your Code as a Crime
 * Scene*). A file alone being long is not a reason to split it; what matters is
 * how many *independent* responsibilities it holds. Responsibility boundaries
 * follow the Single Responsibility Principle and Fowler's "Large Class" smell
 * (*Refactoring*), and the cohesive unit that should become its own module is
 * the custom hook (React docs, "Reusing Logic with Custom Hooks").
 *
 * The script therefore:
 *
 *   1. parses every component file with the TypeScript compiler API,
 *   2. collects the hook declarations of each top-level component
 *      (`useState` pairs, `useEffect`, `useCallback`, `useMemo`, `use*Query`),
 *   3. builds a cohesion graph: two declarations are connected when one uses an
 *      identifier the other declares (state name or its setter), and
 *   4. reports the connected components ("clusters") next to line count,
 *      cyclomatic complexity and git churn.
 *
 * Clusters are computed *per component function*: two components in the same
 * file may both declare `open`/`setOpen` without being connected.
 *
 * CLI: `node scripts/analyze-component-hotspots.mjs [src/components]` — emits a
 * complete Markdown report on stdout, so
 * `... > ../docs/analysis/2026-11-frontend-hotspots.md` is the whole pipeline.
 *
 * This file runs outside the `tsc` program (`tsconfig.json` only includes
 * `src`), which is why it is plain ESM JavaScript with JSDoc types.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import ts from "typescript";

/** Files below this many lines are not analysed at all (pre-filter only). */
const LINE_PREFILTER = 300;

/** Churn window used by the CLI. */
const CHURN_SINCE = "6 months ago";

/** Kinds in the order a cluster reports them. */
const KIND_ORDER = ["state", "effect", "callback", "memo", "query"];

/**
 * @typedef {"state" | "effect" | "callback" | "memo" | "query"} HookKind
 *
 * @typedef {object} Cluster
 * @property {string[]} names
 * @property {HookKind[]} kinds
 * @property {string[]} apiCalls
 *
 * @typedef {object} FileAnalysis
 * @property {string} path
 * @property {number} lines
 * @property {number} cyclomatic
 * @property {number} hooks
 * @property {Cluster[]} clusters
 */

// ---------------------------------------------------------------------------
// AST helpers
// ---------------------------------------------------------------------------

function isFunctionNode(node) {
  return (
    ts.isFunctionDeclaration(node) ||
    ts.isFunctionExpression(node) ||
    ts.isArrowFunction(node) ||
    ts.isMethodDeclaration(node) ||
    ts.isConstructorDeclaration(node) ||
    ts.isGetAccessorDeclaration(node) ||
    ts.isSetAccessorDeclaration(node)
  );
}

function walk(node, visit) {
  visit(node);
  node.forEachChild((child) => walk(child, visit));
}

function containsJsx(node) {
  let found = false;
  walk(node, (current) => {
    if (
      ts.isJsxElement(current) ||
      ts.isJsxSelfClosingElement(current) ||
      ts.isJsxFragment(current)
    ) {
      found = true;
    }
  });
  return found;
}

function calleeName(call) {
  return ts.isIdentifier(call.expression) ? call.expression.text : null;
}

/** @returns {HookKind | null} */
function hookKind(name) {
  if (!name || !name.startsWith("use")) return null;
  if (name === "useState") return "state";
  if (name === "useEffect") return "effect";
  if (name === "useCallback") return "callback";
  if (name === "useMemo") return "memo";
  if (name === "useQuery" || name === "useMutation" || /Query$/.test(name)) {
    return "query";
  }
  return null;
}

function bindingNames(name) {
  if (ts.isIdentifier(name)) return [name.text];
  if (ts.isArrayBindingPattern(name) || ts.isObjectBindingPattern(name)) {
    return name.elements.flatMap((element) =>
      ts.isBindingElement(element) ? bindingNames(element.name) : [],
    );
  }
  return [];
}

/** Identifiers the node *reads* (property names and binding names excluded). */
function usedIdentifiers(node, declaredNames) {
  const used = new Set();
  walk(node, (current) => {
    if (!ts.isIdentifier(current)) return;
    if (declaredNames.has(current.text)) return;
    const parent = current.parent;
    if (parent && ts.isPropertyAccessExpression(parent) && parent.name === current) {
      return;
    }
    if (parent && ts.isPropertyAssignment(parent) && parent.name === current) {
      return;
    }
    if (parent && ts.isParameter(parent) && parent.name === current) {
      return;
    }
    used.add(current.text);
  });
  return used;
}

function apiCallsIn(node) {
  const calls = new Set();
  walk(node, (current) => {
    if (!ts.isCallExpression(current)) return;
    const expression = current.expression;
    if (ts.isPropertyAccessExpression(expression)) {
      const receiver = expression.expression;
      if (ts.isIdentifier(receiver) && /(?:Api|api)$/.test(receiver.text)) {
        calls.add(`${receiver.text}.${expression.name.text}`);
      }
    } else if (ts.isIdentifier(expression) && /(?:Api|api)$/.test(expression.text)) {
      calls.add(expression.text);
    }
  });
  return calls;
}

// ---------------------------------------------------------------------------
// Per-component hook declarations
// ---------------------------------------------------------------------------

/**
 * Hook declarations of one component function. Nested functions are not
 * descended into: a hook called inside a callback is not a top-level
 * responsibility of the component.
 */
function collectUnits(component) {
  /** @type {{ names: Set<string>, kind: HookKind, node: any, apiCalls: Set<string> }[]} */
  const units = [];
  let anonymous = 0;

  const addUnit = (kind, binding, callExpression) => {
    const names = new Set(binding);
    if (names.size === 0) anonymous += 1;
    const fallback = `${kind}#${anonymous}`;
    units.push({
      names: names.size > 0 ? names : new Set([fallback]),
      kind,
      node: callExpression,
      apiCalls: apiCallsIn(callExpression),
    });
  };

  const visit = (node) => {
    if (isFunctionNode(node) && node !== component) return;

    if (ts.isVariableDeclaration(node)) {
      const init = node.initializer;
      if (init && ts.isCallExpression(init)) {
        const kind = hookKind(calleeName(init));
        if (kind) {
          addUnit(kind, bindingNames(node.name), init);
          return;
        }
      }
    }

    if (ts.isExpressionStatement(node) && ts.isCallExpression(node.expression)) {
      const kind = hookKind(calleeName(node.expression));
      if (kind) {
        addUnit(kind, [], node.expression);
        return;
      }
    }

    node.forEachChild(visit);
  };

  visit(component.body);
  return units;
}

/** Top-level components: function declarations / assigned function expressions returning JSX. */
function findComponents(sourceFile) {
  const components = [];
  for (const statement of sourceFile.statements) {
    if (
      ts.isFunctionDeclaration(statement) &&
      statement.body &&
      containsJsx(statement.body)
    ) {
      components.push(statement);
      continue;
    }
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        const init = declaration.initializer;
        if (
          init &&
          (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) &&
          containsJsx(init.body)
        ) {
          components.push(init);
        }
      }
    }
  }
  return components;
}

/**
 * Connected components of the declaration graph: two declarations are linked
 * when one reads a name the other declares.
 *
 * @returns {Cluster[]}
 */
function clustersOf(units) {
  const parent = units.map((_, index) => index);

  const find = (index) => {
    let root = index;
    while (parent[root] !== root) root = parent[root];
    while (parent[index] !== root) {
      const next = parent[index];
      parent[index] = root;
      index = next;
    }
    return root;
  };

  const union = (a, b) => {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent[rootB] = rootA;
  };

  const identifiers = units.map((unit) =>
    usedIdentifiers(unit.node, unit.names),
  );

  for (let i = 0; i < units.length; i += 1) {
    for (let j = i + 1; j < units.length; j += 1) {
      const linked =
        [...units[i].names].some((name) => identifiers[j].has(name)) ||
        [...units[j].names].some((name) => identifiers[i].has(name));
      if (linked) union(i, j);
    }
  }

  /** @type {Map<number, Cluster & { names: Set<string>, kinds: Set<HookKind>, apiCalls: Set<string> }>} */
  const groups = new Map();
  units.forEach((unit, index) => {
    const root = find(index);
    if (!groups.has(root)) {
      groups.set(root, {
        names: new Set(),
        kinds: new Set(),
        apiCalls: new Set(),
      });
    }
    const group = groups.get(root);
    for (const name of unit.names) group.names.add(name);
    group.kinds.add(unit.kind);
    for (const call of unit.apiCalls) group.apiCalls.add(call);
  });

  return [...groups.values()]
    .map((group) => ({
      names: [...group.names].sort(),
      kinds: KIND_ORDER.filter((kind) => group.kinds.has(kind)),
      apiCalls: [...group.apiCalls].sort(),
    }))
    .sort((a, b) => (a.names[0] ?? "").localeCompare(b.names[0] ?? ""));
}

/** Cyclomatic complexity per file: 1 + decision points. */
function cyclomaticComplexity(sourceFile) {
  let count = 1;
  walk(sourceFile, (node) => {
    if (
      ts.isIfStatement(node) ||
      ts.isConditionalExpression(node) ||
      ts.isForStatement(node) ||
      ts.isForInStatement(node) ||
      ts.isForOfStatement(node) ||
      ts.isWhileStatement(node) ||
      ts.isDoStatement(node) ||
      ts.isCaseClause(node) ||
      ts.isCatchClause(node)
    ) {
      count += 1;
      return;
    }
    if (ts.isBinaryExpression(node)) {
      const operator = node.operatorToken.kind;
      if (
        operator === ts.SyntaxKind.AmpersandAmpersandToken ||
        operator === ts.SyntaxKind.BarBarToken ||
        operator === ts.SyntaxKind.QuestionQuestionToken
      ) {
        count += 1;
      }
    }
  });
  return count;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Analyse one component file.
 *
 * @param {string} path
 * @returns {FileAnalysis}
 */
export function analyzeFile(path) {
  const source = readFileSync(path, "utf8");
  const sourceFile = ts.createSourceFile(
    path,
    source,
    ts.ScriptTarget.Latest,
    true,
    path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );

  const components = findComponents(sourceFile);
  const unitsByComponent = components.map((component) => collectUnits(component));
  const units = unitsByComponent.flat();

  const lines = source.split(/\r\n|\r|\n/).length;

  return {
    path,
    // Mirror `wc -l`: a trailing newline terminates the last line, it does not
    // open an extra empty one.
    lines: source.endsWith("\n") ? lines - 1 : lines,
    cyclomatic: cyclomaticComplexity(sourceFile),
    hooks: units.length,
    clusters: unitsByComponent.flatMap((componentUnits) =>
      clustersOf(componentUnits),
    ),
  };
}

/**
 * Number of commits touching `path` since `since` (default: last six months).
 * A path outside a git work tree yields 0 rather than aborting the report.
 *
 * @param {string} path
 * @param {string} [since]
 * @returns {number}
 */
export function churn(path, since = CHURN_SINCE) {
  try {
    const output = execFileSync(
      "git",
      ["log", `--since=${since}`, "--format=%H", "--", path],
      { cwd: process.cwd(), encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    );
    return output.split("\n").filter(Boolean).length;
  } catch {
    return 0;
  }
}

// ---------------------------------------------------------------------------
// CLI report
// ---------------------------------------------------------------------------

function collectTsx(root) {
  const files = [];
  const visit = (directory) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      if (entry.name === "node_modules" || entry.name === "fixtures") continue;
      const full = join(directory, entry.name);
      if (entry.isDirectory()) {
        visit(full);
        continue;
      }
      if (extname(entry.name) !== ".tsx") continue;
      if (/\.(test|spec)\.tsx$/.test(entry.name)) continue;
      files.push(full);
    }
  };
  visit(root);
  return files.sort();
}

function markdownTable(rows) {
  const header =
    "| Rank | File | Lines | Churn (commits, 6 mo) | Cyclomatic | Hotspot | Clusters | with own state |\n" +
    "|---:|---|---:|---:|---:|---:|---:|---:|";
  const body = rows.map((row, index) =>
    `| ${index + 1} | \`${row.path}\` | ${row.lines} | ${row.churn} | ${row.cyclomatic} | ${row.hotspot} | ${row.clusters.length} | ${row.stateClusters} |`,
  );
  return [header, ...body].join("\n");
}

function buildReport(root, analyses) {
  const rows = analyses
    .map((analysis) => {
      const churnCount = churn(analysis.path);
      return {
        ...analysis,
        churn: churnCount,
        hotspot: churnCount * analysis.cyclomatic,
        stateClusters: analysis.clusters.filter((cluster) =>
          cluster.kinds.includes("state"),
        ).length,
      };
    })
    .sort(
      (a, b) =>
        b.hotspot - a.hotspot ||
        b.cyclomatic - a.cyclomatic ||
        a.path.localeCompare(b.path),
    );

  const topQuartile = Math.max(1, Math.ceil(rows.length / 4));
  const toSplit = rows.filter(
    (row, index) => index < topQuartile && row.stateClusters >= 3,
  );

  const lines = [
    "# Frontend component hotspots — 2026-11",
    "",
    `Scope: \`${root}\` (production \`.tsx\`, tests and fixtures excluded).`,
    "Generated by `frontend/scripts/analyze-component-hotspots.mjs`.",
    "",
    "## Method",
    "",
    "Hotspot = change frequency × complexity (Adam Tornhill, *Your Code as a",
    'Crime Scene*). The responsibility cut follows the Single Responsibility',
    'Principle and the "Large Class" smell (Martin Fowler, *Refactoring*).',
    "Cohesion is the connection graph of a component's hook declarations: two",
    "declarations are connected when one uses an identifier the other declares",
    "(state value or setter). Connected components are the candidates for their",
    'own custom hook (React docs, "Reusing Logic with Custom Hooks").',
    "",
    "| Signal | Definition |",
    "|---|---|",
    `| Lines | Physical lines. Only a pre-filter: files ≤ ${LINE_PREFILTER} lines are not analysed. |`,
    "| Churn | `git log --since=\"6 months ago\"` commits touching the file. |",
    "| Cyclomatic | 1 + `if`, `?:`, `&&`, `\\|\\|`, `??`, loops, `case`, `catch`. |",
    "| Cluster | Connected component of hook declarations inside one component function. |",
    "| own state | Cluster that contains at least one `useState` pair. |",
    "",
    "Clusters are computed per component function: identical local names in two",
    "components of the same file do not connect.",
    "",
    "## Decision rule",
    "",
    "Split a file only when **both** hold:",
    "",
    "1. at least **three independent clusters with their own state**, and",
    "2. the file sits in the **top quartile of the hotspot rank**.",
    "",
    "Everything else stays as it is — even at 1500 lines. Long but cohesive",
    "files are not a defect.",
    "",
    "## Ranked overview",
    "",
    markdownTable(rows),
    "",
    "## Clusters per file",
    "",
  ];

  if (rows.length === 0) {
    lines.push("_No file above the line pre-filter._", "");
  }

  for (const row of rows) {
    lines.push(`### \`${row.path}\``, "");
    if (row.clusters.length === 0) {
      lines.push("_No hook declarations detected._", "");
      continue;
    }
    for (const [index, cluster] of row.clusters.entries()) {
      const names =
        cluster.names.length > 0
          ? cluster.names.map((name) => `\`${name}\``).join(", ")
          : "_anonymous_";
      const api =
        cluster.apiCalls.length > 0
          ? cluster.apiCalls.map((call) => `\`${call}\``).join(", ")
          : "—";
      lines.push(
        `${index + 1}. names: ${names} · kinds: ${cluster.kinds.join(", ")} · API: ${api}`,
      );
    }
    lines.push("");
  }

  lines.push("## Files to decompose", "");
  if (toSplit.length === 0) {
    lines.push(
      "_No file satisfies the decision rule: no top-quartile file carries three independent state-owning clusters._",
      "",
    );
  } else {
    for (const row of toSplit) {
      lines.push(
        `- \`${row.path}\` — ${row.stateClusters} independent clusters with own state, hotspot ${row.hotspot} (rank ${rows.indexOf(row) + 1}).`,
      );
    }
    lines.push("");
  }

  return `${lines.join("\n")}\n`;
}

function main() {
  const root = process.argv[2] ?? "src/components";
  const files = collectTsx(root);
  const analyses = files
    .map((file) => analyzeFile(file))
    .filter((analysis) => analysis.lines > LINE_PREFILTER);

  process.stdout.write(
    buildReport(relative(process.cwd(), resolve(root)) || root, analyses),
  );
}

const entry = process.argv[1] ? resolve(process.argv[1]) : "";
if (entry && fileURLToPath(import.meta.url) === entry) {
  main();
}

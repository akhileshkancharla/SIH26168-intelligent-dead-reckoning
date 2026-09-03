#!/usr/bin/env node
/** Synchronize the SIH26168 GitHub Project from repository-owned metadata. */

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const EXPECTED_ISSUES = 128;
const DEFAULT_OWNER = "akhileshkancharla";
const DEFAULT_PROJECT = "4";

const requestedViews = [
  { name: "Submission Critical", layout: "TABLE_LAYOUT", filter: 'label:"submission-critical"' },
  { name: "Roadmap", layout: "ROADMAP_LAYOUT", filter: '-label:"post-submission"' },
  { name: "Backlog", layout: "BOARD_LAYOUT", filter: 'label:"status:backlog"' },
  { name: "Ready", layout: "BOARD_LAYOUT", filter: 'label:"status:ready"' },
  { name: "In Progress", layout: "BOARD_LAYOUT", filter: 'label:"status:in-progress"' },
  { name: "In Review", layout: "BOARD_LAYOUT", filter: 'label:"status:in-review"' },
  { name: "Blocked", layout: "TABLE_LAYOUT", filter: 'label:"status:blocked"' },
  { name: "At Risk", layout: "TABLE_LAYOUT", filter: 'label:"status:at-risk"' },
  { name: "By Owner", layout: "TABLE_LAYOUT", filter: "" },
  { name: "By Milestone", layout: "TABLE_LAYOUT", filter: "" },
  { name: "Scientific Gates", layout: "TABLE_LAYOUT", filter: 'label:"scientific-review"' },
  { name: "Operations Queue", layout: "TABLE_LAYOUT", filter: 'label:"role:operations"' },
  { name: "Post-Submission", layout: "ROADMAP_LAYOUT", filter: 'label:"post-submission"' },
  { name: "Done", layout: "TABLE_LAYOUT", filter: 'label:"status:done"' },
];

const scientificGateByWp = {
  "WP-02": "S1",
  "WP-03": "S2",
  "WP-04": "S1",
  "WP-05": "S1",
  "WP-06": "S3",
  "WP-07": "S2",
  "WP-08": "S6B1",
  "WP-09": "S6A",
  "WP-10": "S0",
  "WP-11": "S0",
  "WP-12": "S4",
  "WP-13": "S2",
  "WP-14": "S3",
  "WP-15": "Demo contract",
  "WP-17": "All gates",
};

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function runGh(args, input) {
  const result = spawnSync("gh", args, {
    cwd: ROOT,
    encoding: "utf8",
    input,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (result.error) fail(result.error.message);
  if (result.status !== 0) fail((result.stderr || result.stdout).trim());
  const payload = JSON.parse(result.stdout);
  if (payload.errors) fail(JSON.stringify(payload.errors, null, 2));
  return payload;
}

function parseCsv(text) {
  const records = [];
  let record = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        value += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        value += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      record.push(value);
      value = "";
    } else if (char === "\n") {
      record.push(value.replace(/\r$/, ""));
      records.push(record);
      record = [];
      value = "";
    } else {
      value += char;
    }
  }
  if (value || record.length) {
    record.push(value.replace(/\r$/, ""));
    records.push(record);
  }
  const [header, ...rows] = records;
  return rows.filter((row) => row.some(Boolean)).map((row) =>
    Object.fromEntries(header.map((name, index) => [name, row[index] ?? ""])),
  );
}

function optionId(field, value) {
  const option = field.options.find(
    (candidate) => candidate.name.toLowerCase() === value.toLowerCase(),
  );
  if (!option) fail(`Field ${field.name} has no option ${value}`);
  return option.id;
}

function selectValue(field, value) {
  return { singleSelectOptionId: optionId(field, value) };
}

function statusFromLabels(labels) {
  if (labels.has("status:done") || labels.has("status:closure-approved")) return "Done";
  if (labels.has("status:in-progress") || labels.has("status:in-review")) {
    return "In Progress";
  }
  return "Todo";
}

function dependencyFromLabels(labels) {
  if (labels.has("status:blocked")) return "Blocked";
  if (labels.has("status:done") || labels.has("status:closure-approved")) {
    return "Satisfied";
  }
  if (labels.has("status:in-progress") || labels.has("status:in-review")) {
    return "In progress";
  }
  if (labels.has("status:ready")) return "Ready";
  return "Not assessed";
}

function graphqlValue(value) {
  const [key, raw] = Object.entries(value)[0];
  return `{${key}:${JSON.stringify(raw)}}`;
}

function applyUpdates(projectId, updates, batchSize) {
  for (let offset = 0; offset < updates.length; offset += batchSize) {
    const batch = updates.slice(offset, offset + batchSize);
    const mutations = batch.map((update, index) =>
      `u${index}:updateProjectV2ItemFieldValue(input:{projectId:${JSON.stringify(projectId)},` +
      `itemId:${JSON.stringify(update.itemId)},fieldId:${JSON.stringify(update.fieldId)},` +
      `value:${graphqlValue(update.value)}}){projectV2Item{id}}`,
    );
    runGh(
      ["api", "graphql", "--input", "-"],
      JSON.stringify({ query: `mutation{${mutations.join(" ")}}` }),
    );
    process.stdout.write(
      `Applied ${Math.min(offset + batch.length, updates.length)}/${updates.length} field values\n`,
    );
  }
}

function configureViews(projectId, visibleFieldIds) {
  const viewQuery =
    "query($id:ID!){node(id:$id){... on ProjectV2{" +
    "views(first:50){nodes{id name layout filter}}}}}";
  const existingPayload = runGh(
    ["api", "graphql", "--input", "-"],
    JSON.stringify({ query: viewQuery, variables: { id: projectId } }),
  );
  const existing = new Map(
    existingPayload.data.node.views.nodes.map((view) => [view.name, view]),
  );
  let defaultView = existing.get("View 1");

  for (const requested of requestedViews) {
    const configuration =
      requested.layout === "TABLE_LAYOUT" ? { visibleFieldIds } : undefined;
    let view = existing.get(requested.name);
    if (!view && defaultView) {
      view = defaultView;
      defaultView = null;
    }
    if (!view) {
      const createQuery =
        "mutation($input:CreateProjectV2ViewInput!){createProjectV2View(input:$input){" +
        "projectV2View{id name layout filter}}}";
      const created = runGh(
        ["api", "graphql", "--input", "-"],
        JSON.stringify({
          query: createQuery,
          variables: {
            input: {
              projectId,
              name: requested.name,
              layout: requested.layout,
              ...(configuration ? { configuration } : {}),
            },
          },
        }),
      );
      view = created.data.createProjectV2View.projectV2View;
    }
    const updateQuery =
      "mutation($input:UpdateProjectV2ViewInput!){updateProjectV2View(input:$input){" +
      "projectV2View{id name layout filter}}}";
    const updated = runGh(
      ["api", "graphql", "--input", "-"],
      JSON.stringify({
        query: updateQuery,
        variables: {
          input: {
            viewId: view.id,
            name: requested.name,
            layout: requested.layout,
            filter: requested.filter,
            ...(configuration ? { configuration } : {}),
          },
        },
      }),
    );
    const result = updated.data.updateProjectV2View.projectV2View;
    existing.set(result.name, result);
    process.stdout.write(`Configured view: ${result.name}\n`);
  }
}

function verifyValues(itemsByNumber, register, phases) {
  const keyFor = (fieldName) => fieldName[0].toLowerCase() + fieldName.slice(1);
  const coverage = Object.fromEntries(
    [
      "Status", "WP ID", "Parent WP", "Phase", "Submission critical", "Priority", "Area",
      "Owner role", "Due date", "Evidence required", "Scientific gate", "Dependency status", "Risk",
    ].map((name) => [name, 0]),
  );
  const mismatches = [];
  for (const [number, row] of register) {
    const item = itemsByNumber.get(number);
    const labels = new Set(item.labels ?? []);
    const parentWp = row["WP ID"].slice(0, 5);
    const dueDate = row["Due date"] || item.milestone?.dueOn?.slice(0, 10);
    const expected = {
      Status: statusFromLabels(labels),
      "WP ID": row["WP ID"],
      "Parent WP": row.Parent || undefined,
      Phase: phases.get(parentWp),
      "Submission critical": labels.has("submission-critical") ? "Yes" : "No",
      Priority: row.Priority[0].toUpperCase() + row.Priority.slice(1),
      Area: ["ml", "ci"].includes(row.Area)
        ? row.Area.toUpperCase()
        : row.Area[0].toUpperCase() + row.Area.slice(1),
      "Owner role": row["Owner role"],
      "Due date": dueDate,
      "Evidence required": labels.has("evidence-required") ? "Yes" : "No",
      "Scientific gate": scientificGateByWp[parentWp] ?? "Not applicable",
      "Dependency status": dependencyFromLabels(labels),
      Risk: row.Priority[0].toUpperCase() + row.Priority.slice(1),
    };
    for (const [fieldName, expectedValue] of Object.entries(expected)) {
      const actualValue = item[keyFor(fieldName)];
      if (actualValue !== undefined) coverage[fieldName] += 1;
      const valuesMatch =
        fieldName === "Phase" && typeof actualValue === "string"
          ? actualValue.toLowerCase() === expectedValue.toLowerCase()
          : actualValue === expectedValue;
      if (!valuesMatch) {
        mismatches.push({ number, fieldName, expectedValue, actualValue });
      }
    }
  }
  if (mismatches.length) {
    fail(`Project field verification failed: ${JSON.stringify(mismatches.slice(0, 20))}`);
  }
  process.stdout.write(`Verified field coverage: ${JSON.stringify(coverage)}\n`);
}

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const owner = option("--owner", DEFAULT_OWNER);
const projectNumber = option("--project", DEFAULT_PROJECT);
const batchSize = Number(option("--batch-size", "40"));
if (!Number.isSafeInteger(batchSize) || batchSize < 1 || batchSize > 100) {
  fail("--batch-size must be an integer from 1 through 100");
}
const shouldApply = args.includes("--apply");
const shouldConfigureViews = args.includes("--configure-views");
const shouldVerifyValues = args.includes("--verify-values");
const dueDatesOnly = args.includes("--due-dates-only");

const registerRows = parseCsv(
  readFileSync(join(ROOT, "docs", "bootstrap", "ISSUE_REGISTER.csv"), "utf8").replace(/^\uFEFF/, ""),
);
if (registerRows.length !== EXPECTED_ISSUES) {
  fail(`Issue register invariant failed: expected ${EXPECTED_ISSUES}, found ${registerRows.length}`);
}
const register = new Map(registerRows.map((row) => [Number(row["Issue number"]), row]));
const workPackages = JSON.parse(
  readFileSync(
    join(ROOT, "docs", "architecture", "machine_readable", "work_packages.json"),
    "utf8",
  ),
);
const phases = new Map(workPackages.work_packages.map((row) => [row.id, row.phase]));

const project = runGh([
  "project", "view", projectNumber, "--owner", owner, "--format", "json",
]);
const itemsPayload = runGh([
  "project", "item-list", projectNumber, "--owner", owner, "--limit", "200", "--format", "json",
]);
const fieldsPayload = runGh([
  "project", "field-list", projectNumber, "--owner", owner, "--format", "json",
]);

const itemsByNumber = new Map(
  itemsPayload.items
    .filter((item) => item.content?.type === "Issue")
    .map((item) => [Number(item.content.number), item]),
);
const missing = [...register.keys()].filter((number) => !itemsByNumber.has(number));
const extra = [...itemsByNumber.keys()].filter((number) => !register.has(number));
if (
  itemsPayload.items.length !== EXPECTED_ISSUES ||
  itemsByNumber.size !== EXPECTED_ISSUES ||
  missing.length ||
  extra.length
) {
  fail(
    `Project membership invariant failed: items=${itemsPayload.items.length}, ` +
    `issues=${itemsByNumber.size}, missing=${JSON.stringify(missing)}, extra=${JSON.stringify(extra)}`,
  );
}

const fields = new Map(fieldsPayload.fields.map((field) => [field.name, field]));
const requiredFields = [
  "Status", "WP ID", "Parent WP", "Phase", "Submission critical", "Priority", "Area",
  "Owner role", "Due date", "Evidence required", "Scientific gate", "Dependency status", "Risk",
];
const missingFields = requiredFields.filter((field) => !fields.has(field));
if (missingFields.length) fail(`Missing project fields: ${JSON.stringify(missingFields)}`);

const updates = [];
for (const [number, row] of register) {
  const item = itemsByNumber.get(number);
  const labels = new Set(item.labels ?? []);
  const parentWp = row["WP ID"].slice(0, 5);
  const dueDate = row["Due date"] || item.milestone?.dueOn?.slice(0, 10);
  const values = {
    Status: selectValue(fields.get("Status"), statusFromLabels(labels)),
    "WP ID": { text: row["WP ID"] },
    "Parent WP": row.Parent ? { text: row.Parent } : null,
    Phase: selectValue(fields.get("Phase"), phases.get(parentWp)),
    "Submission critical": selectValue(
      fields.get("Submission critical"), labels.has("submission-critical") ? "Yes" : "No",
    ),
    Priority: selectValue(fields.get("Priority"), row.Priority),
    Area: selectValue(fields.get("Area"), row.Area),
    "Owner role": selectValue(fields.get("Owner role"), row["Owner role"]),
    "Due date": dueDate ? { date: dueDate } : null,
    "Evidence required": selectValue(
      fields.get("Evidence required"), labels.has("evidence-required") ? "Yes" : "No",
    ),
    "Scientific gate": selectValue(
      fields.get("Scientific gate"), scientificGateByWp[parentWp] ?? "Not applicable",
    ),
    "Dependency status": selectValue(
      fields.get("Dependency status"), dependencyFromLabels(labels),
    ),
    Risk: selectValue(fields.get("Risk"), row.Priority),
  };
  for (const [fieldName, value] of Object.entries(values)) {
    if (value && (!dueDatesOnly || fieldName === "Due date")) {
      updates.push({ itemId: item.id, fieldId: fields.get(fieldName).id, value });
    }
  }
}

process.stdout.write(
  `Verified project ${project.url}: ${itemsPayload.items.length} exact repository issues; ` +
  `prepared ${updates.length} deterministic field values\n`,
);
if (shouldApply) applyUpdates(project.id, updates, batchSize);
else process.stdout.write("Dry run only; pass --apply to synchronize fields\n");

if (shouldConfigureViews) {
  const visibleFieldNames = [
    "Title", "Status", "Assignees", "WP ID", "Parent WP", "Phase",
    "Submission critical", "Priority", "Area", "Owner role", "Milestone",
    "Start date", "Due date", "Evidence required", "Scientific gate",
    "Dependency status", "Risk",
  ];
  configureViews(
    project.id,
    visibleFieldNames.map((name) => fields.get(name).id),
  );
}

if (shouldVerifyValues) verifyValues(itemsByNumber, register, phases);

const form = document.getElementById("chat-form");
const logsEl = document.getElementById("logs");
const summaryEl = document.getElementById("summary");
const issuesEl = document.getElementById("issues");
const mappingsEl = document.getElementById("mappings");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  logsEl.innerHTML = "";
  summaryEl.innerHTML = "";
  issuesEl.innerHTML = "";
  mappingsEl.innerHTML = "";

  const repoUrl = document.getElementById("repo-url").value.trim();
  const response = await fetch("/api/analyze/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6));
      renderEvent(payload);
    }
  }
});

function renderEvent(event) {
  if (event.type === "log") {
    const log = event.payload;
    const el = document.createElement("div");
    el.className = "log-item";
    el.innerHTML = `<div class="status">${log.agent} · ${log.status}</div><div>${log.message}</div>`;
    logsEl.prepend(el);
    return;
  }

  if (event.type === "result") {
    renderSummary(event.payload.summary);
    renderMappings(event.payload.links);
    renderIssues(event.payload.suggestions, event.payload.prioritization);
  }
}

function renderSummary(summary) {
  const entries = {
    "Total Issues": summary.total_issues,
    Resolved: summary.resolved_issues,
    Unresolved: summary.unresolved_issues,
    "Easy Fixes": summary.easy_fix_issues,
  };
  for (const [label, value] of Object.entries(entries)) {
    const el = document.createElement("div");
    el.className = "summary-item";
    el.innerHTML = `<div class="status">${label}</div><div>${value}</div>`;
    summaryEl.appendChild(el);
  }
}

function renderMappings(links) {
  links.forEach((link) => {
    const el = document.createElement("div");
    el.className = "mapping-item";
    el.innerHTML = `
      <div class="status">Issue #${link.issue_number}</div>
      <div>${link.resolved ? "Resolved" : "Unresolved"}${link.pr_numbers.length ? ` · PRs ${link.pr_numbers.map((number) => `#${number}`).join(", ")}` : ""}</div>
      <div>${link.evidence.join(" ")}</div>
    `;
    mappingsEl.appendChild(el);
  });
}

function renderIssues(suggestions, prioritization) {
  const scoreMap = new Map(prioritization.map((item) => [item.issue_number, item]));
  suggestions.forEach((item) => {
    const score = scoreMap.get(item.issue_number);
    const el = document.createElement("div");
    el.className = "issue-item";
    el.innerHTML = `
      <details>
        <summary>#${item.issue_number} ${item.issue_title}</summary>
        <div class="chip">Priority: ${score?.priority ?? "unknown"}</div>
        <div class="chip">Complexity: ${score?.complexity ?? "unknown"}</div>
        <div class="chip">Confidence: ${item.confidence_score}</div>
        <p><strong>Problem:</strong> ${item.problem}</p>
        <p><strong>Root cause:</strong> ${item.root_cause}</p>
        <p><strong>Suggested fix:</strong> ${item.suggested_fix}</p>
        <p><strong>Files:</strong> ${(item.files_to_modify || []).join(", ") || "Needs deeper scan"}</p>
        <p><a href="/${item.markdown_path}" target="_blank" rel="noreferrer">Open markdown brief</a></p>
      </details>
    `;
    issuesEl.appendChild(el);
  });
}

import React from "react";
import { createRoot } from "react-dom/client";
import { BindingFigure } from "../src/components/BindingFigure";
import "../src/styles.css";

const taskId = new URLSearchParams(location.search).get("task") ?? "75b670c8-faad-4c17-803c-cc17c9f8158f";
const path = `/api/tasks/${taskId}/binding-figures/0`;
const scenario = new URLSearchParams(location.search).get("scenario") ?? "success";
localStorage.removeItem(`drug-design-agent:binding-ready:${path}`);
sessionStorage.removeItem(`drug-design-agent:binding-submitted:${path}`);
const calls: string[] = [];
let gets = 0;
const png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII=";
const originalFetch = window.fetch.bind(window);
window.fetch = async (input, init) => {
  const url = String(input);
  if (!url.includes(path) || scenario === "real") return originalFetch(input, init);
  const method = init?.method ?? "GET";
  calls.push(`${method} ${url}`);
  document.getElementById("calls")!.textContent = calls.join("\n");
  if (method === "POST" && scenario === "locked") return new Response(JSON.stringify({ detail: "Palette locked" }), { status: 409 });
  if (scenario === "network") throw new TypeError("offline");
  if (scenario === "missing") return new Response(JSON.stringify({ detail: "Unknown task" }), { status: 404 });
  const state = scenario === "pose-unavailable" ? "unavailable" : scenario === "pose-failed" || scenario === "render-failed" ? "failed" : method === "POST" ? "rendering" : (++gets < 2 && scenario === "success") ? "rendering" : "ready";
  return new Response(JSON.stringify({ task_id: taskId, candidate_index: 0, state,
    palette_id: scenario === "locked" ? 1 : 7, image_url: state === "ready" ? scenario === "broken-image" ? "/missing-binding-figure.png" : png : null,
    message: scenario === "pose-unavailable" || scenario === "pose-failed" ? "No verified Vina pose for this candidate" : state === "failed" ? "Rendering failed" : null,
    reference_ligand_present: scenario === "without-native" ? false : true }), { status: 200, headers: { "Content-Type": "application/json" } });
};

document.body.style.padding = "24px";
document.body.insertAdjacentHTML("afterbegin", `<h1>Mock binding figure: ${scenario}</h1><pre id="calls"></pre>`);
createRoot(document.getElementById("root")!).render(<BindingFigure taskId={taskId} candidateIndex={0} molBlock={`\n  Mrv2014 09192006112D\n\n  1  0  0  0  0  0            999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\nM  END`} />);

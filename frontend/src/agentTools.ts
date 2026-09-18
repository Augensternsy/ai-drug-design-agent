import type { AgentTool } from "./types";

type DisplayAgentTool = AgentTool & {
  status: "completed" | "running" | "pending" | "failed";
  description: string;
};

const TOOL_DEFINITIONS = [
  { name: "ESM-2", description: "Protein encoding", aliases: ["esm2", "esm2encoding", "esm2proteinencoding", "proteinencoding", "encodeprotein"] },
  { name: "DLPS-E2PO", description: "Molecule generation", aliases: ["dlpse2po", "dlpse2pogeneration", "generatemolecules", "moleculegeneration"] },
  { name: "RDKit", description: "Structure validation", aliases: ["rdkit", "rdkitvalidation", "validatemolecules", "moleculevalidation"] },
  { name: "Property Analyzer", description: "Property evaluation", aliases: ["propertyevaluation", "evaluateproperties", "molecularproperties"] },
  { name: "AutoDock Vina", description: "Molecular docking", aliases: ["autodockvina", "autodockvinadocking", "moleculardocking", "vinadocking", "docking"] },
] as const;

function normalizedName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function normalizedStatus(status?: string): DisplayAgentTool["status"] {
  const value = status?.toLowerCase();
  return value === "completed" || value === "running" || value === "failed" ? value : "pending";
}

export function displayAgentTools(tools?: AgentTool[]): DisplayAgentTool[] {
  return TOOL_DEFINITIONS.map((definition) => {
    const acceptedNames: readonly string[] = [normalizedName(definition.name), ...definition.aliases];
    const match = tools?.find((tool) => acceptedNames.includes(normalizedName(tool.name)));
    return { name: definition.name, description: definition.description, status: normalizedStatus(match?.status) };
  });
}

export function agentToolStatusIcon(status: string): string {
  if (status === "completed") return "✓";
  if (status === "running") return "⏳";
  if (status === "failed") return "✗";
  return "○";
}

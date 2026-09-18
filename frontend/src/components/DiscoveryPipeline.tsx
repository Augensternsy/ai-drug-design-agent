import { agentToolStatusIcon, displayAgentTools } from "../agentTools";
import type { AgentTool } from "../types";

export function DiscoveryPipeline({ tools }: { tools?: AgentTool[] }) {
  const pipeline = displayAgentTools(tools);

  return (
    <section className="discovery-pipeline" aria-labelledby="discovery-pipeline-title">
      <div className="discovery-pipeline__heading">
        <div><span>Agent orchestration</span><h3 id="discovery-pipeline-title">AI Drug Discovery Pipeline</h3></div>
        <small>Tool status</small>
      </div>
      <ol>
        {pipeline.map((tool, index) => (
          <li className={tool.status} key={tool.name}>
            <span className="pipeline-index">0{index + 1}</span>
            <div><strong>{tool.name}</strong><small>{tool.description}</small></div>
            <span className="pipeline-status" aria-label={tool.status}><i aria-hidden="true">{agentToolStatusIcon(tool.status)}</i>{tool.status}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

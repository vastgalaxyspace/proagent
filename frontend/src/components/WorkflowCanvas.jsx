import { useMemo } from "react";
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow } from "@xyflow/react";
import { Braces, Pause } from "lucide-react";
import { getNodeStatus, phases, workflowEdges, workflowNodes } from "../data/workflow.js";
import { StatusPill } from "./StatusPill.jsx";

function AgentNode({ data }) {
  const phase = phases.find((item) => item.id === data.node.phase);
  return (
    <div className={`agent-node node-${data.status}`} style={{ "--phase": phase.color }}>
      <Handle type="target" position={Position.Top} />
      <div className="node-topline"><span>{data.index.toString().padStart(2, "0")}</span>{data.node.interrupt ? <Pause size={12} /> : <Braces size={12} />}</div>
      <strong>{data.node.label}</strong>
      <p>{data.node.id}</p>
      <StatusPill status={data.status} />
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };

export function WorkflowCanvas({ run, selectedNode, onSelect }) {
  const nodes = useMemo(() => workflowNodes.map((node, index) => {
    const column = index % 3;
    const row = Math.floor(index / 3);
    const reverseColumn = row % 2 ? 2 - column : column;
    return {
      id: node.id,
      type: "agent",
      position: { x: reverseColumn * 245, y: row * 155 },
      selected: selectedNode === node.id,
      data: { node, index: index + 1, status: getNodeStatus(node, run) },
    };
  }), [run, selectedNode]);

  const edges = useMemo(() => workflowEdges.map((item, index) => {
    const active = run?.next_nodes?.includes(item.target) || (run?.current_node === item.target);
    const sourceComplete = getNodeStatus(workflowNodes.find((node) => node.id === item.source), run) === "complete";
    return {
      id: `e-${index}`,
      source: item.source,
      target: item.target,
      label: item.conditional ? item.condition : undefined,
      animated: active,
      markerEnd: { type: MarkerType.ArrowClosed, color: active ? "#38bdf8" : "#536174" },
      style: { stroke: active ? "#38bdf8" : sourceComplete ? "#7790a8" : "#344153", strokeWidth: active ? 2.4 : 1.3, strokeDasharray: item.conditional ? "6 4" : undefined },
      labelStyle: { fill: "#a7b4c5", fontSize: 9, fontWeight: 600 },
      labelBgStyle: { fill: "#111b2a", fillOpacity: 0.94 },
    };
  }), [run]);

  return (
    <section className="panel graph-panel">
      <div className="panel-heading graph-heading"><div><p className="eyebrow">LANGGRAPH EXECUTION MAP</p><h2>Node & conditional-edge trace</h2></div><div className="legend"><span><i className="solid" /> normal edge</span><span><i className="dashed" /> conditional edge</span></div></div>
      <div className="flow-wrap">
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodeClick={(_, node) => onSelect(node.id)} fitView fitViewOptions={{ padding: 0.15 }} minZoom={0.35} maxZoom={1.6}>
          <Background color="#26364a" gap={24} size={1} />
          <MiniMap pannable zoomable nodeColor={(node) => phases.find((p) => p.id === node.data.node.phase)?.color || "#64748b"} maskColor="rgba(5, 10, 18, .76)" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </section>
  );
}

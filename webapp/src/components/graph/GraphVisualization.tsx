"use client";

import { InteractiveNvlWrapper } from "@neo4j-nvl/react";
import type { Node, Relationship, NVL } from "@neo4j-nvl/base";
import { useEffect, useState, useRef, useCallback } from "react";

interface RecordNode {
  identity: number;
  labels: string[];
  properties: {
    name?: string;
  };
}

interface RecordRelationship {
  identity: number;
  start: number;
  end: number;
  type: string;
}

interface Record {
  seed: RecordNode;
  r: RecordRelationship[];
  m: RecordNode;
}

// Color palette for different node labels (light theme friendly)
const labelColors: { [key: string]: string } = {
  Entity: "#4f46e5", // indigo
  Episodic: "#059669", // emerald
  default: "#6366f1",
};

export function GraphVisualization() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const nvlRef = useRef<NVL>(null);

  useEffect(() => {
    async function loadGraphData() {
      try {
        const response = await fetch("/graph-data.json");
        if (!response.ok) {
          throw new Error("Failed to load graph data");
        }
        const records: Record[] = await response.json();

        // Transform records into NVL nodes and relationships
        const nodeMap = new Map<string, Node>();
        const relSet = new Set<string>();
        const rels: Relationship[] = [];

        records.forEach((record) => {
          // Add seed node
          if (record.seed && !nodeMap.has(String(record.seed.identity))) {
            const label = record.seed.labels?.[0] || "Entity";
            nodeMap.set(String(record.seed.identity), {
              id: String(record.seed.identity),
              captions: [
                {
                  value:
                    record.seed.properties?.name?.replace(/_/g, " ") ||
                    `Node ${record.seed.identity}`,
                },
              ],
              color: labelColors[label] || labelColors.default,
              size: 25,
            });
          }

          // Add m node (episodic)
          if (record.m && !nodeMap.has(String(record.m.identity))) {
            const label = record.m.labels?.[0] || "Episodic";
            nodeMap.set(String(record.m.identity), {
              id: String(record.m.identity),
              captions: [
                {
                  value:
                    record.m.properties?.name?.substring(0, 30) ||
                    `Node ${record.m.identity}`,
                },
              ],
              color: labelColors[label] || labelColors.default,
              size: 20,
            });
          }

          // Add relationships (darker color for light theme)
          if (record.r) {
            record.r.forEach((rel) => {
              const relId = String(rel.identity);
              if (!relSet.has(relId)) {
                relSet.add(relId);
                rels.push({
                  id: relId,
                  from: String(rel.start),
                  to: String(rel.end),
                  captions: [{ value: rel.type }],
                  color: "#64748b",
                });
              }
            });
          }
        });

        // Limit nodes for performance (take first 100 unique nodes)
        const limitedNodes = Array.from(nodeMap.values()).slice(0, 100);
        const limitedNodeIds = new Set(limitedNodes.map((n) => n.id));

        // Filter relationships to only include those between limited nodes
        const limitedRels = rels.filter(
          (r) => limitedNodeIds.has(r.from) && limitedNodeIds.has(r.to)
        );

        setNodes(limitedNodes);
        setRelationships(limitedRels);

        // Auto-select the first node
        if (limitedNodes.length > 0) {
          setSelectedNode(limitedNodes[0]);
        }

        setLoading(false);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
        setLoading(false);
      }
    }

    loadGraphData();
  }, []);

  const handleNodeClick = useCallback(
    (node: Node) => {
      setSelectedNode(node);
    },
    []
  );

  if (loading) {
    return (
      <div className="flex h-[500px] items-center justify-center rounded-lg border border-gray-200 bg-gray-50">
        <div className="text-gray-500">Loading graph data...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[500px] items-center justify-center rounded-lg border border-red-200 bg-red-50">
        <div className="text-red-600">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="relative h-[500px] w-full overflow-hidden rounded-lg border border-gray-200 bg-white">
        <InteractiveNvlWrapper
          ref={nvlRef}
          nodes={nodes}
          rels={relationships}
          nvlOptions={{
            initialZoom: 1,
            disableTelemetry: true,
            layout: "forceDirected",
            relationshipThreshold: 0.5,
          }}
          mouseEventCallbacks={{
            onNodeClick: handleNodeClick,
            onZoom: true,
            onPan: true,
            onDrag: true,
            onHover: true,
          }}
          style={{ width: "100%", height: "100%" }}
        />

        {/* Legend */}
        <div className="absolute bottom-4 left-4 flex gap-4 rounded-lg border border-gray-200 bg-white/95 p-3 text-sm shadow-sm">
          <div className="flex items-center gap-2">
            <div
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: labelColors.Entity }}
            />
            <span className="text-gray-700">Entity</span>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="h-3 w-3 rounded-full"
              style={{ backgroundColor: labelColors.Episodic }}
            />
            <span className="text-gray-700">Episodic</span>
          </div>
        </div>

        {/* Controls hint */}
        <div className="absolute right-4 top-4 rounded-lg border border-gray-200 bg-white/95 px-3 py-2 text-xs text-gray-500 shadow-sm">
          Scroll to zoom • Drag to pan • Drag nodes to interact
        </div>
      </div>

      {/* Selected node info */}
      {selectedNode && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <h4 className="mb-2 text-sm font-semibold text-gray-800">
            Selected Node
          </h4>
          <p className="text-sm text-gray-600">
            <span className="text-gray-400">ID:</span> {selectedNode.id}
          </p>
          <p className="text-sm text-gray-600">
            <span className="text-gray-400">Label:</span>{" "}
            {selectedNode.captions?.[0]?.value || "N/A"}
          </p>
        </div>
      )}

      {/* Stats */}
      <div className="flex gap-4 text-sm text-gray-500">
        <span>
          Showing {nodes.length} nodes and {relationships.length} relationships
        </span>
      </div>
    </div>
  );
}

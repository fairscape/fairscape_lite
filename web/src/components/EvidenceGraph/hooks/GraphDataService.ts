import { RawGraphData, RawGraphEntity } from "../../../types/graph";

export class GraphDataService {
  private graphDict: { [arkId: string]: RawGraphEntity };
  private outputs: Array<{ "@id": string }>;
  private metadata: {
    "@type": string;
    "@id": string;
    name: string;
    description: string;
  };

  constructor(rawData: RawGraphData) {
    this.graphDict = rawData["@graph"] || {};
    this.outputs = rawData.outputs || [];
    this.metadata = {
      "@type": rawData["@type"],
      "@id": rawData["@id"],
      name: rawData.name,
      description: rawData.description,
    };
  }

  getNode(id: string): RawGraphEntity | null {
    return this.graphDict[id] || null;
  }

  getOutputNodes(): RawGraphEntity[] {
    return this.outputs
      .map((ref) => this.getNode(ref["@id"]))
      .filter((node): node is RawGraphEntity => node !== null);
  }

  getAllNodes(): RawGraphEntity[] {
    return Object.values(this.graphDict);
  }

  getNodesByType(type: string): RawGraphEntity[] {
    return Object.values(this.graphDict).filter((node) => {
      const nodeType = Array.isArray(node["@type"])
        ? node["@type"]
        : [node["@type"]];
      return nodeType.some((t) => t.includes(type));
    });
  }

  resolveReference(
    ref: { "@id": string } | string | undefined,
  ): RawGraphEntity | null {
    if (!ref) return null;
    const id = typeof ref === "string" ? ref : ref["@id"];
    return this.getNode(id);
  }

  resolveReferences(
    refs: { "@id": string } | Array<{ "@id": string }> | undefined,
  ): RawGraphEntity[] {
    if (!refs) return [];
    const refsArray = Array.isArray(refs) ? refs : [refs];
    return refsArray
      .map((ref) => this.resolveReference(ref))
      .filter((node): node is RawGraphEntity => node !== null);
  }

  getRelatedNodes(
    nodeId: string,
    relationshipType: keyof RawGraphEntity,
  ): RawGraphEntity[] {
    const node = this.getNode(nodeId);
    if (!node) return [];

    const refs = node[relationshipType];
    if (!refs) return [];

    return this.resolveReferences(refs as any);
  }

  getAllRelationships(nodeId: string): {
    generatedBy: RawGraphEntity[];
    usedDataset: RawGraphEntity[];
    usedSoftware: RawGraphEntity[];
    usedSample: RawGraphEntity[];
    usedInstrument: RawGraphEntity[];
    usedMLModel: RawGraphEntity[];
    hasOutputs: RawGraphEntity[];
    createdBy: RawGraphEntity[];
  } {
    return {
      generatedBy: this.getRelatedNodes(nodeId, "generatedBy"),
      usedDataset: this.getRelatedNodes(nodeId, "usedDataset"),
      usedSoftware: this.getRelatedNodes(nodeId, "usedSoftware"),
      usedSample: this.getRelatedNodes(nodeId, "usedSample"),
      usedInstrument: this.getRelatedNodes(nodeId, "usedInstrument"),
      usedMLModel: this.getRelatedNodes(nodeId, "usedMLModel"),
      hasOutputs: this.getRelatedNodes(nodeId, "hasOutputs"),
      createdBy: this.getCreatedByNodes(nodeId),
    };
  }

  /**
   * Get createdBy nodes - handles both @id references and email strings
   */
  getCreatedByNodes(nodeId: string): RawGraphEntity[] {
    const node = this.getNode(nodeId);
    if (!node || !node.createdBy) return [];

    const createdByRefs = Array.isArray(node.createdBy)
      ? node.createdBy
      : [node.createdBy];

    const results: RawGraphEntity[] = [];

    for (const ref of createdByRefs) {
      if (typeof ref === "string") {
        // It's an email or plain string - create a synthetic Person node
        const personId = `person:${ref}`;
        // Check if we already have this person in the graph
        const existingNode = this.getNode(personId);
        if (existingNode) {
          results.push(existingNode);
        } else {
          // Create a synthetic Person entity for the email
          results.push({
            "@id": personId,
            "@type": "Person",
            name: ref,
            email: ref,
          });
        }
      } else if (ref && ref["@id"]) {
        // It's an @id reference - resolve it
        const resolved = this.resolveReference(ref);
        if (resolved) {
          results.push(resolved);
        }
      }
    }

    return results;
  }

  findPath(startId: string, targetId: string): string[] | null {
    const visited = new Set<string>();
    const queue: { id: string; path: string[] }[] = [
      { id: startId, path: [startId] },
    ];

    while (queue.length > 0) {
      const { id, path } = queue.shift()!;

      if (id === targetId) {
        return path;
      }

      if (visited.has(id)) continue;
      visited.add(id);

      const node = this.getNode(id);
      if (!node) continue;

      const relationships = [
        "generatedBy",
        "usedDataset",
        "usedSoftware",
        "usedSample",
        "usedInstrument",
        "usedMLModel",
        "hasOutputs",
        "createdBy",
      ];

      for (const rel of relationships) {
        const relatedNodes = this.getRelatedNodes(
          id,
          rel as keyof RawGraphEntity,
        );
        for (const relatedNode of relatedNodes) {
          if (!visited.has(relatedNode["@id"])) {
            queue.push({
              id: relatedNode["@id"],
              path: [...path, relatedNode["@id"]],
            });
          }
        }
      }
    }

    return null;
  }

  findPathFromAnyOutput(targetId: string): string[] | null {
    for (const outputRef of this.outputs) {
      const path = this.findPath(outputRef["@id"], targetId);
      if (path) return path;
    }
    return null;
  }
}

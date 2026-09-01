import {
  RawGraphEntity,
  EvidenceNodeData,
  EvidenceNode,
  EvidenceEdge,
} from "../../../types/graph";
import { GraphDataService } from "../hooks/GraphDataService";

const MAX_LABEL_LENGTH = 50;
const COLLECTION_THRESHOLD = 5;
// BASE_URL is "/ui/" in both dev and the built app, so tooltip links land
// on the router's basename instead of the API root.
const feUrl = window.location.origin + import.meta.env.BASE_URL + "view/";

export function getEntityType(typeUri: string | string[] | undefined): string {
  if (!typeUri) return "Unknown";

  // Handle array of types - check for special types first
  if (Array.isArray(typeUri)) {
    const hasROCrate = typeUri.some(
      (t) =>
        t.includes("ROCrate") ||
        t.includes("RO-Crate") ||
        t.includes("rocrate"),
    );
    if (hasROCrate) return "ROCrate";
    if (typeUri.some((t) => t.includes("DatasetGroup"))) return "DatasetGroup";

    // Otherwise use the last type (most specific)
    const typeString = typeUri[typeUri.length - 1];
    return typeString.split(/[#\/]/).pop() || "Unknown";
  }

  // Handle single type string
  const typeString = typeUri;
  return typeString.split(/[#\/]/).pop() || "Unknown";
}

export function abbreviateName(
  name: string | undefined,
  maxLength = MAX_LABEL_LENGTH,
): string {
  if (!name) return "";
  if (name.length <= maxLength) return name;
  return name.substring(0, maxLength - 3) + "...";
}

export function formatPropertyValue(value: any, propKey?: string): string {
  if (value === null || value === undefined) {
    return "<em>Not specified</em>";
  }

  if (typeof value === "string") {
    if (value.startsWith("ark:")) {
      const fullUrl = `${feUrl}${value}`;
      return `<a href="${fullUrl}" target="_blank" rel="noopener noreferrer">${value}</a>`;
    }

    const urlRegex = /^(https?:\/\/\S+)$/;
    if (urlRegex.test(value)) {
      return `<a href="${value}" target="_blank" rel="noopener noreferrer">${value}</a>`;
    }

    if (propKey === "command") {
      return `<pre>${value}</pre>`;
    }

    return String(value);
  }

  if (Array.isArray(value)) {
    return value.map((item) => formatPropertyValue(item)).join("<br/>");
  }

  if (typeof value === "object" && value !== null) {
    if (value["@id"]) {
      return formatPropertyValue(value["@id"]);
    }
    try {
      return `<pre>${JSON.stringify(value, null, 2)}</pre>`;
    } catch (e) {
      return "[Object]";
    }
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  return String(value);
}

export function getDisplayableProperties(
  entityData: RawGraphEntity | undefined,
): Record<string, any> {
  const excludeKeys = [
    "@id",
    "@type",
    "generatedBy",
    "usedDataset",
    "usedSoftware",
    "usedSample",
    "usedInstrument",
    "usedMLModel",
    "hasOutputs",
    "createdBy",
    "name",
    "label",
    "description",
  ];

  const properties: Record<string, any> = {};
  if (!entityData) return properties;

  for (const key in entityData) {
    if (!excludeKeys.includes(key) && !key.startsWith("_")) {
      properties[key] = entityData[key];
    }
  }
  return properties;
}

export function createEvidenceNode(
  entityData: RawGraphEntity,
  visibleNodes: Set<string>,
  dataService: GraphDataService,
): EvidenceNode {
  const id = entityData["@id"];
  const type = getEntityType(entityData["@type"]);
  const label = entityData.name || entityData.label || entityData["@id"];
  const displayName = abbreviateName(label);
  const description = entityData.description || "";

  const relationships = dataService.getAllRelationships(id);
  const allRelated = [
    ...relationships.generatedBy,
    ...relationships.usedDataset,
    ...relationships.usedSoftware,
    ...relationships.usedSample,
    ...relationships.usedInstrument,
    ...relationships.usedMLModel,
    ...relationships.hasOutputs,
    ...relationships.createdBy,
  ];

  const visibleRelatedCount = allRelated.filter((node) =>
    visibleNodes.has(node["@id"]),
  ).length;

  const isExpandable = allRelated.length > visibleRelatedCount;

  const properties = getDisplayableProperties(entityData);

  // DatasetGroup nodes support progressive expansion of their member datasets
  if (type === "DatasetGroup") {
    const memberIds = entityData["evi:memberIds"];
    if (Array.isArray(memberIds)) {
      // Filter out summary strings like "... and N more (total: M)"
      properties._childNodeIds = memberIds.filter(
        (id: any) => typeof id === "string" && id.startsWith("ark:"),
      );
      properties._visibleChildren = 0;
    }
  }

  const nodeData: EvidenceNodeData = {
    id,
    type,
    label,
    displayName,
    description,
    expandable:
      type === "DatasetGroup"
        ? properties._childNodeIds?.length > 0
        : isExpandable,
    _sourceData: entityData,
    properties,
    _expanded: type === "DatasetGroup" ? false : !isExpandable,
  };

  return {
    id,
    type: "evidenceNode",
    position: { x: 0, y: 0 },
    data: nodeData,
  };
}

export function createEdge(
  sourceId: string,
  targetId: string,
  relationshipType: string,
): EvidenceEdge {
  const labelMap: { [key: string]: string } = {
    generatedBy: "generated by",
    usedDataset: "used",
    usedSoftware: "used software",
    usedSample: "used sample",
    usedInstrument: "used instrument",
    usedMLModel: "used model",
    hasOutputs: "has outputs",
    contains: "contains",
    createdBy: "created by",
  };

  const label = labelMap[relationshipType] || relationshipType;
  const edgeId = `${sourceId}_${relationshipType}_${targetId}`;

  const edge: EvidenceEdge = {
    id: edgeId,
    source: sourceId,
    target: targetId,
    type: "smoothstep",
    label,
  };

  if (relationshipType === "contains") {
    edge.animated = true;
  }

  return edge;
}

export interface GraphElements {
  nodes: EvidenceNode[];
  edges: EvidenceEdge[];
}

export class GraphBuilder {
  private dataService: GraphDataService;
  private visibleNodes: Set<string>;
  private nodes: Map<string, EvidenceNode>;
  private edges: Map<string, EvidenceEdge>;

  constructor(dataService: GraphDataService) {
    this.dataService = dataService;
    this.visibleNodes = new Set();
    this.nodes = new Map();
    this.edges = new Map();
  }

  buildInitialGraph(depth: number = 2): GraphElements {
    const outputNodes = this.dataService.getOutputNodes();
    for (const outputNode of outputNodes) {
      this.addNodeAndRelationships(outputNode["@id"], depth);
    }
    return this.getElements();
  }

  buildPathGraph(path: string[]): GraphElements {
    for (let i = 0; i < path.length; i++) {
      const nodeId = path[i];
      this.addNode(nodeId);

      if (i > 0) {
        const prevNodeId = path[i - 1];
        const relationshipType = this.findRelationshipType(prevNodeId, nodeId);
        if (relationshipType) {
          const edge = createEdge(prevNodeId, nodeId, relationshipType);
          this.edges.set(edge.id, edge);
        }
      }
    }
    return this.getElements();
  }

  expandNode(nodeId: string): GraphElements {
    const nodeToExpand = this.nodes.get(nodeId);
    if (!nodeToExpand) return this.getElements();

    if (
      nodeToExpand.data.type === "DatasetCollection" ||
      nodeToExpand.data.type === "DatasetGroup"
    ) {
      this._expandCollectionByOne(nodeToExpand);
    } else {
      const relationships = this.dataService.getAllRelationships(nodeId);

      this._processRelationship(
        nodeId,
        relationships.generatedBy,
        "generatedBy",
      );
      this._processRelationship(
        nodeId,
        relationships.usedSoftware,
        "usedSoftware",
      );
      this._processRelationship(nodeId, relationships.usedSample, "usedSample");
      this._processRelationship(
        nodeId,
        relationships.usedInstrument,
        "usedInstrument",
      );
      this._processRelationship(
        nodeId,
        relationships.usedMLModel,
        "usedMLModel",
      );
      this._processRelationship(nodeId, relationships.hasOutputs, "hasOutputs");

      if (relationships.usedDataset.length > COLLECTION_THRESHOLD) {
        this._addDatasetCollection(nodeId, relationships.usedDataset);
      } else {
        this._processRelationship(
          nodeId,
          relationships.usedDataset,
          "usedDataset",
        );
      }

      // Handle createdBy - these may be synthetic Person nodes
      this._processCreatedByRelationship(nodeId, relationships.createdBy);

      nodeToExpand.data._expanded = true;
      nodeToExpand.data.expandable = false;
    }
    return this.getElements();
  }

  private _expandCollectionByOne(collectionNode: EvidenceNode): void {
    const { _childNodeIds, _visibleChildren = 0 } =
      collectionNode.data.properties;
    if (!_childNodeIds || _visibleChildren >= _childNodeIds.length) {
      collectionNode.data.expandable = false;
      return;
    }

    const nextChildId = _childNodeIds[_visibleChildren];
    this.addNode(nextChildId);
    const edge = createEdge(collectionNode.id, nextChildId, "contains");
    this.edges.set(edge.id, edge);

    const newVisibleCount = _visibleChildren + 1;
    collectionNode.data.properties._visibleChildren = newVisibleCount;
    const groupLabel =
      collectionNode.data.type === "DatasetGroup"
        ? "Grouped Datasets"
        : "Used Datasets";
    collectionNode.data.displayName = `${_childNodeIds.length} ${groupLabel} (${newVisibleCount} shown)`;

    if (newVisibleCount >= _childNodeIds.length) {
      collectionNode.data.expandable = false;
    }
  }

  private _addDatasetCollection(
    parentNodeId: string,
    datasets: RawGraphEntity[],
  ) {
    const collectionId = `${parentNodeId}-dataset-collection`;
    if (this.nodes.has(collectionId)) return;

    const collectionNode = this._createDatasetCollectionNode(
      parentNodeId,
      datasets,
    );
    this.nodes.set(collectionId, collectionNode);
    this.visibleNodes.add(collectionId);

    const edge = createEdge(parentNodeId, collectionId, "usedDataset");
    this.edges.set(edge.id, edge);
  }

  private _createDatasetCollectionNode(
    parentNodeId: string,
    datasets: RawGraphEntity[],
  ): EvidenceNode {
    const collectionId = `${parentNodeId}-dataset-collection`;
    const count = datasets.length;
    const childIds = datasets.map((d) => d["@id"]);

    const nodeData: EvidenceNodeData = {
      id: collectionId,
      type: "DatasetCollection",
      label: `Used Datasets Collection`,
      displayName: `${count} Used Datasets`,
      expandable: true,
      _sourceData: {},
      properties: {
        count: count,
        _childNodeIds: childIds,
        _parentNodeId: parentNodeId,
        _visibleChildren: 0,
      },
    };
    return {
      id: collectionId,
      type: "evidenceNode",
      position: { x: 0, y: 0 },
      data: nodeData,
    };
  }

  private addNode(nodeId: string): void {
    if (this.visibleNodes.has(nodeId)) return;
    const nodeEntity = this.dataService.getNode(nodeId);
    if (!nodeEntity) return;

    const node = createEvidenceNode(
      nodeEntity,
      this.visibleNodes,
      this.dataService,
    );
    this.nodes.set(nodeId, node);
    this.visibleNodes.add(nodeId);
  }

  private _processRelationship(
    sourceId: string,
    relatedNodes: RawGraphEntity[],
    type: string,
    depth?: number,
  ) {
    for (const relNode of relatedNodes) {
      if (depth) {
        this.addNodeAndRelationships(relNode["@id"], depth - 1);
      } else {
        this.addNode(relNode["@id"]);
      }
      const edge = createEdge(sourceId, relNode["@id"], type);
      this.edges.set(edge.id, edge);
    }
  }

  /**
   * Process createdBy relationships - handles synthetic Person nodes (e.g., emails)
   * that don't exist in the dataService
   */
  private _processCreatedByRelationship(
    sourceId: string,
    createdByNodes: RawGraphEntity[],
  ) {
    for (const personEntity of createdByNodes) {
      const personId = personEntity["@id"];

      // Skip if already added
      if (this.visibleNodes.has(personId)) {
        const edge = createEdge(sourceId, personId, "createdBy");
        this.edges.set(edge.id, edge);
        continue;
      }

      // Create node directly from the entity data (works for synthetic Person nodes)
      const node = this._createNodeFromEntity(personEntity);
      this.nodes.set(personId, node);
      this.visibleNodes.add(personId);

      const edge = createEdge(sourceId, personId, "createdBy");
      this.edges.set(edge.id, edge);
    }
  }

  /**
   * Create an EvidenceNode directly from entity data (for synthetic nodes)
   */
  private _createNodeFromEntity(entityData: RawGraphEntity): EvidenceNode {
    const id = entityData["@id"];
    const type = getEntityType(entityData["@type"]);
    const label = entityData.name || entityData.email || entityData["@id"];
    const displayName = abbreviateName(label);
    const description = entityData.description || "";

    const nodeData: EvidenceNodeData = {
      id,
      type,
      label,
      displayName,
      description,
      expandable: false,
      _sourceData: entityData,
      properties: getDisplayableProperties(entityData),
      _expanded: true,
    };

    return {
      id,
      type: "evidenceNode",
      position: { x: 0, y: 0 },
      data: nodeData,
    };
  }

  private addNodeAndRelationships(nodeId: string, depth: number): void {
    if (depth <= 0 || this.visibleNodes.has(nodeId)) return;
    this.addNode(nodeId);
    if (depth <= 1) return;

    const relationships = this.dataService.getAllRelationships(nodeId);

    this._processRelationship(
      nodeId,
      relationships.generatedBy,
      "generatedBy",
      depth,
    );
    this._processRelationship(
      nodeId,
      relationships.usedSoftware,
      "usedSoftware",
      depth,
    );
    this._processRelationship(
      nodeId,
      relationships.usedSample,
      "usedSample",
      depth,
    );
    this._processRelationship(
      nodeId,
      relationships.usedInstrument,
      "usedInstrument",
      depth,
    );
    this._processRelationship(
      nodeId,
      relationships.usedMLModel,
      "usedMLModel",
      depth,
    );
    this._processRelationship(
      nodeId,
      relationships.hasOutputs,
      "hasOutputs",
      depth,
    );

    if (relationships.usedDataset.length > COLLECTION_THRESHOLD) {
      this._addDatasetCollection(nodeId, relationships.usedDataset);
    } else {
      this._processRelationship(
        nodeId,
        relationships.usedDataset,
        "usedDataset",
        depth,
      );
    }

    // Handle createdBy relationships (synthetic Person nodes)
    this._processCreatedByRelationship(nodeId, relationships.createdBy);
  }

  private findRelationshipType(
    sourceId: string,
    targetId: string,
  ): string | null {
    const rels = this.dataService.getAllRelationships(sourceId);
    if (rels.generatedBy.some((n) => n["@id"] === targetId))
      return "generatedBy";
    if (rels.usedDataset.some((n) => n["@id"] === targetId))
      return "usedDataset";
    if (rels.usedSoftware.some((n) => n["@id"] === targetId))
      return "usedSoftware";
    if (rels.usedSample.some((n) => n["@id"] === targetId)) return "usedSample";
    if (rels.usedInstrument.some((n) => n["@id"] === targetId))
      return "usedInstrument";
    if (rels.usedMLModel.some((n) => n["@id"] === targetId))
      return "usedMLModel";
    if (rels.hasOutputs.some((n) => n["@id"] === targetId)) return "hasOutputs";
    if (rels.createdBy.some((n) => n["@id"] === targetId)) return "createdBy";
    return null;
  }

  getElements(): GraphElements {
    return {
      nodes: Array.from(this.nodes.values()),
      edges: Array.from(this.edges.values()),
    };
  }
}

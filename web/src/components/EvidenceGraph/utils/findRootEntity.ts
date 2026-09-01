// Extracted from fairscape_web_client's MetadataDisplay/utils/metadataProcessing.ts
// so the EvidenceGraph folder has no dependency on the MetadataDisplay tree.
import { RawGraphEntity } from "../../../types/graph";

export const findRootEntity = (
  graph: RawGraphEntity[],
): RawGraphEntity | undefined => {
  const metadataDescriptor = graph.find(
    (e) =>
      e["@id"] === "ro-crate-metadata.json" ||
      e["@id"] === null ||
      e["@id"] === "./ro-crate-metadata.json",
  );

  let rootId = metadataDescriptor?.about?.["@id"];

  if (
    !rootId &&
    metadataDescriptor?.about &&
    Array.isArray(metadataDescriptor.about) &&
    metadataDescriptor.about.length > 0
  ) {
    rootId = metadataDescriptor.about[0]["@id"];
  }

  if (rootId === "./" && metadataDescriptor) {
    const mainEntity = graph.find(
      (e) =>
        Array.isArray(e["@type"]) &&
        e["@type"].includes("https://w3id.org/EVI#ROCrate"),
    );
    if (mainEntity) return mainEntity;
  }

  if (rootId) {
    const foundRoot = graph.find((e) => e["@id"] === rootId);
    if (foundRoot) return foundRoot;
  }

  return (
    graph.find(
      (e) =>
        (Array.isArray(e["@type"]) &&
          e["@type"].includes("https://w3id.org/EVI#ROCrate")) ||
        e["@id"] === "./",
    ) || graph.find((e) => e["@id"] === "./")
  );
};

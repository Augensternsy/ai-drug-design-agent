/** Map the legacy backend method label to the deployed model name for UI only. */
export function displayTaskStage(stage: string): string {
  return stage.replace(/DLPS-E2PO/g, "AP-MolDiff");
}

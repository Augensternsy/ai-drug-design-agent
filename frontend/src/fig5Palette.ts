// Mirrors documentation/fig5_palettes.py: three surface colors × four generated-carbon colors.
// RGB percentages are the PyMOL values used to render the ligand, not the paper panel's display hex.
const GENERATED_RGB = [
  "rgb(0% 72% 90%)",
  "rgb(22% 32% 78%)",
  "rgb(96% 46% 6%)",
  "rgb(62% 27% 78%)",
] as const;

export const NATIVE_RGB = "rgb(10% 78% 15%)";

export function generatedRgbForPalette(paletteId: number | null): string | null {
  if (paletteId === null || !Number.isInteger(paletteId) || paletteId < 1 || paletteId > 12) return null;
  return GENERATED_RGB[(paletteId - 1) % GENERATED_RGB.length];
}

declare module "3dmol" {
  type AtomSelection = Record<string, unknown>;
  type MolecularStyle = Record<string, unknown>;

  type ViewerModel = {
    setStyle(selection: AtomSelection, style: MolecularStyle): void;
  };

  export function createViewer(element: HTMLElement, config?: Record<string, unknown>): {
    addModel(data: string, format: string): ViewerModel;
    addSurface(type: string, style: MolecularStyle, selection?: AtomSelection): Promise<unknown>;
    setStyle(selection: Record<string, unknown>, style: Record<string, unknown>): void;
    zoomTo(selection?: AtomSelection): void;
    zoom(factor?: number, animationDuration?: number, fixedPath?: boolean): void;
    resize(): void;
    render(): void;
    clear(): void;
  };
}

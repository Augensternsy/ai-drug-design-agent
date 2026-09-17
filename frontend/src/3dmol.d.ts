declare module "3dmol" {
  export function createViewer(element: HTMLElement, config?: Record<string, unknown>): {
    addModel(data: string, format: string): void;
    setStyle(selection: Record<string, unknown>, style: Record<string, unknown>): void;
    zoomTo(): void;
    zoom(factor?: number, animationDuration?: number, fixedPath?: boolean): void;
    resize(): void;
    render(): void;
    clear(): void;
  };
}

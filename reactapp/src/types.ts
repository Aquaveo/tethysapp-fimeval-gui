// reactapp/src/types.ts

// Which step of the wizard is currently active.
export type Step = 'upload' | 'running' | 'results';

// Wizard order. Index in this array determines complete/active/pending state.
export const STEP_ORDER: Step[] = ['upload', 'running', 'results'];

// Display labels shown beneath each stepper circle.
export const STEP_LABELS: Record<Step, string> = {
  upload: 'Upload',
  running: 'Running',
  results: 'Results',
};

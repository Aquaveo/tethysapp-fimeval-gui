// reactapp/src/static.ts
declare global {
  interface Window {
    STATIC_IMAGES_BASE?: string;
  }
}

export const STATIC_IMAGES = (
  window.STATIC_IMAGES_BASE || '/static/fimeval_gui/images/'
).replace(/\/$/, '');

// reactapp/src/static.ts
// Base URL for the app's Django static images. index.html injects the resolved
// {% static %} value, so it works whether static is served locally (dev) or from
// S3/CDN (prod, where a hardcoded /static/... path on the app domain 404s). The
// literal fallback only applies if the injection is missing (e.g. a bare mount).
declare global {
  interface Window {
    STATIC_IMAGES_BASE?: string;
  }
}

export const STATIC_IMAGES = (
  window.STATIC_IMAGES_BASE || '/static/fimeval_gui/images/'
).replace(/\/$/, '');

// reactapp/src/Footer.tsx
// FIM-family footer (matches FIMbench): MapLibre/Esri attribution, partner logos,
// and copyright, over the Footer-HQ banner. Rendered by AppShell.
const LOGO_BASE = '/static/fimeval_gui/images';

const PARTNERS = [
  { src: '1_CIROH-Horizontal-Logo_AI-Canva-470x125px.png', alt: 'CIROH', href: 'https://ciroh.ua.edu/' },
  { src: '3_UA-University-of-Alabama_Logo.png', alt: 'University of Alabama', href: 'https://www.ua.edu/' },
  { src: '4_SDML-lab_logo.png', alt: 'Surface Dynamics Modeling Lab', href: 'https://sdml.ua.edu/' },
  { src: '5_BYU-Brigham-Young-University_Logo.png', alt: 'Brigham Young University', href: 'https://www.byu.edu/' },
  { src: '6_Aquaveo-blue-black_Logo.png', alt: 'Aquaveo', href: 'https://aquaveo.com/' },
];

export default function Footer() {
  return (
    <footer className="wk-footer">
      <p className="wk-footer-attr">
        Map powered by{' '}
        <a href="https://maplibre.org" target="_blank" rel="noreferrer">MapLibre</a>
        {' '}· Basemap tiles ©{' '}
        <a href="https://www.esri.com" target="_blank" rel="noreferrer">Esri</a>
      </p>
      <div className="wk-footer-logos">
        {PARTNERS.map((p) => (
          <a key={p.alt} href={p.href} target="_blank" rel="noreferrer">
            <img src={`${LOGO_BASE}/${p.src}`} alt={p.alt} />
          </a>
        ))}
      </div>
      <p className="wk-footer-copy">
        <a href="https://sdml.ua.edu/" target="_blank" rel="noreferrer">© 2026 SDML</a>
        {' '}·{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>
      </p>
    </footer>
  );
}

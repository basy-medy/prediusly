import { useEffect, useRef } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#F5F2E8',
    primaryTextColor: '#0A0A0A',
    primaryBorderColor: '#0A0A0A',
    lineColor: '#0A0A0A',
    secondaryColor: '#F0F040',
    tertiaryColor: '#FFFFFF',
    fontFamily: '"JetBrains Mono", monospace'
  }
});

export default function MermaidChart({ chart, id }: { chart: string, id: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      mermaid.render(id, chart).then((result) => {
        if (containerRef.current) {
          containerRef.current.innerHTML = result.svg;
        }
      }).catch(e => console.error(e));
    }
  }, [chart, id]);

  return <div ref={containerRef} className="mermaid-chart" style={{ display: 'flex', justifyContent: 'center', margin: '2rem 0', padding: '1.5rem', border: '2px solid var(--black)', background: 'var(--white)', boxShadow: '4px 4px 0px var(--black)' }} />;
}

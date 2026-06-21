import { useState } from 'react';
import { translateVariable } from '../translations';
import MermaidChart from './MermaidChart';

const chartPredios = `
graph TD
    A[Inicio] --> B[Cargar SHP SII]
    B --> C[Validar campos]
    C --> D{HABITACIONAL?}
    D -- No --> E[Descartar]
    D -- Sí --> F{URBANA?}
    F -- No --> G[Descartar]
    F -- Sí --> H{Superficie 50-20k m2?}
    H -- No --> I[Descartar]
    H -- Sí --> J[Conservar registro]
    J --> K[Exportar SHP depurado]
`;

const chartEducacion = `
graph TD
    A[Inicio] --> B[Cargar SHP Educación]
    B --> C[Validar institución]
    C --> D[Agrupar por nombre]
    D --> E[Buscar homónimos < 1.5km]
    E --> F{¿Cuántos puntos?}
    F -- Solo 1 --> G[Conservar]
    F -- 2 o más --> H[Calcular centroide]
    H --> I[Punto representativo]
    I --> J[Eliminar originales]
    G --> K[Capa final]
    J --> K
`;

const chartSalud = `
graph TD
    A[Inicio] --> B[Cargar SHP Salud]
    B --> C[Validar campo tipo]
    C --> D{¿Categoría excluida?}
    D -- Sí --> E[Eliminar registro]
    D -- No --> F[Conservar]
    E --> G[Exportar SHP depurado]
    F --> G
`;

export default function ViewB({ pipelineSteps, shapGlobal, modelComparison }: { pipelineSteps: any, shapGlobal: any, modelComparison: any }) {
  const [activeStep, setActiveStep] = useState(0);

  if (!pipelineSteps || !shapGlobal || !modelComparison) return <div style={{padding: '3rem', textAlign: 'center'}}>Cargando narrativa...</div>;

  const etapas = pipelineSteps.etapas || [];
  const models = Object.keys(modelComparison).map(k => ({name: k, ...modelComparison[k]}));

  // SHAP formatting
  const shapEntries = Object.entries(shapGlobal)
    .sort((a: any, b: any) => b[1] - a[1])
    .slice(0, 15); // Top 15
  
  const maxShap = shapEntries.length > 0 ? (shapEntries[0][1] as number) : 1;

  const renderStepContent = (stepIndex: number) => {
    const step = etapas[stepIndex];
    if (!step) return null;

    return (
      <div className="step-content glass-panel">
        <h3 className="section-title" style={{fontSize: '1.8rem'}}>{step.nombre}</h3>
        <p style={{fontSize: '1.1rem', color: 'var(--text-secondary)', marginBottom: '2rem'}}>{step.descripcion}</p>

        {step.nombre === "Limpieza de predios" && step.embudo && (
          <div>
            <h4 style={{marginBottom: '1rem'}}>Embudo de Descarte</h4>
            <p style={{marginBottom: '1rem', color: 'var(--text-secondary)'}}>
              De los 3.79M predios originales del SII (que incluyen usos agrícolas, comerciales e industriales), 
              nos enfocamos exclusivamente en predios habitacionales urbanos.
            </p>
            <div className="funnel-container">
              {Object.entries(step.embudo).map(([key, count]: [string, any], idx: number, arr: any[]) => {
                const isFinal = idx === arr.length - 1;
                const firstCount = arr[0][1];
                const width = Math.max(5, (count / firstCount) * 100);
                
                // Formatear nombre del paso: "01_total_cargados" -> "total cargados"
                const pasoName = key.replace(/^\d+_/, '').replace(/_/g, ' ');

                return (
                  <div key={idx} className="funnel-bar-wrapper">
                    <div className="funnel-label" style={{width: '220px', textAlign: 'right', textTransform: 'capitalize'}}>{pasoName}</div>
                    <div style={{flex: 1}}>
                      <div className="funnel-bar" style={{width: `${width}%`, background: isFinal ? 'var(--positive)' : 'var(--accent-gradient)'}}></div>
                    </div>
                    <div className="funnel-value" style={{width: '120px', color: isFinal ? 'var(--positive)' : 'white'}}>
                      {new Intl.NumberFormat('es-CL').format(count)}
                    </div>
                  </div>
                );
              })}
            </div>
            
            <h4 style={{marginTop: '3rem', marginBottom: '1.5rem'}}>Ejemplos Reales de Exclusión</h4>
            {step.reglas && step.reglas.map((r: any, idx: number) => (
              <div key={idx} className="rule-card">
                <strong>{r.nombre}:</strong> {r.descripcion}
                <div className="rule-example">
                  Ejemplo: {r.ejemplo}
                </div>
              </div>
            ))}
            
            <h4 style={{marginTop: '3rem', marginBottom: '1.5rem', background: 'var(--black)', color: 'var(--white)', display: 'inline-block', padding: '0.5rem 1rem'}}>Diagramas de Flujo de Limpieza</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              <div>
                <h5 style={{marginBottom: '0.5rem', fontSize: '1rem'}}>Lógica de Filtrado de Predios (Catastro SII)</h5>
                <MermaidChart chart={chartPredios} id="mermaid-predios" />
              </div>
              <div>
                <h5 style={{marginBottom: '0.5rem', fontSize: '1rem'}}>Lógica de Agrupación por Homonimia (Educación)</h5>
                <MermaidChart chart={chartEducacion} id="mermaid-educacion" />
              </div>
              <div>
                <h5 style={{marginBottom: '0.5rem', fontSize: '1rem'}}>Lógica de Exclusión por Tipo (Salud)</h5>
                <MermaidChart chart={chartSalud} id="mermaid-salud" />
              </div>
            </div>
          </div>
        )}

        {step.nombre === "Modelo" && (
          <div>
            <p style={{marginBottom: '1.5rem'}}>
              Se entrenaron 5 modelos con validación cruzada espacial (por comuna, para medir generalización real). 
              Previo a la comparación final, <strong>el mejor modelo fue optimizado mediante un grid search con Optuna</strong> 
              (30 iteraciones sobre una muestra de ~100,000 predios) para sintonizar los hiperparámetros y luego reentrenado 
              a escala completa, asegurando el máximo rendimiento predictivo.
            </p>
            <table className="model-table">
              <thead>
                <tr>
                  <th>Modelo</th>
                  <th>R²</th>
                  <th>RMSE (CLP)</th>
                  <th>MAPE (%)</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m: any) => (
                  <tr key={m.name} className={m.ganador ? 'winner' : ''}>
                    <td>
                      {m.name}
                      {m.ganador && <span className="winner-badge" style={{ marginLeft: '8px' }}>Ganador</span>}
                      {m.tuned_optuna && <span className="optuna-badge" style={{ marginLeft: '8px', fontSize: '0.75rem', background: 'var(--accent-primary)', color: '#000', padding: '2px 6px', borderRadius: '4px', fontWeight: 600 }}>Optimizado con Optuna</span>}
                    </td>
                    <td>{m.R2.toFixed(3)}</td>
                    <td>{new Intl.NumberFormat('es-CL', {style: 'currency', currency: 'CLP', maximumFractionDigits: 0}).format(m.RMSE_CLP)}</td>
                    <td>{m.MAPE_pct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {models.find((m: any) => m.nota) && (
              <div className="info-box" style={{marginTop: '1.5rem'}}>
                <strong>Nota sobre GWR:</strong> {models.find((m: any) => m.nota).nota}
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="view-b-layout">
      <h2 className="section-title">Cómo se obtuvo la predicción</h2>
      <p className="section-subtitle">
        El suelo urbano es un bien heterogéneo. El valor decae con la distancia a centros de actividad (renta de localización / bid-rent) 
        y la concentración de equipamiento genera plusvalía (economías de aglomeración). Conoce el pipeline de datos espaciales que comprueba esta teoría.
      </p>

      {/* STEPPER */}
      <div className="stepper-container">
        <div className="stepper-tabs">
          {etapas.map((s: any, idx: number) => (
            <div 
              key={idx} 
              className={`step-tab ${activeStep === idx ? 'active' : ''}`}
              onClick={() => setActiveStep(idx)}
            >
              <div className="step-number">Etapa {idx + 1}</div>
              <div className="step-title">{s.nombre}</div>
            </div>
          ))}
        </div>
        {renderStepContent(activeStep)}
      </div>

      {/* SHAP GLOBAL */}
      <div className="shap-chart-container glass-panel">
        <h3 className="section-title" style={{fontSize: '1.8rem', marginBottom: '0.5rem'}}>Importancia de Variables (SHAP Global)</h3>
        <p style={{color: 'var(--text-secondary)', marginBottom: '2rem'}}>
          SHAP indica cuánto empuja cada variable la predicción hacia arriba o hacia abajo, en promedio, para todos los predios.
        </p>
        
        <div style={{maxWidth: '800px'}}>
          {shapEntries.map(([key, val]: [string, any]) => {
            const width = (val / maxShap) * 100;
            const label = translateVariable(key).label;
            return (
              <div key={key} className="shap-bar-row">
                <div className="shap-label">{label}</div>
                <div className="shap-bar-track">
                  <div className="shap-bar-fill" style={{width: `${width}%`}}></div>
                </div>
                <div className="shap-value">{val.toFixed(3)}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* HALLAZGOS TERRITORIALES */}
      <div className="cards-grid">
        <div className="glass-panel hallazgo-card">
          <h4>La Posición Domina</h4>
          <p style={{fontSize: '0.9rem', color: 'var(--text-secondary)'}}>
            Las coordenadas del predio son los predictores más fuertes. El "dónde" dentro de la ciudad domina por sobre 
            cualquier variable de accesibilidad individual, lo que confirma la premisa de la renta de localización.
          </p>
        </div>
        <div className="glass-panel hallazgo-card">
          <h4>Economías de Aglomeración</h4>
          <p style={{fontSize: '0.9rem', color: 'var(--text-secondary)'}}>
            La concentración de oferta (ej. densidad de jardines infantiles en 1km) tiene enorme peso. No basta con la distancia al más cercano; 
            la densidad de equipamiento genera valor.
          </p>
        </div>
        <div className="glass-panel hallazgo-card">
          <h4>Sesgo de Densidad Vertical</h4>
          <p style={{fontSize: '0.9rem', color: 'var(--text-secondary)'}}>
            El modelo subestima sistemáticamente comunas como Providencia, Santiago y Ñuñoa. Al no tener variables de edificación (pisos, m² construidos), 
            subestima el valor de zonas de alta densidad en altura.
          </p>
        </div>
        <div className="glass-panel hallazgo-card">
          <h4>Efectos No Estacionarios (GWR)</h4>
          <p style={{fontSize: '0.9rem', color: 'var(--text-secondary)'}}>
            El impacto de la distancia al metro no es constante en la ciudad. En zonas consolidadas aumenta el valor, pero en otros sectores puede asociarse 
            a externalidades negativas (congestión).
          </p>
        </div>
      </div>
      
      {/* DATOS CARD */}
      <h3 className="section-title" style={{fontSize: '1.8rem', marginTop: '4rem', marginBottom: '2rem'}}>Fuentes de Datos</h3>
      <div className="cards-grid" style={{marginTop: '0'}}>
        <div className="glass-panel source-card">
          <div className="source-title">Catastro SII (2025)</div>
          <div className="source-meta"><strong>Origen:</strong> SII Chile, datos administrativos</div>
          <div className="source-meta"><strong>Formato:</strong> Parquet, Polígonos (EPSG:4326 a 32719)</div>
          <p style={{fontSize: '0.9rem', marginTop: '1rem'}}>Predios habitacionales urbanos de 50 a 20,000 m². Avalúos correspondientes al primer semestre de 2026.</p>
        </div>

        <div className="glass-panel source-card">
          <div className="source-title">Red Vial Estructurante</div>
          <div className="source-meta"><strong>Origen:</strong> Clasificación funcional RM</div>
          <div className="source-meta"><strong>Formato:</strong> Shapefile, Líneas</div>
          <div className="source-limitation">
            <strong>Limitación:</strong> Solo contiene 479 segmentos arteriales principales, no la malla local. 
            Por eso se usa distancia euclidiana como proxy de accesibilidad y no distancia por red.
          </div>
        </div>

        <div className="glass-panel source-card">
          <div className="source-title">Topografía</div>
          <div className="source-meta"><strong>Origen:</strong> Curvas de nivel S34W071</div>
          <div className="source-meta"><strong>Formato:</strong> Shapefile, Líneas</div>
          <div className="source-limitation">
            <strong>Limitación:</strong> Cubre el 98.5% de la RM. Comunas periféricas o rurales extremas no están completamente cubiertas.
          </div>
        </div>
        
        <div className="glass-panel source-card">
          <div className="source-title">Equipamiento de Educación</div>
          <div className="source-meta"><strong>Origen:</strong> MINEDUC</div>
          <div className="source-meta"><strong>Manejo de Calidad:</strong> Clustering DBSCAN (1.5 km)</div>
          <p style={{fontSize: '0.9rem', marginTop: '1rem'}}>
            Las sedes homónimas muy cercanas se fusionan para no inflar la accesibilidad. 
            Ejemplo real: "Universidad de Chile" tenía 55 puntos fusionados en uno solo.
          </p>
        </div>
      </div>
    </div>
  );
}

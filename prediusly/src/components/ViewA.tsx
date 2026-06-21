import { useState, useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON, CircleMarker } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { translateVariable } from '../translations';

export default function ViewA({ predictions }: { predictions: any }) {
  const [colorMode, setColorMode] = useState<'predicho' | 'residual'>('predicho');
  const [selectedFeature, setSelectedFeature] = useState<any>(null);
  const [selectedComuna, setSelectedComuna] = useState<string>('TODAS');
  const [maxAvaluo, setMaxAvaluo] = useState<number>(500000000); // 500M default max

  // Extract unique comunas
  const comunas = useMemo(() => {
    if (!predictions) return [];
    const c = new Set<string>();
    predictions.features.forEach((f: any) => {
      if (f.properties.nombre_comuna) {
        c.add(f.properties.nombre_comuna);
      }
    });
    return Array.from(c).sort();
  }, [predictions]);

  // Filter features
  const filteredFeatures = useMemo(() => {
    if (!predictions) return null;
    return {
      ...predictions,
      features: predictions.features.filter((f: any) => {
        if (selectedComuna !== 'TODAS' && f.properties.nombre_comuna !== selectedComuna) return false;
        if (f.properties.avaluo_fiscal > maxAvaluo) return false;
        return true;
      })
    };
  }, [predictions, selectedComuna, maxAvaluo]);

  // Color scales
  const getPredichoColor = (val: number) => {
    // scale from yellow to dark red based on 10M to 200M approx
    if (val > 150000000) return '#7f0000';
    if (val > 100000000) return '#b30000';
    if (val > 75000000) return '#d7301f';
    if (val > 50000000) return '#ef6548';
    if (val > 30000000) return '#fc8d59';
    return '#fdbb84';
  };

  const getResidualColor = (pct: number) => {
    // Blue for negative (underestimated), Red for positive (overestimated)
    if (pct < -30) return '#08519c';
    if (pct < -15) return '#3182bd';
    if (pct < -5) return '#6baed6';
    if (pct > 30) return '#a50f15';
    if (pct > 15) return '#de2d26';
    if (pct > 5) return '#fb6a4a';
    return '#cccccc';
  };

  const styleFeature = (feature: any) => {
    const props = feature.properties;
    const color = colorMode === 'predicho' 
      ? getPredichoColor(props.avaluo_predicho)
      : getResidualColor(props.residual_pct);
      
    return {
      fillColor: color,
      weight: 3,
      opacity: 1,
      color: color, // Set stroke color same as fill to make the polygon appear thicker/larger from afar
      fillOpacity: 0.8
    };
  };

  const onEachFeature = (feature: any, layer: any) => {
    layer.on({
      click: () => {
        setSelectedFeature(feature);
      }
    });
  };

  const formatCLP = (val: number) => {
    return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(val);
  };

  return (
    <div className="view-a-layout">
      <div className="sidebar">
        <div className="sidebar-header">
          <h2 style={{fontSize: '1.5rem', marginBottom: '1rem'}}>Panel de Análisis</h2>
          
          <div className="control-group">
            <label className="control-label">Filtro por Comuna</label>
            <select 
              className="select-input"
              value={selectedComuna} 
              onChange={(e) => {
                setSelectedComuna(e.target.value);
                setSelectedFeature(null);
              }}
            >
              <option value="TODAS">Todas las comunas</option>
              {comunas.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <div className="control-group">
            <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem'}}>
              <label className="control-label" style={{marginBottom: 0}}>Avalúo Real Máximo</label>
              <span style={{fontSize: '0.85rem', color: 'var(--accent-primary)', fontWeight: 600}}>
                {formatCLP(maxAvaluo)}
              </span>
            </div>
            <input 
              type="range" 
              className="range-input" 
              min={10000000} 
              max={1000000000} 
              step={10000000}
              value={maxAvaluo}
              onChange={(e) => setMaxAvaluo(Number(e.target.value))}
            />
          </div>
          
          <div className="control-group" style={{marginBottom: 0}}>
            <label className="control-label">Modo de Visualización</label>
            <div className="toggle-group">
              <button 
                className={`toggle-btn ${colorMode === 'predicho' ? 'active' : ''}`}
                onClick={() => setColorMode('predicho')}
              >
                Avalúo Predicho
              </button>
              <button 
                className={`toggle-btn ${colorMode === 'residual' ? 'active' : ''}`}
                onClick={() => setColorMode('residual')}
              >
                Error (Residual %)
              </button>
            </div>
          </div>
        </div>

        <div className="sidebar-content" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 }}>
          {selectedFeature ? (
            <div className="predio-detail" style={{ padding: '1.5rem', overflowY: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                <h3 style={{ color: 'var(--text-secondary)', fontSize: '1rem', margin: 0 }}>
                  Predio Rol: <span style={{color: 'white'}}>{selectedFeature.properties.rol}</span>
                </h3>
                <button 
                  onClick={() => setSelectedFeature(null)}
                  style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '1.2rem', lineHeight: 1 }}
                >
                  &times;
                </button>
              </div>
              <p style={{marginBottom: '1.5rem', fontSize: '0.9rem'}}>
                {selectedFeature.properties.nombre_comuna} • {selectedFeature.properties.superficie_m2} m²
              </p>

              <div className="value-card">
                <div className="value-row">
                  <span className="value-label">Avalúo Real (SII 2025)</span>
                  <span className="value-amount">{formatCLP(selectedFeature.properties.avaluo_fiscal)}</span>
                </div>
                <div className="value-row">
                  <span className="value-label">Avalúo Predicho (Modelo)</span>
                  <span className="value-amount highlight">{formatCLP(selectedFeature.properties.avaluo_predicho)}</span>
                </div>
                
                <div style={{marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.1)'}}>
                  <div className="value-row" style={{marginBottom: 0}}>
                    <span className="value-label">Diferencia (Residual)</span>
                    <div>
                      <span style={{marginRight: '1rem', fontSize: '0.9rem'}}>
                        {formatCLP(selectedFeature.properties.residual)}
                      </span>
                      <span className={`residual-badge ${selectedFeature.properties.residual_pct > 0 ? 'positive' : 'negative'}`}>
                        {selectedFeature.properties.residual_pct > 0 ? '+' : ''}{selectedFeature.properties.residual_pct.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <p style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem', textAlign: 'right'}}>
                    {selectedFeature.properties.residual_pct > 0 
                      ? 'El modelo sobreestimó el valor' 
                      : 'El modelo subestimó el valor'}
                  </p>
                </div>
              </div>

              {selectedFeature.properties.variacion_avaluo_pct_2020_2025 !== null && (
                <div className="info-box" style={{padding: '1rem', margin: '1rem 0'}}>
                  <p style={{fontSize: '0.85rem'}}>
                    <strong>Contexto Temporal:</strong> Este predio varió un <span style={{color: 'white', fontWeight: 'bold'}}>{selectedFeature.properties.variacion_avaluo_pct_2020_2025.toFixed(1)}%</span> respecto al valor promedio de su manzana en 2020.
                  </p>
                </div>
              )}

              <h4 style={{marginTop: '1.5rem', marginBottom: '1rem'}}>Top 3 Factores (SHAP)</h4>
              <p style={{fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem'}}>
                Estas son las variables de ubicación que más influyeron en empujar el valor de este predio específico hacia arriba o hacia abajo.
              </p>
              
              <ul className="feature-list">
                {selectedFeature.properties.shap_top3.map((s: any, idx: number) => {
                  const t = translateVariable(s.feature);
                  return (
                    <li key={idx} className="feature-item">
                      <div className="feature-name">{t.label}</div>
                      <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
                        {s.direccion === 'sube' ? (
                          <span style={{color: 'var(--positive)'}}>↑ Sube</span>
                        ) : (
                          <span style={{color: 'var(--negative)'}}>↓ Baja</span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>

              <h4 style={{marginTop: '2rem', marginBottom: '1rem'}}>Atributos de Accesibilidad</h4>
              <ul className="feature-list">
                {['dist_metro_m', 'dist_micro_m', 'dist_salud_m', 'dist_edu_escolar_m', 'dist_red_vial_m'].map(feat => {
                  const val = selectedFeature.properties[feat];
                  const t = translateVariable(feat);
                  return val !== undefined ? (
                    <li key={feat} className="feature-item">
                      <span className="feature-name">{t.label}</span>
                      <span className="feature-val">{val.toFixed(0)} {t.unit}</span>
                    </li>
                  ) : null;
                })}
                <li className="feature-item">
                  <span className="feature-name">Uso de Suelo</span>
                  <span className="feature-val" style={{textAlign: 'right'}}>{selectedFeature.properties.uso_suelo_ipt}</span>
                </li>
              </ul>
            </div>
          ) : (
            <div style={{height: '100%', display: 'flex', flexDirection: 'column'}}>
              <div style={{textAlign: 'center', color: 'var(--text-secondary)', marginBottom: '1rem', padding: '1.5rem'}}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" style={{opacity: 0.5, marginBottom: '0.5rem', display: 'inline-block'}}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15.042 21.672 13.684 16.6m0 0-2.51 2.225.569-9.47 5.227 7.917-3.286-.672Zm-7.518-.267A8.25 8.25 0 1 1 20.25 10.5M8.288 14.212A5.25 5.25 0 1 1 17.25 10.5" />
                </svg>
                <p>Haz clic en un predio del mapa o selecciona uno de la lista inferior ({filteredFeatures?.features.length} predios en vista).</p>
              </div>
              <div style={{flex: 1, overflowY: 'auto', borderTop: '1px solid var(--border-color)'}}>
                <ul style={{listStyle: 'none', padding: 0, margin: 0}}>
                  {filteredFeatures?.features.map((f: any, idx: number) => (
                    <li 
                      key={idx} 
                      onClick={() => setSelectedFeature(f)}
                      style={{
                        padding: '1rem', 
                        borderBottom: '1px solid rgba(255,255,255,0.05)', 
                        cursor: 'pointer',
                        transition: 'background 0.2s',
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                      <div style={{fontWeight: 600, color: 'white', marginBottom: '0.25rem'}}>
                        Rol: {f.properties.rol}
                      </div>
                      <div style={{fontSize: '0.85rem', color: 'var(--text-secondary)'}}>
                        {f.properties.nombre_comuna} • {formatCLP(f.properties.avaluo_fiscal)}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="map-container">
        {filteredFeatures && filteredFeatures.features.length > 0 ? (
          <MapContainer 
            center={[-33.4489, -70.6693]} 
            zoom={11} 
            style={{ minHeight: '600px', height: 'calc(100vh - 85px)', width: '100%', background: '#111', zIndex: 0 }}
          >
            <TileLayer
              attribution='&copy; <a href="https://carto.com/">CartoDB</a>'
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            />
            
            {/* Draw a CircleMarker for each feature's first coordinate, ensuring it NEVER disappears at low zooms */}
            {filteredFeatures && filteredFeatures.features.map((f: any, idx: number) => {
              // Approximate centroid by taking the first coordinate of the first ring
              const coords = f.geometry.coordinates[0][0];
              const latLng: [number, number] = [coords[1], coords[0]];
              
              const props = f.properties;
              const color = colorMode === 'predicho' 
                ? getPredichoColor(props.avaluo_predicho)
                : getResidualColor(props.residual_pct);
              
              const isSelected = selectedFeature && selectedFeature.properties.rol === props.rol;

              return (
                <CircleMarker
                  key={`marker-${idx}-${colorMode}`}
                  center={latLng}
                  radius={isSelected ? 8 : 4}
                  fillColor={color}
                  fillOpacity={0.9}
                  color={isSelected ? '#fff' : color}
                  weight={isSelected ? 3 : 1}
                  eventHandlers={{
                    click: () => setSelectedFeature(f)
                  }}
                />
              );
            })}

            {/* Keep the GeoJSON for actual polygon hover/shape at high zooms */}
            <GeoJSON 
              key={`${selectedComuna}-${colorMode}`} 
              data={filteredFeatures} 
              style={styleFeature}
              onEachFeature={onEachFeature}
            />
          </MapContainer>
        ) : (
          <div style={{height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white'}}>
            Cargando mapa... o no hay predios en esta comuna.
          </div>
        )}
      </div>
    </div>
  );
}

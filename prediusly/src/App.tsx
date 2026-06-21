import { useState } from 'react';
import { useData } from './useData';
import ViewA from './components/ViewA';
import ViewB from './components/ViewB';
import './index.css';

function App() {
  const { predictions, pipelineSteps, modelComparison, shapGlobal, loading } = useData();
  const [activeTab, setActiveTab] = useState<'A' | 'B'>('A');

  if (loading) {
    return (
      <div style={{display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', background: 'var(--bg-primary)'}}>
        <div style={{textAlign: 'center'}}>
          <div style={{width: '40px', height: '40px', border: '3px solid rgba(255,255,255,0.1)', borderTopColor: 'var(--accent-primary)', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 1rem'}}></div>
          <p style={{color: 'var(--text-secondary)'}}>Cargando datos geoespaciales...</p>
          <style>{`
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          `}</style>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <header>
        <div className="logo-container">
          <div className="logo-text">Prediusly</div>
        </div>
        <div className="nav-tabs">
          <button 
            className={`nav-tab ${activeTab === 'A' ? 'active' : ''}`}
            onClick={() => setActiveTab('A')}
          >
            Resultados (Mapa)
          </button>
          <button 
            className={`nav-tab ${activeTab === 'B' ? 'active' : ''}`}
            onClick={() => setActiveTab('B')}
          >
            Cómo se obtuvo la predicción
          </button>
        </div>
      </header>

      <main className="main-content">
        {activeTab === 'A' ? (
          <ViewA 
            predictions={predictions} 
          />
        ) : (
          <ViewB 
            pipelineSteps={pipelineSteps}
            shapGlobal={shapGlobal}
            modelComparison={modelComparison}
          />
        )}
      </main>
    </div>
  );
}

export default App;
